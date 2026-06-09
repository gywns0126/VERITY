"""macro_industry_align — Macro Themes × Industry Themes × Mapping → sector alignment.

PM 직관 (5/20): Top-down Macro → Industry → Stock 의 B 단계.
  - A: macro_themes_pulse (IB strategist weekly themes, 5/20 추가 af33a9f0)
  - B (본 모듈): A + Industry Themes + mapping dict → favored/disfavored sectors 시그널
  - C: 위 신호를 5단계 funnel + Brain v5 grade 에 적용 (Brain v6 정합 후)

산식 v0 (자체 결정, RULE 7):
  sector_score[sector] = Σ_themes (
      direction_score × conviction_weight × mapping_tilt[macro_category][direction][sector]
  )

  alignment 분류:
    |score| ≥ 0.5 → STRONG_TILT
    |score| ≥ 0.2 → TILT
    else → NEUTRAL

  favored / disfavored = 비-NEUTRAL sectors (score 부호 별)

신규 LLM call 0건 — static dictionary + 기존 pulse JSON 재사용. RULE 6 정합.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
KST = timezone(timedelta(hours=9))
DATA_DIR = REPO_ROOT / "data"
MAPPING_PATH = DATA_DIR / "macro_industry_mapping.json"
MACRO_THEMES_PATH = DATA_DIR / "macro_themes_pulse.json"
INDUSTRY_THEMES_PATH = DATA_DIR / "industry_themes_pulse.json"
OUTPUT_PATH = DATA_DIR / "macro_industry_alignment.json"

_logger = logging.getLogger(__name__)

DIRECTION_SCORE = {"positive": 1.0, "negative": -1.0, "neutral": 0.0}
CONVICTION_WEIGHT = {"high": 1.0, "mid": 0.6, "low": 0.3}


def load_mapping(path: Path = MAPPING_PATH) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _tilt_for(mapping: Dict[str, Any], category: str, direction: str, sector: str) -> float:
    """category × direction × sector 의 tilt 조회. 없으면 0.0.

    neutral direction 은 tilt 없음 (mapping 에 neutral 키 없음 → 0.0 자연 반환).
    """
    cat_map = (mapping.get("mappings") or {}).get(category)
    if not isinstance(cat_map, dict):
        return 0.0
    dir_map = cat_map.get(direction)
    if not isinstance(dir_map, dict):
        return 0.0
    val = dir_map.get(sector)
    if isinstance(val, (int, float)):
        return float(val)
    return 0.0


def _classify_tilt(score: float, strong_threshold: float, tilt_threshold: float) -> str:
    if abs(score) >= strong_threshold:
        return "STRONG_TILT"
    if abs(score) >= tilt_threshold:
        return "TILT"
    return "NEUTRAL"


def compute_alignment(
    macro_themes: List[Dict[str, Any]],
    industry_themes: Optional[List[Dict[str, Any]]] = None,
    mapping: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """macro themes (+ optional industry themes) → sector alignment scores.

    Args:
        macro_themes: macro_themes_pulse.json 의 themes list (각 dict — category/direction/conviction).
        industry_themes: industry_themes_pulse.json 의 themes (optional). v0 = 미사용 (큐잉, v0.1 에서 결합).
        mapping: macro_industry_mapping.json. None 이면 default 로드.

    Returns: alignment dict with sectors[], favored[], disfavored[], computed_at.
    """
    if mapping is None:
        mapping = load_mapping()
    sectors_list = mapping.get("sectors") or []
    thresholds = mapping.get("_thresholds") or {}
    strong = float(thresholds.get("strong_tilt", 0.5))
    tilt = float(thresholds.get("tilt", 0.2))

    sector_scores: Dict[str, float] = {s: 0.0 for s in sectors_list}
    sector_contrib_count: Dict[str, int] = {s: 0 for s in sectors_list}

    for t in macro_themes or []:
        if not isinstance(t, dict):
            continue
        cat = (t.get("category") or "").strip().lower()
        direction = (t.get("direction") or "").strip().lower()
        conviction = (t.get("conviction") or "mid").strip().lower()
        dir_score = DIRECTION_SCORE.get(direction, 0.0)
        conv_w = CONVICTION_WEIGHT.get(conviction, CONVICTION_WEIGHT["mid"])
        if dir_score == 0.0:
            continue  # neutral theme = no tilt contribution
        for sector in sectors_list:
            tilt_val = _tilt_for(mapping, cat, direction, sector)
            if tilt_val == 0.0:
                continue
            # dir_score 가 이미 +1 / -1 부호 반영 — mapping 의 direction key 와 매칭.
            # 그러나 tilt_val 자체가 direction-specific 반영됨 → 부호 중복 X.
            # 합성: contribution = conviction_weight × tilt_val (이미 dir-specific)
            contribution = conv_w * tilt_val
            sector_scores[sector] += contribution
            sector_contrib_count[sector] += 1

    # 정규화: contribution count 로 평균. 일부 sector 가 모든 theme 에서 영향 받지 않을 수 있음.
    sectors_out = []
    for sector in sectors_list:
        raw = sector_scores[sector]
        count = sector_contrib_count[sector]
        normalized = (raw / count) if count > 0 else 0.0
        tier = _classify_tilt(normalized, strong, tilt)
        sectors_out.append({
            "sector": sector,
            "score": round(normalized, 3),
            "raw_score": round(raw, 3),
            "contribution_count": count,
            "tier": tier,
        })

    sectors_out.sort(key=lambda x: -x["score"])
    favored = [s for s in sectors_out if s["tier"] != "NEUTRAL" and s["score"] > 0]
    disfavored = [s for s in sectors_out if s["tier"] != "NEUTRAL" and s["score"] < 0]

    return {
        "schema_version": "v0.1",
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "macro_themes_count": len([t for t in (macro_themes or []) if isinstance(t, dict)]),
        "sectors": sectors_out,
        "favored": [s["sector"] for s in favored],
        "disfavored": [s["sector"] for s in disfavored],
        "favored_count": len(favored),
        "disfavored_count": len(disfavored),
        "thresholds": {"strong_tilt": strong, "tilt": tilt},
    }


def main() -> int:
    if not MACRO_THEMES_PATH.exists():
        _logger.error("macro_themes_pulse.json 없음 — macro_themes_brief 먼저 실행")
        return 1
    if not MAPPING_PATH.exists():
        _logger.error("macro_industry_mapping.json 없음")
        return 1

    macro_data = json.loads(MACRO_THEMES_PATH.read_text(encoding="utf-8"))
    macro_themes = macro_data.get("themes") or []

    industry_data: Optional[Dict[str, Any]] = None
    if INDUSTRY_THEMES_PATH.exists():
        try:
            industry_data = json.loads(INDUSTRY_THEMES_PATH.read_text(encoding="utf-8"))
        except Exception as e:
            _logger.warning("industry_themes_pulse load failed: %s", e)

    industry_themes = (industry_data or {}).get("themes") if industry_data else None
    out = compute_alignment(macro_themes, industry_themes=industry_themes)
    OUTPUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"[align] favored={out['favored_count']} disfavored={out['disfavored_count']}",
        file=sys.stderr,
    )
    for s in out["sectors"]:
        if s["tier"] != "NEUTRAL":
            print(
                f"  · {s['sector']:25s} score={s['score']:+.2f} ({s['tier']}, n={s['contribution_count']})",
                file=sys.stderr,
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
