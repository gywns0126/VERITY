"""
ipo_scout — IPO 파이프라인 Watch (DART 증권신고서 중심)

상장 전(pre-IPO) 종목 후보를 수집한다. "비상장 기대주 미리 선별"의 검증 가능한 형태.

수집 경로 (PM 결정 2026-06-07: DART 증권신고서 중심):
  list.json  pblntf_detail_ty=C001 (증권신고서/지분증권)
    → corp_cls="E" (미상장) 필터로 신규 IPO 후보 격리
    → SPAC(기업인수목적) + 증권발행실적보고서 제외
    → 정정 공시는 최신본만 유지 (dedupe by corp_name)
    → fnlttSinglAcnt 로 재무 보강 (외감 사업보고서 있을 때만, graceful)

⚠️ 검증 한계 (CLAUDE.md RULE 7 + [[feedback_scope]]):
  - 상장 전 = 가격/거래 데이터 0 → Brain 가격·모멘텀 축 적용 불가.
  - 산출물 = watch list (후보 신호, 가설 N=0). **추천 아님.**
  - 검증 trail 은 상장 후 funnel 편입 시점부터 N 누적으로만 시작.

DART 제약 (실 호출 검증 2026-06-07):
  - corp_code 없는 list.json = 검색기간 최대 3개월 (90일 초과 시 status=100).
  - C001 에는 기존 상장사 유상증자(corp_cls Y/K)가 다수 혼입 → E 필터 필수.
"""
import json
import os
import re
import sys
from datetime import timedelta
from typing import Any, Dict, List

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from api.config import DART_API_KEY, DATA_DIR, now_kst
from api.collectors.DartScout import _call, fetch_financials
from api.analyzers.ipo_prospectus_parser import parse_prospectus

OUTPUT_PATH = os.path.join(DATA_DIR, "ipo_watch.json")
SEARCH_DAYS = 88  # DART 90일 제약 (corp_code 없는 list.json) 안쪽 여유
DART_VIEW_URL = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo={}"

# SPAC(기업인수목적회사) 제외 — 실 운영사 IPO 아님.
_SPAC_PAT = re.compile(r"기업인수목적|스팩|SPAC", re.IGNORECASE)
# 진짜 IPO 신고서 — 정정/발행조건확정 prefix 허용, 증권발행실적보고서/투자설명서 제외.
_IPO_REPORT_PAT = re.compile(r"증권신고서\(지분증권\)")


def fetch_ipo_filings(days: int = SEARCH_DAYS) -> List[Dict[str, Any]]:
    """C001 증권신고서(지분증권) 공시 목록 전 페이지 수집."""
    end = now_kst()
    bgn = end - timedelta(days=days)
    common = {
        "pblntf_detail_ty": "C001",
        "bgn_de": bgn.strftime("%Y%m%d"),
        "end_de": end.strftime("%Y%m%d"),
        "page_count": "100",
        "sort": "date",
        "sort_mth": "desc",
    }
    rows: List[Dict[str, Any]] = []
    for page in range(1, 11):  # 안전 상한 (100×10 = 1000건)
        data = _call("list.json", {**common, "page_no": str(page)})
        chunk = data.get("list", [])
        if not chunk:
            break
        rows.extend(chunk)
        total_page = int(data.get("total_page", 1) or 1)
        if page >= total_page:
            break
    return rows


def _select_ipo_candidates(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """E(미상장) + IPO 신고서 + SPAC 제외 → corp_name 별 최신 1건."""
    latest: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        if r.get("corp_cls") != "E":
            continue
        name = (r.get("corp_name") or "").strip()
        report = r.get("report_nm") or ""
        if not name or not _IPO_REPORT_PAT.search(report):
            continue
        if _SPAC_PAT.search(name):
            continue
        prev = latest.get(name)
        # rcept_dt 최신 우선 (정정본 = 최신 접수). 동일자면 rcept_no 큰 쪽.
        if prev is None or (r.get("rcept_dt"), r.get("rcept_no")) > (
            prev.get("rcept_dt"), prev.get("rcept_no")
        ):
            latest[name] = r
    return sorted(latest.values(), key=lambda r: r.get("rcept_dt", ""), reverse=True)


# 본문 없는 정정 유형 — fallback 대상 (첨부문서만 정정 → 표 0개)
_ATTACH_ONLY = ("첨부정정", "첨부추가")


def _has_offering(doc: Dict[str, Any]) -> bool:
    o = doc.get("offering") or {}
    return bool(o.get("price_planned") or o.get("price_confirmed") or o.get("subscribe_start"))


def _parse_with_fallback(corp_code: str, rcept_no: str, report_nm: str) -> Dict[str, Any]:
    """본문 파싱. 최신 신고서가 [첨부정정](본문 0)이면 corp 의 최신 본문 신고서로 fallback (v0.2)."""
    doc = parse_prospectus(rcept_no, report_nm)
    if _has_offering(doc):
        return doc
    # corp_code 스코프 C001 목록 → 최신 본문 신고서 (첨부정정/첨부추가 제외) 재시도.
    now = now_kst()
    listing = _call("list.json", {
        "corp_code": corp_code,
        "pblntf_detail_ty": "C001",
        "bgn_de": f"{now.year}0101",
        "end_de": now.strftime("%Y%m%d"),
        "page_count": "30",
        "sort": "date",
        "sort_mth": "desc",
    })
    for it in listing.get("list", []):
        rc = it.get("rcept_no", "")
        rn = it.get("report_nm", "")
        if rc == rcept_no or any(a in rn for a in _ATTACH_ONLY):
            continue
        if "증권신고서(지분증권)" not in rn:
            continue
        alt = parse_prospectus(rc, rn)
        if _has_offering(alt):
            alt["offering_from_rcept"] = rc
            return alt
    return doc  # fallback 실패 — 원본(offering 빈 채) 반환


# KSIC 대분류(2자리) → 섹터. scripts/kr_sector_dart_fallback.py 의 대응표와 동일 체계.
#   🚨 자체 판단이 아니라 회사가 공시한 표준산업분류를 우리 섹터 축에 대응시킨 것뿐이다.
_KSIC2_SECTOR: Dict[str, str] = {
    **{k: "필수소비재" for k in ["01", "02", "03", "10", "11", "12"]},
    **{k: "에너지" for k in ["05", "19"]},
    **{k: "소재" for k in ["06", "07", "08", "16", "17", "20", "22", "23", "24"]},
    **{k: "경기소비재" for k in ["13", "14", "15", "30", "32", "45", "46", "47", "55", "56", "85", "90", "91"]},
    **{k: "헬스케어" for k in ["21", "27", "70", "86", "87"]},
    **{k: "산업재" for k in ["18", "25", "28", "29", "31", "33", "34", "41", "42", "49", "50", "51", "52", "71", "72", "73", "74", "75", "76"]},
    **{k: "유틸리티" for k in ["35", "36", "37", "38", "39"]},
    **{k: "IT·기술" for k in ["26", "58", "62", "63"]},
    **{k: "커뮤니케이션" for k in ["59", "60", "61"]},
    **{k: "금융" for k in ["64", "65", "66"]},
    "68": "부동산",
}


def _enrich_profile(corp_code: str) -> Dict[str, Any]:
    """DART 기업개황 — 업종·설립일·소재지. 🚨 상장 전(corp_cls=E)에도 응답한다(실호출 확인).

    왜 넣었나: 카드에 이름·숫자·날짜만 있어 **무슨 회사인지 알 수 없었다**.
    정기공시 재무는 상장 전이라 실측 1/10 밖에 안 채워진다 — 그 자리를 이게 메운다.
    전부 DART 기재값이고 섹터만 KSIC 표준 대응이다(자체 판단 아님).
    """
    if not corp_code:
        return {"available": False}
    # 🚨 raw requests 대신 DartScout._call 을 쓴다 — 재시도·dart_metrics 기록이 붙은
    #    정규 경로이고, 이 파일에 requests 임포트가 없다(첫 구현에서 NameError 를 냈다).
    try:
        d = _call("company.json", {"corp_code": corp_code}) or {}
    except Exception:  # noqa: BLE001 — 개황 하나 실패로 전체 수집을 죽이지 않는다
        return {"available": False, "reason": "기업개황 조회 실패"}
    if str(d.get("status")) != "000":
        return {"available": False, "reason": f"status {d.get('status')}"}
    code = str(d.get("induty_code") or "").strip()
    est = str(d.get("est_dt") or "").strip()
    adres = str(d.get("adres") or "").strip()
    # 소재지는 앞 2어절만 (시/도 + 시/군/구) — 전체 주소는 카드에 과하다.
    region = " ".join(adres.split()[:2]) if adres else ""
    return {
        "available": True,
        "induty_code": code or None,
        "sector_ko": _KSIC2_SECTOR.get(code[:2]) if code else None,
        "est_dt": est or None,
        "ceo_nm": str(d.get("ceo_nm") or "").strip() or None,
        "region": region or None,
        "hm_url": str(d.get("hm_url") or "").strip() or None,
    }


def _enrich_financials(corp_code: str) -> Dict[str, Any]:
    """외감 사업보고서가 있으면 재무 보강 (없으면 available=False).

    pre-IPO 기업 다수는 정기공시 미제출 → fnlttSinglAcnt 빈 응답. graceful.
    """
    now = now_kst()
    for year in (now.year - 1, now.year - 2):
        try:
            fin = fetch_financials(corp_code, str(year))
        except Exception:
            continue
        if fin.get("total_assets"):
            return {
                "available": True,
                "bsns_year": str(year),
                "total_assets": fin.get("total_assets"),
                "total_liabilities": fin.get("total_liabilities"),
                "equity": fin.get("equity"),
                "debt_ratio_pct": fin.get("debt_ratio_pct"),
            }
    return {"available": False, "reason": "정기공시 미제출(상장 전) 또는 재무 데이터 없음"}


def scout() -> Dict[str, Any]:
    if not DART_API_KEY:
        raise RuntimeError("DART_API_KEY 환경변수가 설정되지 않았습니다.")

    rows = fetch_ipo_filings()
    candidates = _select_ipo_candidates(rows)

    watch: List[Dict[str, Any]] = []
    for c in candidates:
        corp_code = c.get("corp_code", "")
        rcept_no = c.get("rcept_no", "")
        report_nm = c.get("report_nm", "")
        # 증권신고서 본문 파싱 — 공모가/청약일/stage/요약재무. 첨부정정 시 fallback (v0.2)
        doc = _parse_with_fallback(corp_code, rcept_no, report_nm)
        # offering 데이터가 fallback 신고서에서 왔으면 링크도 그 신고서로 (데이터-링크 정합)
        data_rcept = doc.get("offering_from_rcept") or rcept_no
        watch.append({
            "corp_name": c.get("corp_name", ""),
            "corp_code": corp_code,
            "rcept_no": rcept_no,
            "rcept_dt": c.get("rcept_dt", ""),
            "report_nm": report_nm,
            "dart_url": DART_VIEW_URL.format(data_rcept),
            "stage": doc.get("stage"),
            "offering": doc.get("offering", {}),
            "doc_financials": doc.get("summary_financials", {"available": False}),
            "doc_parse_error": doc.get("error"),
            # 정기공시 재무 (외감 기업만) — debt_ratio 등 보조
            "financials": _enrich_financials(corp_code) if corp_code else {"available": False},
            # 기업개황 — 업종·설립일·소재지. 재무가 상장 전이라 대부분 비는 자리를 메운다.
            "profile": _enrich_profile(corp_code),
        })

    return {
        "updated_at": now_kst().isoformat(),
        "source": "DART OpenAPI list.json (C001 증권신고서/지분증권, corp_cls=E)",
        "search_window_days": SEARCH_DAYS,
        "disclaimer": (
            "watch list (후보 신호, 가설 N=0). 추천 아님 — 상장 전은 가격 데이터가 없어 "
            "검증 trail 미적용. 상장 후 funnel 편입 시점부터 검증 시작."
        ),
        "raw_c001_count": len(rows),
        "count": len(watch),
        "watch": watch,
    }


def main() -> int:
    print("ipo_scout — DART 증권신고서(C001) IPO 파이프라인 수집...")
    result = scout()

    # 🚨 전량 실패 가드 (#46). 두 개의 0 을 구분한다.
    #   · count == 0        = IPO 후보 없음. 정상이다(증분 성격).
    #   · raw_c001_count == 0 = DART 조회 자체가 실패. SEARCH_DAYS=88일 창에서
    #     C001 증권신고서가 한 건도 없는 경우는 사실상 없다.
    #   _call 이 실패 시 빈 dict 를 돌려주므로 rows=[] 만 보면 둘이 같아 보인다.
    #   여기서 정상 종료하면 후보 0건 파일이 새로 기록되고 mtime 만 갱신되어
    #   신선도 보드가 통과시킨다. [[feedback_silent_total_failure_guard]]
    if not result.get("raw_c001_count"):
        print(
            f"[ipo_scout] outcome=total_fail DART C001 조회 {SEARCH_DAYS}일 창에서 0건 "
            "— 조회 실패로 판정, 산출 미갱신·실패 종료",
            file=sys.stderr,
        )
        return 1

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"완료: 원시 {result['raw_c001_count']}건 → IPO 후보 {result['count']}개 → {OUTPUT_PATH}")
    for w in result["watch"]:
        o = w.get("offering", {})
        price = o.get("price_confirmed") or o.get("price_planned")
        price_s = f"{price:,}원" if price else "공모가 미상"
        sub = o.get("subscribe_start", "?")
        print(f"  {w['corp_name'][:18]:18s} | {w.get('stage') or '?':2s} | {price_s:>12s} | 청약 {sub}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
