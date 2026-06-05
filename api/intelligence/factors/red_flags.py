"""Red flag detection — auto_avoid / downgrade 분류 + 이벤트 신선도 가중.

원본: api/intelligence/verity_brain.py:1689-1993 (분해 전).
"""
from __future__ import annotations

from datetime import date as _date, datetime as _datetime
from typing import Any, Dict, Optional

from api.config import (
    US_INSIDER_MSPR_PENALTY,
    US_IV_PERCENTILE_WARN,
    US_PUT_CALL_BEARISH,
    now_kst,
)


def _parse_event_date(event_date: Any) -> Optional[_date]:
    """event_date 입력(str/datetime/date/None) → date or None."""
    if event_date is None:
        return None
    if isinstance(event_date, _datetime):
        return event_date.date()
    if isinstance(event_date, _date):
        return event_date
    if isinstance(event_date, str):
        try:
            return _datetime.strptime(event_date[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return None
    return None


def _compute_freshness(
    event_date: Any,
    drop_since_event_pct: Optional[float] = None,
    today: Optional[_date] = None,
) -> tuple[str, float, Optional[int]]:
    """이벤트 신선도 계산.

    Returns: (freshness, weight, days_since_event)

    - 발생일 없음            → ("FRESH", 1.0, None)  # 정적 지표(부채/PER 등) 기본값
    - days_since_event ≤ 7   → ("FRESH",   1.0)
    - days_since_event ≤ 30  → ("STALE",   0.5)
    - days_since_event > 30  → ("EXPIRED", 0.0)

    가격 반응 보정:
      이벤트 후 -10% 이상 하락 시 FRESH 도 STALE 로 강제 강등
      ('이미 시장에 반영된 악재' — 두 번 차감 금지).
      EXPIRED 는 이미 0 → 추가 강등 의미 없음.
    """
    parsed = _parse_event_date(event_date)
    if parsed is None:
        return ("FRESH", 1.0, None)

    if today is None:
        today = now_kst().date()
    days = max(0, (today - parsed).days)

    if days <= 7:
        freshness, weight = "FRESH", 1.0
    elif days <= 30:
        freshness, weight = "STALE", 0.5
    else:
        freshness, weight = "EXPIRED", 0.0

    if (
        drop_since_event_pct is not None
        and drop_since_event_pct <= -10
        and freshness == "FRESH"
    ):
        freshness, weight = "STALE", 0.5

    return (freshness, weight, days)


def _make_flag(
    text: str,
    event_date: Any = None,
    drop_since_event_pct: Optional[float] = None,
) -> Dict[str, Any]:
    """레드플래그 dict 빌더. freshness 자동 계산.

    스키마: {text, event_date(iso str|None), freshness, days_since_event, weight}
    """
    freshness, weight, days = _compute_freshness(event_date, drop_since_event_pct)
    parsed = _parse_event_date(event_date)
    return {
        "text": text,
        "event_date": parsed.isoformat() if parsed else None,
        "freshness": freshness,
        "days_since_event": days,
        "weight": weight,
    }


def _sec_risk_event_date(stock: Dict[str, Any], portfolio: Dict[str, Any]) -> Optional[str]:
    """portfolio.sec_risk_scan.filings 에서 해당 ticker 의 가장 최근 filed_date 조회."""
    ticker = (stock.get("ticker") or "").upper()
    if not ticker:
        return None
    scan = portfolio.get("sec_risk_scan") or {}
    filings = scan.get("filings") or []
    dates: list[str] = []
    for f in filings:
        if (f.get("ticker") or "").upper() != ticker:
            continue
        fd = f.get("filed_date")
        if isinstance(fd, str) and fd:
            dates.append(fd[:10])
    return max(dates) if dates else None


def _detect_red_flags(
    stock: Dict[str, Any],
    portfolio: Dict[str, Any],
) -> Dict[str, Any]:
    """레드플래그 자동 감지. auto_avoid / downgrade_one 분류 + 이벤트 신선도 가중.

    반환 dict:
      auto_avoid (list[str])           — 후방 호환용 텍스트 (EXPIRED 제외)
      downgrade  (list[str])           — 후방 호환용 텍스트 (EXPIRED 제외)
      auto_avoid_detail (list[dict])   — 전체 audit 메타 (EXPIRED 포함)
      downgrade_detail  (list[dict])   — 전체 audit 메타 (EXPIRED 포함)
      has_critical (bool)              — FRESH/STALE auto_avoid 1건 이상
      downgrade_count (float)          — weight 합 (예: STALE=0.5 기여)
    """
    auto_avoid_d: list[Dict[str, Any]] = []
    downgrade_d: list[Dict[str, Any]] = []
    is_us = stock.get("currency") == "USD"

    risk_kw = stock.get("detected_risk_keywords") or []
    if risk_kw:
        auto_avoid_d.append(_make_flag(f"위험 키워드 감지: {', '.join(risk_kw)}"))

    sec_risk = stock.get("sec_risk_flags") or []
    if sec_risk:
        unique_kw = list(dict.fromkeys(sec_risk))[:3]
        sec_event_date = _sec_risk_event_date(stock, portfolio)
        downgrade_d.append(_make_flag(
            f"SEC 8-K 리스크 공시: {', '.join(unique_kw)}",
            event_date=sec_event_date,
        ))

    if is_us:
        sec_fin = stock.get("sec_financials") or {}
        us_fcf = sec_fin.get("fcf")
        us_debt_ratio = sec_fin.get("debt_ratio") or stock.get("debt_ratio", 0)
        # 2026-05-12 audit fix (HIGH #7): 섹터별 임계. 미국 금융주(Financial Services) D/E 정상 범위 다름.
        from api.analyzers.sector_thresholds import resolve_sector_bucket, get_debt_ratio_thresholds
        _us_high = get_debt_ratio_thresholds(resolve_sector_bucket(stock))["high"]
        if us_fcf is not None and us_fcf < 0 and us_debt_ratio > _us_high:
            auto_avoid_d.append(_make_flag(f"FCF ${us_fcf/1e6:,.0f}M + 부채 {us_debt_ratio:.0f}% (섹터 임계 {_us_high:.0f}%)"))
        elif us_fcf is not None and us_fcf < 0:
            downgrade_d.append(_make_flag(f"FCF ${us_fcf/1e6:,.0f}M (음수)"))

        insider = stock.get("insider_sentiment") or {}
        mspr = insider.get("mspr", 0)
        if mspr < US_INSIDER_MSPR_PENALTY:
            downgrade_d.append(_make_flag(f"내부자 MSPR {mspr:.2f} (대량 매도)"))

        opts = stock.get("options_flow") or {}
        pc_ratio = opts.get("put_call_ratio")
        avg_iv = opts.get("avg_iv")
        if pc_ratio is not None and pc_ratio > US_PUT_CALL_BEARISH:
            downgrade_d.append(_make_flag(f"약세 옵션 시그널: P/C {pc_ratio:.2f}"))
        if avg_iv is not None and avg_iv > US_IV_PERCENTILE_WARN:
            downgrade_d.append(_make_flag(f"고변동성 경고: IV {avg_iv:.0f}%"))

        short = stock.get("short_interest") or {}
        short_pct = short.get("short_pct")
        if short_pct is not None and short_pct > 20:
            downgrade_d.append(_make_flag(f"공매도 비율 {short_pct:.1f}%"))
    else:
        dart = stock.get("dart_financials", {})
        cf = dart.get("cashflow", {})
        fcf = cf.get("free_cashflow")
        debt = stock.get("debt_ratio", 0)
        if fcf is not None and fcf < 0 and debt > 80:
            auto_avoid_d.append(_make_flag(f"FCF 마이너스({fcf/1e8:,.0f}억) + 부채 {debt:.0f}%"))
        elif fcf is not None and fcf < 0:
            downgrade_d.append(_make_flag(f"FCF 마이너스({fcf/1e8:,.0f}억)"))

        # ── DART distress red-flag 3종 — 2026-06-05 점수 사전등록 (RULE 7, PM 승인) ──
        # 관측 only(2026-06-03/04 부착) → 점수 반영. binary 신호 3종 = fit할 임계 없음
        # (곡선맞추기 surface 0). 출처 = DART 감사보고서/공시 원문. prior = 회계/distress 문헌.
        # going_concern_doubt + distress 공시 = auto_avoid(critical). 불성실공시 = downgrade.
        # 정정·유상증자·올빼미·터널링 score 는 임계 fit 필요 → 관측 유지(N 누적 후 별도 등록).
        _gc = stock.get("dart_audit_signals") or {}
        if _gc.get("going_concern_doubt"):
            auto_avoid_d.append(_make_flag("계속기업 불확실성 (감사인 명시)"))
        _ev = stock.get("dart_disclosure_events") or {}
        _distress = _ev.get("distress_events") or []
        if _distress:
            auto_avoid_d.append(_make_flag(f"distress 공시: {', '.join(_distress[:3])}"))
        if _ev.get("unfaithful_disclosure"):
            downgrade_d.append(_make_flag("불성실공시법인 지정"))

        # KIS 공매도 비율 경고
        ks = stock.get("kis_short_sale", {})
        short_r = ks.get("avg_short_ratio_5d", 0)
        if short_r > 15:
            auto_avoid_d.append(_make_flag(f"공매도 비율 5일 평균 {short_r:.1f}% (과다)"))
        elif short_r > 8:
            downgrade_d.append(_make_flag(f"공매도 비율 주의 {short_r:.1f}%"))

        # KIS 신용잔고 경고
        kc = stock.get("kis_credit_balance", {})
        credit_rate = kc.get("credit_rate", 0)
        if credit_rate > 10:
            downgrade_d.append(_make_flag(f"신용잔고율 {credit_rate:.1f}% (레버리지 과다)"))
        elif credit_rate > 5:
            downgrade_d.append(_make_flag(f"신용잔고율 주의 {credit_rate:.1f}%"))

        # KIS 재무비율 직접 검증
        kfr = stock.get("kis_financial_ratio", {})
        if kfr.get("source") == "kis":
            kis_debt = kfr.get("debt_ratio", 0)
            kis_roe = kfr.get("roe", 0)
            kis_cr = kfr.get("current_ratio", 100)
            # 2026-05-12 audit fix (HIGH #7): sector_aware 임계 — 금융주 D/E 200~1000% 정상.
            # feedback_sector_aware_thresholds 정합 (단일 임계 분기 금지).
            from api.analyzers.sector_thresholds import resolve_sector_bucket, get_debt_ratio_thresholds
            _debt_t = get_debt_ratio_thresholds(resolve_sector_bucket(stock))
            if kis_debt > _debt_t["avoid"]:
                auto_avoid_d.append(_make_flag(f"부채비율 {kis_debt:.0f}% (KIS, 섹터 임계 {_debt_t['avoid']:.0f}%)"))
            elif kis_debt > _debt_t["high"]:
                downgrade_d.append(_make_flag(f"고부채 {kis_debt:.0f}% (KIS, 섹터 임계 {_debt_t['high']:.0f}%)"))
            if kis_roe < -20:
                downgrade_d.append(_make_flag(f"ROE {kis_roe:.1f}% (KIS 기준)"))
            # Hard Floor (배리티 브레인 투자 바이블 ⑥) — 유동비율 < 50% 단기 운영 자금 부족
            if 0 < kis_cr < 50:
                auto_avoid_d.append(_make_flag(f"유동비율 {kis_cr:.0f}% (단기 운영 자금 부족)"))

    # V5: Graham PBR×PER 기준 위반
    _per = stock.get("per") or stock.get("price_to_earnings")
    _pbr = stock.get("pbr") or stock.get("price_to_book")
    if _per is not None and _pbr is not None:
        try:
            pb_pe = float(_pbr) * float(_per)
            if pb_pe > 22.5 and float(_per) > 0 and float(_pbr) > 0:
                downgrade_d.append(_make_flag(f"PBR×PER {pb_pe:.1f} > 22.5 (Graham 기준)"))
        except (TypeError, ValueError):
            pass

    # ── Hard Floor: PEG > 3.0 (운영 자체 보수화 임계) ──
    # Lynch *One Up on Wall Street* 원전 = PEG > 2 (정성 "위험" 영역).
    # 본 시스템은 두 단계 분리:
    #   - PEG > 2 → _compute_graham_score 에서 -15 점수 차감 (downgrade)
    #   - PEG > 3 → 본 Hard Floor 발동 (auto_avoid). 원전 임계의 1.5× 보수화 = 자체 결정.
    # 한미 공통 적용. 자체 결정 명시 (큐 22cdd1ec, 2026-05-03 — feedback_master_rule_drift_audit).
    _cons = stock.get("consensus") or {}
    _eps_g = (
        _cons.get("eps_growth_yoy_pct")
        or _cons.get("eps_growth_qoq_pct")
        or _cons.get("operating_profit_yoy_est_pct")
        or stock.get("revenue_growth")
    )
    if _per is not None and _eps_g is not None:
        try:
            _per_f = float(_per)
            _eps_f = float(_eps_g)
            if _per_f > 0 and _eps_f > 0:
                peg_v = _per_f / _eps_f
                if peg_v > 3.0:
                    auto_avoid_d.append(_make_flag(f"PEG {peg_v:.1f} (Lynch 절대 매도)"))
        except (TypeError, ValueError):
            pass

    macro = portfolio.get("macro", {})
    vix = macro.get("vix", {}).get("value", 0)
    mf_score = stock.get("multi_factor", {}).get("multi_score", 50)
    if vix > 35 and mf_score < 50:
        auto_avoid_d.append(_make_flag(f"VIX {vix} + 멀티팩터 {mf_score}"))

    cons_warnings = stock.get("consensus", {}).get("warnings", [])
    if not is_us and any("기관 낙관 주의" in w for w in cons_warnings):
        downgrade_d.append(_make_flag("컨센서스↑ vs 수출↓ 괴리"))

    # Q5 RULE 7 (2026-05-26) — sector 면제: 금융/헬스케어/커뮤니케이션 = commodity 상관 무의미.
    # [[project_sector_aware_exemption_2026_05_26]] 정합. fact.py:COMMODITY_MARGIN_EXEMPT_SECTORS 와 동일 set.
    from api.intelligence.factors.fact import COMMODITY_MARGIN_EXEMPT_SECTORS
    _cm_exempt = (stock.get("sector") or "") in COMMODITY_MARGIN_EXEMPT_SECTORS
    if not _cm_exempt:
        cm = stock.get("commodity_margin", {})
        pr = cm.get("primary") or cm
        ms = pr.get("margin_safety_score")
        if ms is not None and float(ms) < 30:
            cm_ticker = pr.get("commodity_ticker", "원자재")
            pct = pr.get("commodity_20d_pct", "?")
            downgrade_d.append(_make_flag(f"{cm_ticker} 급변({pct}%) + 마진안심 {ms}"))

    timing = stock.get("timing", {})
    ts = timing.get("timing_score", 50)
    if ts <= 25:
        downgrade_d.append(_make_flag(f"타이밍 스코어 {ts} — 진입 부적합"))

    earnings = stock.get("earnings", {})
    next_e = earnings.get("next_earnings")
    if next_e:
        try:
            # 2026-06-03: naive datetime.now() → now_kst() (GH=UTC 시 D-day 하루 오차).
            #   date 끼리 비교 (aware-naive 혼용 TypeError 회피). feedback_tz_aware.
            d = _datetime.strptime(next_e[:10], "%Y-%m-%d").date()
            days = (d - now_kst().date()).days
            if 0 <= days <= 1:
                # next_earnings 는 미래 이벤트 — freshness 미적용 (event_date 생략)
                downgrade_d.append(_make_flag(f"실적 발표 D-{days}"))
        except (ValueError, TypeError):
            pass

    # ── KIS 시장전반 크로스체크 ──
    ticker = stock.get("ticker", "")
    kis_mkt = portfolio.get("kis_market", {})
    if kis_mkt and not is_us:
        short_top = kis_mkt.get("short_sale_rank", [])
        for item in short_top[:10]:
            if item.get("mksc_shrn_iscd", "") == str(ticker).zfill(6):
                downgrade_d.append(_make_flag("공매도 시장 상위 10 종목 (KIS)"))
                break
        fi_list = kis_mkt.get("foreign_institution", [])
        for item in fi_list[:15]:
            if item.get("mksc_shrn_iscd", "") == str(ticker).zfill(6):
                ntby = int(item.get("ntby_qty", 0) or 0)
                if ntby < 0:
                    downgrade_d.append(_make_flag("외인·기관 순매도 상위 (KIS)"))
                break

    # ── 2026-05-31 이중계상 제거 (PM 승인, docs/REDFLAG_DOUBLECOUNT_FIX_PROPOSAL_20260531.md) ──
    # graded fact_score(graham_value/moat/export_trade/commodity/timing)에 이미 반영된 신호는
    # downgrade 감점에서 제외. 역할 분리 — graded score=상대 랭킹, red_flag=배제(auto_avoid)만.
    # Grinold-Kahn 독립신호 합산 원칙 / Barra USE4 공선성 최소화 정합 (Perplexity 검증 2026-05-31).
    # auto_avoid(고부채>avoid임계, PEG>3, 유동비율<50 등)는 기능이 달라 유지. 거래량 목적 아님 = correctness.
    _DEDUP_PATTERNS = ("고부채", "ROE ", "PBR×PER", "마진안심", "타이밍 스코어", "외인·기관 순매도")
    def _is_dedup(_t: str) -> bool:
        return any(_p in _t for _p in _DEDUP_PATTERNS)
    _penalized_d = [d for d in downgrade_d if not _is_dedup(d["text"])]
    _dedup_excluded = [d["text"] for d in downgrade_d if _is_dedup(d["text"])]

    # ── 후방 호환: text-only 리스트 (EXPIRED 제외 — weight=0 이므로 표시 가치 없음) ──
    auto_avoid_text = [d["text"] for d in auto_avoid_d if d["freshness"] != "EXPIRED"]
    downgrade_text = [d["text"] for d in _penalized_d if d["freshness"] != "EXPIRED"]
    has_critical = any(d["freshness"] != "EXPIRED" for d in auto_avoid_d)
    weighted_dc = round(sum(d["weight"] for d in _penalized_d), 2)

    return {
        "auto_avoid": auto_avoid_text,
        "downgrade": downgrade_text,
        "auto_avoid_detail": auto_avoid_d,
        "downgrade_detail": downgrade_d,
        "dedup_excluded": _dedup_excluded,
        "has_critical": has_critical,
        "downgrade_count": weighted_dc,
    }
