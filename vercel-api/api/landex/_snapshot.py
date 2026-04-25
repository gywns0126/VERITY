"""LANDEX 스냅샷 컴퓨터 — 3개 어댑터 통합 + Supabase 저장.

Vercel 10s timeout 제약상 25구 일괄 fetch 는 API 라우트 부적합.
이 모듈은 다음 두 곳에서 호출:
  1. 별도 cron 워커 (Railway 또는 GitHub Actions) — 일/월별 자동 실행
  2. 수동 트리거 — `python -m api.landex._snapshot 2026-04` (개발/검증)

저장 위치: Supabase `estate_landex_snapshots` 테이블 (PK: gu+month+preset+methodology_version)
재실행 시 upsert (on_conflict=...).

API 라우트(`/api/landex/scores`)는 이 스냅샷을 읽기만 함 — 빠른 응답 보장.
"""
from __future__ import annotations

import logging
import os
import sys
import time
from typing import Optional

import requests
from statistics import median

from . import _methodology as M
from ._compute import (
    filter_outliers_statistical, normalize_minmax, compute_landex,
    score_to_tier10, tier10_to_tier5, detect_divergence,
)
from ._sources._lawd import SEOUL_25_GU
from ._sources import ecos, molit, seoul_subway

_logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# ◆ Supabase upsert helper (snapshot 쓰기 전용 — service_role 필요)
# ──────────────────────────────────────────────────────────────

def _supabase_upsert(table: str, rows: list[dict], on_conflict: str) -> bool:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    sk = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not sk:
        _logger.warning("Supabase service_role 미설정 — 스냅샷 저장 스킵")
        return False
    endpoint = f"{url}/rest/v1/{table}?on_conflict={on_conflict}"
    headers = {
        "apikey": sk,
        "Authorization": f"Bearer {sk}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    try:
        r = requests.post(endpoint, headers=headers, json=rows, timeout=15)
        r.raise_for_status()
        return True
    except Exception as e:
        _logger.error("Supabase upsert 실패 (%s): %s", table, e)
        return False


# ──────────────────────────────────────────────────────────────
# ◆ 점수 산출 파이프라인
# ──────────────────────────────────────────────────────────────

def _compute_v_scores(month: str) -> dict[str, Optional[float]]:
    """V(Value) 점수 — 국토부 실거래가 API 호출. 25구 순차 fetch.

    Returns: { "강남구": 72.3, "서초구": 65.1, ..., "강북구": None }
    """
    yyyymm = month.replace("-", "")
    gu_medians: dict[str, Optional[float]] = {}
    seoul_total_prices: list[float] = []

    for gu in SEOUL_25_GU:
        trades = molit.fetch_apt_trades(gu, yyyymm, timeout=8.0)
        if not trades:
            gu_medians[gu] = None
            continue
        # 1차 룰 필터
        passed, _ = molit.filter_rule_based(trades)
        if len(passed) < 5:
            gu_medians[gu] = None
            continue
        # 2차 통계 필터
        filtered, _ = filter_outliers_statistical(passed, price_field="price_pyeong")
        if len(filtered) < 3:
            gu_medians[gu] = None
            continue
        # 3차: 중앙값
        prices = [t["price_pyeong"] for t in filtered]
        med = median(prices)
        gu_medians[gu] = med
        seoul_total_prices.extend(prices)
        # API rate limit 대응
        time.sleep(0.1)

    if not seoul_total_prices:
        return {gu: None for gu in SEOUL_25_GU}
    seoul_avg = median(seoul_total_prices)

    # ratio → V 점수 (저평가 = 고점수)
    out: dict[str, Optional[float]] = {}
    for gu, med in gu_medians.items():
        if med is None or seoul_avg <= 0:
            out[gu] = None
            continue
        ratio = med / seoul_avg
        if ratio <= 0.5:
            out[gu] = 100.0
        elif ratio >= 2.0:
            out[gu] = 0.0
        else:
            out[gu] = round(100 - ((ratio - 0.5) / 1.5) * 100, 1)
    return out


def _compute_r_score() -> Optional[float]:
    """R(Risk) 점수 — 한국은행 ECOS 기준금리. 25구 동일 (거시 지표).

    Note: 향후 구별 전세가율·LTV 차이 반영하면 구별로 다른 R 점수 가능.
    v1 은 거시 단일 R.
    """
    series = ecos.fetch_base_rate(months_back=12)
    if not series:
        return None
    return ecos.compute_risk_score(series)


def _compute_c_scores() -> dict[str, Optional[float]]:
    """C(Convenience) 점수 — 서울 지하철 카드 통계.

    한 번의 API 호출로 약 1000행 가져와서 25구 집계.
    """
    rows = seoul_subway.fetch_card_stats_recent(start_idx=1, end_idx=1000, timeout=10.0)
    if not rows:
        return {gu: None for gu in SEOUL_25_GU}
    by_gu = seoul_subway.aggregate_by_gu(rows)
    scores = seoul_subway.compute_convenience_scores(by_gu)
    return {gu: scores.get(gu) for gu in SEOUL_25_GU}


# ──────────────────────────────────────────────────────────────
# ◆ 통합 스냅샷 생성
# ──────────────────────────────────────────────────────────────

def compute_snapshot(month: str, preset: str = "balanced") -> list[dict]:
    """25구 LANDEX 스냅샷 생성 후 dict 리스트 반환.

    실 데이터 없으면 None — 호출자가 판단해서 mock fallback 또는 에러 표시.
    D, S, GEI 는 v1 mock (다음 세션에서 KOSIS·서울 일반 API 추가).
    """
    print(f"[snapshot] 시작 month={month} preset={preset}", flush=True)

    print("[snapshot] V 점수 — 국토부 실거래가 fetch...", flush=True)
    v_scores = _compute_v_scores(month)
    valid_v = sum(1 for v in v_scores.values() if v is not None)
    print(f"[snapshot] V 점수: 25구 중 {valid_v}구 산출 성공", flush=True)

    print("[snapshot] R 점수 — ECOS 기준금리 fetch...", flush=True)
    r_score = _compute_r_score()
    print(f"[snapshot] R 점수: {r_score}", flush=True)

    print("[snapshot] C 점수 — 서울 지하철 fetch...", flush=True)
    c_scores = _compute_c_scores()
    valid_c = sum(1 for v in c_scores.values() if v is not None)
    print(f"[snapshot] C 점수: 25구 중 {valid_c}구 산출 성공", flush=True)

    # D, S, GEI 는 mock (다음 단계 KOSIS·서울 일반에서 채움)
    rows = []
    for gu in SEOUL_25_GU:
        v = v_scores.get(gu)
        c = c_scores.get(gu)
        # D, S 결정적 mock
        seed = sum(ord(ch) for ch in gu) + sum(ord(ch) for ch in month)
        d = round(40 + (abs((seed * 137) % 100) / 100) * 60, 1)
        s = round(40 + (abs((seed * 211) % 100) / 100) * 60, 1)
        # GEI 도 mock (KOSIS·서울 일반 추가 후 실제 산출)
        gei = round((abs((seed * 17) % 100)), 1)
        gei_stage = 4 if gei >= 80 else 3 if gei >= 60 else 2 if gei >= 40 else 1 if gei >= 20 else 0

        scores = {"V": v, "D": d, "S": s, "C": c, "R": r_score}
        landex, missing = compute_landex(scores, preset=preset)
        tier_obj = score_to_tier10(landex) if landex is not None else None

        rows.append({
            "gu": gu, "month": month, "preset": preset,
            "v_score": v, "d_score": d, "s_score": s, "c_score": c, "r_score": r_score,
            "landex": landex,
            "tier10": tier_obj["code"] if tier_obj else None,
            "gei": gei, "gei_stage": gei_stage,
            "raw_payload": {
                "v_source": "molit_real" if v is not None else "missing",
                "c_source": "seoul_subway_real" if c is not None else "missing",
                "r_source": "ecos_real" if r_score is not None else "missing",
                "d_source": "mock",
                "s_source": "mock",
                "gei_source": "mock",
                "missing_factors": missing,
            },
            "methodology_version": M.VERSION,
        })

    return rows


def save_snapshot(rows: list[dict]) -> bool:
    """스냅샷 행들을 estate_landex_snapshots 에 upsert."""
    if not rows:
        return False
    return _supabase_upsert(
        "estate_landex_snapshots",
        rows,
        on_conflict="gu,month,preset,methodology_version",
    )


# ──────────────────────────────────────────────────────────────
# ◆ CLI: python -m api.landex._snapshot 2026-04 [--preset balanced]
# ──────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("Usage: python -m api.landex._snapshot YYYY-MM [--preset balanced|growth|value]", file=sys.stderr)
        sys.exit(1)
    month = sys.argv[1]
    preset = "balanced"
    if "--preset" in sys.argv:
        idx = sys.argv.index("--preset")
        if idx + 1 < len(sys.argv):
            preset = sys.argv[idx + 1]

    rows = compute_snapshot(month, preset=preset)
    print(f"\n[snapshot] 생성 완료: {len(rows)}구")

    if save_snapshot(rows):
        print("[snapshot] Supabase 저장 성공 ✓")
    else:
        print("[snapshot] Supabase 저장 실패 (또는 service_role 미설정) — 결과만 출력")
        for r in rows[:5]:
            print(f"  {r['gu']:6s} V={r['v_score']} D={r['d_score']} S={r['s_score']} "
                  f"C={r['c_score']} R={r['r_score']} → LANDEX={r['landex']} ({r['tier10']})")


if __name__ == "__main__":
    main()
