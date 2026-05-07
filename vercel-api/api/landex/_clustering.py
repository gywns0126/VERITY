"""RTMS 단지명 clustering — RTMS API 의 `aptNm` 문자열 표기 변형을 단일 단지로 묶음.

RTMS 한계 (memory `project_estate_brain_kickoff` V0.2):
  국토부 RTMS API 는 단지 고유 ID 가 없고 *문자열만* 제공.
  같은 단지가 "래미안강남" / "래미안 강남" / "래미안강남(1단지)" / "래미안강남 1차" 등
  다양한 표기로 들어와서 그대로 group 시 단지 단위 산출 불가능.

V0 알고리즘:
  1. normalize_apt_name — 괄호/번호 표기/공백/특수문자 제거
  2. group by (dong, normalized_apt, build_year) → cluster
  3. complex_id = `{gu}_{dong}_{normalized_apt}_{build_year}` 결정적 안정 키

V1 (운영 데이터 누적 후):
  - build_year ±1 fuzzy
  - Levenshtein/Jaro 거리 기반 normalized_apt 추가 매칭
  - 단지 좌표 (VWORLD 지오코더, memory `project_vworld_api_spec`) 로 재검증
"""
from __future__ import annotations

import re
from statistics import mean, median
from typing import Any, Dict, List, Optional

# ────────────────────────────────────────────────────────────
# 단지명 normalize — 표기 변형 흡수

# 순서 의미: 괄호 안 단지 표기가 있으니 괄호부터, 그다음 n단지/n차 명시, 마지막 공백·특수문자
_RE_PARENS = re.compile(r"\([^)]*\)|\[[^\]]*\]")
_RE_NUMBER_UNIT = re.compile(r"\d+\s*(단지|차|동|블록|블럭)")
_RE_SPECIAL = re.compile(r"[\-·~,/_\.]+")
_RE_WHITESPACE = re.compile(r"\s+")


def normalize_apt_name(name: Optional[str]) -> str:
    """RTMS 단지명 → 정규화 키.

    "래미안 강남(1단지)" / "래미안강남 1차" / "래미안·강남" → "래미안강남"
    빈/None 입력 → "" (호출자가 cluster 제외 책임).
    """
    if not name:
        return ""
    s = name.strip()
    s = _RE_PARENS.sub("", s)
    s = _RE_NUMBER_UNIT.sub("", s)
    s = _RE_SPECIAL.sub("", s)
    s = _RE_WHITESPACE.sub("", s)
    return s.strip()


# ────────────────────────────────────────────────────────────
# Cluster 생성 — RTMS trade list → 단지 단위 묶음

def make_complex_id(gu: str, dong: str, normalized_apt: str, build_year: int) -> str:
    """결정적 안정 키. 외부 시스템 (estate_portfolio.json 등) 에서 단지 ID 로 사용.

    공백/특수문자는 normalize 단계에서 이미 제거됨. underscore 안전.
    """
    g = (gu or "unknown").strip().replace(" ", "")
    d = (dong or "unknown").strip().replace(" ", "")
    a = normalized_apt or "unknown"
    y = build_year if build_year and build_year > 0 else 0
    return f"{g}_{d}_{a}_{y}"


def cluster_trades(
    trades: List[Dict[str, Any]],
    gu: str,
) -> List[Dict[str, Any]]:
    """RTMS 거래 list → 단지 cluster list.

    그룹 키: (dong, normalized_apt, build_year)
    면적은 cluster 내부 다양 보존 (59㎡/84㎡/114㎡ 등 같은 단지 내 면적별).

    Returns: cluster list 정렬 = trade_count desc.
    각 cluster:
      complex_id, gu, dong, apt_normalized, apt_raw_examples (≤5 unique),
      build_year, trade_count, area_m2 (min/max/median),
      price_pyeong (mean/median), latest/oldest_deal_date
    """
    groups: Dict[tuple, List[Dict[str, Any]]] = {}
    for t in trades:
        normalized = normalize_apt_name(t.get("apt"))
        if not normalized:
            continue  # 단지명 없음 = cluster 불가능
        dong = (t.get("dong") or "").strip()
        build_year = t.get("build_year") or 0
        key = (dong, normalized, build_year)
        groups.setdefault(key, []).append(t)

    out: List[Dict[str, Any]] = []
    for (dong, normalized, build_year), members in groups.items():
        areas = [m["area_m2"] for m in members if m.get("area_m2", 0) > 0]
        prices_pyeong = [m["price_pyeong"] for m in members if m.get("price_pyeong", 0) > 0]
        deal_dates = sorted([m["deal_date"] for m in members if m.get("deal_date")])
        raw_names = []
        for m in members:
            nm = (m.get("apt") or "").strip()
            if nm and nm not in raw_names:
                raw_names.append(nm)
            if len(raw_names) >= 5:
                break

        out.append({
            "complex_id": make_complex_id(gu, dong, normalized, build_year),
            "gu": gu,
            "dong": dong,
            "apt_normalized": normalized,
            "apt_raw_examples": raw_names,
            "build_year": build_year,
            "trade_count": len(members),
            "area_m2": {
                "min": min(areas) if areas else None,
                "max": max(areas) if areas else None,
                "median": round(median(areas), 1) if areas else None,
            },
            "price_pyeong": {
                "mean": round(mean(prices_pyeong)) if prices_pyeong else None,
                "median": round(median(prices_pyeong)) if prices_pyeong else None,
            },
            "latest_deal_date": deal_dates[-1] if deal_dates else None,
            "oldest_deal_date": deal_dates[0] if deal_dates else None,
        })

    out.sort(key=lambda c: c["trade_count"], reverse=True)
    return out


# ────────────────────────────────────────────────────────────
# Cluster lookup — complex_id 로 거래 역추적

def filter_trades_by_cluster(
    trades: List[Dict[str, Any]],
    cluster: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """단일 cluster 의 멤버 거래만 추출 (estate_brain L4 인근 실거래 입력).

    동일 (dong, normalized_apt, build_year) 매칭. 면적·평형은 호출자 추가 필터.
    """
    target_dong = cluster.get("dong", "")
    target_apt = cluster.get("apt_normalized", "")
    target_year = cluster.get("build_year", 0)
    out = []
    for t in trades:
        if (t.get("dong") or "").strip() != target_dong:
            continue
        if normalize_apt_name(t.get("apt")) != target_apt:
            continue
        if (t.get("build_year") or 0) != target_year:
            continue
        out.append(t)
    return out
