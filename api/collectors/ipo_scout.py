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
        # 증권신고서 본문 파싱 — 공모가/청약일/stage/요약재무 (v0.1)
        doc = parse_prospectus(rcept_no, report_nm)
        watch.append({
            "corp_name": c.get("corp_name", ""),
            "corp_code": corp_code,
            "rcept_no": rcept_no,
            "rcept_dt": c.get("rcept_dt", ""),
            "report_nm": report_nm,
            "dart_url": DART_VIEW_URL.format(rcept_no),
            "stage": doc.get("stage"),
            "offering": doc.get("offering", {}),
            "doc_financials": doc.get("summary_financials", {"available": False}),
            "doc_parse_error": doc.get("error"),
            # 정기공시 재무 (외감 기업만) — debt_ratio 등 보조
            "financials": _enrich_financials(corp_code) if corp_code else {"available": False},
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


def main() -> None:
    print("ipo_scout — DART 증권신고서(C001) IPO 파이프라인 수집...")
    result = scout()
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


if __name__ == "__main__":
    main()
