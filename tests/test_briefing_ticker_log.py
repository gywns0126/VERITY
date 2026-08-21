"""데일리 브리핑 이력이 등장 티커를 남기는지 — 회귀 가드 (2026-08-21).

배경: 종전 이력은 `date/n_sections/n_items` **카운트뿐**이라 307일치가 쌓여 있어도
"회원 보유종목과 며칠에 한 번 겹치나" 를 **소급 측정할 수 없었다**.
브리핑 개인화(보유 종목 승격)의 가치를 판정할 유일한 근거가 이 목록이다.

🚨 이 로그가 없으면 개인화 설계는 **측정 없이** 결정하게 된다 — 도넛에서 겪은 형태다
([[project_segment_donut_abandoned_2026_08_21]]).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "api" / "builders" / "daily_briefing_builder.py"
HIST = ROOT / "data" / "daily_briefing_history.jsonl"


def test_builder_source_logs_tickers():
    s = SRC.read_text(encoding="utf-8")
    assert '"n_tickers"' in s and '"tickers"' in s, "이력에서 티커 로깅이 사라졌다"
    assert '"generated_at"' in s, "run 마다 append 되므로 dedupe 용 generated_at 이 필요하다"


def test_ticker_set_is_deduped_and_sorted_in_source():
    s = SRC.read_text(encoding="utf-8")
    m = re.search(r"_tks\s*=\s*sorted\(\{", s)
    assert m, "티커는 set 으로 중복 제거 후 정렬해야 한다(섹션 간 중복 등장)"


def test_history_last_row_has_tickers():
    if not HIST.exists():
        pytest.skip("이력 없음")
    lines = [l for l in HIST.read_text(encoding="utf-8").splitlines() if l.strip()]
    if not lines:
        pytest.skip("이력 비어 있음")
    row = json.loads(lines[-1])
    if "tickers" not in row:
        pytest.xfail("다음 빌더 run 이후부터 기록됨 (배선 직후 과거 행에는 없다)")
    assert isinstance(row["tickers"], list)
    assert row["n_tickers"] == len(row["tickers"])
    # 섹션 항목 수보다 많을 수 없다 — 티커 없는 항목(지수)이 있으므로
    assert row["n_tickers"] <= row["n_items"]


def test_history_rows_are_deduplicable_by_date():
    """run 마다 append 되므로 date 로 dedupe 가 가능해야 한다(분석 전제)."""
    if not HIST.exists():
        pytest.skip("이력 없음")
    lines = [l for l in HIST.read_text(encoding="utf-8").splitlines() if l.strip()]
    rows = [json.loads(l) for l in lines[-30:]]
    assert all("date" in r for r in rows), "date 없는 행이 있으면 dedupe 불가"
