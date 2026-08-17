"""
DartScout — OpenDART 핵심 데이터 수집기

대상 API
  1. 공시검색           (list.json)
  2. 주요사항 CB/BW     (cvbdIsDecsn.json, bdwtIsDecsn.json)
  3. 지분공시 대주주     (hyslrSttus.json)
  4. 직원현황 → 퇴사율  (empSttus.json)
  5. 재무제표 → 부채비율 (fnlttSinglAcnt.json)
  6. 배당정보           (alotMatter.json)
  7. 타법인 출자 현황    (otrCprInvstmntSttus.json) — 관계회사 지분 구조

사전 게이트: 감사의견(accnutAdtorNmNdAdtOpinion.json)이
             '적정'이 아니면 즉시 CriticalAuditError 반환
"""
import functools
import gzip
import json
import os
import re
import sys
import time
from typing import Any, Dict, List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from api.config import DART_API_KEY, DATA_DIR, now_kst
from api.collectors.dart_corp_code import get_corp_code
from api.collectors.stock_data import ALL_STOCKS

BASE_URL = "https://opendart.fss.or.kr/api"
RAW_DATA_PATH = os.path.join(DATA_DIR, "raw_data.json")
ANNUAL_REPORT = "11011"
API_DELAY = 0.5

_SESSION = requests.Session()
_SESSION.mount("https://", HTTPAdapter(
    max_retries=Retry(
        total=3,
        backoff_factor=1.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    ),
    pool_connections=4,
    pool_maxsize=4,
))


class CriticalAuditError(Exception):
    """감사의견이 '적정'이 아닐 때 발생"""
    pass


# ── 유틸리티 ──────────────────────────────────────────────

def _parse_int(value: Any) -> int:
    if value is None:
        return 0
    s = str(value).replace(",", "").replace(" ", "").strip()
    if not s or s == "-":
        return 0
    try:
        return int(s)
    except ValueError:
        return 0


def _call(endpoint: str, params: Dict[str, str]) -> Dict[str, Any]:
    """OpenDART API 호출 공통 래퍼. 세션 재사용 + 자동/수동 재시도.

    2026-05-23 (W3 4/4): record_dart_call(status) 로 dart_metrics 누적.
    """
    from api.observability.dart_metrics import record_dart_call

    params["crtfc_key"] = DART_API_KEY
    url = f"{BASE_URL}/{endpoint}"
    last_err: Optional[Exception] = None

    for attempt in range(3):
        try:
            resp = _SESSION.get(url, params=params, timeout=(10, 30))
            resp.raise_for_status()
            time.sleep(API_DELAY)

            data = resp.json()
            status = data.get("status", "")
            if status == "013":
                record_dart_call("013")
                return {"status": "013", "list": []}
            if status != "000":
                record_dart_call(status)
                # 2026-05-27 추가: fail status 분포 진단 (cron_health detect 한 ~16% fail rate root cause).
                # corp_code 만 노출 (key 노출 X).
                import sys as _sys
                msg = (data.get("message", "") or "")[:60]
                _cc = params.get("corp_code", "?")
                print(
                    f"[dart_fail] endpoint={endpoint} status={status} corp_code={_cc} msg={msg!r}",
                    file=_sys.stderr,
                )
                return {"status": status, "message": data.get("message", ""), "list": []}
            record_dart_call("000")
            return data
        except (requests.ReadTimeout, requests.ConnectionError) as e:
            last_err = e
            wait = 1.5 * (attempt + 1)
            print(f"  ⚠ DART 재시도 {attempt+1}/3 ({endpoint}): {e.__class__.__name__} — {wait:.1f}s 대기")
            time.sleep(wait)

    record_dart_call("timeout")
    import sys as _sys
    _cc = params.get("corp_code", "?")
    print(
        f"[dart_fail] endpoint={endpoint} status=timeout corp_code={_cc} err={type(last_err).__name__}",
        file=_sys.stderr,
    )
    return {"status": "timeout", "message": str(last_err), "list": []}


# ── 감사의견 게이트 ───────────────────────────────────────

def check_audit(corp_code: str, bsns_year: str) -> str:
    """감사의견 확인. '적정'이 아니면 CriticalAuditError를 발생시킨다."""
    data = _call("accnutAdtorNmNdAdtOpinion.json", {
        "corp_code": corp_code,
        "bsns_year": bsns_year,
        "reprt_code": ANNUAL_REPORT,
    })

    for item in data.get("list", []):
        opinion = (item.get("adt_opinion") or "").strip()
        if opinion and "적정" not in opinion:
            raise CriticalAuditError(
                f"감사의견 '{opinion}' (corp_code={corp_code}, year={bsns_year})"
            )
        if opinion:
            return opinion

    return "데이터 없음"


# ── 1. 공시검색 ──────────────────────────────────────────

def fetch_disclosures(corp_code: str, bgn_de: str, end_de: str) -> List[Dict]:
    data = _call("list.json", {
        "corp_code": corp_code,
        "bgn_de": bgn_de,
        "end_de": end_de,
        "page_count": "20",
        "sort": "date",
        "sort_mth": "desc",
    })
    return [
        {
            "report_nm": d.get("report_nm", ""),
            "rcept_dt": d.get("rcept_dt", ""),
            "flr_nm": d.get("flr_nm", ""),
        }
        for d in data.get("list", [])
    ]


# ── 2. 주요사항 CB/BW ───────────────────────────────────

def fetch_cb_bw(corp_code: str, bgn_de: str, end_de: str) -> Dict[str, List]:
    common = {"corp_code": corp_code, "bgn_de": bgn_de, "end_de": end_de}

    cb_data = _call("cvbdIsDecsn.json", common)
    cb = [
        {
            "bd_tm": d.get("bd_tm", ""),
            "bd_fta": d.get("bd_fta", ""),
            "cvprc": d.get("cvprc", ""),
            "cvisstk_cnt": d.get("cvisstk_cnt", ""),
            "bddd": d.get("bddd", ""),
        }
        for d in cb_data.get("list", [])
    ]

    bw_data = _call("bdwtIsDecsn.json", common)
    bw = [
        {
            "bd_tm": d.get("bd_tm", ""),
            "bd_fta": d.get("bd_fta", ""),
            "ex_prc": d.get("ex_prc", ""),
            "nstk_isstk_cnt": d.get("nstk_isstk_cnt", ""),
            "bddd": d.get("bddd", ""),
        }
        for d in bw_data.get("list", [])
    ]

    return {"cb": cb, "bw": bw}


# ── 3. 지분공시(대주주) ──────────────────────────────────

def fetch_major_shareholders(corp_code: str, bsns_year: str) -> List[Dict]:
    data = _call("hyslrSttus.json", {
        "corp_code": corp_code,
        "bsns_year": bsns_year,
        "reprt_code": ANNUAL_REPORT,
    })
    return [
        {
            "nm": d.get("nm", ""),
            "relate": d.get("relate", ""),
            "stock_cnt": d.get("trmend_posesn_stock_co", ""),
            "stock_rate": d.get("trmend_posesn_stock_qota_rt", ""),
        }
        for d in data.get("list", [])
    ]


# ── 4. 직원현황(퇴사율) ─────────────────────────────────

def fetch_employees(corp_code: str, bsns_year: str) -> Dict[str, Any]:
    data = _call("empSttus.json", {
        "corp_code": corp_code,
        "bsns_year": bsns_year,
        "reprt_code": ANNUAL_REPORT,
    })

    total_prev = 0
    total_curr = 0
    avg_tenure = ""

    for item in data.get("list", []):
        prev = _parse_int(item.get("reform_bfe_emp_co_rgllbr")) + \
               _parse_int(item.get("reform_bfe_emp_co_cnttk"))
        curr = _parse_int(item.get("rgllbr_co")) + \
               _parse_int(item.get("cnttk_co"))
        total_prev += prev
        total_curr += curr
        t = (item.get("avrg_cnwk_sdytrn") or "").strip()
        if t:
            avg_tenure = t

    turnover_rate: Optional[float] = None
    if total_prev > 0:
        turnover_rate = round((total_prev - total_curr) / total_prev * 100, 2)

    return {
        "total_prev": total_prev,
        "total_curr": total_curr,
        "turnover_rate_pct": turnover_rate,
        "avg_tenure": avg_tenure,
    }


# ── 5. 재무제표(부채비율) ────────────────────────────────

@functools.lru_cache(maxsize=512)
def _fetch_fnltt_cached(corp_code: str, bsns_year: str) -> str:
    """fnlttSinglAcnt.json 응답을 캐싱하여 동일 (corp_code, bsns_year) 중복 호출 방지."""
    data = _call("fnlttSinglAcnt.json", {
        "corp_code": corp_code,
        "bsns_year": bsns_year,
        "reprt_code": ANNUAL_REPORT,
    })
    return json.dumps(data, ensure_ascii=False)


def _get_fnltt_data(corp_code: str, bsns_year: str) -> Dict[str, Any]:
    return json.loads(_fetch_fnltt_cached(corp_code, bsns_year))


def fetch_financials(corp_code: str, bsns_year: str) -> Dict[str, Any]:
    """자산총계·부채총계만 추출하여 부채비율을 계산한다."""
    data = _get_fnltt_data(corp_code, bsns_year)

    total_assets = 0
    total_liabilities = 0

    for item in data.get("list", []):
        if item.get("sj_div") != "BS":
            continue
        acct = item.get("account_nm", "")
        amount = _parse_int(item.get("thstrm_amount"))
        if "자산총계" in acct:
            total_assets = amount
        elif "부채총계" in acct:
            total_liabilities = amount

    equity = total_assets - total_liabilities
    debt_ratio: Optional[float] = None
    if equity > 0:
        debt_ratio = round(total_liabilities / equity * 100, 2)

    return {
        "total_assets": total_assets,
        "total_liabilities": total_liabilities,
        "equity": equity,
        "debt_ratio_pct": debt_ratio,
    }


# ── 5.5. 부동산 자산 ──────────────────────────────────

PROPERTY_KEYWORDS = ["투자부동산", "토지", "건물", "사용권자산", "건설중인자산"]

def fetch_property_assets(corp_code: str, bsns_year: str) -> Dict[str, Any]:
    """재무상태표(BS)에서 부동산 관련 계정과목을 추출한다."""
    data = _get_fnltt_data(corp_code, bsns_year)

    items: List[Dict[str, Any]] = []
    total_current = 0
    total_prev = 0
    total_assets = 0

    for item in data.get("list", []):
        if item.get("sj_div") != "BS":
            continue
        acct = item.get("account_nm", "")

        if "자산총계" in acct:
            total_assets = _parse_int(item.get("thstrm_amount"))

        matched = any(kw in acct for kw in PROPERTY_KEYWORDS)
        if not matched:
            continue

        curr = _parse_int(item.get("thstrm_amount"))
        prev = _parse_int(item.get("frmtrm_amount"))
        items.append({
            "account": acct,
            "current": curr,
            "previous": prev,
            "change": curr - prev,
            "change_pct": round((curr - prev) / prev * 100, 2) if prev else None,
        })
        total_current += curr
        total_prev += prev

    property_ratio: Optional[float] = None
    if total_assets > 0 and total_current > 0:
        property_ratio = round(total_current / total_assets * 100, 2)

    return {
        "items": items,
        "total_current": total_current,
        "total_previous": total_prev,
        "total_change": total_current - total_prev,
        "total_change_pct": (
            round((total_current - total_prev) / total_prev * 100, 2)
            if total_prev > 0 else None
        ),
        "property_to_asset_pct": property_ratio,
        "total_assets": total_assets,
    }


# ── 5.6. 현금흐름표 ────────────────────────────────────

def _extract_section_from_rcept(rcept_no: str, latest: Dict[str, Any], bsns_year: str) -> Dict[str, Any]:
    """단일 rcept_no document.xml fetch + ZIP 해제 + 'II. 사업의 내용' 슬라이스.

    raw_text 추출 성공 시 {rcept_no, report_nm, rcept_dt, bsns_year, raw_text, char_count}.
    실패 시 {error, rcept_no, ...}.
    """
    try:
        url = f"{BASE_URL}/document.xml"
        resp = _SESSION.get(url, params={"crtfc_key": DART_API_KEY, "rcept_no": rcept_no},
                            timeout=(10, 60))
        resp.raise_for_status()
        time.sleep(API_DELAY)
    except Exception as e:
        return {"error": f"document_fetch:{e}", "rcept_no": rcept_no}

    import io
    import zipfile
    # 2026-05-26 FIX: ZIP 내 XML 별 개별 decode 후 concat (이전 = bytes concat → 단일 decode).
    # 사업보고서 ZIP 은 별도 인코딩 XML 혼합 가능 (예: 감사보고서 + 본문). bytes concat 후
    # UTF-8 strict 실패 → EUC-KR fallback 시 UTF-8 XML 가 garbage 화 → 본문 "사업의 내용"
    # 키워드 손실 → section_not_found. 개별 decode = encoding 자율, 본문 키워드 보존.
    raw_text_chunks: List[str] = []
    try:
        zf = zipfile.ZipFile(io.BytesIO(resp.content))
        inner_names = [n for n in zf.namelist() if n.lower().endswith(".xml")]
        if not inner_names:
            return {"error": "no_xml_in_zip", "rcept_no": rcept_no}
        for nm in inner_names:
            try:
                with zf.open(nm) as f:
                    content = f.read()
            except Exception:
                continue
            for enc in ("utf-8", "euc-kr", "cp949"):
                try:
                    raw_text_chunks.append(content.decode(enc))
                    break
                except UnicodeDecodeError:
                    continue
            else:
                # 모든 인코딩 실패 — lossy decode (드물지만 fail-safe)
                raw_text_chunks.append(content.decode("utf-8", errors="ignore"))
    except zipfile.BadZipFile:
        ct = resp.headers.get("Content-Type", "")
        if "xml" in ct.lower() or resp.content.lstrip().startswith(b"<"):
            # 단일 XML 직반환 케이스
            for enc in ("utf-8", "euc-kr", "cp949"):
                try:
                    raw_text_chunks.append(resp.content.decode(enc))
                    break
                except UnicodeDecodeError:
                    continue
            else:
                raw_text_chunks.append(resp.content.decode("utf-8", errors="ignore"))
        else:
            return {"error": "bad_zip", "rcept_no": rcept_no}
    except Exception as e:
        return {"error": f"zip:{e}", "rcept_no": rcept_no}

    raw_text = "\n".join(raw_text_chunks)

    # 2026-05-26 FIX: lxml-xml strict 파서가 DART XML 본문 silent drop (text_len 128K vs
    # html.parser 720K, "사업의 내용" 키워드 lxml-xml=0 / html.parser=7). DART XML 은
    # HTML-like 태그 (TABLE/P/SPAN) 사용 → html.parser 가 정합. lxml-xml strict 룰이
    # DART 의 비표준 속성/구조에서 본문 누락 → section_not_found 의 두 번째 root cause.
    try:
        import warnings
        from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", XMLParsedAsHTMLWarning)
            soup = BeautifulSoup(raw_text, "html.parser")
        for tag in soup.find_all(["script", "style"]):
            tag.decompose()
        text = soup.get_text("\n")
    except Exception as e:
        return {"error": f"parse:{e}", "rcept_no": rcept_no}

    import re
    cleaned = re.sub(r"[ \t]+", " ", text)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

    # "II. 사업의 내용" ~ "III. 재무에 관한 사항" 사이 슬라이스.
    # 한국 사업보고서 표준 목차에 기반.
    patterns = [
        r"(?is)(?:Ⅱ|II|2)[\.\s]+사업의\s*내용(.*?)(?:Ⅲ|III|3)[\.\s]+(?:재무|경영진단|보고서에)",
        r"(?is)사업의\s*내용(.*?)재무에\s*관한\s*사항",
        r"(?is)사업의\s*개요(.*?)(?:이사의\s*경영진단|재무제표)",
    ]
    section = ""
    for pat in patterns:
        matches = re.findall(pat, cleaned)
        if matches:
            section = max(matches, key=len).strip()
            if len(section) > 600:
                break

    if not section or len(section) < 300:
        return {
            "error": "section_not_found",
            "rcept_no": rcept_no,
            "report_nm": latest.get("report_nm", ""),
            "rcept_dt": latest.get("rcept_dt", ""),
            "raw_text": "",
            "char_count": 0,
        }

    MAX_CHARS = 60000
    if len(section) > MAX_CHARS:
        section = section[:MAX_CHARS]

    # 2026-06-03 DART 2차 원문 심화 — "대주주 등과의 거래내용"(특수관계자 거래 =
    # 터널링·일감몰아주기) 섹션 additive 슬라이스. 같은 document 라 추가 fetch 0.
    # 한국 특유 지배구조 red flag (글로벌 LLM·개인이 한국 공시에서 체계 추출 못 함).
    rp_patterns = [
        r"(?is)대주주\s*등과의\s*거래\s*내용(.*?)(?:그\s*밖에\s*투자자|이사회\s*등|전문가의\s*확인|재무제표)",
        r"(?is)특수관계자\s*(?:와의|간)?\s*거래(.*?)(?:그\s*밖에|전문가의\s*확인|재무제표\s*주석\s*종료)",
    ]
    related_party = ""
    for pat in rp_patterns:
        rp_matches = re.findall(pat, cleaned)
        if rp_matches:
            related_party = max(rp_matches, key=len).strip()
            if len(related_party) > 300:
                break
    if related_party and len(related_party) > 30000:
        related_party = related_party[:30000]

    # 2026-06-06 DART 2차 원문 심화 — 소송/우발부채/제재 additive 슬라이스.
    # distress(회생·파산, dart_disclosure_events)와 별개 — 진행 중 소송 *규모*·우발채무·
    # 약정·제재는 fundamental risk 신호 (충당부채 인식 전 잠재 손실). 한국 공시 특유 영역
    # (글로벌 LLM·개인 미추출). 같은 document → 추가 fetch 0. 정밀(precision) 우선 — 경계
    # 못 찾으면 미매칭(거대 garbage 회피), 청크별 12K·합산 30K cap.
    lit_patterns = [
        r"(?is)(?:계류\s*중인\s*소송|진행\s*중인\s*소송|소송\s*등의?\s*현황|소송\s*사건)(.*?)(?:우발\s*부채|약정\s*사항|특수관계자|보고기간\s*후|주석\s*\d+)",
        # '약정사항' 은 경계서 제외 — "우발부채 및 약정사항" 헤딩서 즉시 매칭돼 본문 잘림(2026-06-06 검증).
        r"(?is)(?:우발\s*부채|우발\s*채무)(.*?)(?:특수관계자|중요한\s*거래|보고기간\s*후|주석\s*\d+\s*[\.\)])",
        r"(?is)그\s*밖에\s*투자자\s*보호.{0,40}?사항(.*?)(?:전문가의\s*확인|이사회|상장규정|코스닥시장)",
    ]
    lit_chunks: List[str] = []
    for pat in lit_patterns:
        lm = re.findall(pat, cleaned)
        if lm:
            best = max(lm, key=len).strip()
            if len(best) > 150:
                lit_chunks.append(best[:12000])
    litigation = "\n\n---\n\n".join(dict.fromkeys(lit_chunks))  # 순서보존 dedupe
    if litigation and len(litigation) > 30000:
        litigation = litigation[:30000]

    # 2026-07-09 유형자산 주석 슬라이스 — 토지·건물 장부금액(재무제표 주석).
    # fnlttSinglAcntAll(본문 재무제표)엔 '유형자산' 총계만 실리고 토지·건물 세부는 주석에만 있음
    # (자산주 15종 실측: 본문 토지 노출 0/15). 숨은부동산 NAV 프록시용 additive 슬라이스 → LLM 파싱 입력.
    # 정밀 우선: '토지' 토큰 포함 + 150자↑ 만 채택(잘못된 경계 garbage 회피), 14K cap.
    ppe_patterns = [
        r"(?is)유형자산[^\n]{0,24}?(?:증감|변동|명세|내역|장부금액|취득원가)(.*?)(?:무형자산|투자부동산|사용권자산|리스|재고자산|매출채권|주석\s*\d+\s*[\.\)])",
        r"(?is)(?:주석\s*)?\d{0,2}[\.\s]*유형자산\s*\n(.*?)(?:무형자산|투자부동산|사용권자산|영업권|주석\s*\d+\s*[\.\)])",
    ]
    ppe_note = ""
    for pat in ppe_patterns:
        pm = re.findall(pat, cleaned)
        if pm:
            best = max(pm, key=len).strip()
            if len(best) > 150 and ("토지" in best or "건물" in best):
                ppe_note = best[:14000]
                break

    # 🚨 2026-08-17 — 감사의견 표('V. 회계감사인의 감사의견') additive 슬라이스.
    #   8/16 의 `kam_text` 를 이것으로 **교체**했다. 그 패턴은 실측에서 사업보고서 **표지**
    #   (회사명·대표이사·소재지)를 담았다 — `'핵심감사사항'` 출현이 `raw_text` 8회 vs
    #   `kam_text` **0회**. `핵심\s*감사\s*사항` 이 표의 **열 이름**으로도 등장하므로
    #   그 지점부터 산문 헤딩까지 잡으면 표 뒤 문서 경계를 넘어 표지로 흘러간다.
    #
    #   교체 근거: 필요한 사실이 **정형 표**에 있다. 8열 `\n\n` 구분 고정이고 마지막 열이
    #   핵심감사사항이며, 당기/전기/전전기 × 개별/연결 6행이 한 번에 나온다.
    #   → LLM 불필요 (`api.analyzers.dart_kam.extract_kam` 이 결정론 파싱).
    #   🚨 `raw_text`(= 'II. 사업의 내용' 슬라이스)로는 안 된다 — 섹션 V 가 그 밖이라
    #   실측 커버리지가 2/10 이었고 그 2건도 슬라이스가 길어 우연히 걸친 것이었다.
    #   여기서는 `cleaned`(전체 문서)에서 표 머리를 직접 찾는다.
    audit_opinion_text = ""
    _ah = re.search(r"사업연도[\s\S]{0,400}?핵심\s*감사\s*사항", cleaned)
    if _ah:
        # 표 머리 앞 200자(섹션 제목 문맥) + 뒤 6000자(3개 연도 × 2행이면 충분)
        audit_opinion_text = cleaned[max(0, _ah.start() - 200):_ah.end() + 6000]

    # 2026-06-04 going-concern/강조사항 — 감사보고서가 같은 ZIP 번들 시 포착.
    # doubt 전용 구문만 (정상 boilerplate "계속기업을 전제로" 회피, false-positive 차단).
    try:
        from api.analyzers.dart_audit_signals import detect_going_concern
        _gc = detect_going_concern(cleaned)
    except Exception:
        _gc = {"going_concern_doubt": False, "emphasis_of_matter": False,
               "severity": "none", "matched_phrase": "", "snippet": ""}

    return {
        "rcept_no": rcept_no,
        "report_nm": latest.get("report_nm", ""),
        "rcept_dt": latest.get("rcept_dt", ""),
        "bsns_year": bsns_year,
        "raw_text": section,
        "char_count": len(section),
        "related_party_text": related_party,
        "related_party_char_count": len(related_party),
        "litigation_text": litigation,
        "litigation_char_count": len(litigation),
        "ppe_note_text": ppe_note,
        "ppe_note_char_count": len(ppe_note),
        # 🚨 2026-08-17 — `kam_text`(표지를 담던 오슬라이스) → `audit_opinion_text` 교체.
        #   소비처는 `dart_kam.extract_kam` 하나이며 결정론 파싱으로 전환됐다.
        "audit_opinion_text": audit_opinion_text,
        "audit_opinion_char_count": len(audit_opinion_text),
        "going_concern_doubt": _gc["going_concern_doubt"],
        "emphasis_of_matter": _gc["emphasis_of_matter"],
        "going_concern_severity": _gc["severity"],
        "going_concern_phrase": _gc["matched_phrase"],
        "going_concern_snippet": _gc["snippet"],
    }


def _list_reports(corp_code: str, bgn_de: str, end_de: str, detail_ty: str) -> List[Dict[str, Any]]:
    """list.json 호출 → 보고서 후보 list. 실패 시 빈 list."""
    try:
        listing = _call("list.json", {
            "corp_code": corp_code,
            "bgn_de": bgn_de,
            "end_de": end_de,
            "pblntf_detail_ty": detail_ty,
            "page_count": "5",
            "sort": "date",
            "sort_mth": "desc",
        })
    except Exception:
        return []
    return [d for d in listing.get("list", []) if "보고서" in d.get("report_nm", "")]


_RAW_CACHE_DIR = os.path.join(DATA_DIR, "dart_raw_cache")
_RAW_CACHE_MIN_CHARS = 500          # downstream MIN_RAW_TEXT_LENGTH 과 동일 기준


def _raw_cache_path(corp_code: str, bsns_year: str) -> str:
    return os.path.join(_RAW_CACHE_DIR, f"{corp_code}_{bsns_year}.json.gz")


def _raw_cache_get(corp_code: str, bsns_year: str) -> Optional[Dict[str, Any]]:
    p = _raw_cache_path(corp_code, bsns_year)
    try:
        with gzip.open(p, "rt", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) and d.get("raw_text") else None
    except (OSError, ValueError):
        return None


def _raw_cache_put(corp_code: str, bsns_year: str, doc: Dict[str, Any]) -> None:
    """성공분만 저장 — 실패를 캐시하면 다음 run 이 영구히 재시도하지 않는다."""
    if not doc.get("raw_text") or doc.get("char_count", 0) < _RAW_CACHE_MIN_CHARS:
        return
    try:
        os.makedirs(_RAW_CACHE_DIR, exist_ok=True)
        with gzip.open(_raw_cache_path(corp_code, bsns_year), "wt", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
    except OSError as e:
        # 이 모듈은 logging 대신 stderr 관례 — 조용히 죽지 않게 반드시 남긴다
        sys.stderr.write(f"[dart_raw_cache] 저장 실패 {corp_code}_{bsns_year}: {e}\n")


_AUDIT_YEAR_RE = re.compile(r"^제\s*[\d,]+\s*기")
_AUDIT_KIND = ("감사보고서", "연결감사보고서")


def parse_audit_opinion_table(raw_text: str) -> Optional[Dict[str, Any]]:
    """사업보고서 'V. 회계감사인의 감사의견' 표를 **결정론 파싱** (LLM 미사용).

    🚨 2026-08-17 — KAM 판독을 LLM 으로 하려다 실측에서 기각했다. PM 지시
    "재미나이 호출이 무의미하면 아예 배제해" 에 대한 답이 이 함수다.

    ① LLM 은 5/5 종목을 `kam_count=0` 으로 냈다. 원인은 모델이 아니라 내가 어제 만든
       `kam_text` 슬라이스가 **사업보고서 표지**(회사명·대표이사·소재지)를 담고 있었기
       때문이다 — `'핵심감사사항'` 출현이 `raw_text` 8회 vs `kam_text` **0회**.
    ② 그런데 정작 필요한 사실이 **이미 정형 표**에 있다. 8열 `\\n\\n` 구분 고정이고
       마지막 열이 핵심감사사항이다. 즉 LLM 이 할 일이 없다.
    ③ 결정론 파서가 LLM 보다 **더 많이** 준다 — 감사인·감사의견·계속기업 불확실성·
       강조사항·핵심감사사항을 **3개 연도(당기/전기/전전기) × 개별/연결** 6행으로.
       감사인 교체(한미→삼일 · 한영→서현)도 그대로 보인다.
    → 비용 0 · 네트워크 0(이미 캐시된 `raw_text` 만 씀) · 결정론 · 추출 정확도로 검증 가능.

    🚨 `사업연도` 는 **병합 셀**이라 두 번째 행부터 생략된다(8열 → 7필드).
       고정폭 슬라이싱은 여기서 깨진다 — 토큰 스트림으로 읽는다.

    반환: {"columns": [...], "rows": [{사업연도, 구분, 감사인, 감사의견, ..., 핵심감사사항}]}
          표가 없으면 None. 🚨 사업보고서에 감사보고서가 첨부되지 않은 종목이 실제로 많다
          (표본 5 중 3) — 그건 결손이 아니라 **별도 공시**이므로 None 이 정상 응답이다.
    """
    if not raw_text:
        return None
    i = raw_text.find("핵심감사사항")
    if i < 0:
        return None
    # 헤더 시작 = 마지막 열(핵심감사사항) 직전 400자 안의 "사업연도"
    h = raw_text.rfind("사업연도", max(0, i - 400), i)
    if h < 0:
        return None
    cols = [f.strip() for f in re.split(r"\n\s*\n", raw_text[h:i + len("핵심감사사항")]) if f.strip()]
    if len(cols) < 6 or cols[-1] != "핵심감사사항":
        return None                     # 헤더가 온전하지 않으면 추측하지 않는다
    body = [f.strip() for f in
            re.split(r"\n\s*\n", raw_text[i + len("핵심감사사항"):i + 6000]) if f.strip()]
    tail = cols[1:]                     # 병합 셀(사업연도)을 뺀 나머지 열
    rows: List[Dict[str, Any]] = []
    year: Optional[str] = None
    k = 0
    while k < len(body):
        tok = body[k]
        if _AUDIT_YEAR_RE.match(tok):
            year = tok
            k += 1
            continue
        if tok in _AUDIT_KIND and year and k + len(tail) <= len(body):
            rows.append({"사업연도": year, **dict(zip(tail, body[k:k + len(tail)]))})
            k += len(tail)
            continue
        break                           # 표 밖으로 나갔다 — 더 읽지 않는다
    return {"columns": cols, "rows": rows} if rows else None


def fetch_business_facilities_raw(
    corp_code: str,
    bsns_year: Optional[str] = None,
    use_cache: bool = True,
) -> Dict[str, Any]:
    """
    최신 사업보고서(A001) 본문에서 'II. 사업의 내용' 섹션 원문 슬라이스.
    A001 추출 실패 시 반기(A002) + 분기(A003) 보고서 fallback (PM 결정 2026-05-26).
    - REITs:    투자자산 현황 테이블 (주소·면적·감정가·임대율)
    - 일반 기업: 국내/해외 사업장 현황 (공장·R&D·물류·매장)

    반환: {rcept_no, report_nm, rcept_dt, raw_text, char_count, source_report_ty}
    또는 error 키. LLM 파싱(api.analyzers.facilities_parser)의 입력.

    2026-05-26 PM 결정: A001 section_not_found 회복 path.
    - WHY: 15 KR 종목 중 6 (175330/098070/114090/000240/214450/336570) 사업보고서
            본문 ZIP regex 추출 실패 (no_raw_or_too_short / section_not_found).
    - DATA: dart_analysis_cache.json 9/15 OK → 회복 목표 ≥ 13/15.
    - EXPECTED: 분기/반기보고서 "II. 사업의 내용" 동일 구조 — fallback 회복.
    """
    if not DART_API_KEY:
        return {"error": "no_dart_api_key"}

    now = now_kst()
    if bsns_year is None:
        bsns_year = str(now.year - 1)

    # 🚨 2026-08-17 — 디스크 캐시 read-through. 없어서 **같은 문서를 축마다 다시 받았다.**
    #   이 함수 하나가 사업보고서 ZIP 다운로드 + 정규식 슬라이스라 종목당 4분대다
    #   (실측: 코너 3종목 13분 35초에도 미완). 그런데 소비 축이 4개다 —
    #   kam · litigation · related_party · business 가 **각각 따로** 받아왔다.
    #   인수인계 문서는 "추가 DART 호출 0" 이라 적어뒀는데 근거가 없었다.
    #   연 1회 갱신되는 사업보고서라 (corp_code, bsns_year) 키는 자연히 안정적이다.
    #   저장은 gzip · `data/dart_raw_cache/`(gitignore) — 원문 슬라이스라 용량이 크고
    #   재취득 가능한 파생물이므로 발행·추적 대상이 아니다.
    if use_cache:
        _hit = _raw_cache_get(corp_code, bsns_year)
        if _hit is not None:
            _hit["_from_cache"] = True
            return _hit

    bgn = f"{int(bsns_year)}0101"
    end = now.strftime("%Y%m%d")
    prev_bgn = f"{int(bsns_year) - 1}0101"

    # A001 (사업보고서) → A002 (반기) → A003 (분기) 순.
    # A001 은 직전 연도까지 확장 검색 (회계연도 종료 ~3개월 lag).
    # downstream MIN_RAW_TEXT_LENGTH=500 와 정합 — 500↑ 면 A001 즉시 반환,
    # 500 미만은 A002/A003 시도 후 best (max char_count) 반환.
    last_error: Dict[str, Any] = {"error": "no_report_found"}
    attempts: List[Dict[str, Any]] = []

    for detail_ty in ("A001", "A002", "A003"):
        candidates = _list_reports(corp_code, bgn, end, detail_ty)
        if not candidates and detail_ty == "A001":
            candidates = _list_reports(corp_code, prev_bgn, end, detail_ty)
        if not candidates:
            continue

        latest = candidates[0]
        rcept_no = latest.get("rcept_no", "")
        if not rcept_no:
            continue

        result = _extract_section_from_rcept(rcept_no, latest, bsns_year)
        if result.get("raw_text"):
            result["source_report_ty"] = detail_ty
            if result.get("char_count", 0) >= 500:
                _raw_cache_put(corp_code, bsns_year, result)
                return result  # downstream MIN 충족 → 즉시 반환
            attempts.append(result)
        else:
            last_error = result

    if attempts:
        # 500 미달이지만 raw_text 있음 — 가장 긴 것 반환.
        # 🚨 캐시 저장 안 함 — `_raw_cache_put` 이 500 미달을 걸러낸다. 다음 run 이
        #   재시도해 더 긴 본문을 잡을 여지를 남긴다(공시가 정정될 수 있다).
        return max(attempts, key=lambda r: r.get("char_count", 0))
    return last_error


def fetch_cashflow(corp_code: str, bsns_year: str) -> Dict[str, Any]:
    """영업/투자/재무 현금흐름 추출. Gemini 재무 건전성 판단용."""
    data = _get_fnltt_data(corp_code, bsns_year)

    cf = {"operating": 0, "investing": 0, "financing": 0, "free_cashflow": 0}

    for item in data.get("list", []):
        if item.get("sj_div") != "CF":
            continue
        acct = item.get("account_nm", "")
        amount = _parse_int(item.get("thstrm_amount"))
        if "영업활동" in acct:
            cf["operating"] = amount
        elif "투자활동" in acct:
            cf["investing"] = amount
        elif "재무활동" in acct:
            cf["financing"] = amount

    cf["free_cashflow"] = cf["operating"] + cf["investing"]
    return cf


# ── 7. 타법인 출자 현황(관계회사 지분) ──────────────────

def _parse_float(value: Any) -> float:
    if value is None:
        return 0.0
    s = str(value).replace(",", "").replace(" ", "").strip()
    if not s or s == "-":
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def fetch_subsidiary_investments(corp_code: str, bsns_year: str) -> List[Dict]:
    """타법인 출자 현황 — 이 회사가 보유한 타법인 지분 목록.
    OpenDART otrCprInvstmntSttus.json: 사업보고서의 타법인 출자 현황 공시.

    2026-05-29 fix — 이전 endpoint name `otcprSttus.json` 는 DART status=101
    (잘못된 URL). 정확한 endpoint = `otrCprInvstmntSttus.json` (DART 실 호출 검증
    삼성전자 N=138 list 정상 응답). [[feedback_external_api_4bucket_verify]] 정합.
    """
    data = _call("otrCprInvstmntSttus.json", {
        "corp_code": corp_code,
        "bsns_year": bsns_year,
        "reprt_code": ANNUAL_REPORT,
    })
    results = []
    for d in data.get("list", []):
        inv_name = (d.get("inv_prm") or "").strip()
        if not inv_name or inv_name == "-":
            continue
        results.append({
            "inv_corp_name": inv_name,
            "initial_investment": _parse_int(d.get("frst_acqs_amount")),
            "initial_date": (d.get("frst_acqs_de") or "").strip(),
            "begin_balance_qty": _parse_int(d.get("bsis_blce_co")),
            "increase_qty": _parse_int(d.get("incrs_co")),
            "decrease_qty": _parse_int(d.get("dcrs_co")),
            "end_balance_qty": _parse_int(d.get("trmend_blce_co")),
            "ownership_pct": _parse_float(d.get("trmend_blce_qota_rt")),
            "book_value": _parse_int(d.get("trmend_blce_acntbk_amount")),
            "fair_value": _parse_int(d.get("trmend_blce_mktcap_amount")),
            "recent_biz_year_revenue": _parse_int(d.get("recent_bsns_year_fnnr_sttus_tot_amount")),
            "recent_biz_year_profit": _parse_int(d.get("recent_bsns_year_fnnr_sttus_thstrm_ntpf")),
        })
    return results


# ── 6. 배당정보 ─────────────────────────────────────────

def fetch_dividends(corp_code: str, bsns_year: str) -> List[Dict]:
    data = _call("alotMatter.json", {
        "corp_code": corp_code,
        "bsns_year": bsns_year,
        "reprt_code": ANNUAL_REPORT,
    })
    return [
        {
            "category": d.get("se", ""),
            "current": d.get("thstrm", ""),
            "previous": d.get("frmtrm", ""),
        }
        for d in data.get("list", [])
    ]


# ── 오케스트레이션 ───────────────────────────────────────

# ── 7. 자사주 취득/처분 현황 ─────────────────────────
#
# Brain audit: 매입 우세 → 주주환원 긍정 시그널 / 처분 우세 → 자금조달·지분매각 주의 시그널.

def fetch_treasury_stock(corp_code: str, bsns_year: str) -> Dict[str, Any]:
    """자기주식 취득 및 처분현황 (사업보고서 기준).

    DART API: tesstkAcqsDspsSttus.json
    Returns: rows + 누적 취득/처분/소각 + signal (positive/warning/neutral).
    """
    data = _call("tesstkAcqsDspsSttus.json", {
        "corp_code": corp_code,
        "bsns_year": bsns_year,
        "reprt_code": ANNUAL_REPORT,
    })

    rows: List[Dict[str, Any]] = []
    total_acq = 0
    total_dsp = 0
    total_incnr = 0

    for item in data.get("list", []):
        acq = _parse_int(item.get("change_qy_acqs"))
        dsp = _parse_int(item.get("change_qy_dsps"))
        incnr = _parse_int(item.get("change_qy_incnr"))
        rows.append({
            "stock_knd": item.get("stock_knd", ""),
            "acqs_mth1": item.get("acqs_mth1", ""),
            "acqs_mth2": item.get("acqs_mth2", ""),
            "acqs_mth3": item.get("acqs_mth3", ""),
            "bsis_qy": _parse_int(item.get("bsis_qy")),
            "change_qy_acqs": acq,
            "change_qy_dsps": dsp,
            "change_qy_incnr": incnr,
            "trmend_qy": _parse_int(item.get("trmend_qy")),
            "rm": item.get("rm", ""),
        })
        total_acq += acq
        total_dsp += dsp
        total_incnr += incnr

    net_change = total_acq - total_dsp - total_incnr
    if total_acq > total_dsp:
        signal = "positive"
    elif total_dsp > total_acq:
        signal = "warning"
    else:
        signal = "neutral"

    return {
        "rows": rows,
        "row_count": len(rows),
        "total_acquisition_qty": total_acq,
        "total_disposal_qty": total_dsp,
        "total_cancellation_qty": total_incnr,
        "net_change": net_change,
        "signal": signal,
        "status": data.get("status", ""),
    }


# ── 8. 임원 개인별 보수 현황 ───────────────────────────
#
# Brain audit: 5억 이상 공시 대상 임원 개인 보수.
# 매출/영업이익 대비 보수 총액이 과다하면 거버넌스 경고 팩터.

def fetch_exec_compensation(corp_code: str, bsns_year: str) -> Dict[str, Any]:
    """임원 개인별 보수 현황 (5억 이상 공시 대상).

    DART API: hmvAuditIndvdlBySttus.json
    Returns: 개인별 보수 list + 총보수/최고보수/공시인원수.
    """
    data = _call("hmvAuditIndvdlBySttus.json", {
        "corp_code": corp_code,
        "bsns_year": bsns_year,
        "reprt_code": ANNUAL_REPORT,
    })

    individuals: List[Dict[str, Any]] = []
    total_pay = 0
    top_pay = 0

    for item in data.get("list", []):
        amt = _parse_int(item.get("mendng_totamt"))
        individuals.append({
            "nm": item.get("nm", ""),
            "ofcps": item.get("ofcps", ""),
            "mendng_totamt": amt,
            # 보수 산정 기준 — 길어서 200자 truncate
            "mendng_detail": (item.get("mendng_totamt_ct_incls_mendng") or "")[:200],
        })
        total_pay += amt
        if amt > top_pay:
            top_pay = amt

    return {
        "individuals": individuals,
        "count_disclosed": len(individuals),
        "total_pay_won": total_pay,
        "top_pay_won": top_pay,
        "status": data.get("status", ""),
    }


# ── 9. 대주주 (5% 이상) 지분 변동 ───────────────────────
#
# Brain audit: 변동 후 - 변동 전 지분율 차이로 신호 분류.
# delta < -0.5%p = warning (내부자 매도), > +0.5%p = positive (확신), 그 외 neutral.

def fetch_major_shareholder_changes(corp_code: str, bsns_year: str) -> List[Dict[str, Any]]:
    """대주주 (5% 이상 보유) 지분 변동 보고서 목록 (사업연도 기준).

    DART API: hyslrChgSttus.json
    Returns: 변동 보고 list (rcept_dt, hyslr_nm, 변동전/후 지분율, delta, signal).

    2026-05-29 fix — 이전 호출 파라미터 `bgn_de/end_de` 는 DART status=100
    (필수값 corp_code/bsns_year/reprt_code 누락). 정확한 spec = bsns_year + reprt_code
    (DART 실 호출 검증 삼성전자 2024 N=1 list 정상 응답). caller signature 도 정정.
    [[feedback_external_api_4bucket_verify]] 정합.
    """
    data = _call("hyslrChgSttus.json", {
        "corp_code": corp_code,
        "bsns_year": bsns_year,
        "reprt_code": ANNUAL_REPORT,
    })

    rows: List[Dict[str, Any]] = []
    for item in data.get("list", []):
        # 변동 전/후 지분율 — DART 응답이 문자열 (e.g. "5.10")
        try:
            rate_before = float(str(item.get("chnge_pos_jb_qota_rt") or "0").replace(",", ""))
        except (TypeError, ValueError):
            rate_before = 0.0
        try:
            rate_after = float(str(item.get("chnge_aft_jb_qota_rt") or "0").replace(",", ""))
        except (TypeError, ValueError):
            rate_after = 0.0
        delta = rate_after - rate_before

        if delta <= -0.5:
            signal = "warning"
        elif delta >= 0.5:
            signal = "positive"
        else:
            signal = "neutral"

        rows.append({
            "rcept_no": item.get("rcept_no", ""),
            "rcept_dt": item.get("rcept_dt", ""),
            "hyslr_nm": item.get("hyslr_nm", ""),
            "chnge_jb_de": item.get("chnge_jb_de", ""),
            "chnge_pos_jb": _parse_int(item.get("chnge_pos_jb")),
            "chnge_aft_jb": _parse_int(item.get("chnge_aft_jb")),
            "chnge_pos_jb_qota_rt": rate_before,
            "chnge_aft_jb_qota_rt": rate_after,
            "delta_pct_pt": round(delta, 4),
            "chnge_resn": item.get("chnge_resn", ""),
            "signal": signal,
        })
    return rows


def scout(ticker: str, bsns_year: Optional[str] = None) -> Dict[str, Any]:
    """단일 종목 6대 데이터 수집. 감사의견 부적정 시 critical_error를 담아 즉시 반환."""
    if not DART_API_KEY:
        raise RuntimeError("DART_API_KEY 환경변수가 설정되지 않았습니다.")

    corp_code = get_corp_code(ticker)
    if not corp_code:
        return {"ticker": ticker, "error": f"매핑 없음: {ticker}"}

    now = now_kst()
    if bsns_year is None:
        bsns_year = str(now.year - 1)
    bgn_de = f"{int(bsns_year)}0101"
    end_de = now.strftime("%Y%m%d")

    result: Dict[str, Any] = {
        "ticker": ticker.split(".")[0],
        "name": ALL_STOCKS.get(ticker, ticker),
        "corp_code": corp_code,
        "bsns_year": bsns_year,
        "collected_at": now.isoformat(),
    }

    try:
        result["audit_opinion"] = check_audit(corp_code, bsns_year)
    except CriticalAuditError as e:
        result["audit_opinion"] = str(e)
        result["critical_error"] = True
        return result

    collectors = [
        ("disclosures",            lambda: fetch_disclosures(corp_code, bgn_de, end_de)),
        ("cb_bw",                  lambda: fetch_cb_bw(corp_code, bgn_de, end_de)),
        ("major_shareholders",     lambda: fetch_major_shareholders(corp_code, bsns_year)),
        ("employees",              lambda: fetch_employees(corp_code, bsns_year)),
        ("financials",             lambda: fetch_financials(corp_code, bsns_year)),
        ("property_assets",        lambda: fetch_property_assets(corp_code, bsns_year)),
        ("cashflow",               lambda: fetch_cashflow(corp_code, bsns_year)),
        ("dividends",              lambda: fetch_dividends(corp_code, bsns_year)),
        ("subsidiary_investments", lambda: fetch_subsidiary_investments(corp_code, bsns_year)),
        # ── 거버넌스 시그널 (Brain Audit Phase 1.B) ──
        ("treasury_stock",            lambda: fetch_treasury_stock(corp_code, bsns_year)),
        ("exec_compensation",         lambda: fetch_exec_compensation(corp_code, bsns_year)),
        ("major_shareholder_changes", lambda: fetch_major_shareholder_changes(corp_code, bsns_year)),
    ]

    for key, fn in collectors:
        try:
            result[key] = fn()
        except Exception as e:
            result[key] = {"error": str(e)}

    _fetch_fnltt_cached.cache_clear()
    return result


def scout_all(
    tickers: Optional[List[str]] = None,
    bsns_year: Optional[str] = None,
) -> Dict[str, Any]:
    """복수 종목을 수집하여 data/raw_data.json에 저장한다."""
    if tickers is None:
        tickers = list(ALL_STOCKS.keys())

    results: Dict[str, Any] = {}
    total = len(tickers)

    for i, ticker in enumerate(tickers, 1):
        name = ALL_STOCKS.get(ticker, ticker)
        print(f"  [{i}/{total}] {name} 스카우팅...", end="")

        data = scout(ticker, bsns_year)
        key = ticker.split(".")[0]
        results[key] = data

        if data.get("critical_error"):
            print(f" CRITICAL — {data.get('audit_opinion')}")
        elif data.get("error"):
            print(f" SKIP — {data['error']}")
        else:
            print(" OK")

    output = {
        "updated_at": now_kst().isoformat(),
        "bsns_year": bsns_year or str(now_kst().year - 1),
        "count": len(results),
        "stocks": results,
    }

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(RAW_DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    return output


if __name__ == "__main__":
    print("DartScout — OpenDART 6대 핵심 데이터 수집 시작...")
    result = scout_all()
    critical = sum(1 for v in result["stocks"].values() if v.get("critical_error"))
    print(f"\n완료: {result['count']}개 종목 (critical: {critical}) → {RAW_DATA_PATH}")
