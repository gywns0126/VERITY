"""
매크로 지표 메타(as_of/collected_at) 표시 헬퍼.

리포트 매크로 블록 끝에 "지표 기준일" 한 줄을 붙여,
서로 다른 시점의 지표가 혼재되었을 때 사용자가 인지하도록 한다.

feedback_macro_timestamp_policy 메모리 정책 직결.
"""
from __future__ import annotations

from typing import Iterable, Optional


def _gather_as_of(macro: dict, keys: Iterable[str]) -> list:
    out = []
    for k in keys:
        v = (macro.get(k) or {}).get("as_of")
        if v:
            out.append(v)
    return out


def macro_as_of_line(macro: Optional[dict],
                     keys: Iterable[str] = ("vix", "us_10y", "usd_krw", "wti_oil", "sp500")) -> str:
    """매크로 블록 끝에 붙일 한 줄. 시점 통일이면 단일 날짜, 다르면 범위 표기."""
    if not isinstance(macro, dict):
        return ""

    collected = macro.get("collected_at") or ""
    dates = sorted(set(_gather_as_of(macro, keys)))

    if not dates:
        if collected:
            return f"지표 수집 시각: {collected[:16]}"
        return ""

    if len(dates) == 1:
        return f"지표 기준일: {dates[0]} (수집 {collected[:16]})" if collected else f"지표 기준일: {dates[0]}"

    # 시점 불일치
    if collected:
        return (f"지표 기준일: {dates[0]} ~ {dates[-1]} (시점 혼재 {len(dates)}종) "
                f"· 수집 {collected[:16]}")
    return f"지표 기준일: {dates[0]} ~ {dates[-1]} (시점 혼재 {len(dates)}종)"
