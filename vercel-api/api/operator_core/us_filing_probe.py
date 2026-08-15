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
import sys as _sys
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
# 모델 학습 컷오프. 이 뒤에 상장한 회사는 모델 기억에 **아예 없다** — 기억으로 말하면
# 반드시 틀린다(2026-08-15 SPCX: "비상장" 이라고 단정했고 실제는 6/12 나스닥 상장).
# 모델을 갈아탈 때 같이 올릴 것. 보수적으로 두는 편이 안전하다(경보가 좀 더 나올 뿐).
_MODEL_CUTOFF = "2026-05-01"
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
    """공시 원문 텍스트. 대형 투서(50만자+)가 있어 상한을 둔다.

    🚨 **스트립을 먼저, 절단을 나중에** 한다. 이전 구현은 `_strip_html(raw[:limit*4])` 로
    원시 HTML 을 먼저 잘랐는데, "태그가 본문의 4배를 넘지 않는다" 는 가정이 iXBRL 에서
    깨진다. SPCX 424B4 실측(2026-08-15): raw 11,953,976자 → 6,000,000자에서 절단 →
    본문 978,385자만 남아 **락업 조항이 통째로 소실**됐고, 파서가 "본문 미파싱" 으로
    관행값 180일을 썼다. 전량 스트립 시 1,472,657자로 상한 안에 들어온다.
    12MB 스트립 실측 0.09초 — 순서를 뒤집는 비용이 없다.
    태그 비중은 문서마다 다르므로 **절단 여부는 스트립 후에만 판정할 수 있다**
    ([[feedback_api_row_limit_truncation_stale_value]] 계열: 상한이 조용히 값을 바꾼다).
    """
    if not doc:
        return None
    raw = _fetch(_doc_url(cik, accession, doc), f"doc_{accession}.txt", _TTL_DOC, as_json=False)
    if not isinstance(raw, str):
        return None
    txt = _strip_html(raw)
    if len(txt) > limit:
        # 조용히 자르지 않는다 — 무엇을 못 봤는지 로그로 신고한다.
        print(f"[us_filing_probe] 본문 절단: {doc} {len(txt):,}자 → {limit:,}자 "
              f"(뒤쪽 {len(txt) - limit:,}자 미확인)", file=_sys.stderr)
    return txt[:limit]


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


# 10-Q/10-K 표지 발행주식수. XBRL `dei:EntityCommonStockSharesOutstanding` 가 없거나
# 다중 클래스라 무차원 값이 비는 회사가 있어, 표지 원문이 유일하게 확실한 출처다.
# "the registrant had 7,696,293,669 shares of Class A common stock and 5,485,486,276
#  shares of Class B common stock outstanding" → 두 클래스를 합산한다.
_COVER_SHARES_PAT = re.compile(
    r"([\d,]{7,})\s+shares?\s+of\s+(?:the\s+registrant['’]s\s+)?"
    r"(?:its\s+)?(?P<cls>Class\s+[A-Z]\s+)?(?:common\s+stock|common\s+shares)", re.I)
_COVER_ANCHOR_PAT = re.compile(
    r"(?:had|were|there\s+were|outstanding)[^.]{0,600}?outstanding", re.I)


def _cover_shares(cik: str, rows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """최신 10-Q/10-K 표지에서 클래스별 발행주식수를 합산한다.

    2026-08-15 SPCX 실측: companyfacts 에 `dei` 네임스페이스가 통째로 없고
    `CommonStockSharesOutstanding` 도 없어, `_capital_block` 이 **가중평균 희석 EPS
    분모**(58.6억주)로 폴백했다. 실제 발행주식은 131.8억주 — 시총이 $821B 로 나와
    실제 $1.85T 의 **44%** 로 과소 계상됐다. 상장 직후 기업은 가중평균이 상장 전
    기간까지 포함해 구조적으로 작다. 이 폴백은 최근 IPO 종목 전체에 걸린다
    ([[feedback_api_row_limit_truncation_stale_value]] 와 같은 계열 — 그럴듯한 값이라
    미탐지된다).
    """
    latest = next((r for r in sorted(rows, key=lambda r: r["filingDate"], reverse=True)
                   if r["form"] in ("10-Q", "10-K", "10-K/A", "10-Q/A")), None)
    if not latest:
        return None
    # 상한 여유 — SPCX 10-Q 실측에서 표지 문구가 44,123자 지점에 있었다(iXBRL 헤더가
    # 앞을 길게 먹는다). 60K 로 두면 서문이 조금만 길어도 표지를 놓친다.
    txt = _doc_text(cik, latest["accessionNumber"], latest["primaryDocument"], limit=250_000)
    if not txt:
        return None
    anchor = _COVER_ANCHOR_PAT.search(txt)
    if not anchor:
        return None
    seg = txt[max(0, anchor.start() - 400):anchor.end()]
    seen: Dict[str, int] = {}
    for m in _COVER_SHARES_PAT.finditer(seg):
        try:
            n = int(m.group(1).replace(",", ""))
        except ValueError:
            continue
        if n < 1000:            # 액면가·비율 같은 잡음 배제
            continue
        cls = (m.group("cls") or "보통주").strip()
        seen[cls] = max(seen.get(cls, 0), n)   # 같은 클래스 중복 언급은 최대값 1회만
    if not seen:
        return None
    return {"total": sum(seen.values()), "classes": seen,
            "form": latest["form"], "date": latest["filingDate"]}


def _capital_block(facts: Dict[str, Any],
                   cover_doc: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """완전희석 사다리 — 결손(②)의 직접 수정.

    발행주식만으로 계산한 시총은 마이크로캡에서 체계적으로 과소 계상된다. 옵션·워런트가
    깊은 내가격이면 행사 유인이 최대라 '잠재'가 아니라 '예정' 물량에 가깝다.

    🚨 반대 방향 오차도 있다 — 가중평균 희석 분모를 발행주식 대신 쓰면 신규 상장에서
    시총이 절반 이하로 나온다(SPCX 실측). `cover_doc`(표지 원문 파싱)을 최우선으로 둔다.
    """
    if not facts and not cover_doc:
        return None
    facts = facts or {}
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
    if cover_doc:
        cls = cover_doc.get("classes") or {}
        detail = " + ".join(f"{k} {v:,}" for k, v in cls.items()) if len(cls) > 1 else ""
        out["표지 발행주식 (원문)"] = (
            f"{cover_doc['total']:,}주 · {cover_doc['form']} 표지 {cover_doc['date']}"
            + (f" ({detail})" if detail else ""))
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
    #
    # 🚨 우선순위가 이 함수의 전부다. 가중평균(wavg_d)을 앞에 두면 신규 상장에서 시총이
    #    반토막 난다(SPCX 실측: 58.6억 vs 실제 131.8억). 실제 발행주식 → 가중평균 순서다.
    doc_total = float(cover_doc["total"]) if cover_doc else None
    basic = doc_total or (float(cover["val"]) if cover else None) or (
        float(outstanding) if outstanding else None)
    base = basic or (float(wavg_d) if wavg_d else None)
    if base:
        label = ("발행주식(표지 원문)" if doc_total else
                 "발행주식(표지 XBRL)" if cover else
                 "발행주식" if outstanding else "회사 희석 분모")
        rungs: List[Tuple[str, float]] = [(label, float(base))]
        # 가중평균이 실제 발행주식보다 크면(전환 예정분 반영) 그것도 사다리에 올린다.
        if wavg_d and basic and float(wavg_d) > float(basic):
            rungs.append(("회사 희석 분모", float(wavg_d)))
        top = rungs[-1][1]
        if anti:
            rungs.append(("+ 반희석 제외분", top + float(anti)))
        out["완전희석 사다리"] = [f"{lbl}: {int(n):,}주" for lbl, n in rungs]
        out["_diluted_max"] = int(rungs[-1][1])
        out["_basic"] = int(base)
        if wavg_d and basic and float(wavg_d) < float(basic) * 0.9:
            out["_note_wavg"] = (
                f"가중평균 희석 분모 {int(wavg_d):,}주는 발행주식 {int(basic):,}주보다 작다 "
                "— 기중 신주발행·상장. 시총은 발행주식 기준을 쓴다")
            out["가중평균 주의"] = out["_note_wavg"]
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
# 🚨 위 패턴은 락업 조항만 무는 게 아니다. 424B4 에는 같은 어구가 **인수인 초과배정
#    옵션(그린슈)** 에도 쓰인다 — "exercisable for 30 days after the date of this
#    prospectus". SPCX 실측(2026-08-15): `.search()` 가 문서 첫 매치인 그린슈 30일을
#    물어 락업 만기를 2026-07-12 로 냈고 "이미 경과" 라 표시됐다. 실제 락업은 180일
#    기본 + 366일 연장(머스크 64억주)이고, 그 사이에 단계적 해제가 9회 있다.
#    "이미 경과" 는 리스크 없음으로 읽히므로 방향까지 반대인 오답이었다.
#    → 매치마다 **주변 문맥에 락업 어휘가 있는지** 확인하고, 그중 **최댓값**을 만기로 둔다.
_LOCKUP_CTX_PAT = re.compile(
    r"lock-?\s?up|market standoff|may (?:not )?be Transferred|restricted from", re.I)
_LOCKUP_CTX_WINDOW = 700   # 매치 주변 이만큼 안에 락업 어휘가 있어야 채택


def _lockup_days(txt: str) -> Optional[Tuple[int, int, int]]:
    """424B4 본문 → (기본 락업일, 최종 락업일, 단계 해제 후보 수).

    그린슈·딜러 인도의무 같은 무관 조항을 문맥으로 배제한다.
    """
    hits: List[int] = []
    for m in _LOCKUP_DAYS_PAT.finditer(txt):
        s = max(0, m.start() - _LOCKUP_CTX_WINDOW)
        if not _LOCKUP_CTX_PAT.search(txt[s:m.end() + _LOCKUP_CTX_WINDOW]):
            continue
        try:
            hits.append(int(m.group(1)))
        except ValueError:
            continue
    if not hits:
        return None
    # 기본 = 최빈 관행값(180 등) 중 최소, 최종 = 최대(연장 락업)
    return min(hits), max(hits), len(set(hits))
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
            base_days = final_days = _LOCKUP_DEFAULT_DAYS
            stages = 0
            src = "관행값 180일 (본문 미파싱)"
            txt = _doc_text(cik, ipo["accessionNumber"], ipo["primaryDocument"])
            if txt:
                parsed = _lockup_days(txt)
                if parsed:
                    base_days, final_days, stages = parsed
                    src = "424B4 본문 파싱"
            out["상장"] = (f"{ipo['filingDate']} ({ipo['form']}) · 상장 {days_listed}일차"
                          + (" · 상장 1년 미만" if days_listed < 365 else ""))
            # 🚨 학습 컷오프 경보 — 2026-08-15 SPCX 사고의 구조적 차단.
            #    스페이스X 는 2026-06-12 상장인데 나는 "비상장" 이라고 단정해 답을 시작했다.
            #    학습 컷오프(2026-05)가 상장 직전이라 기억에 없었고, **조인을 돌리기도 전에**
            #    말했다. 모델 기억은 이 회사에 대해 틀린 게 아니라 아예 존재하지 않는다.
            #    이건 회사 하나의 문제가 아니라 컷오프 이후 상장 전체에 걸린 계열이므로,
            #    조인이 매번 스스로 신고하게 한다 ([[feedback_knowledge_cutoff_verify_first]]).
            if ipo["filingDate"] >= _MODEL_CUTOFF:
                out["🚨 학습 컷오프 이후 상장"] = (
                    f"{ipo['filingDate']} 상장 = 모델 학습 컷오프({_MODEL_CUTOFF}) 이후. "
                    "이 회사에 대한 모델 기억은 부정확한 게 아니라 **없다**. "
                    "상장 여부·티커·사업 구성·지배구조를 기억으로 말하지 말고 "
                    "전부 이 조인과 원문에서만 읽을 것.")

            def _fmt(d: date) -> str:
                dd = (d - today).days
                return (f"{d.isoformat()} · "
                        + (f"D{dd:+d}일" if dd else "오늘")
                        + (" 🔺 90일 이내" if 0 <= dd <= 90 else
                           " · 이미 경과" if dd < 0 else ""))

            base_exp = ipo_d + timedelta(days=base_days)
            final_exp = ipo_d + timedelta(days=final_days)
            out["락업 만기(추정)"] = f"{_fmt(base_exp)} · 기본 {base_days}일 · {src}"
            if final_days != base_days:
                # 연장 락업이 별도로 있으면 그게 진짜 마지막 물량이다. 기본 만기만 보고
                # "다 풀렸다" 고 읽으면 최대 물량을 놓친다(SPCX = 머스크 64억주 366일).
                out["락업 최종 만기(연장분)"] = (
                    f"{_fmt(final_exp)} · 연장 {final_days}일 · {src}")
            if stages > 2:
                out["락업 단계 해제"] = (
                    f"본문에 서로 다른 기간 {stages}종 — 단계적 해제 구조. "
                    "만기 1개로 수급을 판단하지 말 것 (424B4 'Shares Eligible for Future Sale' 표 확인)")

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

        # 🚨 아래는 전부 "내가 손으로 계산하지 않게" 하려고 넣는다. 2026-08-15 SPCX 실측:
        #    424B4 표지의 공모주식수 × 공모가로 "조달 $75B" 를 만들어 답했는데, 실제
        #    `ProceedsFromIssuanceInitialPublicOffering` = $85,675M 였다(초과배정 전량 행사).
        #    한 번의 호출 거리에 정답이 있었다. 자기 산술은 오답의 상시 경로다
        #    ([[feedback_verify_by_load_bearing_not_surprise]] 규칙 3).
        for label, tag in (
            ("영업손익", "OperatingIncomeLoss"),
            ("매출원가", "CostOfRevenue"),
            ("연구개발비", "ResearchAndDevelopmentExpense"),
            ("판매관리비", "SellingGeneralAndAdministrativeExpense"),
        ):
            r = _fresh(_latest(facts, "us-gaap", tag, "USD"), anchor)
            if r and rev and r.get("start") == rev.get("start") and r.get("end") == rev.get("end"):
                fin[label] = f"${r['val']:,.0f}"
        # 구성요소 합 ↔ 보고 영업손익 대조 — 공짜 자가검증. 어긋나면 태그 누락 신호다.
        op = _fresh(_latest(facts, "us-gaap", "OperatingIncomeLoss", "USD"), anchor)
        if rev and op and all(k in fin for k in ("매출원가", "연구개발비", "판매관리비")):
            parts = sum(float(_latest(facts, "us-gaap", t, "USD")["val"])
                        for t in ("CostOfRevenue", "ResearchAndDevelopmentExpense",
                                  "SellingGeneralAndAdministrativeExpense"))
            resid = float(rev["val"]) - parts - float(op["val"])
            fin["손익 정합"] = (
                f"매출 − (원가+R&D+판관비) − 영업손익 = ${resid:,.0f}"
                + (" ✓ 구성요소로 닫힘" if abs(resid) <= abs(float(rev["val"])) * 0.01
                   else " 🚨 잔차 큼 — 미포착 비용 항목 있음. 손익 해석 시 주의"))

        for label, tag in (
            ("영업현금흐름", "NetCashProvidedByUsedInOperatingActivities"),
            ("설비투자(capex)", "PaymentsToAcquirePropertyPlantAndEquipment"),
            ("IPO 순수취", "ProceedsFromIssuanceInitialPublicOffering"),
        ):
            r = _fresh(_latest(facts, "us-gaap", tag, "USD"), anchor)
            if r:
                per = f" ({r['start']}~{r['end']})" if r.get("start") else f" (기준 {r['end']})"
                fin[label] = f"${r['val']:,.0f}{per}"
        # FCF 는 두 값이 **같은 기간** 일 때만. 기간이 어긋난 뺄셈은 그럴듯해서 더 위험하다.
        _o = _fresh(_latest(facts, "us-gaap",
                            "NetCashProvidedByUsedInOperatingActivities", "USD"), anchor)
        _c = _fresh(_latest(facts, "us-gaap",
                            "PaymentsToAcquirePropertyPlantAndEquipment", "USD"), anchor)
        if _o and _c and _o.get("start") == _c.get("start") and _o.get("end") == _c.get("end"):
            fin["FCF(영업현금흐름 − capex)"] = (
                f"${float(_o['val']) - float(_c['val']):,.0f} ({_o['start']}~{_o['end']})")

        if fin:
            out["재무 요약 (XBRL)"] = fin

        seg = _segment_block(cik, rows)
        if seg:
            out["부문별 (10-Q/10-K 본문)"] = seg

    return out or None


# 부문 표 — "세그먼트 분해 불가" 라는 오답을 구조적으로 막는다.
# 2026-08-15 SPCX 실측: 서브LLM 의 "세그먼트 분해 불가" 를 검증 없이 옮겼는데, 10-Q
# Note 18 에 3부문(Space·Connectivity·AI) 매출·영업손익·capex 가 전부 있었다. 같은 답에서
# 그 LLM 의 다른 오류 4건은 검증했다 — 선택적 검증이 무검증보다 위험하다는 사례다.
# 여기서 **있으면 싣고, 없으면 "본문에 부문 주석 없음(확인함)" 이라고 명시**한다.
# 둘 다 표기해야 "안 찾아본 것" 과 "찾아봤는데 없는 것" 이 구분된다.
_SEG_HEAD_PAT = re.compile(
    r"(?:reportable segments?|operating and reportable segments?|Segment Information|"
    r"Note\s+\d+\s*[-–—]\s*Segments?)", re.I)
_SEG_NAMES_PAT = re.compile(
    r"(?:three|two|four|five)\s+operating and reportable segments?[^.]{0,200}", re.I)


def _segment_block(cik: str, rows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """최신 10-Q/10-K 본문에서 부문 주석을 찾아 원문 발췌로 싣는다.

    XBRL 로 안 가는 이유 = 부문 데이터는 차원(axis/member)으로 태깅돼 companyconcept
    단순 조회로는 안 잡히고, 회사마다 멤버 이름이 달라 일반화가 안 된다. 본문 발췌가
    정확하고 싸다. 파싱해서 표로 만들지 않는 것도 의도적이다 — 우리가 재가공하면 그
    가공이 새 오답 경로가 된다. **원문 그대로 보여주고 읽는 쪽이 판단한다.**
    """
    latest = next((r for r in sorted(rows, key=lambda r: r["filingDate"], reverse=True)
                   if r["form"] in ("10-Q", "10-K", "10-K/A", "10-Q/A")), None)
    if not latest:
        return None
    txt = _doc_text(cik, latest["accessionNumber"], latest["primaryDocument"])
    if not txt:
        return None
    src = f"{latest['form']} {latest['filingDate']}"
    out: Dict[str, Any] = {}

    m = _SEG_NAMES_PAT.search(txt)
    if m:
        out["부문 구성"] = re.sub(r"\s+", " ", m.group(0)).strip()[:400]

    # 부문 손익표 — 헤드 뒤 본문을 그대로 발췌. 숫자를 우리가 재계산하지 않는다.
    for mm in _SEG_HEAD_PAT.finditer(txt):
        seg_txt = txt[mm.start():mm.start() + 2600]
        if not re.search(r"(?:income|loss)\s*\(?loss\)?\s*from operations|Revenue", seg_txt, re.I):
            continue
        out["부문 주석 발췌"] = re.sub(r"\s+", " ", seg_txt).strip()
        out["_출처"] = f"{src} 본문 직접 확인"
        break

    # 매출 분해(제품·서비스·지역) — 부문 주석이 없어도 Note 3 에 있는 경우가 많다.
    i = txt.lower().find("revenue disaggregated")
    if i >= 0:
        out["매출 분해 발췌"] = re.sub(r"\s+", " ", txt[i:i + 1400]).strip()
        out.setdefault("_출처", f"{src} 본문 직접 확인")

    if not out:
        # 🚨 "안 찾아봄" 과 "찾아봤는데 없음" 의 구분. 이게 없으면 부재 주장을 못 한다.
        return {"부문 주석": f"본문에 부문·매출분해 주석 없음 — {src} 전문 검색 확인(추정 아님)"}
    return out


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

    cap = _capital_block(facts, _cover_shares(cik, rows))
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
