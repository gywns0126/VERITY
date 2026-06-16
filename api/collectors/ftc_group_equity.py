"""
FtcGroupEquityScout — 공정위 기업집단포털 OpenAPI (data.go.kr 1130000)

공식 대규모기업집단 소속회사 주주현황(지분율) + 소속회사 목록 수집.
나무위키 지분도의 진짜 원천(법적 강제공시). DART(hyslrSttus/타법인출자)와 이중 출처.

검증된 엔드포인트 (2026-06-16 실호출, [[project_equity_realestate_data_sourcing]]):
  - stockholderCompSttusList/stockholderCompSttusListApi — 소속회사 주주현황(지분율)
  - appnGroupAffiList/appnGroupAffiListApi — 지정 대규모기업집단 소속회사 목록
파라미터: serviceKey, pageNo, numOfRows, presentnYear(지정년도)

키: PUBLIC_DATA_API_KEY (data.go.kr 일반 인증키). 부재 시 graceful no-op.
join key: jurirno(법인등록번호) / bizrno(사업자번호) — 이름 매칭 회피
         (FTC entrprsNm "(주)비지에프" vs 종목명 "BGF" 불일치 회피).
한계: 연 1회 지정 스냅샷 (presentnYear) → as-of 라벨 의무 (RULE 7). 대규모기업집단만 커버.
"""
import os
import sys
import json
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from api.config import PUBLIC_DATA_API_KEY, DATA_DIR, now_kst

BASE_URL = "https://apis.data.go.kr/1130000"
FTC_GROUP_EQUITY_PATH = os.path.join(DATA_DIR, "ftc_group_equity.json")

_PAGE_ROWS = 1000          # data.go.kr 페이지당 행 (totalCount 까지 paginate)
_MAX_PAGES = 30            # 안전 상한 (8천여 건 → ~9페이지)
_REQ_TIMEOUT = 25


def _call(service: str, operation: str, params: Dict[str, Any]) -> Optional[ET.Element]:
    """data.go.kr 1130000 단일 호출 → XML root. 실패 시 None.

    serviceKey 는 PUBLIC_DATA_API_KEY 를 URL 인코딩해서 전달
    (data.go.kr 일반 인증키 = 미인코딩 원본, requests 가 재인코딩하면 깨지므로 직접 quote).
    """
    if not PUBLIC_DATA_API_KEY:
        return None
    q = {"serviceKey": PUBLIC_DATA_API_KEY, **params}
    # serviceKey 만 직접 인코딩, 나머지는 urlencode
    qs = "serviceKey=" + urllib.parse.quote(PUBLIC_DATA_API_KEY, safe="")
    for k, v in params.items():
        qs += f"&{urllib.parse.quote(str(k))}={urllib.parse.quote(str(v))}"
    url = f"{BASE_URL}/{service}/{operation}?{qs}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=_REQ_TIMEOUT) as r:
            body = r.read().decode("utf-8", "replace")
        root = ET.fromstring(body)
        code = root.findtext("resultCode")
        # 2026-06-17 fix: data.go.kr 게이트웨이 에러(키 미등록/쿼터)는 resultCode 없이
        # cmmMsgHeader/returnAuthMsg 봉투로 옴 → None 을 무조건 성공 처리하면 키/쿼터 장애가
        # '데이터 없음'으로 silent 오귀인. cmmMsgHeader 있으면 에러 로깅 후 None.
        if code is None:
            hdr = root.find(".//cmmMsgHeader")
            if hdr is not None:
                auth = hdr.findtext("returnAuthMsg") or hdr.findtext("errMsg") or "gateway_error"
                rc = hdr.findtext("returnReasonCode") or "?"
                sys.stderr.write(f"[ftc] {operation} 게이트웨이 에러 code={rc} msg={auth}\n")
                return None
        if code not in (None, "00"):
            # 97 = presentnYear 부적합 등. 호출자가 처리.
            sys.stderr.write(
                f"[ftc] {operation} resultCode={code} "
                f"msg={root.findtext('resultMsg')}\n"
            )
            return None
        return root
    except Exception as e:
        sys.stderr.write(f"[ftc] {operation} 호출 실패: {type(e).__name__}: {e}\n")
        return None


def _paginate(service: str, operation: str, item_tag: str,
              extra: Dict[str, Any]) -> List[Dict[str, str]]:
    """totalCount 까지 페이지 순회 → 평탄 dict 리스트."""
    out: List[Dict[str, str]] = []
    for page in range(1, _MAX_PAGES + 1):
        root = _call(service, operation, {
            "pageNo": page, "numOfRows": _PAGE_ROWS, **extra,
        })
        if root is None:
            break
        items = root.findall(item_tag)
        for it in items:
            out.append({child.tag: (child.text or "").strip() for child in it})
        total = root.findtext("totalCount")
        try:
            total_n = int(total) if total else 0
        except ValueError:
            total_n = 0
        if not items or len(out) >= total_n:
            break
        time.sleep(0.2)  # rate 예의
    return out


def _to_float(v: Any) -> float:
    try:
        return round(float(str(v).replace(",", "").strip()), 2)
    except (ValueError, TypeError):
        return 0.0


def _to_int(v: Any) -> int:
    """totalCount 등 안전 int 변환 (공백·비숫자 → 0). 2026-06-17: resolver int() 비가드 fix."""
    try:
        return int(str(v).replace(",", "").strip())
    except (ValueError, TypeError):
        return 0


def fetch_shareholders(presentn_year: str) -> List[Dict[str, Any]]:
    """소속회사 주주현황(지분율) 전체. presentn_year = 지정년도(예 '2026')."""
    rows = _paginate(
        "stockholderCompSttusList", "stockholderCompSttusListApi",
        "stockholderCompSttus", {"presentnYear": presentn_year},
    )
    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append({
            "group": r.get("unityGrupNm", ""),
            "company": r.get("entrprsNm", ""),
            "jurirno": r.get("jurirno", ""),
            "bizrno": r.get("bizrno", ""),
            "shareholder": r.get("shrholdrNm", ""),
            "shareholder_type": r.get("shrholdrSe", ""),   # 동일인/특수관계인/계열회사/기타
            "qota_rate": _to_float(r.get("allQotaRate")),  # 전체 지분율 %
            "common_rate": _to_float(r.get("nrmltyQotaRate")),
            "pref_rate": _to_float(r.get("priorQotaRate")),
            "shares": r.get("posesnStockCo", ""),
        })
    return out


def fetch_affiliates(presentn_year: str) -> List[Dict[str, Any]]:
    """지정 대규모기업집단 소속회사 목록. presentn_year = 지정년도."""
    rows = _paginate(
        "appnGroupAffiList", "appnGroupAffiListApi",
        "appnGroupAffi", {"presentnYear": presentn_year},
    )
    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append({
            "group": r.get("unityGrupNm", ""),
            "company": r.get("entrprsNm", ""),
            "jurirno": r.get("jurirno", ""),
            "bizrno": r.get("bizrno", ""),
            "representative": r.get("rprsntvNm", ""),
            "found_date": r.get("fondDe", ""),
        })
    return out


def fetch_holding_companies(presentn_ym: str) -> List[Dict[str, Any]]:
    """지주회사 자회사·손자회사 현황. presentn_ym = 공개년월(YYYYMM, 6월/12월 공개).

    operation = holdingProgCompStusListApi (service 의 Sttus 와 달리 Stus — 실호출 검증).
    cdpny_qota_rate = 출자비율 원값 (지분율과 단위 상이 가능 — 라벨 보수적).
    """
    # 주의: operation 은 ...StusListApi(Stus) 인데 item 태그는 holdingProgCompSttus(Sttus, 검증).
    rows = _paginate(
        "holdingProgCompSttusList", "holdingProgCompStusListApi",
        "holdingProgCompSttus", {"presentnYm": presentn_ym},
    )
    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append({
            "holding_company": r.get("unityGrupNm", ""),     # 지주회사명
            "holding_jurirno": r.get("jurirno", ""),
            "finance_type": r.get("fnncSeNm", ""),            # 일반/금융
            "company": r.get("cdpnyNm", ""),                  # 자/손자회사명
            "company_jurirno": r.get("cdpnyJurirno", ""),
            "relation": r.get("hldcpSeNm", ""),               # 자회사/손자회사
            "parent_jurirno": r.get("parentJurirno", ""),     # 손자회사면 모회사
            "cdpny_qota_rate": _to_float(r.get("cdpnyQotaRate")),
        })
    return out


def _resolve_presentn_ym() -> Optional[str]:
    """지주회사 API 최신 공개년월 탐색 — 당해/전년 12월·6월 순."""
    if not PUBLIC_DATA_API_KEY:
        return None
    y = now_kst().year
    for ym in (f"{y}12", f"{y}06", f"{y-1}12", f"{y-1}06"):
        root = _call("holdingProgCompSttusList", "holdingProgCompStusListApi",
                     {"pageNo": 1, "numOfRows": 1, "presentnYm": ym})
        if root is not None and root.findtext("resultCode") == "00":
            total = root.findtext("totalCount")
            if _to_int(total) > 0:
                return ym
    return None


def _resolve_presentn_year() -> Optional[str]:
    """사용 가능한 최신 지정년도 탐색 — 당해부터 역순 3년."""
    if not PUBLIC_DATA_API_KEY:
        return None
    base_year = now_kst().year
    for y in (base_year, base_year - 1, base_year - 2):
        root = _call("stockholderCompSttusList", "stockholderCompSttusListApi",
                     {"pageNo": 1, "numOfRows": 1, "presentnYear": str(y)})
        if root is not None and root.findtext("resultCode") == "00":
            total = root.findtext("totalCount")
            if _to_int(total) > 0:
                return str(y)
    return None


def build_ftc_group_equity(presentn_year: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """공정위 주주현황 + 소속회사를 bizrno/jurirno 인덱스로 결합.

    Returns:
        {
          "as_of_year": "2026",
          "collected_at": "...",
          "by_bizrno": { "1208144752": {group, company, jurirno, shareholders:[...]} },
          "by_jurirno": { "1101111105215": <same ref> },
          "groups": { "BGF": ["(주)비지에프", ...] },
          "company_count": int, "shareholder_count": int, "group_count": int
        }
    """
    if not PUBLIC_DATA_API_KEY:
        sys.stderr.write("[ftc] PUBLIC_DATA_API_KEY 부재 — skip\n")
        return None
    if presentn_year is None:
        presentn_year = _resolve_presentn_year()
    if not presentn_year:
        sys.stderr.write("[ftc] 사용 가능한 presentnYear 미발견 — skip\n")
        return None

    shareholders = fetch_shareholders(presentn_year)
    affiliates = fetch_affiliates(presentn_year)
    if not shareholders:
        return None

    by_bizrno: Dict[str, Dict[str, Any]] = {}
    by_jurirno: Dict[str, Dict[str, Any]] = {}
    groups: Dict[str, set] = {}

    def _company_entry(group: str, company: str, jurirno: str, bizrno: str) -> Dict[str, Any]:
        key = bizrno or jurirno
        entry = by_bizrno.get(bizrno) if bizrno else None
        if entry is None and jurirno:
            entry = by_jurirno.get(jurirno)
        if entry is None:
            entry = {
                "group": group, "company": company,
                "jurirno": jurirno, "bizrno": bizrno,
                "shareholders": [],
            }
            if bizrno:
                by_bizrno[bizrno] = entry
            if jurirno:
                by_jurirno[jurirno] = entry
        return entry

    # 소속회사 목록 먼저 등록 (주주 없는 회사도 노드로 존재)
    for a in affiliates:
        e = _company_entry(a["group"], a["company"], a["jurirno"], a["bizrno"])
        e.setdefault("representative", a.get("representative", ""))
        e.setdefault("found_date", a.get("found_date", ""))
        groups.setdefault(a["group"], set()).add(a["company"])

    # 주주현황 결합
    for s in shareholders:
        e = _company_entry(s["group"], s["company"], s["jurirno"], s["bizrno"])
        e["shareholders"].append({
            "name": s["shareholder"],
            "type": s["shareholder_type"],
            "qota_rate": s["qota_rate"],
            "common_rate": s["common_rate"],
            "pref_rate": s["pref_rate"],
        })
        groups.setdefault(s["group"], set()).add(s["company"])

    # 각 회사 주주 지분율 내림차순
    for e in by_bizrno.values():
        e["shareholders"].sort(key=lambda x: x.get("qota_rate") or 0, reverse=True)

    # 지주회사 자/손자회사 (별도 공개년월 — 6/12월). 지주회사 jurirno 인덱스.
    holdings_by_jurirno: Dict[str, Dict[str, Any]] = {}
    holding_ym = _resolve_presentn_ym()
    if holding_ym:
        for h in fetch_holding_companies(holding_ym):
            hj = h.get("holding_jurirno")
            if not hj:
                continue
            hentry = holdings_by_jurirno.get(hj)
            if hentry is None:
                hentry = {"holding_company": h["holding_company"], "subsidiaries": []}
                holdings_by_jurirno[hj] = hentry
            hentry["subsidiaries"].append({
                "company": h["company"],
                "jurirno": h["company_jurirno"],
                "relation": h["relation"],
                "qota_rate": h["cdpny_qota_rate"],
                "parent_jurirno": h["parent_jurirno"],
            })

    return {
        "as_of_year": presentn_year,
        "holding_as_of_ym": holding_ym,
        "collected_at": now_kst().isoformat(),
        "source": "공정거래위원회 기업집단포털 (data.go.kr 1130000)",
        "by_bizrno": by_bizrno,
        "by_jurirno": by_jurirno,
        "holdings_by_jurirno": holdings_by_jurirno,
        "groups": {g: sorted(cs) for g, cs in groups.items()},
        "company_count": len(by_bizrno) or len(by_jurirno),
        "shareholder_count": len(shareholders),
        "group_count": len(groups),
        "holding_count": len(holdings_by_jurirno),
    }


# ── 종목 join (corp_code → bizrno/jurirno → FTC 공식 주주) ──────────

_CORP_IDNO_CACHE_PATH = os.path.join(DATA_DIR, "corp_idno_cache.json")
_idno_cache: Optional[Dict[str, Dict[str, str]]] = None
_ftc_cache: Optional[Dict[str, Any]] = None


def _load_idno_cache() -> Dict[str, Dict[str, str]]:
    global _idno_cache
    if _idno_cache is None:
        try:
            with open(_CORP_IDNO_CACHE_PATH, "r", encoding="utf-8") as f:
                _idno_cache = json.load(f)
        except Exception:
            _idno_cache = {}
    return _idno_cache


def _get_corp_idno(corp_code: str) -> Dict[str, str]:
    """corp_code → {jurir_no, bizr_no}. DART company.json, 파일 캐시 (정적 정보)."""
    cache = _load_idno_cache()
    if corp_code in cache:
        return cache[corp_code]
    from api.config import DART_API_KEY
    result = {"jurir_no": "", "bizr_no": ""}
    if DART_API_KEY:
        try:
            url = (f"https://opendart.fss.or.kr/api/company.json"
                   f"?crtfc_key={DART_API_KEY}&corp_code={corp_code}")
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=_REQ_TIMEOUT) as r:
                d = json.loads(r.read().decode("utf-8", "replace"))
            if d.get("status") == "000":
                result = {"jurir_no": d.get("jurir_no", ""), "bizr_no": d.get("bizr_no", "")}
        except Exception as e:
            sys.stderr.write(f"[ftc] company.json {corp_code} 실패: {type(e).__name__}\n")
    cache[corp_code] = result
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(_CORP_IDNO_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return result


def lookup_official_shareholders(corp_code: str) -> Optional[Dict[str, Any]]:
    """corp_code 의 공정위 공식 주주현황(지분율) 반환. 미매칭/데이터 없으면 None.

    DART 최대주주(hyslrSttus)와 이중 출처 — GroupTab 교차검증용.
    """
    global _ftc_cache
    if _ftc_cache is None:
        _ftc_cache = load_ftc_group_equity() or {}
    if not _ftc_cache or not corp_code:
        return None
    idno = _get_corp_idno(corp_code)
    biz, jur = idno.get("bizr_no", ""), idno.get("jurir_no", "")
    entry = None
    if biz:
        entry = (_ftc_cache.get("by_bizrno") or {}).get(biz)
    if entry is None and jur:
        entry = (_ftc_cache.get("by_jurirno") or {}).get(jur)
    # 지주회사 자/손자회사 (이 종목이 지주회사면)
    holding = None
    if jur:
        h = (_ftc_cache.get("holdings_by_jurirno") or {}).get(jur)
        if h and h.get("subsidiaries"):
            holding = {
                "as_of_ym": _ftc_cache.get("holding_as_of_ym"),
                "subsidiaries": h["subsidiaries"][:20],
            }
    if not entry and not holding:
        return None
    return {
        "group": entry.get("group") if entry else None,
        "as_of_year": _ftc_cache.get("as_of_year"),
        "source": _ftc_cache.get("source"),
        "shareholders": (entry.get("shareholders") or [])[:10] if entry else [],
        "holding": holding,
    }


def save_ftc_group_equity(data: Dict[str, Any]) -> str:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(FTC_GROUP_EQUITY_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return FTC_GROUP_EQUITY_PATH


def load_ftc_group_equity() -> Optional[Dict[str, Any]]:
    if not os.path.exists(FTC_GROUP_EQUITY_PATH):
        return None
    try:
        with open(FTC_GROUP_EQUITY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


_FTC_MAX_AGE_S = 90 * 24 * 3600  # 90일 — 연 1회 지정(5월) 흡수 주기 등가
_ftc_ensured = False


def ensure_ftc_group_equity() -> None:
    """ftc_group_equity.json 부재/90일 초과 시 재수집. fail-safe (실패해도 진행).

    collect_group_structures(데일리 파이프라인) 경유로 발동 → 전용 cron 불필요.
    프로세스당 1회 (RULE 8 — 신 데이터 갱신 경로 정합).
    """
    global _ftc_ensured
    if _ftc_ensured:
        return
    _ftc_ensured = True
    if not PUBLIC_DATA_API_KEY:
        return
    try:
        need = True
        if os.path.exists(FTC_GROUP_EQUITY_PATH):
            need = (time.time() - os.path.getmtime(FTC_GROUP_EQUITY_PATH)) > _FTC_MAX_AGE_S
        if need:
            sys.stderr.write("[ftc] ftc_group_equity.json 생성/갱신 (공정위 API)\n")
            data = build_ftc_group_equity()
            if data:
                save_ftc_group_equity(data)
                global _ftc_cache
                _ftc_cache = data
    except Exception as e:
        sys.stderr.write(f"[ftc] ensure 실패(무시): {type(e).__name__}: {e}\n")


if __name__ == "__main__":
    print("공정위 기업집단 지분 수집 시작...")
    result = build_ftc_group_equity()
    if result:
        path = save_ftc_group_equity(result)
        print(f"완료: {result['as_of_year']}년 지정 · 회사 {result['company_count']} · "
              f"주주 {result['shareholder_count']} · 집단 {result['group_count']} → {path}")
    else:
        print("실패 (키 부재 또는 데이터 없음)")
