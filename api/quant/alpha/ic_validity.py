"""ic_validity — factor_ic_history.json 관측의 통계적 유효성 단일 판정 (D9 step 1).

목적 (2026-06-14): factor_ic_history.json 에 sample_count==0 인 degenerate 관측이
123건 섞여 있다(옛 legacy 마이그레이션 placeholder 42 + 무플래그 81). 이들은 ic_std≈0 로
icir 가 폭주(100.0 / 52.928 / -31.089 등)한다. 소비자(factor_decay / validation_summary /
to-be-built alphalens cross-check)가 이를 거르지 않으면 IC 통계가 오염된다.

이 모듈 = "유효 IC 관측"의 **단일 출처(single source of truth)**. 모든 소비자가 이 predicate
하나로 거른다. 데이터 파일은 변형하지 않음 — 읽는 쪽에서 일관 필터(불변 데이터, 멱등).

판정 = 산식·임계 변경 아님(RULE 7 무관). 순수 입력 위생.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List

# IC 관측 유효성 기준.
# sample_count = 해당 윈도의 IC 시계열 길이(periods). icir = ic_mean/ic_std 라 std 에 >=2 필요.
MIN_SAMPLE_FOR_IC = 1     # ic_mean 단독 유효 최소 periods
MIN_SAMPLE_FOR_ICIR = 2   # icir(=ic_mean/ic_std) 유효 최소 periods (std 정의)
# 실데이터 ICIR 은 통상 |.| < 2. |icir| >= 10 = std≈0 degenerate placeholder (방어 상한).
ICIR_SANE_MAX = 10.0


def _finite(x: Any) -> bool:
    return isinstance(x, (int, float)) and math.isfinite(x)


def is_valid_ic_obs(fobj: Any) -> bool:
    """이 per-factor 관측이 IC 통계에 쓸 수 있는가.

    탈락: dict 아님 / legacy=true / sample_count 결손·0 / ic_mean 비유한 /
          icir 비유한·폭주(|icir|>=ICIR_SANE_MAX = std≈0 degenerate).
    """
    if not isinstance(fobj, dict):
        return False
    if fobj.get("legacy") is True:
        return False
    # sample_count: 명시적 0/비유한 = degenerate 거부. 필드 부재 = 미상으로 통과
    # (실데이터는 producer 가 항상 기록 → 명시 0 만 degenerate. fail-safe: 필드 누락 시 깜깜화 방지).
    n = fobj.get("sample_count")
    if n is not None and (not _finite(n) or n < MIN_SAMPLE_FOR_IC):
        return False
    ic = fobj.get("ic_mean")
    if ic is not None and not _finite(ic):
        return False
    # icir 폭주(|.|>=10 = ic_std≈0) = sample_count 누락 degenerate 의 2차 가드
    icir = fobj.get("icir")
    if icir is not None and (not _finite(icir) or abs(icir) >= ICIR_SANE_MAX):
        return False
    return True


def has_valid_icir(fobj: Any) -> bool:
    """icir 항을 평균/추세에 넣어도 되는가 (ic 유효 + periods>=2 + 폭주 아님)."""
    if not is_valid_ic_obs(fobj):
        return False
    icir = fobj.get("icir")
    if icir is None or not _finite(icir):
        return False
    # sample_count 명시 <2 = std 정의 불가 거부. 부재 = 통과(icir 폭주 가드가 백업)
    n = fobj.get("sample_count")
    if n is not None and n < MIN_SAMPLE_FOR_ICIR:
        return False
    return True


def valid_factor_obs(entry: Dict[str, Any]) -> Dict[str, Any]:
    """history 엔트리(1일 스냅샷)에서 유효 팩터 관측만 추린 factors dict 반환."""
    factors = entry.get("factors") or {}
    return {k: v for k, v in factors.items() if is_valid_ic_obs(v)}


def filter_valid_series(history: List[Dict[str, Any]], factor: str) -> List[Dict[str, Any]]:
    """factor 의 유효 관측만(엔트리 dict 그대로) 시계열 반환 — degenerate 제거."""
    out: List[Dict[str, Any]] = []
    for entry in history:
        fobj = (entry.get("factors") or {}).get(factor)
        if is_valid_ic_obs(fobj):
            out.append(fobj)
    return out
