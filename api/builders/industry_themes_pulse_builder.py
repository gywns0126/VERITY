"""industry_themes_pulse_builder — US15 컨콜/earnings 산업 키워드 cross-frequency 합성.

PM 직관 (사용자, 5/20): "분기 컨콜 수십 개 들으면 산업 흐름 그려짐."
→ 자체 universe 25 종목 × 분기 industry_themes 추출 (equity_research_brief 확장).
→ 1년 누적 후 자기 산업 mental model 자산 ([[project_industry_themes_tracker]]).

데이터 흐름:
  api/intelligence/equity_research_brief.py → data/equity_research/*.json (15 ticker brief)
  → 본 builder = 15 brief 읽음 + theme cross-ticker frequency + weighted sentiment 합성
  → data/industry_themes_pulse.json (Brain v6 brief axis 입력 후보).

산식 v0 (자기 자체 결정 — [[project_industry_themes_tracker]] 명시):
  - theme 정규화: lowercase + 공백 정리, 사용자 동의어 매핑 (미장 일반 용어).
  - direction score: positive=+1, negative=-1, neutral=0
  - conviction weight: high=1.0, mid=0.6, low=0.3
  - frequency = unique ticker mentioning theme / 15
  - sentiment = Σ(direction × conviction_weight) / Σ(conviction_weight)
  - verdict:
      frequency ≥ 0.5 AND |sentiment| ≥ 0.7 → STRONG_SIGNAL
      frequency ≥ 0.3 AND |sentiment| ≥ 0.5 → SIGNAL
      else → MENTION

임계 (0.3/0.5, 0.5/0.7) = v0 가설. N≥100 (~7 분기) 후 walk-forward 1회 조정
([[feedback_threshold_calibration_overfit_guard]]).

RULE 6 정합 ([[feedback_no_new_llm_narrative_features]]): 신규 LLM call 없음 — 기존
equity_research_brief 출력 재사용. narrative 결과 X (metric/frequency only).
"""
from __future__ import annotations

import json
import logging
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
KST = timezone(timedelta(hours=9))
BRIEF_DIR = REPO_ROOT / "data" / "equity_research"
OUTPUT_PATH = REPO_ROOT / "data" / "industry_themes_pulse.json"

_logger = logging.getLogger(__name__)

DIRECTION_SCORE = {"positive": 1.0, "negative": -1.0, "neutral": 0.0}
CONVICTION_WEIGHT = {"high": 1.0, "mid": 0.6, "low": 0.3}

# v0 임계 (PM 사전 승인 의무, RULE 7)
STRONG_FREQ_THRESHOLD = 0.50
STRONG_SENT_THRESHOLD = 0.70
SIGNAL_FREQ_THRESHOLD = 0.30
SIGNAL_SENT_THRESHOLD = 0.50

# theme 정규화 — 사용자 동의어 매핑. LLM 가 자유 텍스트 반환 → 매핑 없으면 frequency 분산.
# v0 = US 미장 일반 용어 13건 등록. 신규 발견 시 추가.
THEME_ALIASES: Dict[str, str] = {
    # AI / 반도체
    "ai capex": "AI capex",
    "ai infrastructure": "AI capex",
    "ai investment": "AI capex",
    "ai spending": "AI capex",
    "gen ai": "AI capex",
    "data center": "data center buildout",
    "data center buildout": "data center buildout",
    "data center capacity": "data center buildout",
    # 재고 사이클
    "destocking": "destocking",
    "inventory destocking": "destocking",
    "inventory drawdown": "destocking",
    "channel destocking": "destocking",
    "restocking": "restocking",
    "inventory build": "restocking",
    # 거시
    "fx headwind": "FX headwind",
    "currency headwind": "FX headwind",
    "dollar strength": "FX headwind",
    "tariff": "tariff impact",
    "tariff impact": "tariff impact",
    "tariffs": "tariff impact",
    "trade tension": "tariff impact",
    # 소비/노동
    "consumer weakness": "consumer weakness",
    "weak consumer": "consumer weakness",
    "consumer demand softness": "consumer weakness",
    "labor cost inflation": "labor cost inflation",
    "wage inflation": "labor cost inflation",
    "labor cost": "labor cost inflation",
    # 산업/공급
    "supply chain": "supply chain normalization",
    "supply chain normalization": "supply chain normalization",
    "supply chain disruption": "supply chain disruption",
    # IT/소프트웨어
    "cloud growth": "cloud growth",
    "cloud demand": "cloud growth",
    "cloud spending": "cloud growth",
    # 금융
    "credit quality": "credit quality",
    "loan growth": "loan growth",
    "net interest margin": "net interest margin pressure",
    "nim pressure": "net interest margin pressure",
}


def _normalize_theme(raw: str) -> str:
    """소문자 + 공백 정규화 + alias 매핑. 알 수 없으면 정규화된 raw 반환."""
    if not raw:
        return ""
    cleaned = re.sub(r"\s+", " ", raw.strip().lower())
    cleaned = cleaned.rstrip(".!?,")
    return THEME_ALIASES.get(cleaned, cleaned)


def _classify(frequency: float, sentiment: float) -> str:
    abs_sent = abs(sentiment)
    if frequency >= STRONG_FREQ_THRESHOLD and abs_sent >= STRONG_SENT_THRESHOLD:
        return "STRONG_SIGNAL"
    if frequency >= SIGNAL_FREQ_THRESHOLD and abs_sent >= SIGNAL_SENT_THRESHOLD:
        return "SIGNAL"
    return "MENTION"


def _direction_label(sentiment: float) -> str:
    if sentiment > 0.15:
        return "positive"
    if sentiment < -0.15:
        return "negative"
    return "neutral"


def aggregate_themes(briefs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """15 brief → industry_themes 집계.

    Args:
        briefs: list of brief dict — each containing ticker + industry_themes[]
    Returns:
        dict with themes (sorted by frequency desc), universe_size, generated_at
    """
    # theme → {tickers: set, direction_score_sum: float, conviction_weight_sum: float, evidences: list}
    bucket: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {
            "tickers": set(),
            "direction_score_sum": 0.0,
            "conviction_weight_sum": 0.0,
            "evidences": [],
            "raw_labels": set(),
        }
    )

    universe = []
    for brief in briefs:
        ticker = (brief.get("ticker") or "").upper()
        if not ticker:
            continue
        universe.append(ticker)
        themes_raw = brief.get("industry_themes") or []
        if not isinstance(themes_raw, list):
            continue
        for t in themes_raw:
            if not isinstance(t, dict):
                continue
            raw = t.get("theme") or ""
            normalized = _normalize_theme(raw)
            if not normalized:
                continue
            direction = (t.get("direction") or "").lower().strip()
            conviction = (t.get("conviction") or "mid").lower().strip()
            dir_score = DIRECTION_SCORE.get(direction, 0.0)
            conv_w = CONVICTION_WEIGHT.get(conviction, CONVICTION_WEIGHT["mid"])

            entry = bucket[normalized]
            entry["tickers"].add(ticker)
            entry["direction_score_sum"] += dir_score * conv_w
            entry["conviction_weight_sum"] += conv_w
            entry["raw_labels"].add(raw)
            evidence = t.get("evidence")
            if isinstance(evidence, str) and evidence.strip():
                entry["evidences"].append({"ticker": ticker, "evidence": evidence.strip()[:240]})

    universe_size = len(universe)
    themes_out: List[Dict[str, Any]] = []
    for theme_label, entry in bucket.items():
        ticker_count = len(entry["tickers"])
        if universe_size == 0:
            continue
        frequency = ticker_count / universe_size
        weight_sum = entry["conviction_weight_sum"]
        sentiment = (entry["direction_score_sum"] / weight_sum) if weight_sum > 0 else 0.0
        verdict = _classify(frequency, sentiment)
        themes_out.append({
            "theme": theme_label,
            "ticker_count": ticker_count,
            "frequency": round(frequency, 3),
            "sentiment": round(sentiment, 3),
            "direction_label": _direction_label(sentiment),
            "verdict": verdict,
            "raw_labels": sorted(entry["raw_labels"]),
            "evidences": entry["evidences"][:5],
        })

    # frequency desc, then |sentiment| desc
    themes_out.sort(key=lambda x: (-x["frequency"], -abs(x["sentiment"])))

    return {
        "schema_version": "v0.1",
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "universe_size": universe_size,
        "universe_tickers": sorted(universe),
        "themes": themes_out,
        "thresholds": {
            "strong_frequency": STRONG_FREQ_THRESHOLD,
            "strong_sentiment": STRONG_SENT_THRESHOLD,
            "signal_frequency": SIGNAL_FREQ_THRESHOLD,
            "signal_sentiment": SIGNAL_SENT_THRESHOLD,
        },
    }


def load_briefs(brief_dir: Path = BRIEF_DIR) -> List[Dict[str, Any]]:
    """data/equity_research/*.json 읽음. _summary.json 같은 메타 파일 제외."""
    if not brief_dir.exists():
        return []
    briefs = []
    for p in sorted(brief_dir.glob("*.json")):
        if p.name.startswith("_"):
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            briefs.append(data)
        except Exception as e:
            _logger.warning("brief %s load failed: %s", p.name, e)
    return briefs


def main() -> int:
    briefs = load_briefs()
    if not briefs:
        _logger.error("brief 0 — data/equity_research/ 비어있음. equity_research_brief 먼저 실행")
        return 1
    output = aggregate_themes(briefs)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        f"[industry_themes] universe={output['universe_size']} themes={len(output['themes'])}",
        file=sys.stderr,
    )
    strong = [t for t in output["themes"] if t["verdict"] == "STRONG_SIGNAL"]
    signal = [t for t in output["themes"] if t["verdict"] == "SIGNAL"]
    print(f"  STRONG_SIGNAL: {len(strong)} / SIGNAL: {len(signal)}", file=sys.stderr)
    for t in strong + signal:
        print(
            f"  · {t['theme']:30s} freq={t['frequency']:.2f} sent={t['sentiment']:+.2f} ({t['verdict']})",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
