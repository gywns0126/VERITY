"""universe_scan_builder — universe scan + stock_filter 별도 cron 분리.

배경 (2026-05-10):
  daily_analysis_full 의 STEP 2 (run_filter_pipeline_with_ramp_up) 가 universe 5000
  ticker 처리 = 35분 (cooler/retry 누적). 그 후 STEP 3-12 (60 candidate × 12 외부 API
  step) = 75분. 합 110분 → watchdog 도달 SIGTERM. macro_collect 패턴 확장 = universe
  scan + filter 도 별도 cron 분리. daily_analysis 는 적재된 candidate jsonl 만 읽음.

배치:
  - cron: 평일 KST 15:30 (UTC 06:30). KR 시장 마감 (15:30) 직후 = 당일 종가 반영.
  - 산출: data/universe_candidates.json (collected_at + candidates + diagnostics)
  - daily_analysis_full STEP 2 = snapshot 읽기 fast path + max_stale 2h fallback.

거짓말 트랩 정합 (feedback_data_collection_verification_mandatory):
  - try/finally + logged stderr 표식
  - silent skip 절대 금지 — fail 시 errors[] 박고 최종 exit code 분리
  - 직전 snapshot 보존 (이번 run candidates 0건이면 file 덮어쓰기 X)
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUTPUT_PATH = os.path.join(_REPO_ROOT, "data", "universe_candidates.json")

KST = timezone(timedelta(hours=9))

# KR 결식 시 직전 snapshot KR 후보를 승계할 수 있는 최대 경과(시간).
# 96h = 금요일 스캔 → 월요일 오전까지 커버 (main.py STEP 2 의 주말 max_stale 과 동일 폭).
_KR_FALLBACK_MAX_STALE_H = 96


def _now_kst() -> datetime:
    return datetime.now(KST)


def _snapshot_age_hours(collected_at: Any, now: datetime) -> float | None:
    """collected_at(ISO) 기준 경과 시간. 파싱 실패 시 None (= 승계 불가 취급)."""
    if not collected_at:
        return None
    try:
        dt = datetime.fromisoformat(str(collected_at))
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=KST)
    return (now - dt).total_seconds() / 3600.0


def _load_existing() -> Dict[str, Any]:
    """직전 snapshot — 이번 run 의 candidates 0건 일 때 fallback."""
    if not os.path.isfile(OUTPUT_PATH):
        return {}
    try:
        with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except (OSError, json.JSONDecodeError):
        return {}


def build() -> Dict[str, Any]:
    """run_filter_pipeline_with_ramp_up 호출 → snapshot dict.

    실패 시에도 항상 dict 반환 (T1 — diagnostics 에 source 명시).
    """
    from api.analyzers.stock_filter import run_filter_pipeline_with_ramp_up

    now = _now_kst()
    started = time.time()
    candidates: List[Dict[str, Any]] = []
    error: str | None = None

    try:
        candidates = run_filter_pipeline_with_ramp_up(market_scope="all") or []
    except BaseException as e:
        error = f"{type(e).__name__}: {str(e)[:200]}"
        sys.stderr.write(f"[universe_scan] FAIL: {error}\n")

    elapsed = round(time.time() - started, 2)

    # 0건 fallback — 직전 snapshot 보존 (commit 안 해도 되도록 caller 가 판단)
    prev = _load_existing()
    used_prev = False
    if not candidates and isinstance(prev.get("candidates"), list) and prev["candidates"]:
        candidates = prev["candidates"]
        used_prev = True
        sys.stderr.write(
            f"[universe_scan] used_prev=True (이번 run 0건, 직전 snapshot {len(candidates)}건)\n"
        )

    kr_count = sum(1 for c in candidates if c.get("currency") != "USD")
    us_count = sum(1 for c in candidates if c.get("currency") == "USD")

    # ── 🚨 2026-07-27 — market 단위 결식(starvation) 가드 ──────────────────────
    # 기존 fallback 은 candidates *전체* 0 건만 봤음. 한쪽 시장만 비면 통과 → 오염 snapshot
    # 이 그대로 굳고 37분 뒤 daily_analysis_full 이 물어감.
    #
    # 실사고 (2026-07-27): 15:30 스캔에서 `[Phase 2-A] KR universe build 실패 → 코어 fallback:
    #   KRX OpenAPI K1 빈 응답` → snapshot = 후보 15건 전부 US (kr_count=0 인데 ok=true,
    #   used_prev_snapshot=false 로 기록됨). 16:07 full 이 그 snapshot 을 fast path 로 물어
    #   `최종 후보: 15개` → 그날 KR 추천이 11 → 1 로 붕괴(관심종목 1건만 잔존).
    #   19:41 재스캔은 KR 10 으로 자가복구했으나, 이미 산출된 recommendations 는 KR 1 로 고정.
    # 즉 상류 일시 장애 1회가 그날 KR 판단 대상을 통째로 삭제. 신선한 US 를 버릴 이유는 없으므로
    # **시장별로** 직전 정상분을 잇는다. 선례 = 채움율 급락 publish 차단 게이트(2026-07-13).
    _prev_cands = prev.get("candidates") if isinstance(prev.get("candidates"), list) else []
    kr_used_prev = False
    kr_prev_at: str | None = None
    if not used_prev and kr_count == 0 and _prev_cands:
        prev_kr = [c for c in _prev_cands if c.get("currency") != "USD"]
        # 직전 snapshot 이 이미 splice 본이면 원 스캔 시각을 승계 — 무한 연쇄 방지.
        _pd = prev.get("diagnostics") or {}
        origin_at = _pd.get("kr_prev_collected_at") or prev.get("collected_at")
        age_h = _snapshot_age_hours(origin_at, now)
        if prev_kr and age_h is not None and age_h <= _KR_FALLBACK_MAX_STALE_H:
            candidates = candidates + prev_kr
            kr_count = len(prev_kr)
            kr_used_prev = True
            kr_prev_at = origin_at
            sys.stderr.write(
                f"::warning::[universe_scan] KR 결식 — 이번 run KR 0건. 직전 snapshot KR "
                f"{len(prev_kr)}건 승계 (원 스캔 {origin_at}, {age_h:.1f}h 경과). US {us_count}건은 신선분 유지.\n"
            )
        else:
            sys.stderr.write(
                f"::warning::[universe_scan] KR 결식 — 이번 run KR 0건이고 승계 불가 "
                f"(직전 KR {len(prev_kr)}건, age={age_h}h, 상한 {_KR_FALLBACK_MAX_STALE_H}h).\n"
            )
    kr_starved = kr_count == 0

    # ── 상승 신호 승격 병합 (PREREG_MULTIBAGGER_UPSIDE_FUNNEL_2026_08_22, PM 지시) ──
    # PM "그럼 상승 신호만 잡아." 🚨 실측 문제: alert>=2 인 78종목이 후보(25)·운영풀(38)
    #   어디에도 없었다(교집합 **0**). 신호가 켜져도 구조적으로 매수 후보가 못 됐다.
    # 🚨 이 병합은 **필터가 뺀 소형주를 신호로 되살리는 것**이다(승격분 시총 중앙 1,709억
    #   = 필터 통과분 5.06조의 1/30). 2026-08-21 전향 검정상 그 구간은 90% 손실 확률이
    #   가장 높은 분위이기도 하다 — 하방 배제는 PM 결정으로 미뤄졌다. 조용히 넣지 않고
    #   `promoted_by` 태그 + 진단으로 **분리 집계 가능**하게 남긴다.
    # 추가만 한다 — 기존 후보를 밀어내지 않고, red_flags·auto_avoid·채점은 그대로 받는다.
    candidates, promoted_n, promote_meta = merge_promoted(candidates)
    kr_count += promoted_n if promoted_n else 0

    # US 유니버스 소스 de-silence — 캐시 부재 시 fallback(S&P100+core) 명시.
    # universe_us.json gitignored + 생성기 없음 → 상시 fallback. silent degradation 아닌 의식 상태.
    _us_cache = os.path.join(_REPO_ROOT, "data", "cache", "universe_us.json")
    us_universe_source = "cache" if os.path.exists(_us_cache) else "static_fallback"

    diagnostics = {
        "ok": error is None and bool(candidates),
        "candidates_count": len(candidates),
        "kr_count": kr_count,
        "us_count": us_count,
        # 2026-07-27 — market 단위 결식 가시화. kr_starved=true = 그날 KR 판단 대상 0.
        "kr_used_prev": kr_used_prev,
        "kr_prev_collected_at": kr_prev_at,
        "kr_starved": kr_starved,
        "us_universe_source": us_universe_source,  # "static_fallback" = US ~S&P100 (KR-first interim)
        "ramp_up_stage": int(os.environ.get("UNIVERSE_RAMP_UP_STAGE", "0") or 0),
        "ramp_up_note": "5000 = cap(상한), 목표 아님 — 실 유니버스 = 품질 floor 통과 전체",
        "elapsed_s": elapsed,
        "used_prev_snapshot": used_prev,
        # 🚨 승격 자기신고 — 몇 건이 필터를 우회해 들어왔는지 산출물이 스스로 말한다.
        #   안 남기면 나중에 성적이 무엇 덕분/때문인지 갈리지 않는다(RULE 12).
        "multibagger_promoted": promoted_n,
        "multibagger_promote_meta": promote_meta,
        "error": error,
    }

    return {
        "collected_at": now.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "candidates": candidates,
        "diagnostics": diagnostics,
        "schema_version": "v0",
    }


PROMOTE_PATH = os.path.join(_REPO_ROOT, "data", "metadata", "multibagger_promote.json")


def merge_promoted(candidates: List[Dict[str, Any]],
                   path: Optional[str] = None) -> tuple:
    """멀티배거 승격분을 후보에 **추가**한다. 기존 후보를 밀어내지 않는다.

    Returns: (candidates, promoted_n, promote_meta)

    🚨 별 함수로 뺀 이유 = 인라인이면 58분짜리 스캔을 돌려야만 검증된다.
       배선을 만들고 다음 cron 까지 못 재는 상태가 오늘 반복된 사고 패턴이다.
    """
    pp = path or PROMOTE_PATH
    try:
        if not os.path.exists(pp):
            return candidates, 0, {}
        with open(pp, encoding="utf-8") as f:
            pj = json.load(f)
        have = {c.get("ticker") for c in candidates if isinstance(c, dict)}
        add = [c for c in (pj.get("candidates") or [])
               if isinstance(c, dict) and c.get("ticker") and c["ticker"] not in have]
        meta = {k: pj.get(k) for k in
                ("as_of", "watch_n", "eligible_n", "cap", "promoted_n",
                 "dropped_no_full_record", "min_alert")}
        meta["merged_n"] = len(add)
        meta["dup_skipped"] = len(pj.get("candidates") or []) - len(add)
        sys.stderr.write(
            f"[universe_scan] 멀티배거 승격 병합 {len(add)}건 "
            f"(대상 {pj.get('eligible_n')} · 상한 {pj.get('cap')} · "
            f"중복제외 {meta['dup_skipped']})\n")
        kr_added = sum(1 for c in add if (c.get("currency") or "") != "USD")
        return candidates + add, kr_added, meta
    except Exception as e:  # noqa: BLE001 — 승격 병합 실패가 스캔을 죽이지 않는다
        sys.stderr.write(f"[universe_scan] 승격 병합 skip: {type(e).__name__}: {e}\n")
        return candidates, 0, {}


def _atomic_write(path: str, data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    os.replace(tmp, path)


def main() -> int:
    snapshot = build()
    _atomic_write(OUTPUT_PATH, snapshot)
    diag = snapshot.get("diagnostics", {})
    sys.stderr.write(
        f"[universe_scan] snapshot OK at={snapshot.get('collected_at')} "
        f"candidates={diag.get('candidates_count')} (KR {diag.get('kr_count')} + US {diag.get('us_count')}) "
        f"stage={diag.get('ramp_up_stage')} elapsed={diag.get('elapsed_s')}s "
        f"used_prev={diag.get('used_prev_snapshot')} kr_used_prev={diag.get('kr_used_prev')}\n"
    )
    # 승계로도 못 채운 KR 결식 = 그날 KR 판단 대상 0 → 조용히 넘기지 않음.
    if diag.get("kr_starved"):
        sys.stderr.write(
            "::error::[universe_scan] KR 결식 미해소 — 이 snapshot 으로 분석하면 그날 KR 추천이 "
            "관심종목만 남음(2026-07-27 사고 재현). 상류 KRX universe build 점검 필요.\n"
        )

    # 편승 — data_pipeline_health 갱신 (별도 cron 추가 X)
    try:
        from api.observability.data_pipeline_health import write_data_pipeline_health
        write_data_pipeline_health()
    except Exception as _e:
        sys.stderr.write(f"[universe_scan] data_pipeline_health 갱신 실패(무시): {_e}\n")

    if not diag.get("ok"):
        sys.stderr.write(f"[universe_scan] FATAL — error={diag.get('error')}\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
