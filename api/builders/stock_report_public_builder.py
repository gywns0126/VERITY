"""stock_report_public_builder — 공개 터미널 "종목 리포트" public-safe 합성 빌더.

2026-06-18 전종목 확장: 운영풀 10 → KR 전종목(~1,650).
  - 운영풀(recommendations.json): rich (PER/PBR/ROE/부채/Altman-Z/시총/지분/컨센/일정/공시)
  - 그 외(dart_fundamentals_kr.json 1,650): light (PER/PBR/ROE/부채/영업이익률 + 공시 + 컨센)
  - name/market = kr_listed.json (KP/KQ), 보조 kr_stock_names.json
  - 공시 = dart_catalyst_alerts.jsonl (시장 전체 수집, ticker별)
  - 컨센서스 = consensus_data.json (증권사 집계 — 자체 의견 아님)

🚨 RULE 7 — **allowlist** (점수/등급/추천/trade_plan/prediction 등 전부 비노출).
순수 변환 — 외부호출/KIS 0. publish: data/stock_report_public.json (action.yml 목록 등재됨).
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

KST = timezone(timedelta(hours=9))
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REC_PATH = os.path.join(_ROOT, "data", "recommendations.json")
FUND_PATH = os.path.join(_ROOT, "data", "dart_fundamentals_kr.json")
KRLISTED_PATH = os.path.join(_ROOT, "data", "kr_listed.json")
NAMES_PATH = os.path.join(_ROOT, "data", "kr_stock_names.json")
CONSENSUS_PATH = os.path.join(_ROOT, "data", "consensus_data.json")
CATALYST_PATH = os.path.join(_ROOT, "data", "dart_catalyst_alerts.jsonl")
# 2026-08-09 중·소형주 채움 — light 경로 보강 소스 (전부 로컬 발행물, 부재 시 graceful)
LYNCH_PATH = os.path.join(_ROOT, "data", "kr_lynch_class.json")
OWNER_DART_PATH = os.path.join(_ROOT, "data", "kr_major_shareholders.json")
CBBW_PATH = os.path.join(_ROOT, "data", "dart_cb_bw_cache.json")
CHAIN_PATH = os.path.join(_ROOT, "data", "chain_snippets.json")
# 과거 적재분 — alerts 와 종목 집합이 다르다(공시 커버리지 확대, 2026-08-08)
CATALYST_BACKFILL_PATH = os.path.join(_ROOT, "data", "dart_catalyst_backfill.jsonl")
# DART 최대주주 drip 백필 산출 (ownership 커버리지 확대, 2026-08-08)
KR_OWNERSHIP_PATH = os.path.join(_ROOT, "data", "kr_ownership.json")
SECTOR_MAP_PATH = os.path.join(_ROOT, "data", "kr_sector_map.json")
KRXMKTCAP_PATH = os.path.join(_ROOT, "data", "krx_mktcap.json")
DART_KR_BACKFILL_PATH = os.path.join(_ROOT, "data", "dart_kr_backfill_result.json")
DART_KR_FIN_HISTORY_PATH = os.path.join(_ROOT, "data", "dart_kr_fin_history.json")  # 광범위 연간재무 백필(재무추이 부활)
# 사업보고서 「II. 사업의 내용 › 1. 사업의 개요」 원문 발췌 (2026-08-23 신설)
BIZ_OVERVIEW_PATH = os.path.join(_ROOT, "data", "dart_business_overview.json")
# 🚨 2026-08-25 — 개요는 **별 blob 으로 분리**한다. 메인 리포트에 실으면 목록·검색 화면까지
#   개요를 받는다. 실측 = 메인 16.16MB 중 개요가 2.50MB(15.5%·1,747종목)였고,
#   `stock_slice` 는 콜드 인스턴스마다 이 원본을 통째로 받는다(8월 Fast Origin Transfer
#   236GB·$63.79 = 최대 과금 축). 상세 화면에서만 지연 로드하도록 파일을 나눈다.
#   ([[project_vercel_infra]] · 8/18 전송량 정렬 a680807f5 와 같은 근거)
BIZ_OVERVIEW_PUBLIC_PATH = os.path.join(_ROOT, "data", "kr_business_overview_public.json")
# 발행 본문 상한. 로컬 원장은 2,500자까지 보관하고, 공개 payload 만 여기서 줄인다.
#   🚨 상한을 넘겨 자른 사실은 종목마다 `truncated` 로 신고한다 — 조용히 자르면
#   원문 대조가 불가능해진다(Form 144 12건 절단 학습과 같은 계열).
#   🚨 600 인 이유 = **payload 예산**. 이 blob 은 공개 페이지가 통째로 받는다(12.85MB).
#   한글은 UTF-8 3바이트라 1,200자 × 1,092종목이면 **+3.03MB(+23.6%)** 였다(실측).
#   600 이면 +1.5MB 선. 전문이 필요하면 별 blob + 지연 로드가 맞고, 그건 Framer 작업이
#   따라붙는 별건이다. 원문 전체는 `data/dart_business_overview.json` 에 남아 있고
#   오퍼레이터 조인(ticker_facts)은 그쪽을 읽으므로 판단 품질은 이 상한과 무관하다.
BIZ_OVERVIEW_PUBLISH_CHARS = 600
OUTPUT_PATH = os.path.join(_ROOT, "data", "stock_report_public.json")

# 동종업계 비교 = 섹터별 중앙값. PER/PBR = KRX 시총 ÷ DART 순익·자기자본 자체계산(src="val"),
# 나머지 = dart_fundamentals 키(src=field). (label, src, suffix, digits)
PEER_METRICS = [("PER", "PER", "", 1), ("PBR", "PBR", "", 1),
                ("ROE", "roe", "%", 1), ("부채비율", "debt_ratio", "%", 0), ("영업이익률", "op_margin", "%", 1)]
DART = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo="

FAMILY_TYPES = {"동일인", "친족"}
# 🚨 2026-08-03 — kr_listed.json 실제 코드는 KS/KQ 인데 KP 만 매핑돼 있어 코스피 617종목이
#   시장 라벨에 원시 코드 "KS" 로 발행됐다(실측). KP 는 과거 표기라 호환 유지.
MARKET_MAP = {"KS": "KOSPI", "KP": "KOSPI", "KQ": "KOSDAQ", "KN": "KONEX"}


def _now_kst() -> datetime:
    return datetime.now(KST)


def _load_json(path: str, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def _is_kr(rec: Dict[str, Any]) -> bool:
    if str(rec.get("currency") or "") == "USD":
        return False
    mkt = str(rec.get("market") or "")
    return "KOSPI" in mkt or "KOSDAQ" in mkt or "KRX" in mkt or str(rec.get("ticker", "")).isdigit()


def _fmt_cap(v: Any) -> str:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return "—"
    if x <= 0:
        return "—"
    if x >= 1e12:
        return f"{x / 1e12:.1f}조"
    if x >= 1e8:
        return f"{x / 1e8:.0f}억"
    return f"{x:,.0f}"


def _fmt_won_signed(v: Any) -> Optional[str]:
    """금액 포매터(부호 유지 — 현금흐름 음수 대응). 조/억/원."""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    if x != x:  # NaN
        return None
    a = abs(x)
    sign = "−" if x < 0 else ""
    if a >= 1e12:
        return f"{sign}{a / 1e12:.1f}조"
    if a >= 1e8:
        return f"{sign}{a / 1e8:.0f}억"
    return f"{sign}{a:,.0f}"


def _financials(fund: Dict[str, Any]) -> Dict[str, Any] | None:
    """재무 요약 + 재무제표 그룹 상세 (최근 결산, dart_fundamentals_kr — 단일 연도 실값). 추이 X(KR 소스 단년).
    values=상단 3줄(매출/영업이익/순이익, synth 호환), groups=손익·재무상태·현금흐름·비율 전체(탭 상세). 전부 DART 사실."""
    if not fund:
        return None
    out: Dict[str, str] = {}
    for label, key in [("매출", "revenue"), ("영업이익", "operating_profit"), ("순이익", "net_income")]:
        v = fund.get(key)
        if v:
            out[label] = _fmt_cap(v)
    if not out:
        return None

    money = _fmt_won_signed
    pct = lambda v: _num(v, "%", 1)  # noqa: E731

    def grp(title: str, specs) -> Dict[str, Any] | None:
        rows = []
        for label, key, fmt in specs:
            v = fund.get(key)
            if v is None:
                continue
            fv = fmt(v)
            if fv is None:
                continue
            rows.append({"k": label, "v": fv})
        return {"title": title, "rows": rows} if rows else None

    groups = []
    for g in (
        grp("손익계산서", [("매출", "revenue", money), ("매출원가", "cogs", money), ("매출총이익", "gross_profit", money),
                       ("판매비와관리비", "sga", money), ("영업이익", "operating_profit", money),
                       ("금융수익", "finance_income", money), ("금융원가", "finance_cost", money),
                       ("법인세차감전순이익", "pretax_income", money), ("법인세비용", "income_tax", money),
                       ("순이익", "net_income", money),
                       ("매출총이익률", "gross_margin", pct), ("영업이익률", "op_margin", pct)]),
        grp("재무상태표", [("총자산", "total_assets", money), ("유동자산", "current_assets", money),
                       ("유동부채", "current_liabilities", money), ("이익잉여금", "retained_earnings", money),
                       ("운전자본", "working_capital", money)]),
        grp("현금흐름표", [("영업활동", "operating_cashflow", money), ("투자활동", "investing_cashflow", money),
                       ("재무활동", "financing_cashflow", money), ("잉여현금흐름(FCF)", "free_cashflow", money)]),
        grp("주요 비율", [("부채비율", "debt_ratio", pct), ("유동비율", "current_ratio", lambda v: _num(float(v) * 100, "%", 1) if v is not None else None),
                       ("ROE", "roe", pct), ("ROA", "roa", pct), ("자산회전율", "asset_turnover", lambda v: _num(v, "회", 2))]),
    ):
        if g:
            groups.append(g)

    yr = fund.get("report_date")
    res: Dict[str, Any] = {"values": out, "period": (str(yr) if yr else "최근 결산")}
    if groups:
        res["groups"] = groups
    return res


def _num(v: Any, suffix: str = "", digits: int = 1) -> Optional[str]:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    if x != x:  # NaN
        return None
    # 🚨 2026-08-03 소값 붕괴 방지 — ROE 0.04% 가 반올림으로 "0%" 가 되면 "값이 없다"로 오독된다.
    #   실제 0 이 아닌데 표기가 0 이면 유효숫자가 보일 때까지 자릿수를 늘린다(최대 소수 3자리).
    if x != 0:
        d = digits
        while d < 3 and abs(x) < 0.5 / (10 ** d):
            d += 1
        digits = d
    s = f"{x:.{digits}f}".rstrip("0").rstrip(".") if digits else f"{x:.0f}"
    return f"{s}{suffix}"


# 종목당 공시 상한 — backfill 병합으로 총 행이 11K → 148K 가 되므로 상한이 없으면
# 발행 JSON 이 폭증한다. 최근 순 정렬 후 자르므로 화면이 쓰는 최신분은 보존된다.
CATALYST_PER_TICKER_MAX = 30


def _load_catalyst_by_ticker() -> Dict[str, List[Dict[str, Any]]]:
    """공시 = alerts(최근 감시분) + backfill(과거 적재분) 병합.

    🚨 2026-08-08 (PM "동우팜투테이블 정보량이 적어보여") — 종전엔 alerts 만 읽었다.
    실측: alerts 11,072행/1,760종목 · backfill 137,370행/**1,315종목**. 두 파일의 종목
    집합이 다르다 — 088910 은 alerts 0건인데 backfill 에는 9건 있었고, 그래서 공시 섹션이
    비어 있었다. 커버리지가 서로를 보완하므로 둘 다 읽는다(rcept_no 로 중복 제거).
    fin_history 를 재무추이에 병합한 것과 같은 패턴.
    """
    out: Dict[str, List[Dict[str, Any]]] = {}
    seen: set = set()
    # alerts 를 먼저 읽어 중복 시 최근 감시분이 남게 한다(같은 rcept_no 면 뒤가 skip).
    for path in (CATALYST_PATH, CATALYST_BACKFILL_PATH):
        if not os.path.isfile(path):
            continue
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    a = json.loads(line)
                except json.JSONDecodeError:
                    continue
                tk = str(a.get("ticker") or "")
                rc = str(a.get("rcept_no") or "")
                if not tk or not rc or rc in seen:
                    continue
                seen.add(rc)
                dt = str(a.get("rcept_dt") or "")
                date = f"{dt[:4]}-{dt[4:6]}-{dt[6:8]}" if len(dt) == 8 else dt
                out.setdefault(tk, []).append({
                    "title": a.get("report_nm") or "",
                    "label": a.get("pblntf_label") or "",
                    "date": date,
                    "is_correction": bool(a.get("is_correction")),
                    "filer": a.get("flr_nm") or "",
                    "source_url": DART + rc,
                })
    for tk in out:
        out[tk].sort(key=lambda d: d["date"], reverse=True)
        del out[tk][CATALYST_PER_TICKER_MAX:]
    return out


# ─── 지분구조 인물 링크 생존성 (2026-07-04 PM) ─────────────────────────────
# 문제: 비유명 임원·친족 = 네이버 검색 결과 0 → 죽은 링크. 빌더가 "회사명 이름" 뉴스
# 건수를 네이버 공식 API 로 실검증해 결과 있는 인물만 link_ok 노출 (컴포넌트가 링크 조건으로 사용).
# 키 = NAVER_Client_ID/Secret (naver_stock_news 동일). 키/네트워크 부재 = 플래그 생략(링크 없음) 안전 강등.
# 캐시 = data/metadata/person_link_cache.json — 인물·회사 조합은 공정위 연 1회 갱신이라 사실상 영구.
_PERSON_LINK_CACHE_PATH = os.path.join(_ROOT, "data", "metadata", "person_link_cache.json")
_PERSON_LINK_MIN_NEWS = 5  # 최소 뉴스 건수 — 링크 클릭 화면에 결과 존재 보장선
_SH_GENERIC_RE = re.compile(r"기타|소액주주|자기주식|우리사주|^친족$|^동일인$|^임원$|기관투자|외국인|개인투자자|국민연금공단")
_SH_CORP_RE = re.compile(r"주식회사|\(주\)|㈜|회사|Ltd|LTD|Inc|INC|Limited|Corp|Company|생명|화재|증권|물산|홀딩스|투자|캐피탈|은행|보험|자산운용|전자|중공업|텔레콤|공단|재단")
_person_link_cache: Optional[Dict[str, Any]] = None
_person_link_dirty = False


def _naver_news_total(query: str) -> Optional[int]:
    cid = os.environ.get("NAVER_Client_ID") or os.environ.get("NAVER_CLIENT_ID", "")
    csec = os.environ.get("NAVER_Client_Secret") or os.environ.get("NAVER_CLIENT_SECRET", "")
    if not cid or not csec:
        return None
    import urllib.parse
    import urllib.request
    try:
        req = urllib.request.Request(
            "https://openapi.naver.com/v1/search/news.json?display=1&query=" + urllib.parse.quote(query),
            headers={"X-Naver-Client-Id": cid, "X-Naver-Client-Secret": csec},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.loads(r.read().decode("utf-8", "replace"))
        time.sleep(0.08)
        return int(d.get("total") or 0)
    except Exception:  # noqa: BLE001
        return None


def _annotate_person_links(own: Optional[Dict[str, Any]], corp_name: str) -> None:
    """shareholders 인물 행에 link_ok 부여 — 검증된(뉴스 결과 있는) 인물만. in-place."""
    global _person_link_cache, _person_link_dirty
    if not isinstance(own, dict) or not corp_name:
        return
    if _person_link_cache is None:
        _person_link_cache = _load_json(_PERSON_LINK_CACHE_PATH, {}) or {}
    for row in own.get("shareholders") or []:
        nm = str(row.get("name") or "")
        if not nm or nm == str(row.get("type") or "") or _SH_GENERIC_RE.search(nm):
            continue
        if str(row.get("type") or "") == "소속회사" or _SH_CORP_RE.search(nm):
            continue  # 법인·재단 = 컴포넌트 자체 링크 (검색 결과 상시 존재)
        key = f"{corp_name}|{nm}"
        ent = _person_link_cache.get(key)
        if not isinstance(ent, dict):
            total = _naver_news_total(f"{corp_name} {nm}")
            if total is None:
                continue
            ent = {"total": total, "checked": datetime.now(KST).strftime("%Y-%m-%d")}
            _person_link_cache[key] = ent
            _person_link_dirty = True
        if int(ent.get("total") or 0) >= _PERSON_LINK_MIN_NEWS:
            row["link_ok"] = True


def _save_person_link_cache() -> None:
    if _person_link_dirty and isinstance(_person_link_cache, dict):
        os.makedirs(os.path.dirname(_PERSON_LINK_CACHE_PATH), exist_ok=True)
        with open(_PERSON_LINK_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(_person_link_cache, f, ensure_ascii=False)


def _ownership(rec: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    gs = rec.get("group_structure") or {}
    ftc = gs.get("ftc_official") or {}
    sh = ftc.get("shareholders") or []
    if not isinstance(sh, list) or not sh:
        return None
    family = 0.0
    rows: List[Dict[str, Any]] = []
    for s in sh:
        try:
            q = float(s.get("qota_rate") or 0)
        except (TypeError, ValueError):
            q = 0.0
        t = str(s.get("type") or "")
        if t in FAMILY_TYPES:
            family += q
        rows.append({"name": str(s.get("name") or t), "type": t, "pct": round(q, 2)})
    rows.sort(key=lambda x: x["pct"], reverse=True)
    out: Dict[str, Any] = {
        "family_pct": round(family, 2),
        "group": str(ftc.get("group") or gs.get("group_name") or ""),
        "shareholders": rows[:8],  # 의결권 지분율 상위 (공정위 분류)
        "note": "동일인+친족 = 총수일가 지배지분 · 공정위 분류(의결권 지분율)",
        "source": "공정거래위원회 기업집단포털" + (f" ({ftc.get('as_of_year')})" if ftc.get("as_of_year") else ""),
    }
    # DART 최대주주 ↔ 공정위 교차검증 (우리 차별 — 1차 출처 이중확인)
    cc = ftc.get("cross_check")
    if isinstance(cc, dict) and cc.get("status"):
        out["cross_check"] = {
            "entity": str(cc.get("entity") or ""),
            "dart_pct": cc.get("dart_pct"),
            "ftc_pct": cc.get("ftc_pct"),
            "status": str(cc.get("status")),
        }
    parent = gs.get("parent")
    if isinstance(parent, dict) and parent.get("name"):
        out["parent"] = str(parent.get("name"))
    subs = gs.get("subsidiaries")
    if isinstance(subs, list) and subs:
        out["sub_count"] = len(subs)
    return out


def _institutional(rec: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """기관·국민연금 5%+ 대량보유 (DART majorstock) — 사실. net_flow_direction(해석) 비노출."""
    mh = rec.get("dart_major_holders") or {}
    inst = mh.get("institutional_holders")
    if not isinstance(inst, list) or not inst:
        return None
    holders: List[Dict[str, Any]] = []
    for h in inst[:6]:
        if not isinstance(h, dict) or not h.get("reporter"):
            continue
        holders.append({
            "reporter": str(h.get("reporter")),
            "pct": h.get("pct"),
            "qty_change": h.get("qty_change"),
            "date": str(h.get("date") or ""),
        })
    if not holders:
        return None
    return {
        "total_pct": mh.get("total_institutional_pct"),
        "n": mh.get("n_institutions"),
        "holders": holders,
        "note": "DART 5%+ 대량보유 보고(기관·국민연금) — 사실, 신호 아님",
    }


def _facilities(rec: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """사업장·설비 현황 (DART 사업보고서 facilities_parser) — 사실."""
    data = (rec.get("facilities_dart") or {}).get("data") or {}
    fac = data.get("domestic_facilities")
    hq = data.get("headquarters")
    if not (isinstance(fac, list) and fac) and not isinstance(hq, dict):
        return None
    items: List[Dict[str, Any]] = []
    for f in (fac if isinstance(fac, list) else [])[:6]:
        if not isinstance(f, dict) or not f.get("name"):
            continue
        items.append({k: str(f.get(k)) for k in ("name", "location", "use", "segment") if f.get(k)})
    out: Dict[str, Any] = {"note": "DART 사업보고서 시설 현황 — 사실"}
    if isinstance(hq, dict) and hq.get("location"):
        out["headquarters"] = {"location": str(hq.get("location")),
                               "ownership": str(hq.get("ownership") or "")}
    if items:
        out["facilities"] = items
    return out if (out.get("headquarters") or out.get("facilities")) else None


def _consensus_from_rec(rec: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    c = rec.get("consensus") or {}
    if not c.get("consensus_available"):
        return None
    out: Dict[str, Any] = {}
    if c.get("target_price"):
        out["target_price"] = _fmt_won(c["target_price"])
    if c.get("investment_opinion"):
        out["opinion"] = str(c["investment_opinion"])
    eps = rec.get("eps")
    try:
        if eps and float(eps) != 0:
            out["eps"] = f"{float(eps):,.0f}원"
    except (TypeError, ValueError):
        pass
    return out or None


def _verity_lens_from_lynch(lynch: Any) -> Optional[Dict[str, Any]]:
    """VERITY 관측 lens — '컨센서스 위에 얹는' 차별 view (토스·키움·LLM 미보유).
    중앙 산출물(kr_lynch_class.by_ticker)의 규칙 기반 분류만 발행. 자체 산식 점수·등급·매매의견
    (verity_brain/brain_score/grade, multi_factor grade·multi_score, safety_score,
    recommendation, confidence)은 RULE 7대로 검증 게이트 통과 전까지 발행 제외."""
    lynch = lynch if isinstance(lynch, dict) else {}
    cls = lynch.get("class")
    if not cls:
        return None
    # 데이터 품질 미달 분류는 숨김 (RULE 7 — 미검증·저신뢰 표시 금지)
    dq = lynch.get("data_quality")
    if dq and dq != "ok":
        return None
    return {
        "lynch": {
            "class": str(cls),
            "label": str(lynch.get("label") or ""),
            "summary": str(lynch.get("summary") or ""),
            "reasons": [str(x) for x in (lynch.get("reasons") or [])][:4],
            "color": str(lynch.get("color") or "neutral"),
        },
        "note": "Peter Lynch 분류 룰을 공개 재무 사실에 적용한 관측 — 자체 점수·매매의견 아님. 종합점수는 검증 통과 후 공개.",
    }


def _verity_lens_from_rec(rec: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """빌드 중간 호환용. 최종 발행은 중앙 kr_lynch_class 값으로 다시 고정한다."""
    return _verity_lens_from_lynch(rec.get("lynch_kr"))


def _fmt_won(v: Any) -> Optional[str]:
    try:
        return f"{float(v):,.0f}원"
    except (TypeError, ValueError):
        return None


def build_rich(rec: Dict[str, Any], catalyst: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    ticker = str(rec.get("ticker") or "")
    altman = (((rec.get("quant_factors") or {}).get("quality") or {}).get("altman") or {})
    facts: Dict[str, str] = {}
    fnote: Dict[str, str] = {}
    for key, src, suf, dg in [("PER", "per", "", 1), ("PBR", "pbr", "", 1),
                               ("ROE", "roe", "%", 1), ("부채비율", "debt_ratio", "%", 0)]:
        val = _num(rec.get(src), suf, dg)
        if val is not None:
            facts[key] = val
    # Altman-Z — sanity 가드: 정상 범위 밖(데이터 오류 이상치)는 비노출 (공개 사실 신뢰성)
    try:
        zf = float(altman.get("z_score")) if altman.get("z_score") is not None else None
    except (TypeError, ValueError):
        zf = None
    if zf is not None and -20.0 <= zf <= 30.0:
        az = _num(zf, digits=1)
        if az is not None:
            facts["Altman-Z"] = az
            if altman.get("zone"):
                fnote["Altman-Z"] = "안전구간" if altman["zone"] == "safe" else str(altman["zone"])
    if rec.get("market_cap"):
        facts["시가총액"] = _fmt_cap(rec.get("market_cap"))
    # 투자지표 확장 (EPS·배당수익률 — 사실)
    eps = _num(rec.get("eps"), "원", 0)
    if eps is not None and str(rec.get("eps") or "0") not in ("0", "0.0"):
        facts["EPS"] = eps
    dy = _num(rec.get("div_yield"), "%", 2)
    if dy is not None and float(rec.get("div_yield") or 0) > 0:
        facts["배당수익률"] = dy
    # BPS = 자기자본 ÷ 발행주식수 — _valuation_map 에서 부착한다 (아래 보강 루프).
    # 🚨 여기서 주가÷PBR 로 역산하지 말 것: rec["pbr"] 은 이상치일 때 1.0 으로 정규화되므로
    #    (rec["data_quality_fixes"] = ["pbr_invalid_to_1.0"]) BPS 가 주가와 같은 값으로 나온다.
    #    2026-08-03 발행본 rich 14종목 전수 오염 확인 → 역산 경로 제거.
    # PSR = 시가총액 ÷ 매출 (배 · 매출 있을 때만 · sanity 가드로 이상치 비노출)
    try:
        mc = float(rec.get("market_cap") or 0)
        rev = float(rec.get("revenue") or 0)
        if mc > 0 and rev > 0:
            psr_v = mc / rev
            if 0 < psr_v <= 100:
                facts["PSR"] = f"{psr_v:,.2f}배"
                fnote["PSR"] = "시가총액 ÷ 매출 (DART)"
    except (TypeError, ValueError):
        pass
    # 배당 상세 (DART 배당 표 — 주당배당금·배당성향, 사실)
    divs = (rec.get("dart_financials") or {}).get("dividends") or []

    def _div_val(cat_sub: str) -> Optional[str]:
        for it in divs:
            v = str(it.get("current") or "").strip()
            if cat_sub in str(it.get("category") or "") and v and v != "-":
                return v
        return None

    dps = _div_val("주당 현금배당금")
    if dps:
        facts["주당배당금"] = dps + "원"
        fnote["주당배당금"] = "DART 배당 — 주당 현금배당금"
    payout = _div_val("현금배당성향")
    if payout:
        try:
            facts["배당성향"] = f"{float(payout):.1f}%"
            fnote["배당성향"] = "현금배당성향 (배당금 ÷ 순이익, DART)"
        except (TypeError, ValueError):
            pass
    # 지분 보유율 (기관·내부자 — 사실)
    for label, key in (("기관 보유율", "held_pct_institutions"), ("내부자 지분", "held_pct_insiders")):
        hv = rec.get(key)
        if hv not in (None, "", 0):
            try:
                facts[label] = f"{float(hv):.1f}%"
            except (TypeError, ValueError):
                pass
    # 52주 고점대비 (사실 — 현재가가 52주 최고가 대비 몇 %)
    dfh = rec.get("drop_from_high_pct")
    if dfh not in (None, ""):
        try:
            facts["52주 고점대비"] = f"{float(dfh):.1f}%"
            fnote["52주 고점대비"] = "현재가 ÷ 52주 최고가 − 1"
        except (TypeError, ValueError):
            pass
    # 거래량(평균대비) (사실 — 직전 거래일 거래량 ÷ 최근 평균)
    # 🚨 technical 블록이 미산출인 레코드(관심종목 유래 — price/ma 전부 0)는 vol_ratio 기본값 1.0 이
    #    그대로 "100%" 로 나가 '거래량 평범' 으로 오독된다 (2026-08-03 094970 확인).
    #    technical.price > 0 = 실제 산출된 블록. 미산출이면 필드 자체를 비노출한다.
    tech = rec.get("technical") or {}
    try:
        tech_computed = float(tech.get("price") or 0) > 0
    except (TypeError, ValueError):
        tech_computed = False
    vr = tech.get("vol_ratio") if tech_computed else None
    if vr not in (None, "", 0):
        try:
            facts["거래량(평균대비)"] = f"{float(vr) * 100:.0f}%"
            fnote["거래량(평균대비)"] = "직전 거래일 거래량 ÷ 최근 평균"
        except (TypeError, ValueError):
            pass

    # 헤더 메타 — 🚨 시세 재배포 컴플라이언스(2026-07-03): range_52w(주가 밴드)·trading_value(거래대금 raw) 제거.
    # market_cap 은 유지 — KRX MKTCAP 파생(PER/PBR 자체계산 입력·자본 규모 사실), sector medians 유지와 동일 논리.
    # 컴포넌트(StockReport)는 필드 부재 시 자동 미표시(graceful).
    header: Dict[str, str] = {}
    if rec.get("market_cap"):
        header["market_cap"] = _fmt_cap(rec.get("market_cap"))

    # 기업 개요 (사실 — tagline/발행주식수/섹터. one_line_summary=자체분석 제외 RULE6)
    overview: Dict[str, str] = {}
    if rec.get("company_tagline"):
        overview["tagline"] = str(rec["company_tagline"])
    so = rec.get("shares_outstanding")
    try:
        if so and float(so) > 0:
            overview["shares"] = f"{float(so) / 1e8:,.2f}억주" if float(so) >= 1e8 else f"{float(so):,.0f}주"
    except (TypeError, ValueError):
        pass
    if rec.get("sector") or rec.get("company_type"):
        overview["sector"] = str(rec.get("company_type") or rec.get("sector"))

    # 부동산 자산 (DART 재무상태표 투자부동산 장부가 — 사실, 시가 아님)
    real_estate = None
    pa = (rec.get("dart_financials") or {}).get("property_assets") or {}
    try:
        tot = float(pa.get("total_current") or 0)
        if tot > 0:
            items = []
            for it in (pa.get("items") or [])[:6]:
                v = float(it.get("current") or 0)
                if v > 0:
                    items.append({"name": str(it.get("account_nm") or it.get("name") or ""), "value": _fmt_cap(v)})
            real_estate = {"total": _fmt_cap(tot), "items": items,
                           "note": "재무상태표 장부가(시가 아님) · DART"}
    except (TypeError, ValueError):
        real_estate = None

    out = {
        "ticker": ticker, "name": rec.get("name") or ticker, "market": rec.get("market") or "",
        "business": rec.get("company_tagline") or rec.get("company_type") or "",
        "facts": facts, "facts_note": fnote,
        "header": header or None,
        "overview": overview or None,
        "real_estate": real_estate,
        "disclosures": catalyst.get(ticker, [])[:8],
        "ownership": _ownership(rec),
        "institutional": _institutional(rec),
        "facilities": _facilities(rec),
        # consensus 미부착 (2026-07-10) — 쟁점4 이중IP(네이버 ToS+증권사 리서치). 표시=출처 링크아웃 대체.
        "consensus": None,
        "verity_lens": _verity_lens_from_rec(rec),
        "calendar": ([{"event": "실적발표", "kind": "실적", "date": (rec.get("earnings") or {}).get("next_earnings")}]
                     if (rec.get("earnings") or {}).get("next_earnings") else []),
        "rich": True,
    }
    return out


def _ownership_from_dart(rec: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """DART 최대주주 현황(hyslrSttus) → ownership 노출 shape.

    🚨 2026-08-09 — 기존 ownership 은 공정위 `ftc_official` 이 유일 소스였는데 공정위는
    **대규모기업집단(~346개사)만** 공시한다. 중·소형주는 구조적으로 대상 밖이라 8.6% 에
    머물렀다(소스 부재가 아니라 소스 성격 문제). DART 사업보고서 최대주주 현황은
    **전 상장사 제출 의무**라 여기서 채운다. 두 소스는 note 로 구분한다.
    """
    rows_in = (rec or {}).get("shareholders") or []
    if not isinstance(rows_in, list) or not rows_in:
        return None
    # 🚨 DART hyslrSttus 응답에는 '계/합계/소계/총계' 집계행이 섞인다. 수집 단계에서도
    #   거르지만 여기서 한 번 더 막는다 — 소스가 오염된 채 들어와도 공개 화면에
    #   "계 76.2%" 같은 잡음이 나가면 안 된다(2026-08-09 실측 2,368행 오염).
    _AGG = {"계", "합계", "소계", "총계"}
    rows: List[Dict[str, Any]] = []
    for s in rows_in:
        try:
            pct = float(str(s.get("stock_rate") or "0").replace(",", ""))
        except (TypeError, ValueError):
            pct = 0.0
        nm = str(s.get("nm") or "").strip()
        if not nm or re.sub(r"\s+", "", nm) in _AGG:
            continue
        rows.append({"name": nm, "type": str(s.get("relate") or ""), "pct": round(pct, 2)})
    if not rows:
        return None
    rows.sort(key=lambda x: x["pct"], reverse=True)
    return {
        "family_pct": None,   # 공정위 '동일인+친족' 분류가 없는 소스 — 지어내지 않는다
        "group": "",
        "shareholders": rows[:8],
        "note": f"DART 사업보고서 최대주주 현황 ({(rec or {}).get('bsns_year') or ''}) · "
                "지분율은 보고서 기재값. 공정위 총수일가 분류는 이 소스에 없음",
    }


def _overhang_from_cache(rec: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """CB/BW 오버행 — DART 발행결정 공시 + 발행주식수 비율. LLM 0, 자체 점수 0."""
    if not isinstance(rec, dict):
        return None
    n = rec.get("n_instruments")
    if not n:
        return None      # 0건 = '오버행 없음 확정'. 빈 섹션을 만들지 않는다
    return {
        "count": n,
        "dilution_pct": rec.get("dilution_pct"),
        "issuable_shares": rec.get("total_issuable_shares"),
        "window": rec.get("window"),
        "note": "전환사채·신주인수권부사채 발행결정 공시 기준 잠재 희석 · DART 사실",
    }


def build_light(ticker: str, fund: Dict[str, Any], name: str, market: str,
                catalyst: Dict[str, List[Dict[str, Any]]],
                consensus_map: Dict[str, Dict[str, Any]],
                lynch_map: Optional[Dict[str, Any]] = None,
                owner_map: Optional[Dict[str, Any]] = None,
                overhang_map: Optional[Dict[str, Any]] = None,
                chain_map: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    facts: Dict[str, str] = {}
    for key, src, suf, dg in [("PER", "per", "", 1), ("PBR", "pbr", "", 1),
                               ("ROE", "roe", "%", 1), ("부채비율", "debt_ratio", "%", 0),
                               ("영업이익률", "op_margin", "%", 1)]:
        val = _num(fund.get(src), suf, dg)
        if val is not None:
            facts[key] = val
    cons = consensus_map.get(ticker)
    # 🚨 2026-08-09 — 여기까지가 옛 light 였다. 아래 4종은 운영풀 20종(build_rich)에만
    #   달려 있어 소형주 리포트가 "네이버와 같은 화면" 이던 원인이다.
    #   전부 DART/규칙 기반 사실이라 RULE 7 정합(자체 점수·등급·매매의견 0).
    lynch = (lynch_map or {}).get(ticker)
    lens = None
    if isinstance(lynch, dict) and lynch.get("data_quality") == "ok":
        # 미검증·저신뢰 분류는 숨긴다 — build_rich 의 _verity_lens_from_rec 와 같은 규율
        lens = {
            "lynch": {k: lynch.get(k) for k in ("class", "label", "summary", "color")}
                     | {"reasons": (lynch.get("reasons") or [])[:4]},
            "note": "Peter Lynch 분류 룰을 공개 재무 사실에 적용한 관측 — 자체 점수·매매의견 "
                    "아님. 종합점수는 검증 통과 후 공개.",
        }
    chain = (chain_map or {}).get(ticker) or {}
    snippets = (chain.get("snippets") or [])[:3] if isinstance(chain, dict) else []
    return {
        "ticker": ticker, "name": name or ticker, "market": market or "",
        "business": "",
        "facts": facts, "facts_note": {},
        "disclosures": catalyst.get(ticker, [])[:8],
        "ownership": _ownership_from_dart((owner_map or {}).get(ticker)),
        "overhang": _overhang_from_cache((overhang_map or {}).get(ticker)),
        "supply_chain": ({"report_nm": chain.get("report_nm"), "rcept_dt": chain.get("rcept_dt"),
                          "snippets": snippets,
                          "note": "사업보고서 '주요 매출처' 앵커 주변 원문 발췌 · DART"}
                         if snippets else None),
        "consensus": None,  # 쟁점4 봉인 (2026-07-10) — cons map 은 내부 관측용으로만 유지
        "verity_lens": lens,
        "calendar": [],
        "rich": False,
    }


def _median(vals: List[float]) -> Optional[float]:
    xs = sorted(v for v in vals if isinstance(v, (int, float)) and v == v)
    n = len(xs)
    if n == 0:
        return None
    mid = n // 2
    return xs[mid] if n % 2 else (xs[mid - 1] + xs[mid]) / 2.0


def _valuation_map(fundamentals: Dict[str, Any], krx_map: Dict[str, Any],
                   fin_series: Optional[Dict[str, List[Dict[str, Any]]]] = None,
                   panel_facts: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, Dict[str, float]]:
    """PER/PBR/BPS 자체계산: KRX 공식 시총·발행주식수 ÷ DART 순이익·자기자본.
    (자기자본 = 자산/(1+부채비율/100), BPS = 자기자본/발행주식수).

    fin_series 를 주면 fundamentals 결측 종목도 **시총 + PER 까지는** 채운다
    (2026-08-08). 근거는 동일하다 — KRX 공식 시총 ÷ DART 공시 순이익. 다만 자기자본
    (총자산·부채비율)이 연간 시계열에 없어 PBR/BPS 는 계산하지 않고 비워 둔다.
    🚨 없는 값을 역산해 채우지 않는다 — 2026-08-03 rich 14종목 전수 오염이 역산 경로에서
    나왔다. 계산 가능한 것만 계산하고 나머지는 결측으로 남기는 편이 맞다.
    """
    out: Dict[str, Dict[str, float]] = {}
    for tk, f in fundamentals.items():
        km = krx_map.get(tk)
        if not km:
            continue
        try:
            mktcap = float(km.get("mktcap") or 0)
        except (TypeError, ValueError):
            mktcap = 0.0
        if mktcap <= 0:
            continue
        v: Dict[str, Any] = {"mktcap": mktcap}  # 시총 항상 보유 (PER/PBR 결측이어도 정렬·필터용)
        try:
            ni = float(f.get("net_income")) if f.get("net_income") is not None else None
            if ni and ni > 0:
                v["PER"] = round(mktcap / ni, 2)
                v["_per_in"] = {"mktcap": mktcap, "net_income": ni}
        except (TypeError, ValueError):
            pass
        # PSR = 시가총액 ÷ 매출. build_rich 와 **같은 산식·같은 sanity 가드**(0<psr<=100).
        #   2026-08-23 — 종전엔 운영풀(rich) 경로에만 있어 10/1,790 이었다. 입력(KRX 시총 ·
        #   DART 매출)은 전 종목에 있었으므로 결손은 소스가 아니라 **부착 경로**였다.
        try:
            rv = float(f.get("revenue")) if f.get("revenue") is not None else None
            if rv and rv > 0:
                _psr = mktcap / rv
                if 0 < _psr <= 100:
                    v["PSR"] = round(_psr, 2)
                    v["_psr_in"] = {"mktcap": mktcap, "revenue": rv}
        except (TypeError, ValueError):
            pass
        try:
            shares = float(km.get("shares") or 0)
        except (TypeError, ValueError):
            shares = 0.0
        try:
            ta = float(f.get("total_assets")) if f.get("total_assets") is not None else None
            dr = float(f.get("debt_ratio")) if f.get("debt_ratio") is not None else None
            if ta and ta > 0 and dr is not None and dr > -100:
                equity = ta / (1.0 + dr / 100.0)
                if equity > 0:
                    v["PBR"] = round(mktcap / equity, 2)
                    v["_pbr_in"] = {"mktcap": mktcap, "equity": equity}
                    # BPS = 자기자본 ÷ 발행주식수 (KRX 공식 주식수 · DART 자본).
                    # 🚨 주가÷PBR 역산 금지 — rec["pbr"] 은 placeholder 1.0 로 정규화되는 경우가 있어
                    #    BPS 가 주가 그대로 나온다 (2026-08-03 rich 14종목 전수 오염 확인).
                    if shares > 0:
                        v["BPS"] = equity / shares
                        v["_bps_in"] = {"equity": equity, "shares": shares}
        except (TypeError, ValueError):
            pass
        if v:
            out[tk] = v

    # 분기 패널 소스 종목 보강 (2026-08-26) — 시총 + PER(TTM) + PBR(최신 분기 자기자본).
    # fin_series 폴백과 같은 자체계산 선례(시총 ÷ DART 공시 실값)이며 TTM 기준. RULE 7 사실만.
    for tk, pf in (panel_facts or {}).items():
        if tk in out:
            continue
        km = krx_map.get(tk)
        if not km:
            continue
        try:
            mktcap = float(km.get("mktcap") or 0)
        except (TypeError, ValueError):
            continue
        if mktcap <= 0:
            continue
        v: Dict[str, Any] = {"mktcap": mktcap}
        try:
            ni = float(pf.get("net_income_ttm") or 0)
            if ni > 0:
                v["PER"] = round(mktcap / ni, 2)
                v["_per_in"] = {"mktcap": mktcap, "net_income_ttm": ni,
                                "quarter_end": pf.get("quarter_end"), "basis": "ttm"}
        except (TypeError, ValueError):
            pass
        try:
            eq = float(pf.get("equity") or 0)
            if eq > 0:
                v["PBR"] = round(mktcap / eq, 2)
                v["_pbr_in"] = {"mktcap": mktcap, "equity": eq,
                                "quarter_end": pf.get("quarter_end")}
        except (TypeError, ValueError):
            pass
        out[tk] = v

    # fundamentals 결측 종목 보강 — 시총 + PER 만 (근거: KRX 공식 시총 ÷ DART 공시 순이익).
    # 이 종목들은 위 루프가 아예 훑지 않아 시총조차 없었고, 그래서 정렬·필터·동종비교에서
    # 통째로 빠졌다. PBR/BPS 는 자기자본 입력이 없어 계산하지 않는다(결측 유지).
    for tk, pts in (fin_series or {}).items():
        if tk in out or not pts:
            continue
        km = krx_map.get(tk)
        if not km:
            continue
        try:
            mktcap = float(km.get("mktcap") or 0)
        except (TypeError, ValueError):
            continue
        if mktcap <= 0:
            continue
        v = {"mktcap": mktcap}
        latest = pts[-1]  # _load_fin_series 가 연도 오름차순으로 정렬해 둔다
        try:
            ni = float(latest.get("net")) if latest.get("net") is not None else None
        except (TypeError, ValueError):
            ni = None
        if ni and ni > 0:
            v["PER"] = round(mktcap / ni, 2)
            v["_per_in"] = {"mktcap": mktcap, "net_income": ni, "fiscal_year": latest.get("year")}
        try:
            rv = float(latest.get("revenue")) if latest.get("revenue") is not None else None
        except (TypeError, ValueError):
            rv = None
        if rv and rv > 0:
            _psr = mktcap / rv
            if 0 < _psr <= 100:
                v["PSR"] = round(_psr, 2)
                v["_psr_in"] = {"mktcap": mktcap, "revenue": rv, "fiscal_year": latest.get("year")}
        out[tk] = v
    return out


_BAD_NAME_RE = re.compile(r"^\d{6}\.K[SQ]\b|,0P[0-9A-Z]{8}|^\d{6}$")


def _normalize_kr_identity(s: Dict[str, Any], tk: str, name_market) -> None:
    """국내 종목명·시장 = 자체 SoT(kr_listed → kr_stock_names) 우선.

    🚨 2026-08-03 — 운영풀(recommendations.json) 경로(rich)가 외부 소스에서 받은
    `"094970.KS,0P0000EOZ4,42992"`(야후 심볼·모닝스타 ID·숫자 CSV 한 줄)를 그대로 종목명으로
    노출했다(제이엠티·KT밀리의서재 2종목, PM 지적). 시장도 `.KS` 접미사로만 판정해 코스닥
    종목이 KOSPI 로 찍혔다. 국내 종목은 kr_listed 라는 자체 SoT 가 있으므로 외부 값보다 우선한다.
    되돌리지 말 것 — 외부 소스 이름을 신뢰하면 같은 오염이 재발한다.
    """
    if not re.fullmatch(r"\d{6}", tk):
        return
    nm, mk = name_market(tk)
    cur = str(s.get("name") or "")
    if nm and nm != tk and (not cur or cur == tk or _BAD_NAME_RE.search(cur)):
        s["name"] = nm
    if mk:
        s["market"] = mk


def _normalize_dart_facts(s: Dict[str, Any], fund: Optional[Dict[str, Any]]) -> None:
    """ROE·부채비율·영업이익률 = DART 재무 우선. 값 없으면 **필드 자체를 뺀다**.

    🚨 2026-08-03 — rich 경로는 운영풀 rec 의 `roe`/`debt_ratio` 를 썼는데, 그 값은 외부
    조회 실패 시 0 으로 채워진다(결손의 0 인코딩). `_num(0)` → `"0%"` 라 화면에 "ROE 0%"
    가 사실처럼 떴다(실측 10종목). 같은 종목의 DART 값은 멀쩡했다 — 제이엠티 ROE 8.65% /
    부채비율 46.84%. 없는 값을 0 으로 보여주는 건 RULE 7 위반이므로 미노출로 되돌린다.
    되돌리지 말 것 — rec 값을 DART 보다 우선하면 같은 오표시가 재발한다.
    """
    fund = fund or {}
    facts = s.get("facts")
    if not isinstance(facts, dict):
        return
    for key, src, suf, dg in (("ROE", "roe", "%", 1), ("부채비율", "debt_ratio", "%", 0),
                              ("영업이익률", "op_margin", "%", 1)):
        v = fund.get(src)
        val = _num(v, suf, dg) if v is not None else None
        if val is not None:
            facts[key] = val
        elif facts.get(key) in ("0%", "0"):
            facts.pop(key, None)  # 결손의 0 인코딩 — 사실인 척하지 않는다


def _apply_krx_market_facts(s: Dict[str, Any], km: Optional[Dict[str, Any]]) -> None:
    """공개 시가총액·발행주식수는 KRX 공식 스냅샷으로 항상 덮어쓴다.

    recommendations의 market_cap/shares_outstanding은 유통 기준 또는 외부 추정치일 수 있다.
    같은 라벨에 두 정의가 섞이면 facts·header·overview가 서로 다른 숫자를 보이므로,
    공개 기본 라벨은 KRX 공식값 하나로 고정한다. 유통시총은 별도 라벨·출처 계약 전까지
    공개하지 않는다.
    """
    if not isinstance(km, dict):
        return
    try:
        mktcap = float(km.get("mktcap") or 0)
    except (TypeError, ValueError):
        mktcap = 0.0
    if mktcap > 0:
        cap = _fmt_cap(mktcap)
        s.setdefault("facts", {})["시가총액"] = cap
        s.setdefault("facts_note", {})["시가총액"] = "KRX 공식 시가총액"
        header = s.get("header")
        if not isinstance(header, dict):
            header = {}
            s["header"] = header
        header["market_cap"] = cap

    try:
        shares = float(km.get("shares") or 0)
    except (TypeError, ValueError):
        shares = 0.0
    if shares > 0:
        overview = s.get("overview")
        if not isinstance(overview, dict):
            overview = {}
            s["overview"] = overview
        overview["shares"] = (f"{shares / 1e8:,.2f}억주" if shares >= 1e8
                              else f"{shares:,.0f}주")
        overview["shares_source"] = "KRX 상장주식수"


def _metric_val(tk: str, src: str, fundamentals: Dict[str, Any], valuation: Dict[str, Any]) -> Optional[float]:
    if src in ("PER", "PBR"):
        v = (valuation.get(tk) or {}).get(src)
    else:
        v = (fundamentals.get(tk) or {}).get(src)
    try:
        return float(v) if v is not None and float(v) == float(v) else None
    except (TypeError, ValueError):
        return None


def _sector_medians(fundamentals: Dict[str, Any], sector_map: Dict[str, Any],
                    valuation: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """섹터(한글)별 PER/PBR(자체계산)·ROE·부채비율·영업이익률 중앙값 + N. 사실 통계."""
    buckets: Dict[str, Dict[str, List[float]]] = {}
    for tk in set(fundamentals.keys()):
        smeta = sector_map.get(tk)
        if not smeta:
            continue
        sk = smeta.get("sector_ko") or smeta.get("sector")
        if not sk:
            continue
        b = buckets.setdefault(sk, {m[0]: [] for m in PEER_METRICS})
        for label, src, _suf, _dg in PEER_METRICS:
            fv = _metric_val(tk, src, fundamentals, valuation)
            if fv is not None:
                b[label].append(fv)
    out: Dict[str, Dict[str, Any]] = {}
    for sk, b in buckets.items():
        med: Dict[str, Any] = {}
        ns: Dict[str, int] = {}
        dist: Dict[str, List[float]] = {}  # 백분위 계산용 정렬 분포 (빌드시점 only, JSON 미출력)
        for label, _src, _suf, _dg in PEER_METRICS:
            vals = b[label]
            m = _median(vals)
            if m is not None and len(vals) >= 5:  # N≥5 미만 섹터-지표는 중앙값 무의미
                med[label] = round(m, 2)
                ns[label] = len(vals)
                dist[label] = sorted(vals)
        if med:
            out[sk] = {"median": med, "ns": ns, "dist": dist}
    return out


def _peer(ticker: str, fundamentals: Dict[str, Any], sector_map: Dict[str, Any],
          medians: Dict[str, Dict[str, Any]], valuation: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    smeta = sector_map.get(ticker)
    if not smeta:
        return None
    sk = smeta.get("sector_ko") or smeta.get("sector")
    sm = medians.get(sk)
    if not sk or not sm:
        return None
    rows = []
    n_max = 0
    for label, src, suf, dg in PEER_METRICS:
        med = sm["median"].get(label)
        if med is None:
            continue
        fv = _metric_val(ticker, src, fundamentals, valuation)
        if fv is None:
            continue
        ds = sm.get("dist", {}).get(label)  # 동종 분포 → 백분위 (사실, 좋다·나쁘다 라벨 없음)
        pct = round(100.0 * sum(1 for x in ds if x < fv) / len(ds)) if ds else None
        rows.append({
            "key": label,
            "value": _num(fv, suf, dg),
            "median": _num(med, suf, dg),
            "vs": "above" if fv > med else "below" if fv < med else "equal",
            "pct": pct,
        })
        n_max = max(n_max, sm.get("ns", {}).get(label, 0))
    if not rows:
        return None
    return {
        "sector": sk,
        "industry": smeta.get("industry") or "",
        "n": n_max,
        "rows": rows,
        "note": "같은 섹터 종목 중앙값과 비교 · PER/PBR=KRX 시총÷DART 재무 자체계산 — 자체 등급 아님",
    }


def _ownership_from_official(off: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """공정위 공식 주주현황(ftc_group_equity.lookup_official_shareholders 반환)을 ownership 노출 shape 로.
    전 종목 확장(2026-06-21) — rec-embedded group_structure 없는 대규모기업집단 소속 상장사 ~346.
    토스·LLM 못 가진 KR 1차자료(공정위 의결권 지분율) 해자. RULE 7 = 공식 분류 사실만, 자체 점수 0.
    """
    if not isinstance(off, dict):
        return None
    sh = off.get("shareholders") or []
    if not isinstance(sh, list) or not sh:
        return None
    family = 0.0
    rows: List[Dict[str, Any]] = []
    for s in sh:
        try:
            q = float(s.get("qota_rate") or 0)
        except (TypeError, ValueError):
            q = 0.0
        t = str(s.get("type") or "")
        if t in FAMILY_TYPES:
            family += q
        rows.append({"name": str(s.get("name") or t), "type": t, "pct": round(q, 2)})
    rows.sort(key=lambda x: x["pct"], reverse=True)
    out: Dict[str, Any] = {
        "family_pct": round(family, 2),
        "group": str(off.get("group") or ""),
        "shareholders": rows[:8],
        "note": "동일인+친족 = 총수일가 지배지분 · 공정위 분류(의결권 지분율)",
        "source": "공정거래위원회 기업집단포털" + (f" ({off.get('as_of_year')})" if off.get("as_of_year") else ""),
    }
    h = off.get("holding")
    if isinstance(h, dict) and h.get("subsidiaries"):
        out["sub_count"] = len(h["subsidiaries"])
    return out


def _load_panel_facts() -> Dict[str, Dict[str, Any]]:
    """분기 재무 패널 → 발행 품질 통과 티커의 최신 사실 (2026-08-26 유니버스 4번째 소스).

    🚨 왜: 발행 유니버스가 fundamentals ∪ rich ∪ fin_series 라, **분기 패널(2,751종)에
    재무가 멀쩡히 있어도** 세 소스에 못 들면 종목이 통째로 빠졌다 — 실측 726종목
    (시총≥50억), 그중 한국금융지주(10.7조)·한화(6.3조) 포함. 8/8 동우팜(fin_series
    소스 누락)과 같은 클래스의 소스 하나 더.

    품질 게이트(발행 최소선): 최근 분기 ≤390일 + 4분기 이상 이력.
    구조 필터 = hard_floor R4~R6 정합(우선주·외국주권·스팩) — 발행도 보통주만.
    값 = DART 공시 실값의 합산(TTM)·최신 분기 스톡 — 자체 산식·점수 없음(RULE 7).
    """
    from datetime import date, timedelta
    path = os.path.join(_ROOT, "data", "metadata", "kr_fundamental_panel.jsonl")
    if not os.path.exists(path):
        return {}
    cutoff = (date.today() - timedelta(days=390)).isoformat()
    rows_by: Dict[str, List[Dict[str, Any]]] = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                r = json.loads(line)
                rows_by.setdefault(str(r.get("ticker") or ""), []).append(r)
    except (OSError, ValueError):
        return {}
    try:
        from api.analyzers.hard_floor import is_spac as _is_spac
    except ImportError:
        _is_spac = lambda _n: False  # noqa: E731 — 폴백: 스팩 필터만 생략
    _names_doc = _load_json(os.path.join(_ROOT, "data", "kr_stock_names.json"), {})
    _panel_names = (_names_doc.get("by_ticker") or _names_doc.get("names") or _names_doc
                    if isinstance(_names_doc, dict) else {}) or {}
    if _panel_names and not isinstance(next(iter(_panel_names.values()), ""), str):
        _panel_names = {k: (v.get("name") if isinstance(v, dict) else str(v)) for k, v in _panel_names.items()}
    out: Dict[str, Dict[str, Any]] = {}
    for tk, rows in rows_by.items():
        if len(tk) != 6 or tk[-1] != "0" or tk[0] == "9":   # R4 우선주 · R5 외국주권
            continue
        rows.sort(key=lambda r: str(r.get("quarter_end") or ""))
        last = rows[-1]
        qe = str(last.get("quarter_end") or "")
        if len(rows) < 4 or qe < cutoff:
            continue
        nm = _panel_names.get(tk) or ""
        if _is_spac(str(nm)):                                # R6 스팩
            continue
        out[tk] = {
            "quarter_end": qe,
            "n_quarters": len(rows),
            "net_income_ttm": last.get("net_income_ttm"),
            "equity": last.get("equity"),
            "roa_ttm": last.get("roa_ttm"),
            "debt_ratio": last.get("debt_ratio"),
        }
    return out


def _load_fin_series() -> Dict[str, List[Dict[str, Any]]]:
    """DART KR backfill → ticker별 연도 재무 시계열 (매출/영업이익/순익).

    소스 = data/dart_kr_backfill_result.json (DART 원본 연간 실값, fiscal_year 2015~).
    period == "annual" 만(분기 q1/h1/q3 혼재 제외). 자체 산식·점수 없음 = 공시 사실(RULE 7 allowlist).
    커버리지는 backfill 적재분만(현재 일부 종목) — 없는 종목은 빈 dict.
    """
    doc = _load_json(DART_KR_BACKFILL_PATH, {})
    rows = list((doc.get("rows") if isinstance(doc, dict) else None) or [])
    hist = _load_json(DART_KR_FIN_HISTORY_PATH, {})  # 광범위 백필 merge (universe 확대)
    rows += (hist.get("rows") if isinstance(hist, dict) else None) or []
    by_ticker: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        if not isinstance(r, dict) or r.get("period") != "annual":
            continue
        tk = str(r.get("ticker") or "")
        fy = r.get("fiscal_year")
        f = r.get("fundamentals") or {}
        if not tk or fy is None:
            continue
        rev, op, net = f.get("revenue"), f.get("operating_profit"), f.get("net_income")
        if rev is None and op is None and net is None:
            continue
        by_ticker.setdefault(tk, []).append({
            "year": int(fy),
            "revenue": rev,
            "op": op,
            "net": net,
        })
    # 연도 오름차순 정렬 + 종목당 최근 ~12년 cap (JSON size 정합)
    out: Dict[str, List[Dict[str, Any]]] = {}
    for tk, pts in by_ticker.items():
        pts.sort(key=lambda p: p["year"])
        # 중복 연도 dedup (마지막 우선)
        seen: Dict[int, Dict[str, Any]] = {}
        for p in pts:
            seen[p["year"]] = p
        ordered = [seen[y] for y in sorted(seen.keys())][-12:]
        if len(ordered) >= 2:
            out[tk] = ordered
    return out


def _load_real_estate_history() -> Dict[str, Dict[str, Any]]:
    """fin_history 최신연도 투자부동산 장부가 → {ticker: real_estate} (부동산 섹션 부활, 백필 공유)."""
    hist = _load_json(DART_KR_FIN_HISTORY_PATH, {})
    rows = (hist.get("rows") if isinstance(hist, dict) else None) or []
    latest: Dict[str, Tuple[int, float]] = {}
    for r in rows:
        if not isinstance(r, dict) or r.get("period") != "annual":
            continue
        tk = str(r.get("ticker") or "")
        fy = r.get("fiscal_year")
        inv = (r.get("fundamentals") or {}).get("investment_property")
        try:
            inv = float(inv) if inv else 0.0
        except (TypeError, ValueError):
            inv = 0.0
        if not tk or fy is None or inv <= 0:
            continue
        if tk not in latest or fy > latest[tk][0]:
            latest[tk] = (int(fy), inv)
    out: Dict[str, Dict[str, Any]] = {}
    for tk, (fy, inv) in latest.items():
        out[tk] = {"total": _fmt_cap(inv),
                   "items": [{"name": "투자부동산", "value": _fmt_cap(inv)}],
                   "note": f"재무상태표 투자부동산 장부가({fy}, 시가 아님) · DART"}
    return out


def main() -> int:
    ok = False
    try:
        recs = _load_json(REC_PATH, [])
        if not isinstance(recs, list):
            recs = []
        fund_doc = _load_json(FUND_PATH, {})
        fundamentals = (fund_doc.get("fundamentals") if isinstance(fund_doc, dict) else {}) or {}
        fin_series = _load_fin_series()
        panel_facts = _load_panel_facts()
        print(f"  [패널 소스] 발행 품질 통과 {len(panel_facts)}종")
        _dart_holders = (_load_json(KR_OWNERSHIP_PATH, {}) or {}).get("holders") or {}
        real_estate_map = _load_real_estate_history()
        # 유형자산 주석 LLM 토지·건물 장부가 map — recommendations facilities_parser(고빈도) 유래.
        # 본문 재무제표엔 유형자산 총계만 → 토지 세부는 주석에만 → NAV 프록시 정밀화 입력.
        land_map: Dict[str, Tuple[int, int]] = {}
        for _rec in (recs if isinstance(recs, list) else []):
            if not isinstance(_rec, dict):
                continue
            _tk = str(_rec.get("ticker") or _rec.get("code") or "")
            _ta = ((_rec.get("facilities_dart") or {}).get("data") or {}).get("tangible_assets") or {}
            try:
                _lk = int(float(_ta.get("land_book_value_krw") or 0))
                _bk = int(float(_ta.get("buildings_book_value_krw") or 0))
            except (TypeError, ValueError):
                _lk = _bk = 0
            if _tk and (_lk > 0 or _bk > 0):
                land_map[_tk] = (_lk, _bk)
        kr_listed = _load_json(KRLISTED_PATH, {}) or {}
        names = _load_json(NAMES_PATH, {}) or {}
        catalyst = _load_catalyst_by_ticker()

        # 컨센서스 map (증권사 집계 — 자체 의견 아님)
        consensus_map: Dict[str, Dict[str, Any]] = {}
        cdoc = _load_json(CONSENSUS_PATH, {})
        cstocks = (cdoc.get("stocks") if isinstance(cdoc, dict) else cdoc) or []
        for c in (cstocks if isinstance(cstocks, list) else []):
            tk = str(c.get("ticker") or "")
            if not tk:
                continue
            entry: Dict[str, Any] = {}
            tp = _fmt_won(c.get("target_price"))
            if tp:
                entry["target_price"] = tp
            if c.get("investment_opinion"):
                entry["opinion"] = str(c["investment_opinion"])
            if entry:
                consensus_map[tk] = entry

        # 운영풀 rich (recommendations)
        rich_by_ticker: Dict[str, Dict[str, Any]] = {}
        for r in recs:
            if _is_kr(r) and r.get("ticker"):
                t = str(r["ticker"])
                rich_by_ticker[t] = build_rich(r, catalyst)

        def _name_market(tk: str):
            li = kr_listed.get(tk) if isinstance(kr_listed, dict) else None
            if isinstance(li, dict):
                return li.get("name") or names.get(tk) or tk, MARKET_MAP.get(li.get("market"), li.get("market") or "")
            return (names.get(tk) or tk), ""

        # universe = fundamentals ∪ 운영풀 ∪ **연간재무 백필 보유분**
        # 🚨 2026-08-08 (PM "동우팜투테이블 정보량이 적어보여") — 유니버스가 fundamentals
        #   키에만 묶여 있어, 시총·연간재무가 멀쩡히 있는데도 fundamentals 에 없으면 종목이
        #   리포트에서 통째로 빠졌다. 088910 실측: 시총 552억·연간재무 11개년 보유,
        #   fundamentals 누락 → 공개 리포트 부재(검색에는 노출되어 "정보량 0" 으로 보임).
        #   fin_series 는 이미 1013행에서 종목에 부착되는데 유니버스에만 못 들어가던 상태.
        #   DART 공시 실값이라 RULE 7 allowlist 정합(자체 산식·점수 없음).
        # 🚨 2026-08-09 중·소형주 채움 — light 경로에 붙일 사실 4종.
        #   전부 로컬 발행물이고 부재 시 graceful({}) — 한 파일이 없어도 리포트는 그대로 난다.
        _lynch_map = (_load_json(LYNCH_PATH, {})
                      or {}).get("by_ticker") or {}
        _owner_map = (_load_json(OWNER_DART_PATH, {})
                      or {}).get("by_ticker") or {}
        _overhang_map = (_load_json(CBBW_PATH, {})
                         or {}).get("by_ticker") or {}
        _chain_map = (_load_json(CHAIN_PATH, {})
                      or {}).get("by_ticker") or {}
        print(f"  [light 보강] lynch {len(_lynch_map)} · 최대주주 {len(_owner_map)} · "
              f"CB/BW {len(_overhang_map)} · 공급망 {len(_chain_map)}")

        universe = (set(fundamentals.keys()) | set(rich_by_ticker.keys())
                    | set(fin_series.keys()) | set(panel_facts.keys()))
        stocks: List[Dict[str, Any]] = []
        for tk in universe:
            if tk in rich_by_ticker:
                stocks.append(rich_by_ticker[tk])
            else:
                fund = fundamentals.get(tk) or {}
                nm, mk = _name_market(tk)
                light = build_light(tk, fund, nm, mk, catalyst, consensus_map,
                                    lynch_map=_lynch_map, owner_map=_owner_map,
                                    overhang_map=_overhang_map, chain_map=_chain_map)
                # 컨센서스 보강만 있고 facts 전무면 노출 가치 낮음 — 실체가 있을 때만.
                # 연간재무 시계열(fin_series)도 실체로 인정한다 — DART 공시 실값이고
                # 1013행에서 종목에 부착되어 추이 그래프로 렌더된다. 이걸 제외하면
                # fundamentals 결측 종목이 "검색은 되는데 리포트는 빈" 상태가 된다.
                if light["facts"] or light["disclosures"] or fin_series.get(tk) or panel_facts.get(tk):
                    stocks.append(light)

        # PER/PBR 자체계산 (KRX 공식 시총 ÷ DART) + 동종업계 비교 준비
        krx_doc = _load_json(KRXMKTCAP_PATH, {})
        krx_map = (krx_doc.get("map") if isinstance(krx_doc, dict) else {}) or {}
        valuation = _valuation_map(fundamentals, krx_map, fin_series, panel_facts) if krx_map else {}
        sector_doc = _load_json(SECTOR_MAP_PATH, {})
        sector_map = (sector_doc.get("map") if isinstance(sector_doc, dict) else {}) or {}
        sector_medians = _sector_medians(fundamentals, sector_map, valuation) if sector_map else {}
        # KR↔US 교차피어 (Tier B B-5) — GICS 공통축 헬퍼 (로컬 import, 파일 관례 정합)
        from api.builders.cross_sector_peer import (
            GICS_KO as _GICS_KO,
            compute_gics_medians as _xpeer_medians,
            kr_ksic_gics as _kr_ksic_gics,
            normalize_gics as _norm_gics,
            write_medians as _xpeer_write,
        )

        # 공정위 공식 지분/지배구조 (전 종목 — ftc_group_equity 조인, corp_idno 캐시 적재됨 → 네트워크 0/캐시 hit)
        try:
            from api.collectors.ftc_group_equity import lookup_official_shareholders as _ftc_lookup
            from api.collectors.dart_corp_code import get_corp_code as _get_cc
        except Exception:  # noqa: BLE001
            _ftc_lookup = None
            _get_cc = None

        # 어닝 캘린더 — DART 제출 패턴 자체계산 (kr_earnings_pattern.json, 어닝 캘린더 스프린트 2026-07-04).
        # 잠정실적(자율, 대형주) 이력 ≥3 = 정밀 신호 우선 / 아니면 정기보고서 리듬. 파일 부재 = 기존 calendar 유지.
        earn_pats = (_load_json(os.path.join(_ROOT, "data", "kr_earnings_pattern.json"), {}) or {}).get("patterns") or {}

        def _kr_earnings_window(rows):
            from datetime import date as _date, timedelta as _td
            prov = [r for r in (rows or []) if r.get("form") == "잠정실적"]
            use = prov if len(prov) >= 3 else (rows or [])
            try:
                dates = sorted({_date.fromisoformat(str(r.get("filed"))) for r in use if r.get("filed")})
            except (ValueError, TypeError):
                return None
            if len(dates) < 3:
                return None
            gaps = sorted(g for g in ((b - a).days for a, b in zip(dates, dates[1:])) if 20 <= g <= 130)
            if not gaps:
                return None
            med = gaps[len(gaps) // 2]
            est = dates[-1] + _td(days=med)
            today = _date.today()
            for _ in range(2):
                if est >= today - _td(days=7):
                    break
                est += _td(days=med)
            basis = "잠정실적 공시 패턴" if use is prov else "정기보고서 제출 패턴"
            return {"event": "다음 실적 공시 예상 창 (±7일)", "kind": "실적", "date": est.isoformat(),
                    "basis": f"과거 {basis} · 자체계산 (확정 공시 시 갱신)"}

        n_cal = 0
        # 재무요약 + PER/PBR 자체계산 보강 + 동종업계 비교 부착
        for s in stocks:
            tk = s["ticker"]
            _normalize_kr_identity(s, tk, _name_market)
            _normalize_dart_facts(s, fundamentals.get(tk))
            # 중앙 Lynch 산출물만 최종 발행한다. recommendations 내장 분류는 입력 시점과
            # 성장률 정의가 달라 같은 종목이 rich/light 경로에서 다르게 보일 수 있다.
            s["verity_lens"] = _verity_lens_from_lynch(_lynch_map.get(tk))
            # 공개 시장 규모의 단일 진실 소스. rich 경로의 유통 기준 추정값도 여기서 교체한다.
            _apply_krx_market_facts(s, krx_map.get(tk))
            fin = _financials(fundamentals.get(tk))
            if fin:
                s["financials"] = fin
            fs = fin_series.get(tk)
            if fs:
                s["fin_series"] = fs  # 연도별 매출/영업이익/순익 시계열(DART 공시 실값, 추이 그래프용)
            if not s.get("calendar"):  # rich 풀(운영풀) 기존 calendar 존중 — 빈 종목만 패턴 창
                w = _kr_earnings_window(earn_pats.get(tk))
                if w:
                    s["calendar"] = [w]
                    n_cal += 1
            val = valuation.get(tk)
            if val:
                fn = s.setdefault("facts_note", {})
                fc = s.setdefault("facts_calc", {})
                if val.get("PER") is not None:
                    s["facts"]["PER"] = _num(val["PER"], "", 1)
                    fn["PER"] = "자체계산"
                    pin = val.get("_per_in") or {}
                    if pin:
                        fc["PER"] = f"시가총액 {_fmt_won_signed(pin.get('mktcap'))} ÷ 순이익 {_fmt_won_signed(pin.get('net_income'))}"
                if val.get("PBR") is not None:
                    s["facts"]["PBR"] = _num(val["PBR"], "", 1)
                    fn["PBR"] = "자체계산"
                    qin = val.get("_pbr_in") or {}
                    if qin:
                        fc["PBR"] = f"시가총액 {_fmt_won_signed(qin.get('mktcap'))} ÷ 자기자본 {_fmt_won_signed(qin.get('equity'))}"
                if val.get("PSR") is not None:
                    s["facts"]["PSR"] = f"{float(val['PSR']):,.2f}배"
                    fn["PSR"] = "자체계산"
                    sin = val.get("_psr_in") or {}
                    if sin:
                        fc["PSR"] = (f"시가총액 {_fmt_won_signed(sin.get('mktcap'))} "
                                     f"÷ 매출 {_fmt_won_signed(sin.get('revenue'))}")
                if val.get("BPS") is not None:
                    # 🚨 2026-08-23 — 종전 `and tk in rich_by_ticker` 제한을 **풀었다**.
                    #   근거: BPS 는 이미 공개 중인 필드이고(운영풀 18종목), 값은
                    #   `_valuation_map` 이 **전 종목에 대해 이미 계산**하고 있었다.
                    #   즉 결손은 새 정보 공개가 아니라 **부착 범위**였다(18 → 1,435).
                    #   산식·입력·sanity 가드 전부 무변경. 되돌리려면 이 조건만 복원하면 된다.
                    #   RULE 7 = 자기 산식·점수 비노출인데 BPS 는 DART 공시값 나눗셈이라 해당 없음.
                    s["facts"]["BPS"] = f"{float(val['BPS']):,.0f}원"
                    fn["BPS"] = "자체계산"
                    bin_ = val.get("_bps_in") or {}
                    if bin_:
                        fc["BPS"] = (f"자기자본 {_fmt_won_signed(bin_.get('equity'))} "
                                     f"÷ 발행주식수 {int(bin_.get('shares') or 0):,}주")
            peer = _peer(tk, fundamentals, sector_map, sector_medians, valuation) if sector_map else None
            if peer:
                s["peer"] = peer
            # 교차피어용 GICS 섹터 태그. 표준 11섹터 실측 우선 → KSIC-* 는 2/3자리 근사 폴백.
            # (2026-07-30) 폴백 이전엔 KSIC 표기 232종목의 gics 가 통째로 비어 섹터 비교·히트맵에서
            # 누락됐다. 근사분은 gics_src="ksic_approx" 로 표기해 실측과 구분한다 (RULE 7).
            _raw_sector = (sector_map.get(tk) or {}).get("sector")
            _g = _norm_gics(_raw_sector)
            _approx = False
            if not _g and _kr_ksic_gics:
                _g = _kr_ksic_gics(_raw_sector)
                _approx = bool(_g)
            if _g:
                s["gics"] = _g
                s["gics_ko"] = _GICS_KO.get(_g, _g)
                if _approx:
                    s["gics_src"] = "ksic_approx"
            # 공정위 공식 지분/지배구조 — rec-embedded 없을 때 ftc 조인 부착(전 종목 ~346 대규모기업집단 소속사)
            if _ftc_lookup and _get_cc and not s.get("ownership"):
                try:
                    cc = _get_cc(tk)
                    off = _ftc_lookup(cc) if cc else None
                    own = _ownership_from_official(off) if off else None
                    if own:
                        s["ownership"] = own
                except Exception:  # noqa: BLE001
                    pass

            # DART 최대주주(hyslrSttus) 폴백 — 공정위는 대규모기업집단 ~346개사가 상한이라
            #   나머지 종목은 지분구조가 통째로 비었다(커버리지 18.8%). DART 사업보고서는
            #   전 상장사가 제출하므로 그쪽으로 메운다(2026-08-08, drip 백필이 적재).
            #   공정위분이 있으면 그대로 둔다 — 지정 자료라 더 정밀하다.
            if not s.get("ownership"):
                _dh = (_dart_holders.get(tk) or {}).get("top")
                if _dh:
                    s["ownership"] = {
                        "holders": [{"name": h["name"], "relate": h.get("relate") or "", "pct": h["pct"]}
                                    for h in _dh],
                        "source": "DART 최대주주 현황(사업보고서)",
                    }

            # 인물 링크 생존성 — 검증된 인물만 link_ok (죽은 링크 0, PM 2026-07-04)
            if s.get("ownership"):
                _annotate_person_links(s["ownership"], str(s.get("name") or ""))

            # 기업개요 보강 — shares는 위 _apply_krx_market_facts가 공식값으로 교체한다.
            # sector는 sector_map fallback. 죽은섹션(overview 1%) 살림(백필 0, 사실만).
            ov = s.get("overview") or {}
            if not ov.get("sector"):
                sk = (sector_map.get(tk) or {}).get("sector_ko")
                if sk:
                    ov["sector"] = str(sk)
            if ov:
                s["overview"] = ov

            # 부동산 부활 — rec 미보유 시 fallback: fin_history → dart_fundamentals 투자부동산 + 유형자산 주석 토지 (사실·장부가)
            _f = fundamentals.get(tk) or {}
            _ll_land, _ll_bld = land_map.get(tk, (0, 0))
            if not s.get("real_estate"):
                re_fb = real_estate_map.get(tk)
                if re_fb:
                    s["real_estate"] = re_fb
                else:
                    try:
                        inv = float(_f.get("investment_property") or 0)
                    except (TypeError, ValueError):
                        inv = 0.0
                    base_re = inv + _ll_land + _ll_bld
                    if base_re > 0:
                        _mk = []
                        if _ll_land > 0:
                            _mk.append({"name": "토지(주석)", "value": _fmt_cap(_ll_land)})
                        if _ll_bld > 0:
                            _mk.append({"name": "건물(주석)", "value": _fmt_cap(_ll_bld)})
                        if inv > 0:
                            _mk.append({"name": "투자부동산", "value": _fmt_cap(inv)})
                        s["real_estate"] = {"total": _fmt_cap(base_re), "items": _mk,
                                            "note": "재무상태표·유형자산 주석 장부가(시가 아님) · DART"}
            elif _ll_land > 0 or _ll_bld > 0:
                # 이미 real_estate 있음(투자부동산 등) — 주석 토지/건물을 item 으로 보강
                _exist = s["real_estate"].setdefault("items", [])
                if isinstance(_exist, list):
                    if _ll_land > 0:
                        _exist.append({"name": "토지(주석)", "value": _fmt_cap(_ll_land)})
                    if _ll_bld > 0:
                        _exist.append({"name": "건물(주석)", "value": _fmt_cap(_ll_bld)})
            # NAV 프록시 — 소유 부동산 장부가(투자부동산 + 주석 토지·건물) ÷ 시총 (장부가·가설, 시가 아님).
            #   토지 취득원가라 실제 시가는 더 높을 수 있음 → 자산주/숨은부동산 스크리닝.
            if s.get("real_estate"):
                try:
                    _mc = float((valuation.get(tk) or {}).get("mktcap") or 0)
                    _api_reb = float(_f.get("real_estate_book") or _f.get("investment_property") or 0)
                    _inv = float(_f.get("investment_property") or 0)
                except (TypeError, ValueError):
                    _mc = _api_reb = _inv = 0.0
                _reb = max(_api_reb, _inv + _ll_land + _ll_bld)  # 주석 토지 반영분과 본문분 중 큰 값(중복 회피)
                if _mc > 0 and _reb > 0:
                    _pct = round(_reb / _mc * 100, 1)
                    _re = s["real_estate"]
                    # 기존 렌더러(realEstate.items → kvRow)가 그대로 표시 → Framer 변경 없이 사이트 노출.
                    _items = _re.get("items")
                    if not isinstance(_items, list):
                        _items = []
                        _re["items"] = _items
                    _items.append({"name": "부동산 장부가 ÷ 시총", "value": f"{_pct}%"})
                    # 구조화 소비용(향후 전용 렌더/스크리닝)
                    _re["nav_proxy"] = {"re_book": _fmt_cap(_reb), "mktcap_pct": _pct,
                                        "land_from_note": bool(_ll_land)}
                    _re["note"] = ("장부가 ÷ 시총 (가설 · 시가 아님 · 토지 취득원가라 실제 시가는 "
                                   "더 높을 수 있음) · DART")

        # 배당 이력 부착 (2026-08-23) — 한국예탁결제원 배당기준일 원장.
        #   PM 결정 = 단독 배당 페이지·스크리너는 취소(8/09, 토스 후발 열위)이나
        #   **리포트 안의 한 파트**는 별개다. 여기서만 붙인다.
        try:
            from api.collectors.dividend_ksd import load_dividends_ledger_for_report
            _div_map = load_dividends_ledger_for_report()
            _n_div = 0
            _n_dps = 0
            for s in stocks:
                sec = _div_map.get(s["ticker"])
                if sec:
                    s["dividends"] = sec
                    _n_div += 1
                    # 주당배당금(TTM) 을 facts 에도 올린다 — 🚨 신규 공개가 아니다.
                    #   같은 값이 이 payload 의 `dividends.ttm_dps` 로 이미 나가고 있고,
                    #   여기서는 요약 카드가 읽는 자리에 같은 사실을 복제할 뿐이다.
                    #   🚨 배당수익률(=DPS÷주가)은 **여기서 계산하지 않는다** — 이 리포트는
                    #   가격을 싣지 않는다(클라이언트 라이브 조회). 시총÷주식수로 주가를
                    #   역산해 붙이면 회전 수집 시점의 값이 '현재 수익률' 로 둔갑한다
                    #   ([[feedback_snapshot_cannot_answer_point_in_time]]).
                    _dps = sec.get("ttm_dps")
                    if _dps:
                        s.setdefault("facts", {})["주당배당금(1년)"] = f"{float(_dps):,.0f}원"
                        s.setdefault("facts_note", {})["주당배당금(1년)"] = "한국예탁결제원"
                        _n_dps += 1
            print(f"[stock_report_public] 배당 이력 부착 {_n_div}/{len(stocks)} 종목 "
                  f"(KSD · 주당배당금 fact {_n_dps})", file=sys.stderr)
        except Exception as _de:  # noqa: BLE001
            # 🚨 배당 결손이 리포트 전체를 막지 않는다. 다만 조용히 넘기지 않고 신고한다.
            _n_div = 0
            print(f"[stock_report_public] 배당 부착 실패(리포트는 계속): {_de}", file=sys.stderr)

        # 사업의 개요 부착 (2026-08-23) — DART 사업보고서 원문 발췌.
        #   🚨 요약이 아니라 **원문 발췌**다. LLM 0 (RULE 6 — 신규 narrative 컴포넌트 아님).
        #   종전 `business` 는 운영풀 태그라인이라 16/1,790(0.9%)뿐이었다.
        try:
            from api.analyzers.dart_business_overview import _cut_at_sentence as _cut_sent
            with open(BIZ_OVERVIEW_PATH, encoding="utf-8") as _bf:
                _bo = json.load(_bf)
            _bo_rows = _bo.get("rows") or {}
            _bo_out: Dict[str, Any] = {}
            _n_bo = _n_bo_trunc = 0
            for s in stocks:
                row = _bo_rows.get(s["ticker"])
                if not row or not row.get("text"):
                    continue
                _txt, _cut = _cut_sent(row["text"], BIZ_OVERVIEW_PUBLISH_CHARS)
                _bo_out[s["ticker"]] = {
                    "name": s.get("name"),
                    "text": _txt,
                    "chars": len(_txt),
                    # 원장에서 이미 잘렸거나(2,500자) 발행 상한에서 또 잘렸으면 True
                    "truncated": bool(row.get("truncated")) or _cut,
                    "fiscal_year": row.get("bsns_year"),
                    "filed_at": row.get("rcept_dt"),
                    "report": row.get("report_nm"),
                    "source": "DART 사업보고서 II. 사업의 내용 › 1. 사업의 개요",
                    "url": (DART + str(row.get("rcept_no"))) if row.get("rcept_no") else None,
                }
                _n_bo += 1
                _n_bo_trunc += 1 if _bo_out[s["ticker"]]["truncated"] else 0
            # 🚨 메인 리포트에 싣지 않는다 — 별 blob 으로 나간다(전송량 축, 위 상수 주석 참조).
            _bo_payload = {
                "_meta": {
                    "generated_at": _now_kst().isoformat(),
                    "source": "DART 사업보고서 II. 사업의 내용 › 1. 사업의 개요 (원문 발췌 · LLM 0)",
                    "count": len(_bo_out),
                    "universe": len(stocks),
                    "publish_chars": BIZ_OVERVIEW_PUBLISH_CHARS,
                    "truncated_n": _n_bo_trunc,
                    "note": ("공개 사실만 (RULE 7) — 원문 발췌이고 요약·해석이 아니다. "
                             "메인 리포트에서 분리 발행(2026-08-25, 전송량 과금)."),
                },
                "rows": _bo_out,
            }
            with open(BIZ_OVERVIEW_PUBLIC_PATH, "w", encoding="utf-8") as _bwf:
                json.dump(_bo_payload, _bwf, ensure_ascii=False)
            print(f"[stock_report_public] 사업의 개요 **별 파일** {_n_bo}/{len(stocks)} 종목 "
                  f"(원장 {len(_bo_rows)} · 절단 {_n_bo_trunc}) -> "
                  f"{os.path.relpath(BIZ_OVERVIEW_PUBLIC_PATH, _ROOT)} "
                  f"({os.path.getsize(BIZ_OVERVIEW_PUBLIC_PATH)/1e6:.2f}MB)", file=sys.stderr)
        except FileNotFoundError:
            _n_bo = 0
            print("[stock_report_public] 사업의 개요 원장 없음 — 부착 0 (리포트는 계속)",
                  file=sys.stderr)
        except Exception as _boe:  # noqa: BLE001
            _n_bo = 0
            print(f"[stock_report_public] 사업의 개요 부착 실패(리포트는 계속): {_boe}",
                  file=sys.stderr)

        # 정렬: rich 먼저 → 공시 많은 순 → ticker
        stocks.sort(key=lambda s: (s.get("rich", False), len(s.get("disclosures", [])), s["ticker"]), reverse=True)
        for s in stocks:
            s.pop("rich", None)

        # KR↔US 교차피어 (Tier B B-5) — 자기 시장(KR) GICS 섹터 중앙값 출력. 프론트가 US 종목 비교용으로 읽음.
        try:
            _xrecs = [{"gics": s["gics"], "metrics": {
                "PER": _metric_val(s["ticker"], "PER", fundamentals, valuation),
                "PBR": _metric_val(s["ticker"], "PBR", fundamentals, valuation),
                "ROE": _metric_val(s["ticker"], "roe", fundamentals, valuation),
                "영업이익률": _metric_val(s["ticker"], "op_margin", fundamentals, valuation),
            }} for s in stocks if s.get("gics")]
            _nsec = _xpeer_write(os.path.join(_ROOT, "data", "cross_gics_kr.json"), "KR",
                                 _xpeer_medians(_xrecs), _now_kst().isoformat())
            print(f"[stock_report_public] 교차피어 KR GICS 중앙값 {_nsec}섹터 -> cross_gics_kr.json", file=sys.stderr)
        except Exception as _xe:  # noqa: BLE001
            print(f"[stock_report_public] 교차피어 KR 중앙값 출력 실패: {_xe}", file=sys.stderr)

        out = {
            "_meta": {
                "generated_at": _now_kst().isoformat(),
                # 🚨 한국예탁결제원 = 배당 원장 출처. 라이선스 제2유형(출처표시 + 상업적
                #   이용금지)이라 표기 의무이고, 유료화 시 정보이용계약이 선행돼야 한다.
                "source": ("DART(전자공시·재무) · 공정위 · FnGuide 집계 · KRX · "
                           "한국예탁결제원(배당)"),
                "count": len(stocks),
                "rich_count": len(rich_by_ticker),
                # 🚨 RULE 12 ② — 산출물이 자기 커버리지를 스스로 신고한다.
                #   분모 없이 "붙였다" 고만 쓰면 하류가 표본을 전수로 읽는다(RULE 13).
                # 🚨 개요는 이 파일에 없다 — kr_business_overview_public.json 로 분리(2026-08-25).
                #   숫자만 남겨 하류가 "없다" 와 "다른 파일에 있다" 를 구분하게 한다.
                "business_overview_count": _n_bo,
                "business_overview_file": "kr_business_overview_public.json",
                "dividends_count": _n_div,
                "note": "공개 사실만 (RULE 7 allowlist) — 점수·등급·추천 비노출. 컨센서스=증권사 집계(자체 의견 아님). 가격은 클라이언트 라이브 조회.",
            },
            "stocks": stocks,
        }
        if not stocks and os.path.isfile(OUTPUT_PATH):
            print("[stock_report_public] 0 stocks — 기존 snapshot 보존", file=sys.stderr)
            ok = True
            return 0
        _save_person_link_cache()
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False)
        print(f"[stock_report_public] logged=True · {len(stocks)} 종목 (rich {len(rich_by_ticker)}, "
              f"어닝캘린더 {n_cal}) -> {os.path.relpath(OUTPUT_PATH, _ROOT)}", file=sys.stderr)
        ok = True
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[stock_report_public] FAILED: {e!r}", file=sys.stderr)
        return 1
    finally:
        if not ok:
            print("[stock_report_public] logged=False", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
