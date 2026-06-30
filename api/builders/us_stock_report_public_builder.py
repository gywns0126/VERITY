"""us_stock_report_public_builder — 공개 터미널 미장(US) 종목 리포트 public-safe 빌더.

2026-06-19 국장/미장 분리. data/us_financials/_summary.json (SEC EDGAR XBRL, 15 빅캡) →
public-safe JSON. 스키마 = KR stock_report_public.json 동일 → PublicStockReport 컴포넌트 재사용
(/us/stock 페이지에 stockUrl=이 파일).

🚨 RULE 7 — allowlist. 노출: ROE / D/E / 매출성장 / 마진 / Altman-Z(학술) / PER·PBR(자체계산, KR 정합).
  비노출: fscore_grade / lynch_class (자체 등급). 가격 = 컴포넌트 라이브.
  PER/PBR = 시총(universe 캐시) ÷ SEC 최근 연간 순이익·자기자본 (KR stock_report_public 동일 방식).
순수 변환 — 외부호출 0. publish: data/us_stock_report_public.json (action.yml 등재 필요).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

KST = timezone(timedelta(hours=9))
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SUMMARY_PATH = os.path.join(_ROOT, "data", "us_financials", "_summary.json")
OUTPUT_PATH = os.path.join(_ROOT, "data", "us_stock_report_public.json")
US_CONSENSUS_PATH = os.path.join(_ROOT, "data", "us_analyst_consensus.json")
# yfinance rec_key → 한글 (외부 집계 사실, 자체 의견 아님 — RULE 7 fact_safe)
REC_KEY_KO = {"strong_buy": "적극 매수", "buy": "매수", "hold": "중립", "sell": "매도", "strong_sell": "적극 매도"}


def _now_kst() -> datetime:
    return datetime.now(KST)


def _pct(v: Any, digits: int = 1, signed: bool = False) -> str | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    if x != x:
        return None
    sign = "+" if (signed and x > 0) else ""
    return f"{sign}{x:.{digits}f}%"


def _num(v: Any, digits: int = 2) -> str | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    if x != x:
        return None
    s = f"{x:.{digits}f}".rstrip("0").rstrip(".")
    return s


def _title(name: str) -> str:
    # "MICROSOFT CORPORATION" → "Microsoft Corporation"
    return " ".join(w.capitalize() for w in str(name or "").split())


CACHE_PATH = os.path.join(_ROOT, "data", "cache", "universe_us.json")
SIC_KO_PATH = os.path.join(_ROOT, "data", "us_sic_ko.json")  # SIC 영문업종 → 한글 (정적, 런타임 번역 0)
NAME_KO_PATH = os.path.join(_ROOT, "data", "us_name_ko.json")  # 주요 종목 ticker → 한글명 (병기·한국어 검색)
US_DISCLOSURE_FEED_PATH = os.path.join(_ROOT, "data", "us_disclosure_feed.json")  # SEC 8-K 수시공시(S&P1500) — disclosures 섹션 배선


def _load_us_disclosures() -> Dict[str, List[Dict[str, Any]]]:
    """us_disclosure_feed.json (SEC EDGAR 8-K, S&P1500) → {ticker: disclosures[]}.
    disclosures item shape = KR catalyst 와 동일(date/filer/is_correction/label/source_url/title) → 무변환 주입.
    RULE 7 = 공시 사실·일정만(점수·등급 0). 리포트 disclosures 섹션 부활(0%→~97%)."""
    out: Dict[str, List[Dict[str, Any]]] = {}
    try:
        with open(US_DISCLOSURE_FEED_PATH, encoding="utf-8") as f:
            doc = json.load(f)
        for it in (doc.get("items") or []):
            tk = str(it.get("ticker") or "").upper()
            ds = it.get("disclosures") or []
            if tk and ds:
                out[tk] = ds
    except (OSError, json.JSONDecodeError):
        pass
    return out


def _load_name_ko() -> Dict[str, str]:
    try:
        with open(NAME_KO_PATH, encoding="utf-8") as f:
            d = json.load(f)
        return {str(k).upper(): v for k, v in d.items() if not k.startswith("_")}
    except (OSError, json.JSONDecodeError):
        return {}


# numeric SIC → 한글 fallback (sic_description meta 결손 시 — MSFT/JPM 등 flagship 19종 빈값 방지).
_SIC_CODE_KO = {
    7370: "컴퓨터 서비스", 7371: "SW·데이터 서비스", 7372: "패키지 소프트웨어",
    7373: "컴퓨터 시스템 설계", 7374: "데이터 처리", 7389: "비즈니스 서비스",
    2834: "제약", 2836: "바이오 제품", 2840: "화장품·생활용품", 2844: "화장품·향수",
    3663: "방송·통신 장비", 3576: "컴퓨터 통신장비", 3661: "전화·전신 장비", 3674: "반도체",
    6021: "전국 상업은행", 6022: "주 상업은행", 6020: "상업은행", 6199: "금융 서비스",
    3829: "계측·제어 장치", 3826: "실험·분석 기기", 3827: "광학기기·렌즈",
    7990: "오락·레저", 7900: "오락·엔터", 2911: "석유 정제", 1311: "원유·천연가스",
    6331: "화재·해상·손해보험", 6311: "생명보험", 4911: "전력", 4931: "전력·복합 유틸리티",
    5812: "음식점", 3571: "전자 컴퓨터", 3672: "인쇄회로기판",
}


def _load_sic_ko() -> Dict[str, str]:
    try:
        with open(SIC_KO_PATH, encoding="utf-8") as f:
            d = json.load(f)
        return {k: v for k, v in d.items() if not k.startswith("_")}
    except (OSError, json.JSONDecodeError):
        return {}
# display sanity outlier 임계 — 분모(매출/자본) 과소·XBRL 오추출·기간불일치로 폭발한 값 차단.
# 가짜 숫자 대신 "산정불가" + 사유(정공법). 2026-06-23 정밀검수: net 221640%·Altman 7163 등 70종 노출 발견.
_ROE_MAX = 100.0       # |ROE|>100% = 자사주/자본잠식 자기자본 과소
_MARGIN_MAX = 200.0    # |마진|>200% = 매출 분모 과소(금융 순이자·바이오 미미 매출)
_GROSS_MAX = 100.0     # 매출총이익률>100% = 물리 불가(XBRL 오추출)
_ALTMAN_MAX = 100.0    # |Z|>100 = BS 항목 stale/기간불일치 명백 오추출(REX 7163 등). 무차입 고시총(NVDA 66)은 실제값 유지
_GROWTH_MAX = 500.0    # |매출성장|>500% = 전년 매출 ≈0 분모 효과
_DE_MAX = 50.0         # |D/E|>50 = 자본 과소(ROE 산정불가와 동일 root)


def _guarded(v: Any, bound: float, digits: int = 1, signed: bool = False,
             gross_cap: bool = False) -> tuple:
    """수치 → (표시값, is_na). |v|>bound(또는 gross>100) 면 ('산정불가', True), 정상이면 (_pct, False).

    None/NaN = (None, False) (미수록).
    """
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None, False
    if x != x:
        return None, False
    if abs(x) > bound or (gross_cap and x > _GROSS_MAX):
        return "산정불가", True
    return _pct(x, digits=digits, signed=signed), False


def _load_universe_caps() -> Dict[str, Dict[str, float]]:
    """data/cache/universe_us.json → {ticker: {market_cap, adv}} (header 시총·거래대금)."""
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    out: Dict[str, Dict[str, float]] = {}
    for e in (data if isinstance(data, list) else []):
        tk = str(e.get("ticker") or "").upper()
        if tk:
            out[tk] = {"market_cap": float(e.get("market_cap") or 0),
                       "adv": float(e.get("avg_trading_value_30d") or 0)}
    return out


# 동종업계 비교(peer) 메트릭 — (facts 라벨, 접미사, 소수자릿수). KR PEER_METRICS 의 美 짝.
# 섹터 = business_ko(SIC 한글 업종, sectorOf US 와 동일 grouping). N≥5 섹터-지표만 중앙값.
US_PEER_METRICS = [("PER", "", 1), ("PBR", "", 1), ("ROE", "%", 1), ("D/E", "", 2), ("영업이익률", "%", 1)]


def _median(vals: List[float]) -> Optional[float]:
    vs = sorted(v for v in vals if v is not None)
    n = len(vs)
    if n == 0:
        return None
    mid = n // 2
    return vs[mid] if n % 2 else (vs[mid - 1] + vs[mid]) / 2.0


def _us_sector_medians(stocks: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """섹터(business_ko)별 PER/PBR/ROE/D-E/영업이익률 중앙값 + N + 분포(백분위용). 사실 통계."""
    buckets: Dict[str, Dict[str, List[float]]] = {}
    for s in stocks:
        sec = s.get("_sector")
        pm = s.get("_pm") or {}
        if not sec:
            continue
        b = buckets.setdefault(sec, {m[0]: [] for m in US_PEER_METRICS})
        for label, _suf, _dg in US_PEER_METRICS:
            if label in pm:
                b[label].append(pm[label])
    out: Dict[str, Dict[str, Any]] = {}
    for sec, b in buckets.items():
        med: Dict[str, float] = {}
        ns: Dict[str, int] = {}
        dist: Dict[str, List[float]] = {}
        for label, _suf, _dg in US_PEER_METRICS:
            vals = b[label]
            m = _median(vals)
            if m is not None and len(vals) >= 5:   # N<5 섹터-지표 중앙값 무의미
                med[label] = round(m, 2)
                ns[label] = len(vals)
                dist[label] = sorted(vals)
        if med:
            out[sec] = {"median": med, "ns": ns, "dist": dist}
    return out


def _us_peer(s: Dict[str, Any], medians: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    sec = s.get("_sector")
    pm = s.get("_pm") or {}
    sm = medians.get(sec)
    if not sec or not sm:
        return None
    rows = []
    n_max = 0
    for label, suf, dg in US_PEER_METRICS:
        med = sm["median"].get(label)
        if med is None:
            continue
        fv = pm.get(label)
        if fv is None:
            continue
        ds = sm.get("dist", {}).get(label)
        pct = round(100.0 * sum(1 for x in ds if x < fv) / len(ds)) if ds else None
        rows.append({
            "key": label,
            "value": (_num(fv, dg) or "") + suf,
            "median": (_num(med, dg) or "") + suf,
            "vs": "above" if fv > med else "below" if fv < med else "equal",
            "pct": pct,
        })
        n_max = max(n_max, sm.get("ns", {}).get(label, 0))
    if not rows:
        return None
    return {
        "sector": sec,
        "n": n_max,
        "rows": rows,
        "note": "같은 섹터(SIC 업종) 종목 중앙값과 비교 · PER/PBR=시총÷SEC 재무 자체계산 — 자체 등급 아님",
    }


def _latest_annual(series: Any) -> Optional[float]:
    """series_annual[key] (list of {end,fy,val}) → 가장 최근 end(동률 시 최신 fy)의 val. 없으면 None."""
    if not isinstance(series, list) or not series:
        return None
    best = None
    for e in series:
        if not isinstance(e, dict) or e.get("val") is None:
            continue
        key = (str(e.get("end") or ""), int(e.get("fy") or 0))
        if best is None or key > best[0]:
            best = (key, e.get("val"))
    if best is None:
        return None
    try:
        return float(best[1])
    except (TypeError, ValueError):
        return None


def _load_fin_latest(ticker: str) -> Dict[str, Optional[float]]:
    """per-ticker us_financials/{TK}.json series_annual → 최근 연간 순이익·자기자본 (PER/PBR 자체계산용)."""
    p = os.path.join(_ROOT, "data", "us_financials", f"{ticker}.json")
    try:
        with open(p, "r", encoding="utf-8") as f:
            doc = json.load(f) or {}
    except (OSError, json.JSONDecodeError):
        return {}
    sa = doc.get("series_annual") or {}
    der = doc.get("derived") or {}
    return {"net_income": _latest_annual(sa.get("net_income")),
            "equity": _latest_annual(sa.get("stockholders_equity")),
            "eps_diluted": _latest_annual(sa.get("eps_diluted")),
            "fcf_usd": der.get("fcf_usd")}


def _usd_compact(v: Any) -> str | None:
    """USD 큰 수 → $X.XXT / $X.XB / $XXXM (US header)."""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    if x != x or x <= 0:
        return None
    if x >= 1e12:
        return f"${x / 1e12:.2f}T"
    if x >= 1e9:
        return f"${x / 1e9:.1f}B"
    if x >= 1e6:
        return f"${x / 1e6:.0f}M"
    return f"${x:,.0f}"


def _usd_compact_signed(v: Any) -> str | None:
    """FCF 등 음수 가능 USD → 부호 보존 compact ($X.XB / -$X.XB). 0/NaN = None."""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    if x != x or x == 0:
        return None
    s = _usd_compact(abs(x))
    if s is None:
        return None
    return ("-" + s) if x < 0 else s


def _load_us_consensus() -> Dict[str, Dict[str, Any]]:
    """us_analyst_consensus.json(yfinance 외부 집계) → {ticker: 컨센서스 raw}. 자체 의견 아님(RULE 7 fact_safe)."""
    try:
        with open(US_CONSENSUS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
    except (OSError, json.JSONDecodeError):
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for s in (data.get("stocks") or []):
        tk = str(s.get("ticker") or "").upper()
        if tk and s.get("num_analysts"):
            out[tk] = s
    return out


def _us_consensus_block(cons: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """yfinance 컨센서스 raw → public 블록 (목표가 평균·범위 / 투자의견 / 업사이드 / 의견 분포).
    외부 애널리스트 집계 사실만 — 자체 점수·등급 0 (RULE 7)."""
    if not cons or not cons.get("num_analysts"):
        return None

    def _usd2(v: Any) -> Optional[str]:
        try:
            return f"${float(v):,.2f}"
        except (TypeError, ValueError):
            return None

    out = {
        "target_price": _usd2(cons.get("target_mean")),
        "target_high": _usd2(cons.get("target_high")),
        "target_low": _usd2(cons.get("target_low")),
        "opinion": REC_KEY_KO.get(str(cons.get("rec_key") or "")),
        "upside": _pct(cons.get("upside_pct"), signed=True),
        "num_analysts": cons.get("num_analysts"),
        "counts": cons.get("counts") if isinstance(cons.get("counts"), dict) else None,
        "note": "외부 애널리스트 집계(yfinance) · 자체 의견 아님",
    }
    return {k: v for k, v in out.items() if v is not None}


def build_stock(row: Dict[str, Any], meta: Dict[str, Any], caps: Dict[str, Dict[str, float]],
                sic_ko: Optional[Dict[str, str]] = None,
                name_ko: Optional[Dict[str, str]] = None,
                fin: Optional[Dict[str, Optional[float]]] = None,
                consensus_map: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, Any]:
    facts: Dict[str, str] = {}
    fnote: Dict[str, str] = {}
    pm: Dict[str, float] = {}   # peer 중앙값 산정용 numeric (가드 통과분만)

    def _capn(label: str, raw: Any, bound: float):
        try:
            x = float(raw)
        except (TypeError, ValueError):
            return
        if x != x or abs(x) > bound:
            return
        pm[label] = x

    def _put(label: str, raw: Any, bound: float, na_reason: str,
             signed: bool = False, gross_cap: bool = False):
        val, na = _guarded(raw, bound, signed=signed, gross_cap=gross_cap)
        if val is not None:
            facts[label] = val
            if na:
                fnote[label] = na_reason

    # 전 facts outlier 가드 (분모 과소·XBRL 오추출 → 가짜 숫자 대신 산정불가, 정공법).
    _put("ROE", row.get("roe_pct"), _ROE_MAX,
         "자사주 매입·자본잠식으로 자기자본 과소 → ROE 왜곡(산정 제외)")
    _put("매출성장", row.get("revenue_yoy_pct_annual"), _GROWTH_MAX,
         "전년 매출 거의 0 → 성장률 분모 효과(산정 제외)", signed=True)
    _put("매출총이익률", row.get("gross_margin_pct"), 1e9,
         "매출총이익률>100% 물리 불가 → XBRL 추출 오류(산정 제외)", gross_cap=True)
    _put("영업이익률", row.get("operating_margin_pct"), _MARGIN_MAX,
         "매출 분모 과소·미미로 마진 왜곡(산정 제외)")
    _put("순이익률", row.get("net_margin_pct"), _MARGIN_MAX,
         "매출 분모 과소(금융 순이자수익 등)로 마진 왜곡(산정 제외)")

    # D/E — 자본 과소 시(ROE 산정불가와 동일 root) 가드, 그 외 그대로.
    de_val, de_na = _guarded(row.get("debt_to_equity"), _DE_MAX)
    de_num = _num(row.get("debt_to_equity"))
    if de_na:
        facts["D/E"] = "산정불가"
        fnote["D/E"] = "자기자본 과소(자사주·자본잠식)로 D/E 왜곡(산정 제외)"
    elif de_num is not None:
        facts["D/E"] = de_num  # 부채/자본 (낮을수록 빚 부담 적음)

    # Altman-Z — |Z|>20 = BS 항목 기간불일치 추출(원천 버그) → 산정불가, 그 외 zone 병기.
    az_v, az_na = _guarded(row.get("altman_z"), _ALTMAN_MAX, digits=1)
    az_num = _num(row.get("altman_z"), 1)
    if az_na:
        facts["Altman-Z"] = "산정불가"
        fnote["Altman-Z"] = "재무항목 기간 불일치 추출로 Z 왜곡(산정 제외)"
    elif az_num is not None:
        facts["Altman-Z"] = az_num
        zone = row.get("altman_zone")
        if zone:
            fnote["Altman-Z"] = "안전구간" if zone == "safe" else str(zone)

    sic_desc = (meta or {}).get("sic_description") or ""
    # 업종 한글화 (정적 SIC 맵, 런타임 번역 0). 미매핑 시 영문 유지. 영문은 business_en 보존.
    sic_ko = sic_ko or {}
    business_ko = sic_ko.get(sic_desc, sic_desc)
    # sic_description 결손(MSFT/JPM 등 flagship) 시 numeric SIC fallback.
    if not business_ko:
        try:
            _sic_n = int(row.get("sic")) if row.get("sic") is not None else None
        except (TypeError, ValueError):
            _sic_n = None
        if _sic_n is not None:
            business_ko = _SIC_CODE_KO.get(_sic_n, "")
    # header — 시총·거래대금 (universe 캐시, USD). 52주 범위는 가격 history 부재로 생략(클라이언트 라이브 가격 보완).
    cap = caps.get((row.get("ticker") or "").upper(), {})
    header: Dict[str, str] = {}
    mc = _usd_compact(cap.get("market_cap"))
    if mc:
        header["market_cap"] = mc
        facts["시가총액"] = mc  # Discovery 표/정렬·리포트 facts 시총 노출(US, KR 정합). header 와 동기.
    # PER/PBR 자체계산 = 시총(universe 캐시) ÷ SEC 최근 연간 순이익·자기자본 (KR 정합, src=자체계산·RULE7 사실).
    mc_raw = cap.get("market_cap")
    fin = fin or {}
    ni, eq = fin.get("net_income"), fin.get("equity")
    try:
        mc_f = float(mc_raw) if mc_raw else None
    except (TypeError, ValueError):
        mc_f = None
    if mc_f and ni and ni > 0:
        per = mc_f / ni
        if 0 < per <= 1000:  # 음수(적자)·극단치(분모 미미) 제외
            facts["PER"] = _num(per, 1)
            fnote["PER"] = "시가총액 ÷ 최근 연간 순이익(자체계산)"
            pm["PER"] = per
    if mc_f and eq and eq > 0:
        pbr = mc_f / eq
        if 0 < pbr <= 100:
            facts["PBR"] = _num(pbr, 1)
            fnote["PBR"] = "시가총액 ÷ 자기자본(자체계산)"
            pm["PBR"] = pbr
    # EPS·FCF — SEC EDGAR 최근 연간 사실 (us_financials series_annual/derived). RULE 7 fact_safe.
    eps_v = fin.get("eps_diluted")
    if eps_v is not None:
        try:
            facts["EPS"] = f"${float(eps_v):,.2f}"
            fnote["EPS"] = "희석 주당순이익(SEC 최근 연간)"
        except (TypeError, ValueError):
            pass
    fcf_fmt = _usd_compact_signed(fin.get("fcf_usd"))
    if fcf_fmt:
        facts["FCF"] = fcf_fmt
        fnote["FCF"] = "잉여현금흐름 = 영업현금흐름 − 자본지출(SEC)"
    # peer 중앙값용 numeric 캡처 (facts 와 동일 가드 — ROE/D-E/영업이익률)
    _capn("ROE", row.get("roe_pct"), _ROE_MAX)
    _capn("D/E", row.get("debt_to_equity"), _DE_MAX)
    _capn("영업이익률", row.get("operating_margin_pct"), _MARGIN_MAX)
    tv = _usd_compact(cap.get("adv"))
    if tv:
        header["trading_value"] = tv + "/일"
    return {
        "ticker": row.get("ticker") or "",
        "name": _title(row.get("entity_name") or row.get("ticker")),
        "market": "US",
        "name_ko": (name_ko or {}).get((row.get("ticker") or "").upper()),  # 주요사 한글명(병기·검색)
        "business": business_ko,
        "business_en": sic_desc if business_ko != sic_desc else None,
        "header": header or None,
        "facts": facts,
        "facts_note": fnote,
        "peer": None,        # main 2-pass 에서 섹터 중앙값 부착
        "disclosures": [],   # 8-K 는 /us/feed (us_disclosure_feed_builder) 담당
        "ownership": None,
        "consensus": _us_consensus_block((consensus_map or {}).get((row.get("ticker") or "").upper())),
        "calendar": [],
        "_pm": pm,           # peer 산정용 temp (main 에서 제거)
        "_sector": business_ko or None,
    }


def main() -> int:
    import argparse
    _p = argparse.ArgumentParser()
    _p.add_argument("--summary", default=SUMMARY_PATH,
                    help="_summary.json 경로 (smallcap 트랙 = data/us_financials/_summary_smallcap.json)")
    _p.add_argument("--output", default=OUTPUT_PATH,
                    help="출력 json (smallcap = data/us_stock_report_us_smallcap.json)")
    _a = _p.parse_args()
    summary_path, output_path = _a.summary, _a.output
    ok = False
    try:
        if not os.path.isfile(summary_path):
            print(f"[us_stock_report] {os.path.basename(summary_path)} 부재 — skip", file=sys.stderr)
            return 0
        with open(summary_path, "r", encoding="utf-8") as f:
            summary = json.load(f)
        rows = summary.get("rows") or []
        # per-ticker 파일에서 meta(sic_description) 보강
        meta_by_ticker: Dict[str, Dict[str, Any]] = {}
        for r in rows:
            tk = r.get("ticker")
            if not tk:
                continue
            p = os.path.join(_ROOT, "data", "us_financials", f"{tk}.json")
            try:
                with open(p, "r", encoding="utf-8") as pf:
                    meta_by_ticker[tk] = (json.load(pf) or {}).get("meta") or {}
            except (OSError, json.JSONDecodeError):
                meta_by_ticker[tk] = {}

        caps = _load_universe_caps()   # header 시총·거래대금 (universe 캐시)
        sic_ko = _load_sic_ko()    # SIC 영문업종 → 한글 (정적 맵)
        name_ko = _load_name_ko()  # 주요사 ticker → 한글명
        us_cons = _load_us_consensus()  # yfinance 애널리스트 컨센서스(외부 집계 사실)
        stocks = [build_stock(r, meta_by_ticker.get(r.get("ticker"), {}), caps, sic_ko, name_ko,
                              _load_fin_latest(r.get("ticker")), us_cons)
                  for r in rows if r.get("ticker")]
        # 동종업계 비교(peer) — 2-pass: 섹터 중앙값 산정 → 종목별 부착. KR stock_report 정합.
        medians = _us_sector_medians(stocks)
        for s in stocks:
            pr = _us_peer(s, medians)
            if pr:
                s["peer"] = pr
            s.pop("_pm", None)
            s.pop("_sector", None)
        # 8-K 수시공시 부착 (us_disclosure_feed, SEC EDGAR) — disclosures 섹션 배선(0%→~97%). KR catalyst 패턴 미러.
        us_disc = _load_us_disclosures()
        if us_disc:
            n_disc = 0
            for s in stocks:
                ds = us_disc.get((s.get("ticker") or "").upper())
                if ds:
                    s["disclosures"] = ds[:8]
                    n_disc += 1
            print(f"[us_stock_report] disclosures 부착 {n_disc}/{len(stocks)} 종목 (us_disclosure_feed)", file=sys.stderr)
        # ROE 큰 순 (사실 정렬)
        def _roe(s):
            v = s.get("facts", {}).get("ROE", "")
            try:
                return float(str(v).rstrip("%").lstrip("+"))
            except ValueError:
                return -999
        stocks.sort(key=_roe, reverse=True)

        out = {
            "_meta": {
                "generated_at": _now_kst().isoformat(),
                "source": "SEC EDGAR XBRL (us_financials)",
                "count": len(stocks),
                "market": "US",
                "note": "공개 사실만 (RULE 7 allowlist) — 점수·등급·추천 비노출. 가격은 클라이언트 라이브. 15 빅캡 시작.",
            },
            "stocks": stocks,
        }
        if not stocks and os.path.isfile(output_path):
            print("[us_stock_report] 0 stocks — 기존 snapshot 보존", file=sys.stderr)
            ok = True
            return 0
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False)
        print(f"[us_stock_report] logged=True · {len(stocks)} 종목 -> {os.path.relpath(output_path, _ROOT)}", file=sys.stderr)
        ok = True
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[us_stock_report] FAILED: {e!r}", file=sys.stderr)
        return 1
    finally:
        if not ok:
            print("[us_stock_report] logged=False", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
