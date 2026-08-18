#!/usr/bin/env python3
"""
us_ipo_scout — 미국 IPO 파이프라인 Watch (SEC EDGAR 일별 인덱스 기반).

🚨 왜 신설했나 (2026-08-17)
  `ipo_scout.py` 는 **DART 전용**이다(본문에 SEC/EDGAR/NASDAQ/NYSE 언급 0건, 2경로 확인).
  즉 상장 전 파이프라인이 국내만 있고 미장은 통째로 비어 있었다. 경쟁 서비스(StockPulse)가
  IPO 탭을 별도로 두고 있어 감사하다 발견.

수집 경로 = EDGAR **일별 인덱스** (form.YYYYMMDD.idx).
  전문검색 API 대신 이걸 쓰는 이유 = 폼 타입·회사명·CIK·접수일·문서경로가 한 줄에 다 있고,
  누락 없이 **그날 접수분 전수**라 분모가 확정된다. 인증 0·무료.
  실측(2026-08-17, 10 거래일): 관련 폼 합계 304건 = 일평균 30.4건. 424B4 는 2.3건/일.

## 단계 사다리 (이게 이 수집기의 핵심이다)

  S-1 / F-1        신청      최초 등록신고서 접수
  S-1/A / F-1/A    정정      심사 진행 중 (횟수가 곧 진행도)
  424B4            가격확정  최종 투자설명서 = 공모가 확정 → 상장 임박
  8-A12B / CERT    거래소등록 상장 직전 절차

🚨 **424B4 단독은 IPO 가 아니다.** 선반등록(shelf) 인출·채권 발행에도 같은 폼을 쓴다.
   그래서 **같은 CIK 가 창 안에서 S-1/F-1 계보를 갖고 있을 때만** 가격확정으로 올린다.
   계보 없는 424B4 는 `lineage=false` 로 남겨 두되 단계는 올리지 않는다. 이 구분이 없으면
   회사채 발행이 IPO 목록에 섞인다(2026-08-17 StockPulse 피드에서 EVRG 424B5 가 정확히 그 형태).

⚠️ 관측 ONLY — 산출물 = watch list (후보 신호, 가설 N=0). **추천 아님** (CLAUDE.md RULE 7).
   상장 전 = 가격/거래 시계열 0 → Brain 가격·모멘텀 축 적용 불가. 검증 trail 은 상장 후
   funnel 편입 시점부터 N 누적으로만 시작한다. KR `ipo_scout` 의 규율을 그대로 따른다.

🚨 SPAC 판정은 **회사명 휴리스틱**이다 (`is_spac_likely`). 공시 본문을 읽고 내린 판정이 아니다.
   KR ipo_scout 는 SPAC 을 제외하지만 여기서는 **제외하지 않고 표시만** 한다 — 미장은 SPAC 이
   신규 상장의 큰 비중이라 빼면 분모가 왜곡되고, 이름만 보고 거르면 오분류가 남는다.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
import urllib.request
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)

from api.config import DATA_DIR, now_kst  # noqa: E402
from api.utils import market_calendar as _mcal  # noqa: E402

logger = logging.getLogger(__name__)

OUT_PATH = os.path.join(DATA_DIR, "us_ipo_watch.json")

_UA = {"User-Agent": "VERITY/1.0 (gywns0126@gmail.com)"}
IDX_TMPL = "https://www.sec.gov/Archives/edgar/daily-index/{y}/QTR{q}/form.{ymd}.idx"

# 단계 = 숫자가 클수록 상장에 가깝다. 한 회사의 최종 단계 = 관측된 값의 최대.
STAGE = {
    "S-1": 1, "F-1": 1, "S-1MEF": 1,
    "S-1/A": 2, "F-1/A": 2,
    "424B4": 3,
    "8-A12B": 4, "CERT": 4,
}
STAGE_KO = {1: "신청", 2: "정정(심사중)", 3: "가격확정", 4: "거래소등록"}
FILING_FORMS = set(STAGE)
# 계보(S-1/F-1 최초 접수)로 인정하는 폼
LINEAGE_FORMS = {"S-1", "F-1", "S-1MEF", "S-1/A", "F-1/A"}
# 계보가 있어야만 IPO 단계로 인정하는 폼 (없으면 2차 발행·ETF 등록 등 다른 사건)
_NEEDS_LINEAGE = {"424B4", "8-A12B", "CERT"}

LOOKBACK_DAYS = 45          # 달력일. ≈31 거래일 — S-1 → 상장 리드타임을 덮는다.
DOC_FETCH_CAP = 40          # 424B4 원문 조회 상한 (실측 2.3건/일 이라 넉넉하다)
PROFILE_CAP = 60            # SEC 프로필 조회 상한 — 목록 노출 8건 + 정렬 변동 여유

_SPAC_RE = re.compile(
    r"\b(acquisition\s+corp|acquisition\s+co|blank\s+check|capital\s+acquisition)\b", re.I
)


def _get(url: str, timeout: int = 45) -> bytes:
    return urllib.request.urlopen(urllib.request.Request(url, headers=_UA), timeout=timeout).read()


# 🚨 고정폭 오프셋을 쓰지 않는다. 실측 컬럼은 Form(0:17) Name(17:79) CIK(79:91)
#   Filed(91:103) Path(103:) 인데, 처음에 헤더 글자수만 보고 0:12/12:74/… 로 짐작했다가
#   전량 0건이 나왔다(2026-08-17). 폭이 바뀌어도 안 깨지도록 오른쪽 앵커(숫자 CIK +
#   8자리 날짜 + edgar/ 경로)로 잡는다. split() 은 회사명 공백에서 깨지므로 쓰지 않는다.
_IDX_RE = re.compile(
    r"^(?P<form>\S.{0,19}?)\s{2,}(?P<name>\S.*?)\s{2,}(?P<cik>\d{1,10})\s+"
    r"(?P<filed>\d{8})\s+(?P<path>edgar/\S+)\s*$"
)


def _parse_idx_line(line: str) -> Optional[Dict[str, str]]:
    """일별 인덱스 한 줄 → dict. 관심 폼이 아니면 None."""
    m = _IDX_RE.match(line)
    if not m:
        return None
    form = m.group("form").strip()
    if form not in FILING_FORMS:
        return None
    return {"form": form, "name": m.group("name").strip(), "cik": m.group("cik"),
            "filed": m.group("filed"), "path": m.group("path")}


def _parseable(line: str) -> bool:
    """폼 종류와 무관하게 **행 자체가 읽히는가**. 레이아웃 드리프트 감지용."""
    return bool(_IDX_RE.match(line))


def scan_days(lookback: int = LOOKBACK_DAYS) -> tuple[List[Dict[str, str]], List[str], int]:
    """(접수 행 목록, 조회 실패일, 조회한 거래일 수)."""
    rows: List[Dict[str, str]] = []
    missed: List[str] = []
    scanned = 0
    d = now_kst().date()
    end = d - timedelta(days=lookback)
    while d > end:
        d -= timedelta(days=1)
        if not _mcal.is_trading_day(d, "US"):
            continue
        url = IDX_TMPL.format(y=d.year, q=(d.month - 1) // 3 + 1, ymd=d.strftime("%Y%m%d"))
        try:
            txt = _get(url).decode("utf-8", "ignore")
        except Exception as e:  # noqa: BLE001 — 하루가 없어도 나머지는 산다
            missed.append(f"{d}({type(e).__name__})")
            continue
        scanned += 1
        lines = txt.splitlines()
        # 🚨 레이아웃 드리프트 감지 — "관심 폼이 0건" 과 "포맷이 바뀌어 한 줄도 못 읽음" 은
        #   전혀 다른 사건인데 결과가 똑같이 0 이다. 후자를 조용히 넘기면 IPO 목록이 텅 빈
        #   채로 매일 성공 종료한다. 그래서 폼 무관 파싱률을 따로 잰다.
        body = [l for l in lines if l.strip() and not l.startswith("-")]
        ok = sum(1 for l in body if _parseable(l))
        if len(body) > 100 and ok == 0:
            missed.append(f"{d}(레이아웃드리프트: {len(body)}행 중 파싱 0)")
            logger.error("🚨 EDGAR 인덱스 포맷 변경 의심 — %s 에서 %d행 중 0행 파싱", d, len(body))
            continue
        for line in lines:
            r = _parse_idx_line(line)
            if r:
                rows.append(r)
    return rows, missed, scanned


def _filing_url(path: str) -> str:
    return "https://www.sec.gov/Archives/" + path.lstrip("/")


# 🚨 공모가 추출 — "액면가(par value)" 를 물지 않는 것이 전부다.
#   첫 구현은 `N shares ... $X per share` 였는데 표지의
#   "94,046,357 shares of common stock, par value $0.00001 per share" 를 그대로 물어
#   공모가를 $0.00001 로 읽었다(2026-08-17 실측 9건). 범위 게이트가 걸러주긴 했지만
#   **게이트를 통과하는 오답**이 남을 수 있어 앵커 자체를 바꾼다.
#   → 가격은 "offering price / price to public" 문맥에서만 찾고, par value 는 명시 배제.
_OFFER_PRICE_RE = re.compile(
    r"(?:initial\s+public\s+offering\s+price|public\s+offering\s+price|price\s+to\s+(?:the\s+)?public"
    r"|offering\s+price)\s*(?:of|is|:)?\s*\$\s?(?P<px>\d[\d,]*(?:\.\d+)?)",
    re.I,
)
_PAR_VALUE_RE = re.compile(r"par\s+value", re.I)
# 주식수 = "we are offering N shares" / "offering N shares of" 문맥.
_OFFER_SHARES_RE = re.compile(
    r"(?:we\s+are\s+offering|offering\s+of|are\s+offering)\s+(?:an\s+aggregate\s+of\s+)?"
    r"(?P<sh>\d[\d,]{3,14})\s+shares",
    re.I,
)


def _primary_doc_url(txt_path: str) -> Optional[str]:
    """전체 제출물(.txt) 경로 → **주 문서(투자설명서 본문)** URL.

    🚨 `edgar/data/CIK/ACCESSION.txt` 는 첨부·이미지까지 전부 이어붙인 통짜 파일이라
       앞부분이 표지가 아니다(2026-08-17 실측 — '표지 패턴 불일치' 22건의 주범).
       accession 디렉터리의 index.json 에서 주 문서를 골라 그것만 읽는다.
    """
    m = re.search(r"edgar/data/(\d+)/([\d-]+)\.txt$", txt_path)
    if not m:
        return None
    cik, acc = m.group(1), m.group(2)
    idx = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/index.json"
    try:
        j = json.loads(_get(idx, timeout=45).decode("utf-8", "ignore"))
    except Exception:  # noqa: BLE001
        return None
    items = ((j.get("directory") or {}).get("item") or [])
    cands = [it.get("name", "") for it in items
             if str(it.get("name", "")).lower().endswith((".htm", ".html"))]
    # 첨부(exhibit)·표지 이미지 제외 → 남은 것 중 가장 큰 문서가 본문이다.
    body = [n for n in cands if not re.match(r"^(ex|R\d|Financial_Report)", n, re.I)]
    if not body:
        return None
    sizes = {it.get("name"): int(it.get("size") or 0) for it in items}
    best = max(body, key=lambda n: sizes.get(n, 0))
    return f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/{best}"


def enrich_424b4(item: Dict[str, Any]) -> None:
    """424B4 표지에서 주식수 × 공모가를 뽑는다. 실패하면 **채우지 않는다**.

    🚨 값을 억지로 만들지 않는다 — 없는 정밀도를 있는 척하면 뒤에서 조용히 틀린다.
       파싱 성공 여부를 `pricing.parse_ok` 로 자기 신고한다.
    """
    src = item.get("_priced_url")
    if not src:
        return
    url = _primary_doc_url(src) or src
    try:
        raw = _get(url, timeout=60).decode("utf-8", "ignore")
    except Exception as e:  # noqa: BLE001
        item["pricing"] = {"parse_ok": False, "reason": f"fetch:{type(e).__name__}", "source_url": url}
        return
    text = re.sub(r"<[^>]+>", " ", raw)
    text = re.sub(r"&(nbsp|#160|#8201|#8202);", " ", text)
    text = re.sub(r"\s+", " ", text)
    head = text[:120000]

    pm = None
    for cand in _OFFER_PRICE_RE.finditer(head):
        # 🚨 par value 문맥이면 버린다 — 이게 첫 구현이 틀린 지점이다.
        if _PAR_VALUE_RE.search(head[max(0, cand.start() - 60):cand.start()]):
            continue
        pm = cand
        break
    sm = _OFFER_SHARES_RE.search(head)
    if not pm or not sm:
        miss = "공모가 문구 없음" if not pm else "주식수 문구 없음"
        item["pricing"] = {"parse_ok": False, "reason": miss, "source_url": url}
        return
    try:
        shares = int(sm.group("sh").replace(",", ""))
        price = float(pm.group("px").replace(",", ""))
    except ValueError:
        item["pricing"] = {"parse_ok": False, "reason": "숫자 변환 실패", "source_url": url}
        return
    # 상식 게이트 — 엉뚱한 문장을 물었을 때의 마지막 방어. par value 는 위에서 이미 배제.
    if not (10_000 <= shares <= 2_000_000_000) or not (1.0 <= price <= 1000):
        item["pricing"] = {"parse_ok": False, "reason": f"범위 밖 shares={shares} price={price}",
                           "source_url": url}
        return
    item["pricing"] = {
        "parse_ok": True,
        "shares": shares,
        "price_usd": price,
        "gross_usd": round(shares * price),
        "source_url": url,
        "note": "424B4 본문 자체 파싱(🧮) — 인수인 초과배정 미반영. 확정치는 원문 확인.",
    }


SEC_TICKERS = "https://www.sec.gov/files/company_tickers.json"


SEC_SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik10}.json"
_REPORTER_FORMS = ("10-K", "10-Q", "20-F", "40-F")


def already_public_ciks() -> set:
    """지금 티커를 가진 CIK 집합. **정보용일 뿐 IPO 판별에 쓰지 않는다.**

    🚨 여기서 한 번 틀렸다(2026-08-17). "티커가 있으면 IPO 가 아니다" 로 필터를 걸었더니
       Vogenx·Jersey Mike's 같은 **진짜 IPO 가 전부 탈락**했다 — 상장을 마친 순간 티커가
       생기므로 '지금 시점 스냅샷' 으로는 IPO 와 기존 상장사를 못 가른다.
       실제 판별은 `was_reporter_before()` 의 **시간 기준** 테스트가 한다.
    """
    try:
        j = json.loads(_get(SEC_TICKERS, timeout=45).decode("utf-8", "ignore"))
    except Exception as e:  # noqa: BLE001
        logger.warning("company_tickers 조회 실패 (%s) — has_ticker_now 표시 생략", type(e).__name__)
        return set()
    out = set()
    for v in (j.values() if isinstance(j, dict) else j):
        try:
            out.add(str(int(v["cik_str"])))
        except (KeyError, TypeError, ValueError):
            continue
    return out


# 🚨 SEC 가 SPAC 을 직접 분류한다 — SIC 6770 = "Blank Checks". 회사명 정규식(_SPAC_RE)은
#   우리 휴리스틱이라 화면에 못 쓰지만 이건 **SEC 사실**이라 노출·정렬 양쪽에 쓸 수 있다.
_SIC_BLANK_CHECK = "6770"

_SUB_CACHE: Dict[str, Optional[Dict[str, Any]]] = {}


def _submissions(cik: str) -> Optional[Dict[str, Any]]:
    """CIK → submissions JSON. 🚨 같은 CIK 를 두 번 받지 않는다(프로필·보고이력 공용)."""
    key = str(int(cik))
    if key in _SUB_CACHE:
        return _SUB_CACHE[key]
    try:
        j = json.loads(_get(SEC_SUBMISSIONS.format(cik10=key.zfill(10)),
                            timeout=45).decode("utf-8", "ignore"))
    except Exception:  # noqa: BLE001 — 한 건 실패로 전체 수집을 죽이지 않는다
        j = None
    _SUB_CACHE[key] = j
    return j


def sec_profile(cik: str) -> Dict[str, Any]:
    """업종·상장예정 티커·소재지. 전부 SEC 기재값이다.

    왜 넣었나: 카드에 회사명·단계·공모가뿐이라 **무슨 회사인지 알 수 없었다**(국내 IPO 와
    같은 구멍). sicDescription 은 SEC 자체 분류 문구라 우리 판단이 섞이지 않는다.
    """
    j = _submissions(cik)
    if not j:
        return {"available": False}
    sic = str(j.get("sic") or "").strip()
    tick = [t for t in (j.get("tickers") or []) if t]
    b = (j.get("addresses") or {}).get("business") or {}
    city, st = str(b.get("city") or "").strip(), str(b.get("stateOrCountry") or "").strip()
    return {
        "available": True,
        "sic": sic or None,
        "sic_desc": str(j.get("sicDescription") or "").strip() or None,
        # 🚨 SEC 분류 기반 SPAC 판정 — 회사명 휴리스틱보다 정확하고 공개 노출도 가능하다.
        "is_blank_check": sic == _SIC_BLANK_CHECK,
        "ticker": tick[0] if tick else None,
        "region": ", ".join([x for x in (city, st) if x]) or None,
        "state_of_inc": str(j.get("stateOfIncorporation") or "").strip() or None,
    }


def was_reporter_before(cik: str, before_yyyymmdd: str) -> Optional[bool]:
    """그 회사가 **이 등록 이전에 이미 정기보고서를 내던 회사**였나. 모르면 None.

    이게 IPO 와 2차 발행을 가르는 진짜 기준이다. IPO 기업은 S-1 이전에 10-K/10-Q 가 없고,
    기존 상장사(예: CURIS)는 몇 년치가 있다. 스냅샷이 아니라 **시점 비교**라서 방금 상장한
    회사를 잘못 걸러내지 않는다.
    """
    j = _submissions(cik)
    if not j:
        return None
    rec = ((j.get("filings") or {}).get("recent") or {})
    forms, dates = rec.get("form") or [], rec.get("filingDate") or []
    iso = f"{before_yyyymmdd[:4]}-{before_yyyymmdd[4:6]}-{before_yyyymmdd[6:]}"
    for f, dt in zip(forms, dates):
        if str(f).upper().startswith(_REPORTER_FORMS) and str(dt) < iso:
            return True
    return False


def build(lookback: int = LOOKBACK_DAYS, fetch_docs: bool = True) -> Dict[str, Any]:
    rows, missed, scanned = scan_days(lookback)
    listed = already_public_ciks()
    by_cik: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        it = by_cik.setdefault(r["cik"], {
            "cik": r["cik"], "name": r["name"], "forms": {},
            "first_filed": r["filed"], "last_filed": r["filed"],
            "_priced_url": None,
        })
        it["forms"][r["form"]] = it["forms"].get(r["form"], 0) + 1
        it["first_filed"] = min(it["first_filed"], r["filed"])
        if r["filed"] >= it["last_filed"]:
            it["last_filed"] = r["filed"]
            it["name"] = r["name"]           # 개명 시 최신 이름
        if r["form"] == "424B4":
            it["_priced_url"] = _filing_url(r["path"])

    items: List[Dict[str, Any]] = []
    for it in by_cik.values():
        forms = it["forms"]
        lineage = any(f in LINEAGE_FORMS for f in forms)
        # 🚨 계보(S-1/F-1) 없는 후기 단계 폼은 IPO 가 아니다.
        #   · 424B4  = 선반 인출·채권 발행에도 쓰인다.
        #   · 8-A12B/CERT = ETF 신탁의 신규 시리즈 등록, 기존 상장사의 새 증권 클래스 등록에도
        #     쓰인다 — 실측에서 FIRST TRUST ETF IV, CASTLE BIOSCIENCES(기존 상장) 가 섞였다.
        #   계보가 없으면 이 폼들을 단계 계산에서 뺀다. 남는 단계가 0 이면 목록에서 제외.
        usable = {f: n for f, n in forms.items() if lineage or f not in _NEEDS_LINEAGE}
        stage = max((STAGE[f] for f in usable), default=0)
        if stage == 0:
            continue
        it["lineage"] = lineage
        it["stage"] = stage
        it["stage_ko"] = STAGE_KO[stage]
        it["amend_count"] = forms.get("S-1/A", 0) + forms.get("F-1/A", 0)
        it["is_foreign_issuer"] = any(f.startswith("F-1") for f in forms)
        # 이 시점엔 프로필이 아직 없다 → 회사명 폴백. 프로필 수집 후 SIC 로 덮는다(아래).
        it["is_spac_likely"] = bool(_SPAC_RE.search(it["name"]))
        # 지금 티커 보유 여부 = 정보용. IPO 판별에 쓰지 않는다(위 함수 주석의 사고).
        it["has_ticker_now"] = (str(int(it["cik"])) in listed) if listed else None
        it["edgar_url"] = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={it['cik']}&type=S-1&dateb=&owner=include&count=20"
        items.append(it)

    # 🚨 SEC 프로필(업종·티커·소재지) — 화면에 뜰 상위권에만 붙인다.
    #   전량 265건은 SEC 호출이 과하고, 목록은 상위 8건만 노출한다. 정렬 기준과 같은 순서로
    #   넉넉히 PROFILE_CAP 만큼만 받아 표시 후보를 전부 덮는다. submissions 는 캐시라
    #   뒤의 was_reporter_before 가 같은 CIK 를 다시 받지 않는다.
    for it in sorted(items, key=lambda x: (x["stage"], x["last_filed"]), reverse=True)[:PROFILE_CAP]:
        it["profile"] = sec_profile(it["cik"])
        # 🚨 SPAC 판정을 SEC SIC 6770("Blank Checks")로 **승격**한다 — 회사명 정규식보다
        #   정확하고, SEC 분류라 화면 노출도 가능하다. 프로필을 못 받은 건은 폴백 유지.
        #   🚨 순서 주의: 항목 루프에서 판정하면 프로필이 아직 없어 항상 폴백으로 떨어진다
        #   (첫 구현이 그 순서였다). 반드시 프로필 수집 **뒤**에 덮는다.
        if (it["profile"] or {}).get("available"):
            it["is_spac_likely"] = bool(it["profile"].get("is_blank_check"))

    # 가격확정 건만 원문 보강 — 상한 안에서 최신순.
    if fetch_docs:
        priced = sorted([i for i in items if i["stage"] >= 3 and i.get("_priced_url")],
                        key=lambda x: x["last_filed"], reverse=True)[:DOC_FETCH_CAP]
        for i in priced:
            # 시점 기준으로 기존 보고기업인지 먼저 가른다 — 기존 상장사의 424B4 는
            # IPO 가 아니라 2차 발행이라 공모가 파싱 대상이 아니다(CURIS 실측).
            i["pre_existing_reporter"] = was_reporter_before(i["cik"], i["first_filed"])
            if i["pre_existing_reporter"]:
                continue
            enrich_424b4(i)
        logger.info("424B4 원문 보강 %d건 (성공 %d)", len(priced),
                    sum(1 for i in priced if (i.get("pricing") or {}).get("parse_ok")))

    for i in items:
        i.pop("_priced_url", None)
    items.sort(key=lambda x: (-x["stage"], x["last_filed"]), reverse=False)
    items.sort(key=lambda x: (x["stage"], x["last_filed"]), reverse=True)

    stages = {STAGE_KO[s]: sum(1 for i in items if i["stage"] == s) for s in sorted(STAGE_KO)}
    return {
        "_meta": {
            "generated_at": now_kst().isoformat(timespec="seconds"),
            "lookback_days": lookback,
            "sessions_scanned": scanned,
            "sessions_missed": missed,
            "counts": {
                "filings": len(rows),
                "companies": len(items),
                "by_stage": stages,
                "spac_likely": sum(1 for i in items if i["is_spac_likely"]),
                "has_ticker_now": sum(1 for i in items if i.get("has_ticker_now")),
                "priced_secondary_excluded": sum(1 for i in items if i.get("pre_existing_reporter")),
                "foreign_issuer": sum(1 for i in items if i["is_foreign_issuer"]),
                "priced_parse_ok": sum(1 for i in items if (i.get("pricing") or {}).get("parse_ok")),
            },
            "source": "SEC EDGAR daily-index form.YYYYMMDD.idx (무료·인증 0)",
            "basis": ("상장 전 파이프라인 관측. 단계 = 신청(S-1/F-1) → 정정 → 가격확정(424B4) "
                      "→ 거래소등록(8-A12B/CERT). 🚨 424B4 는 계보(S-1/F-1)가 있을 때만 "
                      "가격확정으로 인정한다 — 선반 인출·채권 발행이 같은 폼을 쓴다. "
                      "🚨 2차 발행 배제는 **시점 기준**이다 — pre_existing_reporter=true(등록 이전에 이미 "
                      "10-K/10-Q 를 내던 회사)면 IPO 가 아니다. '지금 티커 보유' 로 거르면 방금 "
                      "상장한 진짜 IPO 가 전부 탈락한다(2026-08-17 자가 오류). "
                      "SPAC 표시는 회사명 휴리스틱이지 공시 본문 판정이 아니다. "
                      "watch list = 후보 신호(가설 N=0), 추천 아님 (RULE 7)."),
        },
        "items": items,
    }


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    payload = build()
    c = payload["_meta"]["counts"]
    # 🚨 건수 0 + 성공 종료 = 조용한 결손. 실패로 끝낸다 ([[feedback_cluster_silent_defect]]).
    if c["companies"] == 0:
        logger.error("[us_ipo_scout] 수집 0건 — 기존 파일 유지하고 종료")
        return 1
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    m = payload["_meta"]
    logger.info("[us_ipo_scout] 접수 %d건 → 기업 %d개 · 단계 %s · SPAC추정 %d · 외국발행 %d "
                "· 공모가파싱 %d · 거래일 %d 조회(실패 %d) → %s",
                c["filings"], c["companies"], c["by_stage"], c["spac_likely"],
                c["foreign_issuer"], c["priced_parse_ok"], m["sessions_scanned"],
                len(m["sessions_missed"]), OUT_PATH)
    return 0


if __name__ == "__main__":
    sys.exit(main())
