"""
estate_sector_pulse_builder.py — ESTATE 4섹터 dynamics weekly 빌더

SectorPulse.tsx (market/ 폴더) 의 데이터 source.
한국 부동산 4섹터 (아파트 / 오피스 / 상가 / 오피스텔) 각각의 최신 지수 + YoY + 수익률
+ verdict 산출. R-ONE 실측 데이터만 사용 (Perplexity X).

발굴 (2026-05-17 R-ONE 카탈로그 audit):
  - 오피스 임대지수    TT244963134453269 (분기, 2013~)
  - 중대형 상가 임대지수 TT248473134635539 (분기)
  - 오피스 수익률(분기) T245883135037859 (2024Q3~)
  - 중대형 상가 수익률  T242083134887473 (2024Q3~)
  - 오피스텔 매매가격지수 A_2024_00615 (월, 시계열)
  - 오피스텔 수익률      T245503133561624 (월, 2024-01~)

거짓말 트랩:
  T1·T9 silent fabricate X — 섹터별 실패 시 _error 명시 + verdict=UNAVAILABLE
  T2    mock fallback X — 데이터 0 시 ERROR 명시
  T4    임의 상수 X — verdict 임계 모두 박힘

Cost: R-ONE 무료. 1 cron run 당 R-ONE 호출 8회 (4섹터 × 2 통계).

Memory: project_rone_api_spec / feedback_real_call_over_llm_consensus / feedback_simple_front_monster_back
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
KST = timezone(timedelta(hours=9))
OUTPUT_PATH = REPO_ROOT / "data" / "estate_sector_pulse.json"

RONE_BASE = "https://www.reb.or.kr/r-one/openapi"

# 2026-05-20 Fix A (commercial transient resilience, [[project_estate_commercial_v0_design]]) —
# R-ONE RemoteDisconnected 빈발 (실호출 입증: retail/officetel 단발 fetch 실패 → sector UNAVAILABLE blank,
# 신선 재빌드 시 회복 = transient). 단일 blip 으로 sector 가 blank 되지 않게 직전 good 값 carry-forward.
# 상한: 상업 통계는 분기/월 갱신 → 그 이내 stale 값 = 여전히 최신 공표치. STALE_MAX_DAYS 초과 시
# systemic 결함 의심 → UNAVAILABLE 정직 노출 (오래된 값을 현재처럼 보이는 것 방지).
STALE_MAX_DAYS = 35

_logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# 4섹터 정의 (실측 STATBL_ID, 2026-05-17 R-ONE 카탈로그 audit)
# ─────────────────────────────────────────────────────────────────────

# Verdict 임계 — T4 정합 (임의 상수 X, 명시 박음).
# YoY 임계: 한국 부동산 시장 정상 변동 1~3%/yr. 임대지수 ±2% = 의미 있는 시그널.
YOY_BULLISH = 2.0
YOY_BEARISH = -2.0
# 수익률 임계 (연환산 기준 — 분기 단위는 ÷4 변환 후 비교).
# 한국 상업용 부동산 임대수익률 연 4~5% (한국감정원 2024 평균). ≥5% = 양호 / ≤3.5% = 부진.
YIELD_ANNUAL_BULLISH = 5.0
YIELD_ANNUAL_BEARISH = 3.5

# R-ONE ITM_ID 체계 — 통계마다 다름 (실측 2026-05-17).
ITM_ID_INDEX_5DIGIT = 10001   # 매매가격지수 (T244183132827305 류)
ITM_ID_INDEX_6DIGIT = 100001  # 임대가격지수 / 수익률 (TT/T 시리즈)

# CLS_ID 직접 호출 정합 (실측 2026-05-17, _fetch_rone_rows 에 cls_id 파라미터 전달).
# 단일 region 시계열만 받으니 페이지 수 적음 (cron 비용 ↓).
# cls_id None 이면 전체 row 페치 후 region name 으로 select (fallback 패턴).
SECTORS = {
    "residential_apt": {
        "name": "아파트(주거)",
        "index_stat_id": "T244183132827305",
        "index_cycle": "WK",  # 주간
        "index_itm_id": ITM_ID_INDEX_5DIGIT,
        "index_cls_id": 50001,  # 전국 (실측)
        "yield_stat_id": None,
        "yield_cycle": None,
        "yield_itm_id": None,
        "yield_cls_id": None,
        "yield_is_quarterly": False,
        "preferred_region": "전국",
        "fallback_region": "서울",
    },
    "office": {
        "name": "오피스",
        "index_stat_id": "TT244963134453269",
        "index_cycle": "QY",
        "index_itm_id": ITM_ID_INDEX_6DIGIT,
        "index_cls_id": 500001,  # 전국 (실측)
        "yield_stat_id": "T245883135037859",
        "yield_cycle": "QY",
        "yield_itm_id": ITM_ID_INDEX_6DIGIT,
        "yield_cls_id": 500001,  # 전국 (실측, 임대동향 5xxxx 체계)
        "yield_is_quarterly": True,
        "preferred_region": "전국",
        "fallback_region": "서울",
    },
    "retail_mid_large": {
        "name": "중대형 상가",
        "index_stat_id": "TT248473134635539",
        "index_cycle": "QY",
        "index_itm_id": ITM_ID_INDEX_6DIGIT,
        "index_cls_id": 500001,
        "yield_stat_id": "T242083134887473",
        "yield_cycle": "QY",
        "yield_itm_id": ITM_ID_INDEX_6DIGIT,
        "yield_cls_id": 500001,
        "yield_is_quarterly": True,
        "preferred_region": "전국",
        "fallback_region": "서울",
    },
    "officetel": {
        # 오피스텔 매매가격지수 A_2024_00615 = 규모(면적) 구분, 지역 X.
        # CLS_NM = "전체" / "40㎡이하" 등. 지역별 통계 부재.
        "name": "오피스텔",
        "index_stat_id": "A_2024_00615",
        "index_cycle": "MM",
        "index_itm_id": ITM_ID_INDEX_6DIGIT,
        "index_cls_id": None,
        "yield_stat_id": "T245503133561624",
        "yield_cycle": "MM",
        # Fix B (2026-05-20, 실호출 입증): officetel 수익률 ITM_ID = 10001(5-digit "수익률"),
        # office/retail(100001 "투자수익률")과 다름. 옛 100001 = filter 전 행 제거 → yield None.
        # 또 CLS_NM(규모: 전체/40㎡…) × GRP_NM(권역: 전국/서울/지방…) 2차원 → 전국·전체 직접 선택.
        # 값(월 5.27 류) = 연 수익률을 월별 공표 → yield_is_quarterly=False (÷4 안 함) 정합.
        "yield_itm_id": ITM_ID_INDEX_5DIGIT,
        "yield_cls_id": None,
        "yield_cls_nm": "전체",
        "yield_grp_nm": "전국",
        "yield_is_quarterly": False,
        "preferred_region": "전체",
        "fallback_region": "전국",
    },
}


# ─────────────────────────────────────────────────────────────────────
# R-ONE mini client — LANDEX rone.py 와 같은 패턴 (v1 에서 공용 client 분리 큐잉)
# ─────────────────────────────────────────────────────────────────────

def _api_key() -> str:
    return (os.environ.get("R_ONE_API_KEY") or os.environ.get("REB_API_KEY") or "").strip()


def _parse_response(data: dict) -> Tuple[Optional[int], List[dict]]:
    if isinstance(data, dict) and "RESULT" in data:
        code = (data["RESULT"] or {}).get("CODE")
        if code and code != "INFO-000":
            _logger.warning("R-ONE error: %s", data["RESULT"])
            return None, []

    payload = data.get("SttsApiTblData") if isinstance(data, dict) else None
    rows: List[dict] = []
    total: Optional[int] = None
    chunks = payload if isinstance(payload, list) else [payload] if isinstance(payload, dict) else []
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        head = chunk.get("head")
        if isinstance(head, list):
            for h in head:
                if isinstance(h, dict) and "list_total_count" in h:
                    try:
                        total = int(h["list_total_count"])
                    except (TypeError, ValueError):
                        pass
        if isinstance(chunk.get("row"), list):
            rows.extend(chunk["row"])
    return total, rows


def _fetch_rone_rows(
    stat_id: str, cycle: str, cls_id: Optional[int] = None, max_pages: int = 3,
) -> List[dict]:
    """R-ONE SttsApiTblData. 응답이 오래된 데이터부터 → 마지막 N 페이지만 호출.

    Args:
        cls_id: 특정 region CLS_ID 직접 호출 (단일 region 시계열). None 이면 전체.

    Returns: row list. 실패 시 [].
    """
    key = _api_key()
    if not key:
        _logger.error("R_ONE_API_KEY / REB_API_KEY 미설정")
        return []

    url = f"{RONE_BASE}/SttsApiTblData.do"
    base_params: Dict[str, str] = {
        "KEY": key,
        "Type": "json",
        "pSize": "1000",
        "STATBL_ID": stat_id,
        "DTACYCLE_CD": cycle,
    }
    if cls_id is not None:
        base_params["CLS_ID"] = str(cls_id)

    def _get(page_index: int) -> Tuple[Optional[int], List[dict]]:
        # R-ONE 서버 RemoteDisconnected 빈발 (5/17·5/19 cron 4 STATBL 4/4 실패 사례).
        # 1차 호출 후 후속 호출 disconnect → retry 2회 + backoff 로 대부분 해소.
        last_exc = None
        for attempt in range(3):  # 0, 1, 2
            if attempt > 0:
                time.sleep(0.5 * (2 ** (attempt - 1)))  # 0.5s, 1.0s
            try:
                r = requests.get(
                    url,
                    params={**base_params, "pIndex": str(page_index)},
                    timeout=15,
                    headers={"Connection": "close"},
                )
                r.raise_for_status()
                return _parse_response(r.json())
            except (requests.RequestException, ValueError, json.JSONDecodeError) as e:
                last_exc = e
                if attempt < 2:
                    _logger.warning(
                        "R-ONE %s page %d attempt %d failed: %s — retry",
                        stat_id, page_index, attempt + 1, e,
                    )
        _logger.error(
            "R-ONE %s page %d fetch failed after 3 attempts: %s",
            stat_id, page_index, last_exc,
        )
        return None, []

    total, _ = _get(1)
    if total is None:
        return []

    last_page = max(1, (total + 999) // 1000)
    start_page = max(1, last_page - max_pages + 1)
    rows: List[dict] = []
    for p in range(start_page, last_page + 1):
        _, page_rows = _get(p)
        rows.extend(page_rows)
    return rows


# ─────────────────────────────────────────────────────────────────────
# 섹터별 산출
# ─────────────────────────────────────────────────────────────────────

def _select_region_series(
    rows: List[dict], preferred: str, fallback: str, itm_id: int,
) -> Tuple[Optional[str], List[dict]]:
    """preferred CLS_NM 시계열 우선. 없으면 fallback. 그것도 없으면 전체 평균 시계열.

    Args:
        itm_id: 통계별 ITM_ID (매매=10001, 임대/수익률=100001)

    Returns: (region_used, sorted_rows_oldest_first)
    """
    rows = [r for r in rows if r.get("ITM_ID") == itm_id]

    by_region: Dict[str, List[dict]] = {}
    for r in rows:
        nm = r.get("CLS_NM", "")
        by_region.setdefault(nm, []).append(r)

    for region in (preferred, fallback):
        if region in by_region and len(by_region[region]) >= 2:
            series = sorted(by_region[region], key=lambda r: r.get("WRTTIME_IDTFR_ID", ""))
            return region, series

    # fallback 도 부재 — 모든 region 평균 (시점별)
    if not rows:
        return None, []
    period_groups: Dict[str, List[float]] = {}
    for r in rows:
        period = r.get("WRTTIME_IDTFR_ID", "")
        try:
            val = float(r.get("DTA_VAL", 0))
        except (TypeError, ValueError):
            continue
        period_groups.setdefault(period, []).append(val)
    avg_series = [
        {
            "WRTTIME_IDTFR_ID": p,
            "WRTTIME_DESC": p,
            "DTA_VAL": sum(vals) / len(vals),
            "CLS_NM": "전체 평균",
        }
        for p, vals in sorted(period_groups.items())
    ]
    return "전체 평균(추정)", avg_series


def _select_grp_series(
    rows: List[dict], itm_id: int, cls_nm: str, grp_nm: str,
) -> List[dict]:
    """2차원(CLS 규모 × GRP 권역) 통계의 단일 시계열 선택 (Fix B, 2026-05-20).

    officetel 수익률(T245503133561624) 처럼 같은 period 에 CLS_NM(규모: 전체/40㎡이하)과
    GRP_NM(권역: 전국/서울/지방…) 두 분류가 곱해진 통계 전용. 실호출 입증 2026-05-20:
    1차원 _select_region_series 는 CLS_NM 만 그룹핑 → period 당 16 GRP 가 섞여 임의 값 선택.

    필터: ITM_ID==itm_id AND CLS_NM==cls_nm AND GRP_NM==grp_nm → WRTTIME 오름차순 정렬.
    Returns: sorted series (오래된 → 최신). 부재 시 [].
    """
    series = [
        r for r in rows
        if r.get("ITM_ID") == itm_id
        and r.get("CLS_NM") == cls_nm
        and r.get("GRP_NM") == grp_nm
    ]
    return sorted(series, key=lambda r: r.get("WRTTIME_IDTFR_ID", ""))


def _compute_change_pct(series: List[dict], periods_back: int) -> Optional[float]:
    """series (오래된 → 최신) 의 최신값과 N 시점 전 값의 변화율(%). 부재 시 None."""
    if len(series) < periods_back + 1:
        return None
    try:
        latest = float(series[-1].get("DTA_VAL", 0))
        past = float(series[-(periods_back + 1)].get("DTA_VAL", 0))
    except (TypeError, ValueError):
        return None
    if past == 0:
        return None
    return round(((latest - past) / past) * 100, 2)


def _periods_per_year(cycle: str) -> int:
    return {"WK": 52, "MM": 12, "QY": 4, "YY": 1}.get(cycle, 12)


def _classify_sector_verdict(
    yoy_pct: Optional[float],
    yield_pct: Optional[float],
    yield_is_quarterly: bool,
) -> Tuple[str, str]:
    """4 verdict + rationale.

    yield_pct 는 raw (분기 단위면 그대로). 연환산 임계와 비교 위해 분기 ×4.
    """
    if yoy_pct is None and yield_pct is None:
        return "UNAVAILABLE", "데이터 부재"

    bull_signals = 0
    bear_signals = 0
    parts = []

    if yoy_pct is not None:
        if yoy_pct >= YOY_BULLISH:
            bull_signals += 1
            parts.append(f"YoY +{yoy_pct}% (강세)")
        elif yoy_pct <= YOY_BEARISH:
            bear_signals += 1
            parts.append(f"YoY {yoy_pct}% (약세)")
        else:
            parts.append(f"YoY {yoy_pct:+}% (보합)")

    if yield_pct is not None:
        annual = yield_pct * 4 if yield_is_quarterly else yield_pct
        suffix = f"수익률 {yield_pct}%/분기 (연 {annual:.1f}%)" if yield_is_quarterly else f"수익률 {yield_pct}%"
        if annual >= YIELD_ANNUAL_BULLISH:
            bull_signals += 1
            parts.append(f"{suffix} 양호")
        elif annual <= YIELD_ANNUAL_BEARISH:
            bear_signals += 1
            parts.append(f"{suffix} 부진")
        else:
            parts.append(f"{suffix} 보통")

    if bull_signals > 0 and bear_signals == 0:
        verdict = "BULLISH"
    elif bear_signals > 0 and bull_signals == 0:
        verdict = "BEARISH"
    elif bull_signals > 0 and bear_signals > 0:
        verdict = "MIXED"
    else:
        verdict = "NEUTRAL"

    return verdict, " · ".join(parts)


def _build_sector(key: str, spec: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "key": key,
        "name": spec["name"],
        "cycle": spec["index_cycle"],
        "verdict": "UNAVAILABLE",
        "rationale": "",
    }

    # 지수
    index_rows = _fetch_rone_rows(
        spec["index_stat_id"], spec["index_cycle"], cls_id=spec.get("index_cls_id"),
    )
    if not index_rows:
        out["_error_index"] = "fetch failed or empty"
    else:
        region_used, series = _select_region_series(
            index_rows, spec["preferred_region"], spec["fallback_region"],
            spec["index_itm_id"],
        )
        if not series:
            out["_error_index"] = "no region series"
        else:
            try:
                latest_val = float(series[-1].get("DTA_VAL", 0))
            except (TypeError, ValueError):
                latest_val = None

            ppy = _periods_per_year(spec["index_cycle"])
            yoy = _compute_change_pct(series, ppy)
            qoq_or_mom = _compute_change_pct(series, 1)

            out["region"] = region_used
            out["latest_index"] = latest_val
            out["yoy_change_pct"] = yoy
            out["short_change_pct"] = qoq_or_mom
            out["short_change_unit"] = {"WK": "WoW", "MM": "MoM", "QY": "QoQ", "YY": "YoY"}.get(spec["index_cycle"], "")
            out["as_of"] = series[-1].get("WRTTIME_DESC", series[-1].get("WRTTIME_IDTFR_ID", ""))
            out["index_source"] = f"R-ONE {spec['index_stat_id']} ({spec['index_cycle']})"
            # 시계열 마지막 12 포인트만 (sparkline 용)
            out["spark"] = [
                {
                    "t": r.get("WRTTIME_IDTFR_ID", ""),
                    "v": float(r.get("DTA_VAL", 0)) if r.get("DTA_VAL") is not None else None,
                }
                for r in series[-12:]
            ]

    # 수익률
    yield_pct = None
    if spec["yield_stat_id"]:
        yield_rows = _fetch_rone_rows(
            spec["yield_stat_id"], spec["yield_cycle"], cls_id=spec.get("yield_cls_id"),
        )
        if yield_rows:
            if spec.get("yield_grp_nm"):
                # 2차원(CLS × GRP) 통계 = officetel 수익률. 권역+규모 직접 선택 (Fix B).
                yield_series = _select_grp_series(
                    yield_rows, spec["yield_itm_id"],
                    spec["yield_cls_nm"], spec["yield_grp_nm"],
                )
            else:
                _, yield_series = _select_region_series(
                    yield_rows, spec["preferred_region"], spec["fallback_region"],
                    spec["yield_itm_id"],
                )
            if yield_series:
                try:
                    yield_pct = round(float(yield_series[-1].get("DTA_VAL", 0)), 2)
                except (TypeError, ValueError):
                    pass
                out["yield_source"] = f"R-ONE {spec['yield_stat_id']} ({spec['yield_cycle']})"
    out["yield_pct"] = yield_pct
    out["yield_is_quarterly"] = bool(spec["yield_is_quarterly"])

    # verdict
    verdict, rationale = _classify_sector_verdict(
        out.get("yoy_change_pct"), yield_pct, out["yield_is_quarterly"],
    )
    out["verdict"] = verdict
    out["rationale"] = rationale

    return out


def _overall_verdict(sectors: List[Dict[str, Any]]) -> Tuple[str, str]:
    """4 섹터 verdict 종합. 단순 다수결 + tie-break."""
    counts: Dict[str, int] = {"BULLISH": 0, "NEUTRAL": 0, "BEARISH": 0, "MIXED": 0}
    for s in sectors:
        v = s.get("verdict", "UNAVAILABLE")
        if v in counts:
            counts[v] += 1

    total_valid = sum(counts.values())
    if total_valid == 0:
        return "UNAVAILABLE", "4섹터 모두 데이터 부재"

    parts = [
        f"{s['name']} {s['verdict']}"
        for s in sectors if s.get("verdict") != "UNAVAILABLE"
    ]

    bull = counts["BULLISH"]
    bear = counts["BEARISH"]
    if bull >= 3:
        return "BULLISH", " · ".join(parts)
    if bear >= 3:
        return "BEARISH", " · ".join(parts)
    if bull > 0 and bear > 0:
        return "MIXED", " · ".join(parts)
    if bull > bear:
        return "BULLISH", " · ".join(parts)
    if bear > bull:
        return "BEARISH", " · ".join(parts)
    return "NEUTRAL", " · ".join(parts)


def _load_prev_snapshot() -> Dict[str, Dict[str, Any]]:
    """직전 estate_sector_pulse.json 을 key→sector dict 로 로드. 없으면 {}."""
    try:
        prev = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError, OSError):
        return {}
    return {
        s["key"]: s
        for s in prev.get("sectors", [])
        if isinstance(s, dict) and s.get("key")
    }


def _carry_forward_if_transient(
    new_sec: Dict[str, Any], prev_sec: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """index fetch 가 transient 실패면 직전 good 값 유지 (Fix A, 2026-05-20).

    carry-forward 조건 (모두 충족):
      1. 신 build 의 index 실패 사유 == "fetch failed or empty" (= fetch 자체 transient 실패).
         "no region series" 같은 구조적 결함은 제외 → 실결함은 가리지 않고 UNAVAILABLE 노출.
      2. 직전 sector 가 존재 + verdict 가 UNAVAILABLE 아님 (= 살릴 good 값 보유).
      3. stale 누적이 STALE_MAX_DAYS 이내.

    정직성: stale=True / stale_since / stale_reason 명시. 값·verdict 는 직전 것 유지.
    회복 시(다음 fetch 성공) _build_sector 가 fresh 반환 → 이 함수가 손 안 댐 → stale 자동 해제.
    """
    if new_sec.get("_error_index") != "fetch failed or empty":
        return new_sec
    if not prev_sec or prev_sec.get("verdict") in (None, "UNAVAILABLE"):
        return new_sec

    now = datetime.now(KST)
    stale_since = prev_sec.get("stale_since") or now.isoformat(timespec="seconds")
    try:
        since_dt = datetime.fromisoformat(stale_since)
        if since_dt.tzinfo is None:
            since_dt = since_dt.replace(tzinfo=KST)
        if (now - since_dt).days > STALE_MAX_DAYS:
            return new_sec  # 너무 오래 stale — UNAVAILABLE 정직 노출
    except ValueError:
        stale_since = now.isoformat(timespec="seconds")

    carried = dict(prev_sec)
    carried["stale"] = True
    carried["stale_since"] = stale_since
    carried["stale_reason"] = "R-ONE index fetch transient 실패 — 직전 good 값 유지"
    base_rat = carried.get("rationale", "")
    if "⚠ stale" not in base_rat:
        suffix = f"⚠ stale (직전 값 {carried.get('as_of', '')})".strip()
        carried["rationale"] = f"{base_rat} · {suffix}".strip(" ·")
    return carried


def build() -> Optional[Dict[str, Any]]:
    prev_map = _load_prev_snapshot()
    sectors_out: List[Dict[str, Any]] = []
    for key, spec in SECTORS.items():
        print(f"[sector_pulse] {key} ({spec['name']}) 처리 중…", file=sys.stderr)
        sec = _build_sector(key, spec)
        sec = _carry_forward_if_transient(sec, prev_map.get(key))
        sectors_out.append(sec)

    valid_count = sum(1 for s in sectors_out if s.get("verdict") != "UNAVAILABLE")
    if valid_count == 0:
        _logger.error("sector_pulse: 4 섹터 모두 실패 — JSON 안 씀")
        return None

    overall, rationale = _overall_verdict(sectors_out)

    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "overall_verdict": overall,
        "overall_rationale": rationale,
        "sectors": sectors_out,
    }


def _write_json_atomic(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    result = build()
    if result is None:
        print("[sector_pulse] build 실패 — 이전 JSON 유지", file=sys.stderr)
        return 1
    _write_json_atomic(OUTPUT_PATH, result)
    valid = sum(1 for s in result["sectors"] if s.get("verdict") != "UNAVAILABLE")
    print(
        f"[sector_pulse] 완료 overall={result['overall_verdict']} valid={valid}/4",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
