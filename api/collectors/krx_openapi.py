"""
KRX OpenAPI collector.

- AUTH_KEY + basDd 패턴으로 KRX OpenAPI 엔드포인트를 통합 호출
- API별 상태(성공/권한없음/빈데이터/오류)와 샘플 데이터 요약 반환
- 18개는 변동성·용도별 Static / Macro / Active 3단으로 분류 (파이프라인 주기와 맞춤)
"""
from __future__ import annotations

import copy
from datetime import date, timedelta
from typing import Dict, List, Optional, Sequence

import requests

from api.config import KRX_API_KEY, now_kst

_TIMEOUT = 12
_BASE_URL = "https://data-dbg.krx.co.kr/svc/apis"

# 사용자 폴더 기준 18개 매핑.
# 참고: drvprod_dd_trd 폴더 자료는 채권지수(bon_dd_trd) 명세와 동일해 보이며,
# 실서비스 경로는 idx/drvprod_dd_trd 로 우선 매핑한다.
KRX_ENDPOINTS: List[Dict[str, str]] = [
    {"id": "bnd_bydd_trd", "path": "bon/bnd_bydd_trd", "label": "일반채권시장 일별매매정보"},
    {"id": "bon_dd_trd", "path": "idx/bon_dd_trd", "label": "채권지수 시세정보"},
    {"id": "drvprod_dd_trd", "path": "idx/drvprod_dd_trd", "label": "파생상품지수 시세정보"},
    {"id": "esg_etp_info", "path": "esg/esg_etp_info", "label": "ESG 증권상품"},
    {"id": "esg_index_info", "path": "esg/esg_index_info", "label": "ESG 지수"},
    {"id": "etf_bydd_trd", "path": "etp/etf_bydd_trd", "label": "ETF 일별매매정보"},
    {"id": "ets_bydd_trd", "path": "gen/ets_bydd_trd", "label": "배출권시장 일별매매정보"},
    {"id": "gold_bydd_trd", "path": "gen/gold_bydd_trd", "label": "금시장 일별매매정보"},
    {"id": "kosdaq_dd_trd", "path": "idx/kosdaq_dd_trd", "label": "KOSDAQ 시리즈 일별시세"},
    {"id": "kospi_dd_trd", "path": "idx/kospi_dd_trd", "label": "KOSPI 시리즈 일별시세"},
    {"id": "krx_dd_trd", "path": "idx/krx_dd_trd", "label": "KRX 시리즈 일별시세"},
    {"id": "ksq_bydd_trd", "path": "sto/ksq_bydd_trd", "label": "코스닥 일별매매정보"},
    {"id": "ksq_isu_base_info", "path": "sto/ksq_isu_base_info", "label": "코스닥 종목기본정보"},
    {"id": "kts_bydd_trd", "path": "bon/kts_bydd_trd", "label": "국채전문유통시장 일별매매정보"},
    {"id": "oil_bydd_trd", "path": "gen/oil_bydd_trd", "label": "석유시장 일별매매정보"},
    {"id": "smb_bydd_trd", "path": "bon/smb_bydd_trd", "label": "소액채권시장 일별매매정보"},
    {"id": "stk_bydd_trd", "path": "sto/stk_bydd_trd", "label": "유가증권 일별매매정보"},
    {"id": "stk_isu_base_info", "path": "sto/stk_isu_base_info", "label": "유가증권 종목기본정보"},
]

KRX_ENDPOINT_MAP: Dict[str, Dict[str, str]] = {e["id"]: e for e in KRX_ENDPOINTS}

# ── 3단 분류 (18개 전부 포함, 중복 없음) ─────────────────────────────
# Static: 일봉·메타 성격 — full(일 1회)에서 갱신, quick/realtime에서는 유지
KRX_STATIC_IDS: tuple = (
    "stk_isu_base_info",
    "ksq_isu_base_info",
    "esg_index_info",
    "esg_etp_info",
    "stk_bydd_trd",
    "ksq_bydd_trd",
)
# Macro: 원자재·채권·배출권 등 장세 보조 — quick(시간 단위)에서 갱신
KRX_MACRO_IDS: tuple = (
    "oil_bydd_trd",
    "gold_bydd_trd",
    "bnd_bydd_trd",
    "bon_dd_trd",
    "kts_bydd_trd",
    "smb_bydd_trd",
    "ets_bydd_trd",
)
# Active: 지수·ETF·파생지수 등 터미널 상단에 쓰기 좋은 묶음 — realtime에서만 추가 갱신
KRX_ACTIVE_IDS: tuple = (
    "kospi_dd_trd",
    "kosdaq_dd_trd",
    "krx_dd_trd",
    "etf_bydd_trd",
    "drvprod_dd_trd",
)

_ALL_TIER = set(KRX_STATIC_IDS) | set(KRX_MACRO_IDS) | set(KRX_ACTIVE_IDS)
_ALL_MAP = set(KRX_ENDPOINT_MAP.keys())
if _ALL_TIER != _ALL_MAP:
    raise RuntimeError(
        f"KRX tier IDs must match KRX_ENDPOINTS: tier={sorted(_ALL_TIER)} map={sorted(_ALL_MAP)}"
    )
if len(_ALL_TIER) != len(KRX_STATIC_IDS) + len(KRX_MACRO_IDS) + len(KRX_ACTIVE_IDS):
    raise RuntimeError("KRX_STATIC/MACRO/ACTIVE must be disjoint")


def recent_business_day() -> str:
    """KST 기준 최근 평일 YYYYMMDD."""
    d = now_kst().date()
    for _ in range(14):
        if d.weekday() < 5:
            return d.strftime("%Y%m%d")
        d -= timedelta(days=1)
    return now_kst().strftime("%Y%m%d")


def _request_krx(path: str, bas_dd: str) -> Dict[str, object]:
    if not KRX_API_KEY:
        return {"status": "error", "reason": "키 미설정", "http_status": None, "rows": []}
    try:
        resp = requests.get(
            f"{_BASE_URL}/{path}",
            params={"AUTH_KEY": KRX_API_KEY, "basDd": bas_dd},
            timeout=_TIMEOUT,
        )
    except requests.RequestException as e:
        return {
            "status": "error",
            "reason": str(e)[:120],
            "http_status": None,
            "rows": [],
        }
    if resp.status_code == 401:
        return {"status": "error", "reason": "401 인증 실패", "http_status": 401, "rows": []}
    if resp.status_code == 403:
        return {
            "status": "forbidden",
            "reason": "403 권한없음(API 이용신청 필요)",
            "http_status": 403,
            "rows": [],
        }
    if resp.status_code != 200:
        return {
            "status": "error",
            "reason": f"HTTP {resp.status_code}",
            "http_status": resp.status_code,
            "rows": [],
        }
    try:
        payload = resp.json()
    except ValueError:
        return {
            "status": "error",
            "reason": "JSON 파싱 실패",
            "http_status": resp.status_code,
            "rows": [],
        }
    rows = payload.get("OutBlock_1", [])
    if not isinstance(rows, list):
        return {
            "status": "error",
            "reason": "응답 형식 이상",
            "http_status": resp.status_code,
            "rows": [],
        }
    if len(rows) == 0:
        return {
            "status": "empty",
            "reason": "데이터 없음(비거래일/미제공/권한 제한 가능)",
            "http_status": resp.status_code,
            "rows": [],
        }
    return {"status": "ok", "reason": "정상", "http_status": resp.status_code, "rows": rows}


def krx_stk_ksq_rows_sorted_by_trading_value(
    bas_dd: Optional[str] = None,
    max_day_retries: int = 12,
) -> tuple[str, List[Dict[str, object]]]:
    """
    유가증권(stk_bydd_trd) + 코스닥(ksq_bydd_trd) 일별매매를 합쳐 ACC_TRDVAL 기준 내림차순.
    키 미설정·API 실패·연속 휴일이면 ("", []).

    Returns:
        (조회에 성공한 basDd YYYYMMDD, 전체 행 — 티커당 최대 거래대금 row 1건)
    """
    if not KRX_API_KEY:
        return ("", [])

    def _acc_trdval_krw(row: Dict[str, object]) -> int:
        raw = row.get("ACC_TRDVAL") or row.get("ACC_TRDVALU") or 0
        if raw is None:
            return 0
        s = str(raw).strip().replace(",", "")
        if not s:
            return 0
        try:
            return int(float(s))
        except ValueError:
            return 0

    def _merge_day(b: str) -> List[Dict[str, object]]:
        by_ticker: Dict[str, Dict[str, object]] = {}
        for path in ("sto/stk_bydd_trd", "sto/ksq_bydd_trd"):
            res = _request_krx(path, b)
            if res.get("status") != "ok":
                continue
            rows = res.get("rows") or []
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                code_raw = str(row.get("ISU_SRT_CD") or row.get("ISU_CD") or "")
                digits = "".join(c for c in code_raw if c.isdigit())
                if len(digits) < 6:
                    continue
                tid = digits[-6:].zfill(6)
                v = _acc_trdval_krw(row)
                prev = by_ticker.get(tid)
                if prev is None or v > _acc_trdval_krw(prev):
                    by_ticker[tid] = row
        ranked = sorted(by_ticker.values(), key=_acc_trdval_krw, reverse=True)
        return ranked

    if bas_dd and len(str(bas_dd).strip()) == 8:
        d = date.fromisoformat(
            f"{str(bas_dd).strip()[:4]}-{str(bas_dd).strip()[4:6]}-{str(bas_dd).strip()[6:8]}"
        )
    else:
        d = now_kst().date()

    for _ in range(max_day_retries):
        b = d.strftime("%Y%m%d")
        ranked = _merge_day(b)
        if ranked:
            return (b, ranked)
        d -= timedelta(days=1)

    return ("", [])


def collect_krx_openapi_snapshot(
    bas_dd: Optional[str] = None,
    endpoint_ids: Optional[List[str]] = None,
    max_rows_per_endpoint: int = 5,
) -> Dict[str, object]:
    """
    KRX OpenAPI 스냅샷 수집.

    Returns:
      {
        "bas_dd": "...",
        "summary": {"ok": n, "empty": n, "forbidden": n, "error": n, "total": n},
        "endpoints": {"id": {...}}
      }
    """
    b = (bas_dd or "").strip() or recent_business_day()
    target_ids = endpoint_ids or [e["id"] for e in KRX_ENDPOINTS]

    out: Dict[str, object] = {
        "bas_dd": b,
        "updated_at": now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "summary": {"ok": 0, "empty": 0, "forbidden": 0, "error": 0, "total": 0},
        "endpoints": {},
    }

    for eid in target_ids:
        meta = KRX_ENDPOINT_MAP.get(eid)
        if not meta:
            continue
        result = _request_krx(meta["path"], b)
        rows = result.get("rows") or []
        sample = rows[:max_rows_per_endpoint] if isinstance(rows, list) else []
        endpoint_data = {
            "id": eid,
            "label": meta["label"],
            "path": meta["path"],
            "status": result.get("status"),
            "reason": result.get("reason"),
            "http_status": result.get("http_status"),
            "row_count": len(rows) if isinstance(rows, list) else 0,
            "sample": sample,
        }
        out["endpoints"][eid] = endpoint_data
        st = str(result.get("status") or "error")
        if st not in ("ok", "empty", "forbidden", "error"):
            st = "error"
        out["summary"][st] += 1
        out["summary"]["total"] += 1

    return out


def krx_tier_plan_dict() -> Dict[str, List[str]]:
    """프론트·문서용: 18개 ID를 tier별로 노출."""
    return {
        "static": list(KRX_STATIC_IDS),
        "macro": list(KRX_MACRO_IDS),
        "active": list(KRX_ACTIVE_IDS),
    }


def recompute_krx_summary(endpoints: Dict[str, object]) -> Dict[str, int]:
    """병합 후 전체 endpoints 기준으로 summary 재계산."""
    ep = endpoints if isinstance(endpoints, dict) else {}
    counts = {"ok": 0, "empty": 0, "forbidden": 0, "error": 0, "total": len(ep)}
    for data in ep.values():
        if not isinstance(data, dict):
            counts["error"] += 1
            continue
        st = str(data.get("status") or "error")
        if st not in ("ok", "empty", "forbidden", "error"):
            st = "error"
        counts[st] += 1
    return counts


def merge_krx_openapi_snapshots(
    previous: Optional[Dict[str, object]],
    partial: Dict[str, object],
    tiers_refreshed: Sequence[str],
) -> Dict[str, object]:
    """
    이전 portfolio의 krx_openapi에 부분 수집 결과를 덮어씀.
    tiers_refreshed: 갱신된 tier 이름 (예: "macro", "active").
    """
    now_s = now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00")
    base = copy.deepcopy(previous) if isinstance(previous, dict) and previous else {}
    if not isinstance(base.get("endpoints"), dict):
        base["endpoints"] = {}
    if not isinstance(base.get("tier_updated_at"), dict):
        base["tier_updated_at"] = {}

    patch_eps = partial.get("endpoints")
    if isinstance(patch_eps, dict):
        for eid, data in patch_eps.items():
            if isinstance(data, dict):
                base["endpoints"][eid] = copy.deepcopy(data)

    if partial.get("bas_dd"):
        base["bas_dd"] = str(partial["bas_dd"])
    elif not base.get("bas_dd"):
        base["bas_dd"] = recent_business_day()

    base["updated_at"] = now_s
    for t in tiers_refreshed:
        if t:
            base["tier_updated_at"][str(t)] = now_s

    if "tier_plan" not in base:
        base["tier_plan"] = krx_tier_plan_dict()

    base["summary"] = recompute_krx_summary(base["endpoints"])
    return base


def collect_krx_tiers(
    tier_names: Sequence[str],
    bas_dd: Optional[str] = None,
    max_rows_per_endpoint: int = 5,
) -> Dict[str, object]:
    """
    tier 이름 조합으로만 수집 (병합용 patch).
    tier_names: "static" / "macro" / "active" 중 일부.
    """
    want: List[str] = []
    for name in tier_names:
        n = str(name).strip().lower()
        if n == "static":
            want.extend(KRX_STATIC_IDS)
        elif n == "macro":
            want.extend(KRX_MACRO_IDS)
        elif n == "active":
            want.extend(KRX_ACTIVE_IDS)
    if not want:
        return {
            "bas_dd": (bas_dd or "").strip() or recent_business_day(),
            "updated_at": now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
            "summary": {"ok": 0, "empty": 0, "forbidden": 0, "error": 0, "total": 0},
            "endpoints": {},
        }
    return collect_krx_openapi_snapshot(
        bas_dd=bas_dd,
        endpoint_ids=want,
        max_rows_per_endpoint=max_rows_per_endpoint,
    )
