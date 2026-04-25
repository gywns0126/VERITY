"""
Gemini API 기반 최종 의사결정 모듈 (Sprint 9: Verity Brain 통합)
- DART 재무제표(현금흐름) 데이터 통합
- 15년 차 펀드매니저 말투 프롬프트
- Gold/Silver 데이터 분류
- Verity Brain 종합 판단 결과를 system_instruction + 프롬프트에 주입
"""
import json
import os
import time
from typing import List, Optional
from google import genai
from api.mocks import mockable
from api.config import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    GEMINI_MODEL_DEFAULT,
    GEMINI_MODEL_CRITICAL,
    GEMINI_PRO_ENABLE,
    GEMINI_CRITICAL_TOP_N,
    RISK_KEYWORDS,
    DATA_DIR,
)

_CONSTITUTION_PATH = os.path.join(DATA_DIR, "verity_constitution.json")


# ── Gemini 할당량 초과 (429 / RESOURCE_EXHAUSTED) Telegram 알림 ──
# 같은 cap 초과 상황에서 5개 호출이 모두 알림 보내지 않도록 1시간 dedupe.
_QUOTA_ALERT_DEDUPE_SEC = 3600
_quota_alert_last_ts: float = 0.0
_QUOTA_PATTERNS = ("RESOURCE_EXHAUSTED", "spending cap", "429")


def _is_quota_error(err_text: str) -> bool:
    s = str(err_text or "")
    return any(p in s for p in _QUOTA_PATTERNS)


def _alert_gemini_quota_exceeded(context: str, error_msg: str) -> None:
    """Gemini API 가 할당량 초과를 반환했을 때 한 번만 Telegram 알림.
    사용자가 ai.studio/spend 에서 cap 늘리지 않으면 다음 호출도 같은 에러 → 1h dedupe.
    """
    global _quota_alert_last_ts
    if not _is_quota_error(error_msg):
        return
    now = time.time()
    if now - _quota_alert_last_ts < _QUOTA_ALERT_DEDUPE_SEC:
        return
    _quota_alert_last_ts = now
    try:
        from api.notifications.telegram import send_message
        text = (
            "<b>🚨 Gemini API 할당량 초과</b>\n\n"
            f"위치: <code>{context}</code>\n"
            "이번 분석 사이클의 AI 리포트가 fallback 으로 떨어졌습니다.\n\n"
            "조치:\n"
            "1) https://ai.studio/spend 에서 monthly cap 증액\n"
            "2) 또는 GEMINI_PRO_ENABLE=0 으로 Pro 호출 비활성\n"
            "3) 다음 cron 자동 복구"
        )
        send_message(text)
    except Exception:
        # 알림 실패가 분석 흐름을 깨지 않도록 swallow
        pass
_KNOWLEDGE_BASE_PATH = os.path.join(DATA_DIR, "brain_knowledge_base.json")
_knowledge_cache: Optional[dict] = None


def _load_knowledge_base() -> dict:
    global _knowledge_cache
    if _knowledge_cache is not None:
        return _knowledge_cache
    try:
        with open(_KNOWLEDGE_BASE_PATH, "r", encoding="utf-8") as f:
            _knowledge_cache = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        _knowledge_cache = {}
    return _knowledge_cache


def _eval_kb_triggers(stock: dict) -> list:
    """종목 지표로 KB v2 의 trigger_index 키를 매칭해 리스트 반환."""
    per = stock.get("per", 0) or 0
    pbr = stock.get("pbr", 0) or 0
    roe = stock.get("roe", 0) or 0
    drop = abs(stock.get("drop_from_high_pct", 0) or 0)
    cons = stock.get("consensus") or {}
    eps_g = cons.get("eps_growth_yoy_pct") or cons.get("operating_profit_yoy_est_pct")
    tech = stock.get("technical") or {}
    signals = tech.get("signals") or []
    leverage = stock.get("leverage_ratio") or stock.get("debt_ratio")
    cape = stock.get("_macro_cape")  # 상위 컨텍스트가 주입 (없으면 None)

    has_per = per > 0
    has_pbr = pbr > 0
    has_roe = roe > 0

    triggers = []
    if has_per and has_pbr and per <= 15 and pbr < 1.5:
        triggers.append("per_lte_15_pbr_lt_1_5")
    if eps_g is not None:
        try:
            if float(eps_g) >= 20:
                triggers.append("eps_growth_qoq_gte_20")
        except (TypeError, ValueError):
            pass
    if has_roe and roe > 15:
        triggers.append("roe_gt_15")
    if len(signals) >= 2:
        triggers.append("candle_signals_gte_2")
    if drop > 30:
        triggers.append("drop_from_high_gt_30")
    if has_per and per > 40:
        triggers.append("per_gt_40")
    if has_pbr and pbr > 5 and has_roe and roe < 15:
        triggers.append("pbr_gt_5_roe_lt_15")
    if cape is not None:
        try:
            if float(cape) > 30:
                triggers.append("cape_gt_30")
            elif float(cape) < 15:
                triggers.append("cape_lt_15")
        except (TypeError, ValueError):
            pass
    if leverage is not None:
        try:
            if float(leverage) > 15:
                triggers.append("leverage_gt_15")
        except (TypeError, ValueError):
            pass

    # 데이터 결손으로 아무 트리거도 안 잡히면 fallback — per=0 / pbr=0 한국 종목 등
    if not triggers and not (has_per or has_pbr or has_roe):
        triggers.append("fallback_universal")

    return triggers


# 책 ID → Gemini 프롬프트에 표시할 한국어 제목 (가독성)
_BOOK_TITLE_KR = {
    "graham_intelligent_investor": "Graham 안전마진",
    "buffett_essays": "Buffett 4필터·moat",
    "bogle_common_sense": "Bogle 인덱스 철학",
    "fisher_uncommon_profits": "Fisher Scuttlebutt",
    "lynch_one_up": "Lynch 10-bagger",
    "livermore_operator": "Livermore 피봇포인트·탐색매매",
    "oneil_canslim": "O'Neil CANSLIM",
    "antonacci_dual_momentum": "Antonacci 듀얼 모멘텀",
    "covel_turtle_trader": "Turtle 추세추종",
    "carter_mastering_trade": "Carter 단기매매",
    "taleb_fooled_by_randomness": "Taleb 블랙스완·생존자편향",
    "douglas_trading_in_zone": "Douglas Zone 심리",
    "douglas_disciplined_trader": "Douglas 자기규율",
    "elder_trading_for_living": "Elder 삼중스크린·2%룰",
    "mackay_madness_crowds": "Mackay 군중광기 버블",
    "lowenstein_when_genius_failed": "LTCM 교훈",
    "schwager_new_market_wizards": "Schwager 변형인식",
    "schwager_market_wizards": "Market Wizards 공통원칙",
    "chan_algorithmic_trading": "Chan 평균회귀·모멘텀",
    "shiller_irrational_exuberance": "Shiller CAPE·피드백루프",
    "aronson_evidence_based": "Aronson 과학적 검증",
    "natenberg_options_volatility": "Natenberg 옵션 변동성",
    "malkiel_random_walk": "Malkiel 랜덤워크",
    "nison_candlestick_psychology": "Nison 캔들 패턴",
    "murphy_technical_analysis": "Murphy 기술적분석",
}


def _find_book_in_kb(kb: dict, book_id: str):
    """KB 카테고리 6개 중 book_id 를 가진 엔트리 반환 (없으면 None)."""
    for cat in ("value_investing", "trend_momentum", "risk_psychology",
                "quantitative", "technical_candle", "unified_decision_framework"):
        cat_dict = kb.get(cat) or {}
        if isinstance(cat_dict, dict) and book_id in cat_dict:
            return cat_dict[book_id]
    return None


def _build_knowledge_context(stock: dict) -> str:
    """종목 특성에 따라 KB v2 에서 적합한 책·프레임워크를 동적 인용.

    2026-04-24 전면 개편:
      - 기존: 하드코드 4개 프레임만. per=0 한국 종목은 대부분 불발 → 사실상 빈 문자열.
      - 개편: KB v2 의 trigger_index + 각 책 key_principles 활용. fallback 경로로
        지표 결손 종목에도 universal_principles + 기본 책 주입.
    """
    kb = _load_knowledge_base()
    if not kb:
        return ""

    parts = []

    # 1) 기본 원칙 — 모든 종목에 공통 주입 (짧게, 6줄 이내)
    unified = (kb.get("unified_decision_framework") or {}).get("universal_principles", [])
    if isinstance(unified, dict):
        unified = unified.get("principles") or []
    if unified:
        parts.append(
            "[배리티 브레인 기본 원칙 — 30권 고전 통합]\n"
            + "\n".join(f"- {p}" for p in unified[:6])
        )

    # 2) 트리거 매칭된 책의 key_principles 주입 (최대 3권 × 3원칙)
    triggers = _eval_kb_triggers(stock)
    trigger_index = kb.get("trigger_index") or {}
    picked_ids: list = []
    for t in triggers:
        for book_id in trigger_index.get(t, []):
            if book_id not in picked_ids:
                picked_ids.append(book_id)
    picked_ids = picked_ids[:3]

    for book_id in picked_ids:
        book = _find_book_in_kb(kb, book_id)
        if not book:
            continue
        principles = book.get("key_principles") if isinstance(book, dict) else None
        if not principles:
            continue
        title = _BOOK_TITLE_KR.get(book_id, book_id)
        parts.append(
            f"[{title}]\n"
            + "\n".join(f"- {p}" for p in principles[:3])
        )

    if not parts:
        return ""
    return "\n\n".join(parts) + "\n"


def init_gemini():
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY 환경변수가 설정되지 않았습니다.")
    return genai.Client(api_key=GEMINI_API_KEY)


def _pick_model(critical: bool = False) -> str:
    """Flash 기본, GEMINI_PRO_ENABLE=1이고 critical=True일 때만 Pro."""
    if critical and GEMINI_PRO_ENABLE:
        return GEMINI_MODEL_CRITICAL
    return GEMINI_MODEL_DEFAULT


def _load_system_instruction() -> str:
    """verity_constitution.json에서 system_instruction 로드."""
    try:
        with open(_CONSTITUTION_PATH, "r", encoding="utf-8") as f:
            const = json.load(f)
        si = const.get("gemini_system_instruction", {})
        role = si.get("role", "너는 15년 차 한국 펀드매니저다.")
        tone = si.get("tone", "존댓말 필수. 숫자 근거 중심. 서론 없이 핵심부터.")
        principles = si.get("principles", [])
        analysis_protocol = si.get("analysis_protocol", [])
        forecast_horizons = si.get("forecast_horizons", [])

        sections = [f"{role}\n{tone}"]
        if principles:
            sections.append("원칙:\n" + "\n".join(f"- {p}" for p in principles))
        if analysis_protocol:
            sections.append("주식/기업 분석 시 필수 수행 항목:\n" + "\n".join(f"- {a}" for a in analysis_protocol))
        if forecast_horizons:
            sections.append("최종 투자 전망 — 필수 시간대별 예측:\n" + "\n".join(f"- {h}" for h in forecast_horizons))
        return "\n\n".join(sections)
    except Exception:
        return (
            "너는 15년 차 한국 펀드매니저다.\n"
            "사용자를 '대표님'으로 호칭. 존댓말 필수. 숫자 근거 중심."
        )


def _build_perplexity_block(stock: dict) -> str:
    """종목에 첨부된 Perplexity 실시간 리서치 결과를 프롬프트 블록으로 변환."""
    parts = []

    ei = stock.get("earnings_insight")
    if ei and "error" not in ei:
        parts.append(
            f"[실적 속보 — Perplexity]\n"
            f"결과: {ei.get('beat_miss', '?')} | {ei.get('guidance', '')}\n"
            f"{ei.get('earnings_summary', '')[:300]}"
        )

    er = stock.get("external_risk")
    if er and "error" not in er:
        level = er.get("risk_level", "LOW")
        if level != "LOW":
            parts.append(
                f"[외부 리스크 — Perplexity] 등급: {level}\n"
                f"{er.get('external_risks', '')[:300]}"
            )

    return "\n".join(parts)


def _normalize_ticker(t: str) -> str:
    """'005930.KS', '005930', 'AAPL' → 공통 키로 정규화 (suffix 제거)."""
    if not t:
        return ""
    s = str(t).strip().upper()
    for suffix in (".KS", ".KQ", ".TW", ".T", ".HK", ".L"):
        if s.endswith(suffix):
            s = s[: -len(suffix)]
            break
    return s


def _build_geo_trigger_block(stock: dict, geo_triggers: Optional[List[dict]]) -> str:
    """해당 종목이 active geo trigger의 affected_tickers에 포함된 경우에만 블록 생성.

    점수엔 영향 없고 AI 코멘트(ai_verdict / silver_insight)에만 반영되도록
    프롬프트 맥락만 주입. 점수 변경 금지 원칙.
    """
    if not geo_triggers:
        return ""
    ticker_norm = _normalize_ticker(stock.get("ticker", ""))
    if not ticker_norm:
        return ""

    hits: List[dict] = []
    for trig in geo_triggers:
        affected = trig.get("affected_tickers") or []
        affected_norms = {_normalize_ticker(t) for t in affected}
        if ticker_norm in affected_norms:
            hits.append(trig)

    if not hits:
        return ""

    lines = []
    for h in hits:
        meta = h.get("meta", {}) or {}
        mag = meta.get("magnitude")
        place = meta.get("place", "")
        when = h.get("datetime_kst") or h.get("date", "")
        src = h.get("trigger_source", "geo_trigger")
        impact = h.get("impact", "")
        if src == "usgs_taiwan_quake" and mag is not None:
            lines.append(
                f"- 대만 M{mag:.1f} 지진 ({place[:30]}, {when}) → "
                f"TSMC 가치사슬 단기 충격 가능. {impact}"
            )
        else:
            lines.append(f"- {h.get('name', '지정학 이벤트')} ({when}) → {impact}")

    return (
        "\n[지정학 트리거 — 참고용, 점수 반영 금지]\n"
        + "\n".join(lines)
        + "\n※ 이 항목은 맥락 참고용. 숫자 근거 없이 이것만으로 BUY/AVOID 판단하지 말 것.\n"
        + "  단, silver_insight 또는 risk_flags에 '대만 지진 공급망 리스크' 언급은 권장.\n"
    )


def _build_prompt(
    stock: dict,
    macro: Optional[dict] = None,
    geo_triggers: Optional[List[dict]] = None,
) -> str:
    tech = stock.get("technical", {})
    sent = stock.get("sentiment", {})
    flow = stock.get("flow", {})
    mf = stock.get("multi_factor", {})
    pred = stock.get("prediction", {})
    bt = stock.get("backtest", {})
    dart = stock.get("dart_financials", {})
    cf = dart.get("cashflow", {})

    macro_block = ""
    if macro:
        mood = macro.get("market_mood", {})
        fr = macro.get("fred") or {}
        fr_lines = ""
        if fr.get("dgs10"):
            d = fr["dgs10"]
            fr_lines += f"\n- FRED DGS10: {d.get('value')}% (as_of {d.get('date', '?')}, 5d Δ{d.get('change_5d_pp', '?')}%p)"
        if fr.get("core_cpi"):
            c = fr["core_cpi"]
            fr_lines += f"\n- 근원 CPI(CPILFESL): 지수 {c.get('index')} | YoY {c.get('yoy_pct')}% ({c.get('date')})"
        if fr.get("m2"):
            m = fr["m2"]
            fr_lines += f"\n- M2(M2SL): {m.get('billions_usd')}bn USD | YoY {m.get('yoy_pct')}% ({m.get('date')})"
        if fr.get("vix_close"):
            vx = fr["vix_close"]
            fr_lines += f"\n- VIXCLS: {vx.get('value')} (5d Δ{vx.get('change_5d', '?')}pt, {vx.get('date')})"
        if fr.get("korea_policy_rate"):
            kp = fr["korea_policy_rate"]
            fr_lines += (
                f"\n- 한국은행 기준금리(ECOS): {kp.get('value')}% "
                f"({kp.get('date')})"
            )
        if fr.get("korea_gov_10y"):
            k = fr["korea_gov_10y"]
            src = k.get("source_note") or "OECD/IMF 대체"
            fr_lines += (
                f"\n- 한국 국고10Y: {k.get('value')}% | YoYΔ{k.get('yoy_pp', '?')}%p "
                f"({k.get('date')}) — {src}"
            )
        if fr.get("korea_discount_rate"):
            kd = fr["korea_discount_rate"]
            fr_lines += f"\n- 한국 IMF할인율: {kd.get('value')}% ({kd.get('date')})"
        if fr.get("us_recession_smoothed_prob"):
            rp = fr["us_recession_smoothed_prob"]
            fr_lines += f"\n- 미 리세션확률(RECPRO): {rp.get('pct')}% | MoMΔ{rp.get('mom_change_pp', '?')}%p ({rp.get('date')})"
        if not fr_lines:
            fr_lines = "\n- FRED: 키 미설정 또는 수집 스킵"
        u10 = macro.get("us_10y", {})
        macro_block = f"""
[매크로 환경]
- 시장 국면: {mf.get('regime', 'neutral')} | 분위기: {mood.get('label', '?')} ({mood.get('score', 0)}점)
- 미10년 표시: {u10.get('value', '?')}% (출처: {u10.get('source', '?')})
- USD/KRW: {macro.get('usd_krw', {}).get('value', '?')}원
- VIX: {macro.get('vix', {}).get('value', '?')}
- WTI: ${macro.get('wti_oil', {}).get('value', '?')}
- S&P500: {macro.get('sp500', {}).get('change_pct', 0):+.1f}%
- 동적 가중치: {mf.get('weights_used', {})}
[FRED 거시]{fr_lines}
"""

    cashflow_block = ""
    if cf.get("operating") or cf.get("free_cashflow"):
        op = cf.get("operating", 0)
        inv = cf.get("investing", 0)
        fin = cf.get("financing", 0)
        fcf = cf.get("free_cashflow", 0)
        cashflow_block = f"""
[DART 현금흐름표]
- 영업CF: {op/1e8:+,.0f}억 | 투자CF: {inv/1e8:+,.0f}억 | 재무CF: {fin/1e8:+,.0f}억
- FCF(영업+투자): {fcf/1e8:+,.0f}억 {'⚠️ 현금 소진 위험' if fcf < 0 else '✓ 현금 창출'}
"""
    dart_debt = dart.get("financials", {})
    if dart_debt.get("debt_ratio_pct"):
        cashflow_block += f"- DART 부채비율: {dart_debt['debt_ratio_pct']}% | 자본: {dart_debt.get('equity', 0)/1e8:,.0f}억\n"

    flow_detail = []
    fn = flow.get('foreign_net', 0)
    in_ = flow.get('institution_net', 0)
    flow_detail.append(f"외국인 당일 {fn:+,}주 | 5일합산 {flow.get('foreign_5d_sum', 0):+,}주")
    if flow.get('foreign_consec_buy', 0) >= 2:
        flow_detail.append(f"외국인 {flow['foreign_consec_buy']}일 연속매수")
    elif flow.get('foreign_consec_sell', 0) >= 2:
        flow_detail.append(f"외국인 {flow['foreign_consec_sell']}일 연속매도")
    flow_detail.append(f"기관 당일 {in_:+,}주 | 5일합산 {flow.get('institution_5d_sum', 0):+,}주")
    if flow.get('inst_consec_buy', 0) >= 2:
        flow_detail.append(f"기관 {flow['inst_consec_buy']}일 연속매수")
    elif flow.get('inst_consec_sell', 0) >= 2:
        flow_detail.append(f"기관 {flow['inst_consec_sell']}일 연속매도")
    flow_block = "\n".join(f"- {d}" for d in flow_detail)

    sent_detail_block = ""
    for h in sent.get("detail", [])[:3]:
        sent_detail_block += f"\n  [{h.get('label','?')}] {h.get('title','')}"

    cons = stock.get("consensus", {})
    cons_block = ""
    if cons:
        src = cons.get("score_source", "?")
        cs = cons.get("consensus_score", "?")
        up = cons.get("upside_pct")
        up_s = f"{up:+.1f}%" if up is not None else "N/A"
        opg = cons.get("operating_profit_yoy_est_pct")
        opg_s = f"{opg:+.1f}%" if opg is not None else "N/A"
        fb = cons.get("flow_fallback_note") or ""
        cons_block = f"""
[증권사 컨센서스/기관 심리] 점수 {cs} ({src}) | 목표 대비 현재가 여력 {up_s}
올해 영업이익 추정 전년비 {opg_s} | 의견 {cons.get('investment_opinion', '?')}
{fb}"""
        for cw in cons.get("warnings", [])[:2]:
            cons_block += f"\n⚠️ {cw}"

    # ── 증권사 애널리스트 리포트 AI 요약 (Phase 3 wiring) ──
    analyst_report = stock.get("analyst_report_summary") or {}
    analyst_block = ""
    if analyst_report and analyst_report.get("report_count"):
        rc = analyst_report.get("report_count", 0)
        asent = analyst_report.get("analyst_sentiment_score", "?")
        atp = analyst_report.get("avg_target_price")
        disp = analyst_report.get("target_price_dispersion") or 0
        opin_dist = analyst_report.get("opinion_distribution") or {}
        rev_ratio = analyst_report.get("revision_ratio")
        atp_s = f"{int(atp):,}원" if atp else "N/A"
        disp_s = f"{int(disp):,}원" if disp else "0원"
        buy = opin_dist.get("매수", 0)
        neutral = opin_dist.get("중립", 0)
        sell = opin_dist.get("매도", 0)
        hold = opin_dist.get("보유", 0)
        if rev_ratio is not None:
            rev_label = "상향 우세" if rev_ratio > 0.5 else "하향 또는 혼조"
        else:
            rev_label = "N/A"
        analyst_block = f"""
[증권사 리포트 요약] 최근 7일 리포트 {rc}건 | 평균 센티먼트 {asent}/100
평균 목표가 {atp_s} (분산 {disp_s})
의견 분포: 매수 {buy}건, 중립 {neutral}건, 매도 {sell}건, 보유 {hold}건
실적 추정 방향: {rev_label}"""
        recent = analyst_report.get("recent_reports") or []
        if recent:
            r0 = recent[0]
            summary_snip = (r0.get("summary") or "")[:100]
            if summary_snip:
                analyst_block += f'\n최근 리포트: {r0.get("firm", "?")} — "{summary_snip}"'

    # ── DART 사업보고서 AI 분석 (Phase 3 wiring) ──
    dart_analysis = stock.get("dart_business_analysis") or {}
    dart_block = ""
    if dart_analysis and dart_analysis.get("business_health_score") is not None:
        bhs = dart_analysis.get("business_health_score")
        moat = dart_analysis.get("moat_indicators") or []
        moat_s = ", ".join(moat[:4]) if moat else "미식별"
        capex = dart_analysis.get("capex_direction", "불명")
        one_line = dart_analysis.get("one_line_summary", "")
        dart_block = f"""
[사업 건전성] 점수 {bhs}/100
해자 지표: {moat_s}
설비투자 방향: {capex}"""
        if one_line:
            dart_block += f"\n한줄 요약: {one_line}"

    cm = stock.get("commodity_margin") or {}
    pr = cm.get("primary") or {}
    cm_block = ""
    if pr.get("commodity_ticker"):
        cm_block = f"""
[원자재·마진] 연동 {pr.get('commodity_ticker')} | 60일 r {pr.get('correlation_60d', 'n/a')}
20일: 원자재 {pr.get('commodity_20d_pct', '?')}% / 주가 {pr.get('stock_20d_pct', '?')}% | 국면 {pr.get('spread_regime', '?')}
마진안심(가공) {pr.get('margin_safety_score', '?')} (판가력 {pr.get('pricing_power', '?')} vs 원가변동성 {pr.get('raw_material_volatility_score', '?')})
"""

    x_sent = stock.get("x_sentiment", {})
    x_block = ""
    if x_sent.get("tweets"):
        x_block = f"""
[X(트위터) 감성] (점수: {x_sent.get('score', 50)})
- 수집: {x_sent.get('tweet_count', 0)}건 | 긍정 {x_sent.get('positive', 0)} / 부정 {x_sent.get('negative', 0)}
- 주요 트윗: {', '.join(t[:40] for t in x_sent.get('tweets', [])[:2]) or '없음'}
"""

    social = stock.get("social_sentiment") or {}
    social_block = ""
    if social.get("score") and social.get("sources_used"):
        rd = social.get("reddit", {})
        social_block = f"""
[소셜 감성] {social.get('score', 50)}점 ({social.get('trend', 'neutral')}) | 소스: {', '.join(social.get('sources_used', []))}"""
        if rd.get("volume", 0) > 0:
            top_titles = [p.get("title", "")[:50] for p in rd.get("top_posts", [])[:2]]
            social_block += f"\n- Reddit: {rd.get('score', 50)}점 | {rd.get('volume', 0)}건 | 긍정 {rd.get('positive', 0)} / 부정 {rd.get('negative', 0)}"
            if top_titles:
                social_block += f"\n- 인기글: {'; '.join(top_titles)}"

    gs = stock.get("group_structure") or {}
    gs_block = ""
    if gs.get("major_shareholders") or gs.get("parent"):
        shareholders = gs.get("major_shareholders", [])
        if not shareholders and gs.get("parent"):
            shareholders = [gs["parent"]]
        sh_lines = []
        for sh in shareholders[:5]:
            line = f"{sh.get('name','?')} {sh.get('ownership_pct',0)}%"
            if sh.get("relate"):
                line += f" ({sh['relate']})"
            sh_lines.append(line)
        gs_block = f"\n[지분구조] {gs.get('group_name', '?')} 그룹"
        gs_block += f"\n대주주: {' / '.join(sh_lines)}"
        nav = gs.get("nav_analysis", {})
        if nav.get("sum_of_parts_억"):
            d = nav.get("nav_discount_pct")
            d_label = f"{d}% 할인" if d and d < 0 else (f"+{d}% 할증" if d and d > 0 else "N/A")
            gs_block += f"\nNAV: {nav['sum_of_parts_억']}억 | 현재 시총 대비 {d_label}"
        subs = gs.get("subsidiaries", [])[:3]
        if subs:
            sub_names = ", ".join(f"{s.get('name','?')}({s.get('ownership_pct',0)}%)" for s in subs)
            gs_block += f"\n주요 자회사: {sub_names}"
        gs_block += "\n"

    brain = stock.get("verity_brain", {})
    brain_block = ""
    if brain.get("brain_score") is not None:
        vci_info = brain.get("vci", {})
        rf = brain.get("red_flags", {})
        brain_block = f"""
[배리티 브레인 사전 판단]
브레인점수: {brain.get('brain_score', '?')} | 등급: {brain.get('grade_label', '?')} ({brain.get('grade', '?')})
팩트: {brain.get('fact_score', {}).get('score', '?')} | 심리: {brain.get('sentiment_score', {}).get('score', '?')}
VCI(괴리율): {vci_info.get('vci', '?'):+d} → {vci_info.get('label', '')}
근거: {brain.get('reasoning', '')}"""
        if rf.get("auto_avoid"):
            brain_block += f"\n⛔ 레드플래그: {'; '.join(rf['auto_avoid'])}"
        if rf.get("downgrade"):
            brain_block += f"\n⚠️ 하향조정: {'; '.join(rf['downgrade'])}"
        brain_block += "\n"

    scout_block = ""
    cs = stock.get("chain_scout") or {}
    if cs.get("top_customers") or cs.get("supply_chain"):
        parts = []
        for c in (cs.get("top_customers") or [])[:3]:
            parts.append(f"{c.get('name', '?')} ({c.get('revenue_pct', '?')}%)")
        scout_block += f"\n[공급망 스카우트] 주요 고객: {', '.join(parts) or '없음'}"
        if cs.get("risk_summary"):
            scout_block += f" | 리스크: {str(cs['risk_summary'])[:120]}"

    ss = stock.get("special_scout") or {}
    if ss.get("rra") or ss.get("patents"):
        rra_items = [f"{r.get('title', '?')}" for r in (ss.get("rra") or [])[:3]]
        pat_items = [f"{p.get('title', '?')}" for p in (ss.get("patents") or [])[:3]]
        if rra_items:
            scout_block += f"\n[RRA] {'; '.join(rra_items)}"
        if pat_items:
            scout_block += f"\n[특허] {'; '.join(pat_items)}"

    if len(scout_block) > 500:
        scout_block = scout_block[:500] + "…"

    is_us = stock.get("currency") == "USD"

    if is_us:
        price_str = f"${stock['price']:,.2f}"
        mcap_str = f"${stock.get('market_cap', 0)/1e9:.1f}B"
        tv_str = f"${stock.get('trading_value', 0)/1e6:,.0f}M"
    else:
        price_str = f"{stock['price']:,.0f}원"
        mcap_str = f"{stock.get('market_cap', 0)/1e12:.1f}조"
        tv_str = f"{stock.get('trading_value', 0)/1e8:,.0f}억"

    flow_section = ""
    if not is_us:
        flow_section = f"""[수급] {flow.get('flow_score', 50)}점
{flow_block}
외국인지분 {flow.get('foreign_ratio', 0):.1f}%"""
    else:
        # US: Finnhub 컨센서스 + 내부자 + 기관 + SEC 공시 + 옵션 + 메트릭스 + 뉴스
        ac = stock.get("analyst_consensus") or {}
        ins = stock.get("insider_sentiment") or {}
        inst = stock.get("institutional_ownership") or {}
        sec_f = stock.get("sec_filings") or []
        sec_fin = stock.get("sec_financials") or {}
        opts = stock.get("options_flow") or {}
        short = stock.get("short_interest") or {}
        earns = stock.get("earnings_surprises") or []
        fh_metrics = stock.get("finnhub_metrics") or {}
        pre_after = stock.get("pre_after_market") or {}
        peers = stock.get("peer_companies") or []
        co_news = stock.get("company_news") or []
        ins_txns = stock.get("insider_transactions") or []

        flow_section = f"""[수급 — Finnhub/SEC]
- 애널리스트: Buy {ac.get('buy',0)} / Hold {ac.get('hold',0)} / Sell {ac.get('sell',0)} | 목표가 ${ac.get('target_mean',0):,.0f} (업사이드 {ac.get('upside_pct',0):+.1f}%)
- 내부자 MSPR: {ins.get('mspr',0):.3f} | 순매수 {ins.get('net_shares',0):+,}주 (매수 {ins.get('positive_count',0)} / 매도 {ins.get('negative_count',0)})
- 기관 보유자: {inst.get('total_holders',0)}곳 | 지분 변동 {inst.get('change_pct',0):+.1f}%"""

        if earns:
            latest = earns[0]
            flow_section += f"\n- 최근 실적: EPS ${latest.get('actual','?')} vs 예상 ${latest.get('estimate','?')} (서프라이즈 {latest.get('surprise_pct',0):+.1f}%)"

        if fh_metrics:
            w52h = fh_metrics.get("52_week_high")
            w52l = fh_metrics.get("52_week_low")
            beta = fh_metrics.get("beta")
            avg_vol = fh_metrics.get("avg_volume")
            spf = fh_metrics.get("short_pct_float")
            parts = []
            if w52h is not None and w52l is not None:
                parts.append(f"52주 ${w52l:,.0f}~${w52h:,.0f}")
            if beta is not None:
                parts.append(f"Beta {beta:.2f}")
            if avg_vol:
                parts.append(f"평균거래 {avg_vol/1e6:.1f}M주")
            if spf is not None:
                parts.append(f"공매도Float {spf:.1f}%")
            if parts:
                flow_section += f"\n[핵심지표] {' | '.join(parts)}"

        if pre_after.get("pre_price") or pre_after.get("after_price"):
            pa_parts = []
            if pre_after.get("pre_price"):
                pa_parts.append(f"프리 ${pre_after['pre_price']:,.2f} ({pre_after.get('pre_change_pct',0):+.1f}%)")
            if pre_after.get("after_price"):
                pa_parts.append(f"애프터 ${pre_after['after_price']:,.2f} ({pre_after.get('after_change_pct',0):+.1f}%)")
            flow_section += f"\n[장전/장후] {' | '.join(pa_parts)}"

        if sec_f:
            recent = sec_f[0]
            flow_section += f"\n[SEC 공시] 최근: {recent.get('form_type','')} ({recent.get('filed_date','')}) — {recent.get('description','')}"

        if ins_txns:
            recent_txn = ins_txns[0]
            flow_section += f"\n[SEC Form4] {recent_txn.get('filer','?')} — {recent_txn.get('form_type','')} ({recent_txn.get('filed_date','')})"

        if sec_fin.get("fcf") is not None:
            flow_section += f"\n[SEC 재무] FCF ${sec_fin['fcf']/1e6:,.0f}M | 순이익 ${(sec_fin.get('net_income') or 0)/1e6:,.0f}M | 부채비율 {sec_fin.get('debt_ratio', 'N/A')}%"

        if opts.get("put_call_ratio") is not None:
            flow_section += f"\n[옵션] P/C {opts['put_call_ratio']:.2f} | 총 OI {opts.get('total_oi',0):,} | IV {opts.get('avg_iv','N/A')}%"

        if short.get("short_pct") is not None:
            flow_section += f"\n[공매도] Short {short['short_pct']:.1f}% | Days to Cover {short.get('days_to_cover','N/A')}"

        if peers:
            flow_section += f"\n[동종업체] {', '.join(peers[:5])}"

        if co_news:
            flow_section += "\n[기업뉴스]"
            for n in co_news[:3]:
                flow_section += f"\n  - {n.get('title','')[:60]} ({n.get('source','')})"

    geo_block = _build_geo_trigger_block(stock, geo_triggers)

    return f"""[종목]
{stock['name']} ({stock['ticker']}) / {stock['market']}
현재가 {price_str} ({tech.get('price_change_pct', 0):+.1f}%) | 시총 {mcap_str}
PER {stock.get('per', 0):.1f} | PBR {stock.get('pbr', 0):.2f} | 배당 {stock.get('div_yield', 0):.1f}%
52주 고점대비 {stock.get('drop_from_high_pct', 0):.1f}% | 거래대금 {tv_str}
부채 {stock.get('debt_ratio', 0):.0f}% | 영업이익률 {stock.get('operating_margin', 0):.1f}% | ROE {stock.get('roe', 0):.1f}%
{cashflow_block}
[기술적]
RSI {tech.get('rsi', '?')} | MACD히스토 {tech.get('macd_hist', '?')} | 볼린저 {tech.get('bb_position', '?')}%
거래량비 {tech.get('vol_ratio', '?')}x | 추세강도 {tech.get('trend_strength', 0)} | 시그널: {', '.join(tech.get('signals', [])) or '없음'}

[뉴스] {sent.get('score', 50)}점 ({sent.get('headline_count', 0)}건){sent_detail_block or ' 없음'}
{cm_block}{x_block}{social_block}
{flow_section}
{cons_block}{analyst_block}{dart_block}
[멀티팩터] {mf.get('multi_score', 0)}점 ({mf.get('grade', '?')})
기여: {mf.get('factor_contribution', {})}
{macro_block}{geo_block}
[AI예측] XGBoost {pred.get('up_probability', '?')}% ({pred.get('method', '?')})
[백테스트] 승률 {bt.get('win_rate', 0)}% | 샤프 {bt.get('sharpe_ratio', 0)} | {bt.get('total_trades', 0)}회
{gs_block}{brain_block}{scout_block}{_build_knowledge_context(stock)}{_build_perplexity_block(stock)}
규칙:
1. company_tagline = 이 회사가 뭐 하는 곳인지 사업 본질 한줄. 15자 이내. 업종명이 아니라 핵심 사업. 예: "국내 1위 검색·AI 플랫폼", "글로벌 메모리 반도체 1위", "K-POP 4대 기획사", "국내 최대 배달 플랫폼"
2. gold_insight = 재무/차트 핵심 한 줄. 구체적 숫자 필수. 군더더기 빼.
3. recommendation: 배리티 브레인 등급을 존중하되, 정성적 판단으로 조정 가능. 조정 시 이유 명시.
4. risk_flags: 실제 데이터에서 확인된 것만. 레드플래그 있으면 반드시 포함.
5. ai_verdict: 사장님한테 보고하듯 짧게. "~입니다" 금지. 반말 OK. VCI 괴리 있으면 언급.
6. 현금흐름이 마이너스면 반드시 risk_flags에 포함.

JSON만:
{{
  "company_tagline": "15자 이내. 사업 본질 한줄",
  "ai_verdict": "40자 이내. 숫자 근거. 서론 없이 핵심만",
  "recommendation": "BUY/WATCH/AVOID",
  "risk_flags": ["확인된 리스크만"],
  "confidence": 0~100,
  "gold_insight": "재무/차트 팩트 1줄",
  "silver_insight": "수급/뉴스/매크로 1줄"
}}"""


@mockable("gemini.stock_analysis")
def analyze_stock(
    client,
    stock: dict,
    macro: Optional[dict] = None,
    *,
    critical: bool = False,
    geo_triggers: Optional[List[dict]] = None,
) -> dict:
    prompt = _build_prompt(stock, macro, geo_triggers=geo_triggers)
    sys_instr = _load_system_instruction()
    model = _pick_model(critical=critical)

    try:
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config={"system_instruction": sys_instr},
        )
        text = response.text.strip()

        try:
            from api.tracing import get_tracer
            usage = getattr(response, "usage_metadata", None)
            pt = getattr(usage, "prompt_token_count", 0) if usage else 0
            ct = getattr(usage, "candidates_token_count", 0) if usage else 0
            get_tracer().log_ai(
                provider="gemini", model=model,
                prompt_tokens=pt, completion_tokens=ct,
                prompt_preview=prompt[:500], response_preview=text[:500],
                ticker=stock.get("ticker", ""), call_type="stock_analysis",
            )
        except Exception:
            pass

        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            text = text.rsplit("```", 1)[0]

        result = json.loads(text)

        detected_risks = []
        for kw in RISK_KEYWORDS:
            if kw in result.get("ai_verdict", "") or kw in str(result.get("risk_flags", [])):
                detected_risks.append(kw)
        result["detected_risk_keywords"] = detected_risks
        result["_gemini_model"] = model

        return result

    except json.JSONDecodeError:
        return {
            "company_tagline": "",
            "ai_verdict": "AI 분석 파싱 실패 - 수동 확인 필요",
            "recommendation": "WATCH",
            "risk_flags": [],
            "confidence": 0,
            "gold_insight": "데이터 확인 필요",
            "silver_insight": "데이터 확인 필요",
            "detected_risk_keywords": [],
        }
    except Exception as e:
        return {
            "company_tagline": "",
            "ai_verdict": f"AI 분석 오류: {str(e)[:50]}",
            "recommendation": "WATCH",
            "risk_flags": [],
            "confidence": 0,
            "gold_insight": "분석 실패",
            "silver_insight": "분석 실패",
            "detected_risk_keywords": [],
        }


def _is_us_stock(s: dict) -> bool:
    cur = s.get("currency", "")
    mkt = s.get("market", "")
    return cur == "USD" or bool(__import__("re").search(r"NYSE|NASDAQ|AMEX|NMS|NGM|NCM|ARCA", mkt or "", __import__("re").IGNORECASE))


@mockable("gemini.daily_report")
def generate_daily_report(macro: dict, candidates: List[dict], sectors: list, headlines: list, verity_brain: Optional[dict] = None, market: str = "kr", event_insights: Optional[list] = None) -> dict:
    """AI 일일 시장 종합 리포트 생성 (Verity Brain 결과 포함). market='us'이면 미장 전용."""
    try:
        client = init_gemini()
    except Exception:
        return _fallback_report(macro, candidates, sectors, market=market)

    is_us = market == "us"

    mood = macro.get("market_mood", {})
    diags = macro.get("macro_diagnosis", [])

    if is_us:
        top_buys = [s for s in candidates if s.get("recommendation") == "BUY" and _is_us_stock(s)][:5]
    else:
        top_buys = [s for s in candidates if s.get("recommendation") == "BUY" and not _is_us_stock(s)][:5]
        if not top_buys:
            top_buys = [s for s in candidates if s.get("recommendation") == "BUY"][:5]
    top_sectors = sectors[:5] if sectors else []
    top_news = headlines[:5] if headlines else []

    brain_block = ""
    if verity_brain:
        mb = verity_brain.get("market_brain", {})
        ov = verity_brain.get("macro_override")
        dist = mb.get("grade_distribution", {})
        top_picks = mb.get("top_picks", [])
        rf_stocks = mb.get("red_flag_stocks", [])
        brain_block = f"""
[배리티 브레인 시장 종합]
시장 평균: 브레인 {mb.get('avg_brain_score', '?')}점 | 팩트 {mb.get('avg_fact_score', '?')} / 심리 {mb.get('avg_sentiment_score', '?')} / VCI {mb.get('avg_vci', 0):+d}
등급 분포: 강매수 {dist.get('STRONG_BUY', 0)} | 매수 {dist.get('BUY', 0)} | 관망 {dist.get('WATCH', 0)} | 주의 {dist.get('CAUTION', 0)} | 회피 {dist.get('AVOID', 0)}"""
        if ov:
            brain_block += f"\n매크로 오버라이드: {ov.get('label', '?')} — {ov.get('message', '')}"
        if top_picks:
            top_str = ", ".join(f"{t['name']}({t['score']})" for t in top_picks[:3])
            brain_block += f"\n브레인 TOP: {top_str}"
        if rf_stocks:
            rf_str = ", ".join(f["name"] for f in rf_stocks[:3])
            brain_block += f"\n레드플래그: {rf_str}"
        bw = mb.get("bubble_warning")
        if bw and bw.get("detected"):
            brain_block += f"\n버블경고(심각도{bw['severity']}): {'; '.join(bw.get('signals', []))}"

    event_block = ""
    if event_insights:
        parts = []
        for ei in event_insights:
            if "error" in ei:
                continue
            parts.append(
                f"- {ei.get('event', '?')} ({ei.get('date', '?')}): "
                f"영향 {ei.get('severity', '?')} | {ei.get('impact_summary', '')[:200]}"
            )
        if parts:
            event_block = "\n[매크로 이벤트 실시간 분석 — Perplexity]\n" + "\n".join(parts)

    fr = macro.get("fred") or {}
    dgs = fr.get("dgs10") or {}
    cpi = fr.get("core_cpi") or {}
    m2b = fr.get("m2") or {}
    vxf = fr.get("vix_close") or {}
    rpf = fr.get("us_recession_smoothed_prob") or {}

    if is_us:
        fred_daily = ""
        if dgs:
            fred_daily = f" | US 10Y {dgs.get('value')}% ({dgs.get('date', '')})"
        if cpi:
            fred_daily += f" | Core CPI YoY {cpi.get('yoy_pct')}%"
        if m2b:
            fred_daily += f" | M2 YoY {m2b.get('yoy_pct')}%"
        if vxf:
            fred_daily += f" | VIX {vxf.get('value')}"
        if rpf:
            fred_daily += f" | Recession Prob {rpf.get('pct')}%"

        prompt = f"""[US Market Today]
Mood: {mood.get('label', '?')} (score {mood.get('score', 0)})
S&P 500: {macro.get('sp500', {{}}).get('value', '?')} ({macro.get('sp500', {{}}).get('change_pct', 0):+.1f}%)
NASDAQ: {macro.get('nasdaq', {{}}).get('value', '?')} ({macro.get('nasdaq', {{}}).get('change_pct', 0):+.1f}%)
VIX: {macro.get('vix', {{}}).get('value', '?')} ({macro.get('vix', {{}}).get('change_pct', 0):+.1f}%)
US 10Y: {macro.get('us_10y', {{}}).get('value', '?')}% | WTI: ${macro.get('wti_oil', {{}}).get('value', '?')}
Gold: ${macro.get('gold', {{}}).get('value', '?')} | Yield Spread: {macro.get('yield_spread', {{}}).get('value', '?')}%p ({macro.get('yield_spread', {{}}).get('signal', '?')})
USD/KRW: {macro.get('usd_krw', {{}}).get('value', '?')}{fred_daily}

[Macro Diagnosis]
{chr(10).join(f'- {d.get("text","")}' for d in diags) if diags else 'Nothing notable'}

[Hot Sectors]
{chr(10).join(f'- {s["name"]}: {s["change_pct"]:+.2f}%' for s in top_sectors) if top_sectors else 'None'}

[News]
{chr(10).join(f'- [{n.get("sentiment","?")}] {n["title"][:60]}' for n in top_news) if top_news else 'None'}

[Top Picks — US]
{chr(10).join(f'- {s["name"]} ({s.get("multi_factor",{{}}).get("multi_score",0)}pts)' for s in top_buys) if top_buys else 'No strong buys today'}
{brain_block}{event_block}

너는 월가 관점에서 미국 시장을 분석하는 펀드매니저다. 한국어로 답변해.
S&P 500, NASDAQ 움직임 중심으로 쓰되, 글로벌 매크로 맥락도 포함해.

JSON만:
{{
  "market_summary": "미장 한줄 (30자 이내, 서론 없이)",
  "market_analysis": "미장 상황 분석 (150자 이내, S&P/NASDAQ/VIX 숫자 근거)",
  "strategy": "미장 전략 (80자 이내, 실행 가능한 것만)",
  "risk_watch": "미장 리스크 (80자 이내, 레드플래그 종목 있으면 명시)",
  "hot_theme": "미장 관심 테마/섹터 + 이유 (80자 이내)",
  "tomorrow_outlook": "미장 내일 전망 (30자 이내)"
}}"""
    else:
        fred_daily = ""
        if dgs:
            fred_daily = f" | FRED DGS10 {dgs.get('value')}% ({dgs.get('date', '')})"
        if cpi:
            fred_daily += f" | 근원CPI YoY {cpi.get('yoy_pct')}%"
        if m2b:
            fred_daily += f" | M2 YoY {m2b.get('yoy_pct')}%"
        if vxf:
            fred_daily += f" | VIXCLS {vxf.get('value')}"
        kr10f = fr.get("korea_gov_10y") or {}
        krdf = fr.get("korea_discount_rate") or {}
        if kr10f:
            fred_daily += f" | 한국10Y {kr10f.get('value')}%"
        if krdf:
            fred_daily += f" | IMF할인율 {krdf.get('value')}%"
        if rpf:
            fred_daily += f" | 리세션확률 {rpf.get('pct')}%"

        prompt = f"""[오늘 시장]
분위기: {mood.get('label', '?')} ({mood.get('score', 0)}점)
VIX: {macro.get('vix', {{}}).get('value', '?')} ({macro.get('vix', {{}}).get('change_pct', 0):+.1f}%)
원달러: {macro.get('usd_krw', {{}}).get('value', '?')}원 | WTI: ${macro.get('wti_oil', {{}}).get('value', '?')}
금: ${macro.get('gold', {{}}).get('value', '?')} | 스프레드: {macro.get('yield_spread', {{}}).get('value', '?')}%p ({macro.get('yield_spread', {{}}).get('signal', '?')})
미10년: {macro.get('us_10y', {{}}).get('value', '?')}% ({macro.get('us_10y', {{}}).get('source', '?')}){fred_daily}

[매크로]
{chr(10).join(f'- {d.get("text","")}' for d in diags) if diags else '별거 없음'}

[핫 섹터]
{chr(10).join(f'- {s["name"]}: {s["change_pct"]:+.02f}%' for s in top_sectors) if top_sectors else '없음'}

[뉴스]
{chr(10).join(f'- [{n.get("sentiment","?")}] {n["title"][:60]}' for n in top_news) if top_news else '없음'}

[찍은 종목]
{chr(10).join(f'- {s["name"]} ({s.get("multi_factor",{{}}).get("multi_score",0)}점)' for s in top_buys) if top_buys else '오늘 살 만한 거 없음'}
{brain_block}{event_block}

JSON만:
{{
  "market_summary": "시장 한줄 (30자 이내, 서론 없이)",
  "market_analysis": "상황 분석 (150자 이내, 반말 OK, 숫자 근거, VCI 괴리 있으면 언급)",
  "strategy": "오늘 전략 (80자 이내, 실행 가능한 것만, 브레인 등급 분포 참고)",
  "risk_watch": "지금 위험한 것 (80자 이내, 레드플래그 종목 있으면 명시)",
  "hot_theme": "관심 테마/섹터 + 이유 (80자 이내)",
  "tomorrow_outlook": "내일 전망 (30자 이내)"
}}"""

    sys_instr = _load_system_instruction()
    model = _pick_model(critical=True)
    try:
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config={"system_instruction": sys_instr},
        )
        text = response.text.strip()

        try:
            from api.tracing import get_tracer
            usage = getattr(response, "usage_metadata", None)
            pt = getattr(usage, "prompt_token_count", 0) if usage else 0
            ct = getattr(usage, "candidates_token_count", 0) if usage else 0
            get_tracer().log_ai(
                provider="gemini", model=model,
                prompt_tokens=pt, completion_tokens=ct,
                prompt_preview=prompt[:500], response_preview=text[:500],
                call_type="daily_report",
            )
        except Exception:
            pass

        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            text = text.rsplit("```", 1)[0]
        result = json.loads(text)
        result["_gemini_model"] = model
        return result
    except Exception as e:
        _alert_gemini_quota_exceeded("daily_report", str(e))
        return _fallback_report(macro, candidates, sectors, market=market)


def _fallback_report(macro: dict, candidates: list, sectors: list, market: str = "kr") -> dict:
    mood = macro.get("market_mood", {})
    is_us = market == "us"
    if is_us:
        top_buys = [s["name"] for s in candidates if s.get("recommendation") == "BUY" and _is_us_stock(s)][:3]
    else:
        top_buys = [s["name"] for s in candidates if s.get("recommendation") == "BUY"][:3]
    top_sec = [s["name"] for s in sectors[:3]] if sectors else []

    if is_us:
        sp = macro.get("sp500", {})
        ndx = macro.get("nasdaq", {})
        return {
            "market_summary": f"S&P {sp.get('change_pct', 0):+.1f}% · NASDAQ {ndx.get('change_pct', 0):+.1f}%",
            "market_analysis": f"VIX {macro.get('vix', {}).get('value', '?')}, US 10Y {macro.get('us_10y', {}).get('value', '?')}% 수준",
            "strategy": f"매수 후보: {', '.join(top_buys)}" if top_buys else "관망 전략 유지",
            "risk_watch": "Gemini API 연결 시 상세 분석 제공",
            "hot_theme": f"강세 섹터: {', '.join(top_sec)}" if top_sec else "특별한 테마 없음",
            "tomorrow_outlook": "미장 변동성 주시",
        }
    return {
        "market_summary": f"시장 분위기 {mood.get('label', '?')} ({mood.get('score', 0)}점)",
        "market_analysis": f"VIX {macro.get('vix', {}).get('value', '?')}, 원달러 {macro.get('usd_krw', {}).get('value', '?')}원 수준에서 거래 중",
        "strategy": f"매수 후보: {', '.join(top_buys)}" if top_buys else "관망 전략 유지",
        "risk_watch": "구체적 리스크 분석은 Gemini API 연결 시 제공됩니다",
        "hot_theme": f"금일 강세 섹터: {', '.join(top_sec)}" if top_sec else "특별한 테마 없음",
        "tomorrow_outlook": "장중 변동성에 주의하며 대응",
    }


@mockable("gemini.batch_analysis")
def analyze_batch(
    candidates: List[dict],
    macro_context: Optional[dict] = None,
    geo_triggers: Optional[List[dict]] = None,
) -> List[dict]:
    """후보 종목 일괄 분석 (Flash 모델)"""
    if not candidates:
        return []

    client = init_gemini()
    batch_model = _pick_model(critical=False)
    print(f"  [Gemini 배치] 모델: {batch_model} | 종목 {len(candidates)}개")
    if geo_triggers:
        print(f"  [Gemini 배치] 지정학 트리거 {len(geo_triggers)}건 주입 (참고용, 점수 미반영)")
    results = []

    for i, stock_info in enumerate(candidates):
        if i > 0:
            time.sleep(6)
        print(f"  [Gemini] ({i+1}/{len(candidates)}): {stock_info['name']}")

        analysis = None
        for attempt in range(3):
            analysis = analyze_stock(client, stock_info, macro_context, geo_triggers=geo_triggers)
            if "429" not in analysis.get("ai_verdict", ""):
                break
            wait = 15 * (attempt + 1)
            print(f"    ⏳ 속도 제한 → {wait}초 대기 후 재시도 ({attempt+2}/3)")
            time.sleep(wait)

        results.append({**stock_info, **analysis})

    results.sort(key=lambda x: x.get("confidence", 0), reverse=True)
    return results


@mockable("gemini.periodic_report")
def generate_periodic_report(analysis_data: dict) -> dict:
    """
    정기 리포트(주간/월간/분기/반기/연간)용 Gemini 자연어 생성.
    periodic_report.py가 만든 구조화 데이터를 받아 통찰을 작성.
    """
    try:
        client = init_gemini()
    except Exception:
        return _fallback_periodic(analysis_data)

    period_label = analysis_data.get("period_label", "정기")
    days = analysis_data.get("days_available", 0)
    date_range = analysis_data.get("date_range", {})

    recs = analysis_data.get("recommendations", {})
    expected = analysis_data.get("expected_return", {})
    sectors = analysis_data.get("sectors", {})
    macro_t = analysis_data.get("macro", {})
    brain_acc = analysis_data.get("brain_accuracy", {})
    meta = analysis_data.get("meta_analysis", {})
    news_kw = analysis_data.get("news_keywords", {})
    portfolio = analysis_data.get("portfolio", {})

    prompt = f"""[{period_label} 종합 분석 리포트 작성]
기간: {date_range.get('start', '?')} ~ {date_range.get('end', '?')} ({days}일간)

[지난 기간 추천 성과 — 실현 수익률]
총 BUY 추천: {recs.get('total_buy_recs', 0)}개
적중률(Hit Rate): {recs.get('hit_rate_pct', 0)}%
평균 수익률: {recs.get('avg_return_pct', 0)}%
고점수(70+) 적중률: {recs.get('high_score_hit_rate_pct', 0)}%
최고 종목: {json.dumps(recs.get('best_picks', [])[:3], ensure_ascii=False)}
최악 종목: {json.dumps(recs.get('worst_picks', [])[:3], ensure_ascii=False)}

[이번 리포트 기대수익률 — 현재 추천 종목의 목표가 기준]
매수 추천 종목 수: {expected.get('count', 0)}
평균 기대수익률: {expected.get('avg_upside_pct', 0)}%
중앙값 기대수익률: {expected.get('median_upside_pct', 0)}%
상단 픽(업사이드 TOP3): {json.dumps(expected.get('top_picks', [])[:3], ensure_ascii=False)}

[섹터 동향]
TOP 3 섹터: {json.dumps(sectors.get('top3_sectors', []), ensure_ascii=False)}
BOTTOM 3 섹터: {json.dumps(sectors.get('bottom3_sectors', []), ensure_ascii=False)}
자금 유입: {sectors.get('rotation_in', [])}
자금 유출: {sectors.get('rotation_out', [])}

[매크로]
분위기 추이: {macro_t.get('mood_trend', '?')} (평균 {macro_t.get('mood_avg', 0)}점)
VIX: {json.dumps(macro_t.get('indicators', {}).get('vix', {}), ensure_ascii=False)}
환율: {json.dumps(macro_t.get('indicators', {}).get('usd_krw', {}), ensure_ascii=False)}
금: {json.dumps(macro_t.get('indicators', {}).get('gold', {}), ensure_ascii=False)}

[브레인 정확도]
등급별 실적: {json.dumps(brain_acc.get('grades', {}), ensure_ascii=False)}
평가: {brain_acc.get('insight', '')}

[데이터 소스 메타 분석]
정확도 순위: {json.dumps(meta.get('findings', []), ensure_ascii=False)}
결론: {meta.get('best_predictor', '')}

[뉴스 키워드]
상위 키워드: {json.dumps(news_kw.get('top_keywords', [])[:10], ensure_ascii=False)}

[포트폴리오]
기간 수익률: {portfolio.get('period_return_pct', 0)}%
최대 낙폭: {portfolio.get('max_drawdown_pct', 0)}%

규칙:
1. 단순 숫자 나열 금지. "왜?"를 분석. 메타 분석 포함.
2. 어떤 데이터 소스가 정확했고 어떤 게 틀렸는지 명시.
3. 브레인의 오판 사례가 있으면 원인 추론.
4. 다음 {period_label} 전략 제안 포함.
5. 섹터 자금 흐름의 방향성과 이유 분석.
6. executive_summary 첫 문장에 "지난 기간 실현 X% / 이번 기대 Y%" 형태로 성과와 기대수익률을 간결히 언급.

JSON만:
{{
  "title": "{period_label} 종합 분석 리포트 제목 (20자 이내)",
  "executive_summary": "3줄 핵심 요약",
  "performance_review": "추천 성과 복기 (승률, 수익률, 오판 원인 분석)",
  "sector_analysis": "섹터 동향 분석 + 자금 흐름 방향",
  "macro_outlook": "매크로 환경 변화와 향후 전망",
  "brain_review": "AI 브레인 정확도 평가 + 개선 포인트",
  "meta_insight": "데이터 소스 메타 분석 — 어떤 지표가 가장 정확했고 왜 그런지",
  "strategy": "다음 {period_label} 투자 전략 제안",
  "risk_watch": "주의해야 할 리스크 요인"
}}"""

    sys_instr = _load_system_instruction()
    model = _pick_model(critical=True)

    try:
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config={"system_instruction": sys_instr},
        )
        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            text = text.rsplit("```", 1)[0]

        result = json.loads(text)
        result["_gemini_model"] = model
        result["_period"] = analysis_data.get("period", "unknown")
        result["_period_label"] = period_label
        result["_date_range"] = date_range
        result["expected_return"] = expected
        result["_raw_stats"] = {
            "hit_rate_pct": recs.get("hit_rate_pct", 0),
            "avg_return_pct": recs.get("avg_return_pct", 0),
            "total_buy_recs": recs.get("total_buy_recs", 0),
            "best_picks": recs.get("best_picks", [])[:5],
            "worst_picks": recs.get("worst_picks", [])[:3],
            "top3_sectors": sectors.get("top3_sectors", []),
            "brain_grades": brain_acc.get("grades", {}),
            "meta_findings": meta.get("findings", []),
            "portfolio_return": portfolio.get("period_return_pct", 0),
            "max_drawdown": portfolio.get("max_drawdown_pct", 0),
            "expected_count": expected.get("count", 0),
            "expected_avg_upside_pct": expected.get("avg_upside_pct", 0),
            "expected_top_picks": expected.get("top_picks", [])[:3],
        }
        return result

    except Exception as e:
        _alert_gemini_quota_exceeded("periodic_report", str(e))
        return _fallback_periodic(analysis_data, str(e))


@mockable("gemini.reanalyze_pro")
def reanalyze_top_n_pro(
    candidates: List[dict],
    macro_context: Optional[dict] = None,
    top_n: Optional[int] = None,
    geo_triggers: Optional[List[dict]] = None,
) -> dict:
    """Brain 상위 N개 종목을 Pro 모델로 재판단. 반환: {ticker: analysis_dict}."""
    if not GEMINI_PRO_ENABLE:
        return {}
    n = top_n or GEMINI_CRITICAL_TOP_N
    sorted_cands = sorted(
        candidates,
        key=lambda s: s.get("verity_brain", {}).get("brain_score", 0),
        reverse=True,
    )
    targets = [s for s in sorted_cands if s.get("verity_brain", {}).get("brain_score", 0) > 0][:n]
    if not targets:
        return {}

    client = init_gemini()
    model = _pick_model(critical=True)
    print(f"  [Gemini Pro] 상위 {len(targets)}개 재판단 (모델: {model})")

    results = {}
    for i, stock in enumerate(targets):
        if i > 0:
            time.sleep(8)
        ticker = stock.get("ticker", "?")
        name = stock.get("name", ticker)
        print(f"    [Pro] ({i+1}/{len(targets)}): {name}")
        try:
            analysis = analyze_stock(client, stock, macro_context, critical=True, geo_triggers=geo_triggers)
            results[ticker] = analysis
        except Exception as e:
            print(f"    ⚠️ Pro 재판단 실패 ({name}): {e}")
            _alert_gemini_quota_exceeded(f"pro_reanalyze:{ticker}", str(e))
    return results


def _fallback_periodic(data: dict, error: str = "") -> dict:
    """Gemini 실패 시 숫자 기반 폴백."""
    recs = data.get("recommendations", {})
    expected = data.get("expected_return", {})
    period_label = data.get("period_label", "정기")
    return {
        "title": f"{period_label} 분석 리포트",
        "executive_summary": (
            f"지난 기간 실현 {recs.get('avg_return_pct', 0)}% (적중 {recs.get('hit_rate_pct', 0)}%) / "
            f"이번 기대 {expected.get('avg_upside_pct', 0)}% ({expected.get('count', 0)}종목)"
        ),
        "performance_review": f"BUY 추천 {recs.get('total_buy_recs', 0)}건 중 적중 {recs.get('hit_rate_pct', 0)}%",
        "sector_analysis": "AI 분석 실패 — 섹터 데이터 참조",
        "macro_outlook": "AI 분석 실패 — 매크로 데이터 참조",
        "brain_review": data.get("brain_accuracy", {}).get("insight", ""),
        "meta_insight": data.get("meta_analysis", {}).get("best_predictor", ""),
        "strategy": "데이터 기반 판단 필요",
        "risk_watch": "AI 리포트 생성 실패" + (f" ({error})" if error else ""),
        "_period": data.get("period", "unknown"),
        "_period_label": period_label,
        "expected_return": expected,
        "_raw_stats": {
            "expected_count": expected.get("count", 0),
            "expected_avg_upside_pct": expected.get("avg_upside_pct", 0),
        },
    }
