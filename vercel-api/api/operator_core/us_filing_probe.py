"""SEC EDGAR 직조회 — 미장 공시 이력 · 자본구조(완전희석) · 자금조달 경보.

2026-08-12 신설. SWMR(Swarmer) 조회에서 드러난 결손 4종을 한 모듈로 닫는다.

  ① `us_disclosure_feed` 는 **8-K 만** 수집한다. 10-Q/10-K/S-1/424B* 가 조인에 아예
     안 들어와, 재무·희석·락업·유동성 라인이 전부 사각지대였다. SWMR 은 그 전부가
     판단의 핵심이었는데 별도 수작업 직조회로 겨우 확보했다.
  ② 시가총액을 `발행주식(outstanding)` 으로만 계산했다. SWMR 실측 = 발행주식 기준
     $426M vs 완전희석 기준 $863M — **2배 오차**. 마이크로캡에서는 이게 판단을 뒤집는다
     (옵션 9,807,130주 @ 가중평균 행사가 $1.36 = 현재가의 1/29 = 전량 깊은 내가격).
  ③ **락업 만기** 추적 축이 없었다. 신규 상장에서 유통 구조가 바뀌는 단일 최대 사건인데,
     424B4 접수일 + 락업 일수로 기계 산출이 가능하다.
  ④ **ATM·유동성 라인** 탐지가 없었다. `8-K item 1.01` + 근접 `S-1` + 뒤따르는 `424B3`
     는 희석의 조기 경보이고 구조적으로 탐지 가능한 패턴이다.

설계 원칙 — `_dart_recent_filings` (DART 직조회, PM 2026-08-03 상설 배선) 와 동일하다.
발행 파이프라인·유니버스 파일·크론에 의존하지 않는다. **티커만 있으면 그 자리에서 SEC 를
직접 호출**하므로 커버리지 밖 종목도 즉시 답이 나온다([[feedback_join_is_floor_not_ceiling]]).

의존성 0 (urllib 만). `requests` 를 쓰지 않는 이유는 `_us_quote` 와 같다 — Vercel
`operator_core/` 복제본이 이 파일을 그대로 배포한다.

SEC rate limit = 10 req/s. 티커당 호출 = CIK맵(주 1회 캐시) + submissions + companyfacts
+ 경보 확인용 문서 0~2건. RULE 1(KIS) 과 무관 — 토큰 발급 경로가 아니다.
"""
from __future__ import annotations

import html
import json
import os
import re
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

_KST = timezone(timedelta(hours=9))
_TIMEOUT = 20
_CACHE_DIR = os.path.join("/tmp", "verity_sec_probe")

# TTL — 공시 목록은 자주, CIK 맵과 문서 본문은 드물게.
_TTL_SUBMISSIONS = 6 * 3600
_TTL_FACTS = 6 * 3600
_TTL_TICKERMAP = 7 * 86400
_TTL_DOC = 24 * 3600

WINDOW_DAYS = 240          # 공시 이력 창 — 분기보고 2회 + IPO 서류를 포괄
MAX_FILINGS = 24           # 조인 출력 상한 (렌더 절단 방지 — 초과분은 "미표시 N" 신고)
_LOCKUP_DEFAULT_DAYS = 180  # 미기재 시 관행값. 실제 일수는 424B4 본문에서 우선 파싱
_RECENT_IPO_DAYS = 500      # 이 안에 상장한 종목만 락업 경보 대상 (그 밖은 잡음)
_ATM_WINDOW_DAYS = 400      # 이 안에 체결된 자금조달 라인만 경보 (옛 소진분 제외)

# 조인에 싣는 폼 — 8-K 만 보던 결손(①)의 직접 수정.
FORMS_OF_INTEREST = (
    "8-K", "10-Q", "10-K", "10-K/A", "10-Q/A", "20-F", "6-K",
    "S-1", "S-1/A", "S-3", "S-3/A", "S-8",
    "424B1", "424B2", "424B3", "424B4", "424B5",
    "DEF 14A", "DEFA14A",
    "SC 13D", "SC 13D/A", "SC 13G", "SC 13G/A",
)

# 8-K 항목 코드 — 원문 대신 의미를 붙여 준다(코드만으로는 판단이 안 선다).
ITEM_LABELS = {
    "1.01": "중요 계약 체결", "1.02": "중요 계약 종료", "1.03": "파산·법정관리",
    "2.01": "자산 취득·처분", "2.02": "실적 발표", "2.03": "채무 발생",
    "2.04": "기한이익 상실", "2.05": "구조조정 비용", "2.06": "자산 손상",
    "3.01": "상장폐지·규정 미준수", "3.02": "미등록 지분 매각(희석)", "3.03": "주주 권리 변경",
    "4.01": "감사인 변경", "4.02": "과거 재무제표 신뢰 불가",
    "5.01": "지배권 변동", "5.02": "임원·이사 변동", "5.03": "정관 변경",
    "5.07": "주주총회 결과", "7.01": "regulation FD 공시", "8.01": "기타 사건",
    "9.01": "재무제표·첨부",
}

# 자금조달 경보에 쓰는 8-K 항목 — 희석 방향 사건만.
_DILUTIVE_ITEMS = {"1.01", "3.02", "2.03"}


# ── 저수준 ────────────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(_KST)


def _ua() -> str:
    """SEC 는 연락처가 포함된 UA 를 요구한다. 미설정 시에도 동작하도록 기본값을 둔다."""
    return (os.environ.get("SEC_USER_AGENT")
            or os.environ.get("SEC_API_USER_AGENT")
            or "VERITY Research contact@verity.local")


def _cache_path(key: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", key)[:120]
    return os.path.join(_CACHE_DIR, safe)


def _fetch(url: str, cache_key: Optional[str], ttl: int, as_json: bool = True) -> Optional[Any]:
    """URL → JSON 또는 텍스트. 실패는 None(조용히) — 한 축이 죽어도 조인은 산다."""
    if cache_key:
        p = _cache_path(cache_key)
        try:
            if os.path.exists(p) and time.time() - os.path.getmtime(p) < ttl:
                with open(p, encoding="utf-8") as f:
                    return json.load(f) if as_json else f.read()
        except Exception:  # noqa: BLE001
            pass
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": _ua(),
            "Accept-Encoding": "gzip, deflate",
            "Accept": "application/json, text/html;q=0.9",
        })
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
            raw = r.read()
            if (r.headers.get("Content-Encoding") or "") == "gzip":
                import gzip
                raw = gzip.decompress(raw)
        body = raw.decode("utf-8", "replace")
        doc = json.loads(body) if as_json else body
    except Exception:  # noqa: BLE001
        return None
    if cache_key:
        try:
            os.makedirs(_CACHE_DIR, exist_ok=True)
            with open(_cache_path(cache_key), "w", encoding="utf-8") as f:
                if as_json:
                    json.dump(doc, f, ensure_ascii=False)
                else:
                    f.write(doc)
        except Exception:  # noqa: BLE001
            pass
    return doc


def _strip_html(s: str) -> str:
    s = re.sub(r"(?is)<(script|style).*?</\1>", " ", s)
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def _cik(ticker: str) -> Optional[str]:
    """티커 → 10자리 zero-pad CIK. SEC 공식 매핑(주 1회 캐시)."""
    if not ticker:
        return None
    t = str(ticker).strip().upper()
    if re.fullmatch(r"\d{6}", t):
        return None  # KR 6자리 = 이 모듈 대상이 아니다
    doc = _fetch("https://www.sec.gov/files/company_tickers.json",
                 "company_tickers.json", _TTL_TICKERMAP)
    if not isinstance(doc, dict):
        return None
    for v in doc.values():
        if str(v.get("ticker", "")).upper() == t:
            return str(v.get("cik_str", "")).zfill(10)
    return None


def _submissions(cik: str) -> Optional[Dict[str, Any]]:
    return _fetch(f"https://data.sec.gov/submissions/CIK{cik}.json",
                  f"sub_{cik}.json", _TTL_SUBMISSIONS)


def _companyfacts(cik: str) -> Optional[Dict[str, Any]]:
    return _fetch(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json",
                  f"facts_{cik}.json", _TTL_FACTS)


def _doc_url(cik: str, accession: str, doc: str) -> str:
    return (f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
            f"{accession.replace('-', '')}/{doc}")


def _doc_text(cik: str, accession: str, doc: str, limit: int = 1_500_000) -> Optional[str]:
    """공시 원문 텍스트. 대형 투서(50만자+)가 있어 상한을 둔다."""
    if not doc:
        return None
    raw = _fetch(_doc_url(cik, accession, doc), f"doc_{accession}.txt", _TTL_DOC, as_json=False)
    if not isinstance(raw, str):
        return None
    return _strip_html(raw[:limit * 4])[:limit]


# ── 공시 이력 ─────────────────────────────────────────────────────────────

def _rows(subs: Dict[str, Any]) -> List[Dict[str, Any]]:
    r = ((subs or {}).get("filings") or {}).get("recent") or {}
    keys = ("filingDate", "form", "accessionNumber", "primaryDocument", "items", "reportDate")
    cols = {k: r.get(k) or [] for k in keys}
    n = len(cols["form"])
    out = []
    for i in range(n):
        out.append({k: (cols[k][i] if i < len(cols[k]) else "") for k in keys})
    return out


def _item_labels(items: str) -> str:
    codes = [c.strip() for c in str(items or "").split(",") if c.strip()]
    named = [f"{c} {ITEM_LABELS[c]}" for c in codes if c in ITEM_LABELS]
    unknown = [c for c in codes if c not in ITEM_LABELS]
    return " · ".join(named + unknown)


def _filings_block(cik: str, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    cut = (date.today() - timedelta(days=WINDOW_DAYS)).isoformat()
    keep = [r for r in rows if r["form"] in FORMS_OF_INTEREST and r["filingDate"] >= cut]
    keep.sort(key=lambda r: r["filingDate"], reverse=True)
    shown = keep[:MAX_FILINGS]
    out: Dict[str, Any] = {
        "건수": len(keep),
        "창": f"최근 {WINDOW_DAYS}일",
        "확정": ("구간 내 대상 공시 0건 — SEC 직조회 확정 (추정 아님)"
                 if not keep else "SEC EDGAR submissions 직조회"),
    }
    # 🚨 렌더에서 자를 때는 반드시 "미표시 N" 을 신고한다 — 조인 성공을 출력 도달로
    #   착각하면 "배선 0" 보다 발견이 늦다([[feedback_render_stage_silent_field_drop]]).
    if len(keep) > len(shown):
        out["미표시"] = len(keep) - len(shown)
    out["공시"] = [{
        "일자": r["filingDate"], "폼": r["form"],
        **({"항목": _item_labels(r["items"])} if r.get("items") else {}),
        "원문": _doc_url(cik, r["accessionNumber"], r["primaryDocument"]),
    } for r in shown]
    return out


# ── 자본구조 (완전희석) ────────────────────────────────────────────────────

def _latest(facts: Dict[str, Any], ns: str, tag: str, unit: str) -> Optional[Dict[str, Any]]:
    node = ((facts.get("facts") or {}).get(ns) or {}).get(tag)
    if not node:
        return None
    arr = (node.get("units") or {}).get(unit) or []
    arr = [r for r in arr if r.get("end")]
    if not arr:
        return None
    return sorted(arr, key=lambda r: (r["end"], r.get("filed", "")))[-1]


def _val(facts, ns, tag, unit) -> Optional[float]:
    r = _latest(facts, ns, tag, unit)
    return r.get("val") if r else None


# 회계 태그는 회사가 갈아탄다. 옛 태그의 **마지막 값**이 최신으로 둔갑하는 게 이 모듈의
# 가장 위험한 오답이다 — RCAT 실측(2026-08-12): 현금을
# `CashAndCashEquivalentsAtCarryingValue` 로 조회하면 2021-07-31 값이 나오고(그 뒤로는
# `CashCashEquivalentsRestrictedCash...` 를 쓴다), 그 5년 전 잔고로 런웨이를 계산해
# "0.8분기" 라는 **거짓 경보**가 만들어졌다. 초록불 + 그럴듯한 값이라 미탐지된다
# ([[feedback_api_row_limit_truncation_stale_value]]).
_STALE_DAYS = 200  # 최신 보고 기간말 대비 이만큼 뒤처지면 채택하지 않는다

_CASH_TAGS = (
    "CashAndCashEquivalentsAtCarryingValue",
    "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsIncludingDisposalGroupAndDiscontinuedOperations",
)


def _anchor_end(facts: Dict[str, Any]) -> Optional[str]:
    """최신 보고 기간말 — 신선도 판정의 기준점. dei 표지일과 매출·손익 기간말 중 최신."""
    ends = []
    cover = _latest(facts, "dei", "EntityCommonStockSharesOutstanding", "shares")
    if cover and cover.get("end"):
        ends.append(cover["end"])
    for tag in ("NetIncomeLoss", "Assets", "Revenues",
                "RevenueFromContractWithCustomerExcludingAssessedTax"):
        r = _latest(facts, "us-gaap", tag, "USD")
        if r and r.get("end"):
            ends.append(r["end"])
    return max(ends) if ends else None


def _fresh(rec: Optional[Dict[str, Any]], anchor: Optional[str]) -> Optional[Dict[str, Any]]:
    """기준점 대비 신선한 값만 통과. 뒤처지면 None — 조용히 옛 값을 쓰느니 결손이 낫다."""
    if not rec or not rec.get("end"):
        return None
    if not anchor:
        return rec
    try:
        gap = (date.fromisoformat(anchor) - date.fromisoformat(rec["end"])).days
    except ValueError:
        return rec
    return rec if gap <= _STALE_DAYS else None


def _fresh_first(facts, tags, unit, anchor) -> Optional[Dict[str, Any]]:
    """태그 후보를 순회하며 **신선한 첫 값**을 고른다. 태그 교체 회사 대응."""
    best = None
    for t in tags:
        r = _fresh(_latest(facts, "us-gaap", t, unit), anchor)
        if r and (best is None or r["end"] > best["end"]):
            best = r
    return best


def _capital_block(facts: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """완전희석 사다리 — 결손(②)의 직접 수정.

    발행주식만으로 계산한 시총은 마이크로캡에서 체계적으로 과소 계상된다. 옵션·워런트가
    깊은 내가격이면 행사 유인이 최대라 '잠재'가 아니라 '예정' 물량에 가깝다.
    """
    if not facts:
        return None
    out: Dict[str, Any] = {}

    cover = _latest(facts, "dei", "EntityCommonStockSharesOutstanding", "shares")
    outstanding = _val(facts, "us-gaap", "CommonStockSharesOutstanding", "shares")
    issued = _val(facts, "us-gaap", "CommonStockSharesIssued", "shares")
    wavg_d = _val(facts, "us-gaap", "WeightedAverageNumberOfDilutedSharesOutstanding", "shares")
    anti = _val(facts, "us-gaap",
                "AntidilutiveSecuritiesExcludedFromComputationOfEarningsPerShareAmount", "shares")
    opts = _val(facts, "us-gaap",
                "ShareBasedCompensationArrangementByShareBasedPaymentAwardOptionsOutstandingNumber",
                "shares")
    opts_px = _val(facts, "us-gaap",
                   "ShareBasedCompensationArrangementByShareBasedPaymentAward"
                   "OptionsOutstandingWeightedAverageExercisePrice", "USD/shares")
    vest = _val(facts, "us-gaap",
                "ShareBasedCompensationArrangementByShareBasedPaymentAward"
                "OptionsVestedAndExpectedToVestExercisableNumber", "shares")
    warr_px = _val(facts, "us-gaap",
                   "ClassOfWarrantOrRightExercisePriceOfWarrantsOrRights1", "USD/shares")

    if cover:
        out["표지 발행주식"] = f"{int(cover['val']):,}주 (기준 {cover.get('end')})"
    if outstanding:
        out["발행주식 (outstanding)"] = f"{int(outstanding):,}주"
    if issued and outstanding and issued != outstanding:
        out["발행(issued) - 유통 차이"] = f"{int(issued - outstanding):,}주 (미확정 제한주식 등)"
    if wavg_d:
        out["회사 희석주당손실 분모"] = f"{int(wavg_d):,}주"
    if opts:
        s = f"{int(opts):,}주"
        if opts_px:
            s += f" · 가중평균 행사가 ${opts_px:,.4f}".rstrip("0").rstrip(".")
        out["스톡옵션 발행잔량"] = s
    if vest:
        out["  그중 기득·행사가능"] = f"{int(vest):,}주"
    if warr_px:
        out["워런트 행사가"] = f"${warr_px:,.4f}".rstrip("0").rstrip(".")
    if anti:
        out["반희석 제외분 (EPS 미산입)"] = f"{int(anti):,}주"

    # 사다리 — 분모를 하나로 단정하지 않는다. 어느 기준인지 밝히는 게 요점이다.
    base = wavg_d or outstanding or (cover.get("val") if cover else None)
    if base:
        rungs: List[Tuple[str, float]] = [("회사 희석 분모" if wavg_d else "발행주식", float(base))]
        if anti:
            rungs.append(("+ 반희석 제외분", float(base) + float(anti)))
        out["완전희석 사다리"] = [f"{lbl}: {int(n):,}주" for lbl, n in rungs]
        out["_diluted_max"] = int(rungs[-1][1])
        out["_basic"] = int(outstanding or base)
    return out or None


def market_cap_ladder(capital: Dict[str, Any], price: float) -> Optional[List[str]]:
    """가격을 곱해 시총 사다리를 만든다. 가격은 호출자가 실호출로 확보한 값만 넘긴다."""
    if not capital or not price:
        return None
    basic = capital.get("_basic")
    dmax = capital.get("_diluted_max")
    out = []
    if basic:
        out.append(f"발행주식 기준: ${basic * price / 1e6:,.0f}M")
    if dmax and dmax != basic:
        out.append(f"완전희석 기준: ${dmax * price / 1e6:,.0f}M")
    return out or None


# ── 자금조달 경보 ─────────────────────────────────────────────────────────

_GOING_CONCERN_PAT = re.compile(
    r"substantial doubt (?:about|as to|exists)[^.]{0,120}going concern", re.I)
_LOCKUP_DAYS_PAT = re.compile(
    r"(?:period of\s+)?(\d{2,3})\s*days\s+(?:from|after)\s+the date of this prospectus", re.I)
_EQUITY_LINE_PAT = re.compile(
    r"(common stock purchase agreement|committed equity facility|equity line|"
    r"at[- ]the[- ]market offering|purchase agreement with[^.]{0,80}pursuant to which[^.]{0,120}"
    r"(?:sell|issue)[^.]{0,60}shares)", re.I)


def _alerts_block(cik: str, rows: List[Dict[str, Any]],
                  facts: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """락업 만기(③) · ATM/유동성 라인(④) · going concern 을 기계 탐지한다."""
    out: Dict[str, Any] = {}
    today = date.today()

    # ── ③ 신규 상장 + 락업 만기 ──
    ipo = next((r for r in sorted(rows, key=lambda r: r["filingDate"])
                if r["form"] in ("424B4", "424B1")), None)
    if ipo:
        try:
            ipo_d = date.fromisoformat(ipo["filingDate"])
        except ValueError:
            ipo_d = None
        if ipo_d and (today - ipo_d).days <= _RECENT_IPO_DAYS:
            # 오래 상장된 회사의 옛 424B4 로 만든 "락업 만기 2021년" 은 신호가 아니라 잡음이다.
            # 락업이 판단을 바꾸는 구간(상장 ~1년)에서만 낸다.
            days_listed = (today - ipo_d).days
            lock_days = _LOCKUP_DEFAULT_DAYS
            src = "관행값 180일 (본문 미파싱)"
            txt = _doc_text(cik, ipo["accessionNumber"], ipo["primaryDocument"])
            if txt:
                m = _LOCKUP_DAYS_PAT.search(txt)
                if m:
                    lock_days = int(m.group(1))
                    src = "424B4 본문 파싱"
            expiry = ipo_d + timedelta(days=lock_days)
            d_day = (expiry - today).days
            out["상장"] = (f"{ipo['filingDate']} ({ipo['form']}) · 상장 {days_listed}일차"
                          + (" · 상장 1년 미만" if days_listed < 365 else ""))
            out["락업 만기(추정)"] = (
                f"{expiry.isoformat()} · {src} · "
                + (f"D{d_day:+d}일" if d_day else "오늘")
                + (" 🔺 90일 이내" if 0 <= d_day <= 90 else
                   " · 이미 경과" if d_day < 0 else ""))

    # ── ④ ATM·유동성 라인 (희석 조기 경보) ──
    #   구조 = 8-K item 1.01 + 근접 S-1/S-3 + 뒤따르는 424B3. 구조 일치 시에만 본문을 연다
    #   (본문 호출 비용을 아끼면서 오탐을 걸러내는 2단 확인).
    #   창 = 최근 _ATM_WINDOW_DAYS. 4년 전 소진된 라인까지 띄우면 경보가 잡음이 된다
    #   (ONDS 실측 2026-08-12: 2022-03-22 건이 올라왔다).
    atm_cut = (today - timedelta(days=_ATM_WINDOW_DAYS)).isoformat()
    reg = [r for r in rows if r["form"] in ("S-1", "S-3", "424B3", "424B5")]
    for r in rows:
        if r["form"] != "8-K" or r["filingDate"] < atm_cut:
            continue
        codes = {c.strip() for c in str(r.get("items") or "").split(",")}
        if not (codes & _DILUTIVE_ITEMS):
            continue
        try:
            d0 = date.fromisoformat(r["filingDate"])
        except ValueError:
            continue
        near = [x for x in reg
                if 0 <= (date.fromisoformat(x["filingDate"]) - d0).days <= 14]
        if not near:
            continue
        txt = _doc_text(cik, r["accessionNumber"], r["primaryDocument"], limit=200_000)
        if not txt or not _EQUITY_LINE_PAT.search(txt):
            continue
        m = re.search(r"up to (?:the lesser of \(i\)\s*)?([\d,]{7,})\s*shares", txt, re.I)
        detail = f"{r['filingDate']} 8-K item 1.01"
        if m:
            detail += f" · 최대 {m.group(1)}주"
        detail += " · 등록 " + ", ".join(f"{x['form']}({x['filingDate']})" for x in near[:2])
        out.setdefault("자금조달 라인(ATM·유동성 라인)", []).append(detail)

    # ── going concern ──
    latest_fin = next((r for r in sorted(rows, key=lambda r: r["filingDate"], reverse=True)
                       if r["form"] in ("10-K", "10-Q")), None)
    if latest_fin:
        txt = _doc_text(cik, latest_fin["accessionNumber"], latest_fin["primaryDocument"],
                        limit=800_000)
        if txt:
            hit = _GOING_CONCERN_PAT.search(txt)
            out["계속기업 의문(going concern)"] = (
                f"있음 — {latest_fin['form']} ({latest_fin['filingDate']}) 본문 확인"
                if hit else f"미검출 — {latest_fin['form']} ({latest_fin['filingDate']}) 본문 확인")

    # ── 최근 분기 매출·손익 (조인에 10-Q 가 없던 결손 ①의 실질 보완) ──
    if facts:
        anchor = _anchor_end(facts)
        rev = None
        for tag in ("RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues"):
            r = _fresh(_latest(facts, "us-gaap", tag, "USD"), anchor)
            if r and r.get("start"):
                try:
                    dur = (date.fromisoformat(r["end"]) - date.fromisoformat(r["start"])).days
                except ValueError:
                    dur = 0
                if 80 <= dur <= 100:
                    rev = r
                    break
        ni = _fresh(_latest(facts, "us-gaap", "NetIncomeLoss", "USD"), anchor)
        cash = _fresh_first(facts, _CASH_TAGS, "USD", anchor)
        ocf = _fresh(_latest(facts, "us-gaap",
                             "NetCashProvidedByUsedInOperatingActivities", "USD"), anchor)
        fin: Dict[str, Any] = {}
        if rev:
            fin["최근 분기 매출"] = f"${rev['val']:,.0f} ({rev['start']}~{rev['end']})"
        if ni:
            fin["순손익"] = f"${ni['val']:,.0f} (기준 {ni['end']})"
        if cash:
            fin["현금"] = f"${cash['val']:,.0f} (기준 {cash['end']})"
        # 런웨이는 현금과 영업현금흐름이 **같은 기간말**일 때만 낸다. 기간이 어긋난 조합은
        # 숫자가 그럴듯해서 더 위험하다(위 RCAT 사고).
        if (cash and ocf and float(ocf.get("val") or 0) < 0
                and cash["end"] == ocf["end"]):
            try:
                dur = (date.fromisoformat(ocf["end"]) - date.fromisoformat(ocf["start"])).days
            except (ValueError, TypeError):
                dur = 0
            q = abs(float(ocf["val"]))
            if q > 0 and 80 <= dur <= 100:
                fin["런웨이(단순)"] = f"약 {float(cash['val']) / q:.1f}분기 (분기 소진 기준)"
        elif cash and ocf:
            fin["런웨이"] = "미산출 — 현금·영업현금흐름 기간말 불일치 또는 소진 없음"
        if fin:
            out["재무 요약 (XBRL)"] = fin

    return out or None


# ── 공개 진입점 ───────────────────────────────────────────────────────────

def probe(ticker: str) -> Optional[Dict[str, Any]]:
    """티커 → {공시 이력, 자본구조, 경보}. 미국 종목이 아니거나 실패하면 None.

    반환값의 `_capital` 은 시총 사다리 계산용 원시값이며 렌더 대상이 아니다.
    """
    cik = _cik(ticker)
    if not cik:
        return None
    subs = _submissions(cik)
    if not isinstance(subs, dict):
        return None
    rows = _rows(subs)
    if not rows:
        return None
    facts = _companyfacts(cik)

    out: Dict[str, Any] = {"CIK": cik}
    name = subs.get("name")
    if name:
        out["법인명"] = name
    exch = subs.get("exchanges")
    if exch:
        out["거래소"] = ", ".join(exch)
    sic = subs.get("sicDescription")
    if sic:
        out["업종(SIC)"] = sic

    cap = _capital_block(facts) if facts else None
    if cap:
        out["_capital"] = {k: v for k, v in cap.items() if k.startswith("_")}
        out["자본구조"] = {k: v for k, v in cap.items() if not k.startswith("_")}

    al = _alerts_block(cik, rows, facts)
    if al:
        out["경보"] = al

    out.update(_filings_block(cik, rows))
    return out


if __name__ == "__main__":  # 수동 확인용
    import sys
    tk = sys.argv[1] if len(sys.argv) > 1 else "SWMR"
    print(json.dumps(probe(tk), ensure_ascii=False, indent=2))
