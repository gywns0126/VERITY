"""KB 인용 통계 누적 검증 — _log_kb_usage / flush_kb_usage_to_file.

2-4주 데이터 누적 후 책 조합 충돌 분석용. 세션 in-memory 누적 → run 종료시 디스크 flush.
"""
import json
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _reset_session():
    """각 테스트 전 KB usage 세션 초기화."""
    from api.analyzers import gemini_analyst as ga
    ga._kb_usage_session["calls"] = []
    yield
    ga._kb_usage_session["calls"] = []


@pytest.fixture
def _tmp_data_dir(monkeypatch, tmp_path):
    """DATA_DIR 을 tmp 로 격리 (실 data/ 건드리지 않게)."""
    from api.analyzers import gemini_analyst as ga
    monkeypatch.setattr(ga, "DATA_DIR", str(tmp_path))
    yield tmp_path


# ──────────────────────────────────────────────
# _log_kb_usage
# ──────────────────────────────────────────────

def test_log_appends_to_session():
    from api.analyzers.gemini_analyst import _log_kb_usage, _kb_usage_session
    _log_kb_usage(
        ["graham_intelligent_investor", "buffett_essays"],
        ["per_lte_15_pbr_lt_1_5", "roe_gt_15"],
        {"ticker": "005930"},
    )
    assert len(_kb_usage_session["calls"]) == 1
    c = _kb_usage_session["calls"][0]
    assert c["ticker"] == "005930"
    assert c["books"] == ["graham_intelligent_investor", "buffett_essays"]
    assert "per_lte_15_pbr_lt_1_5" in c["triggers"]


def test_log_skips_when_no_books():
    from api.analyzers.gemini_analyst import _log_kb_usage, _kb_usage_session
    _log_kb_usage([], [], {"ticker": "X"})
    assert _kb_usage_session["calls"] == []


def test_log_truncates_long_ticker():
    """ticker 가 비정상적으로 길어도 10자로 잘림."""
    from api.analyzers.gemini_analyst import _log_kb_usage, _kb_usage_session
    _log_kb_usage(
        ["graham_intelligent_investor"], [], {"ticker": "VERY_LONG_TICKER_NAME_12345"}
    )
    assert len(_kb_usage_session["calls"][0]["ticker"]) <= 10


# ──────────────────────────────────────────────
# flush_kb_usage_to_file
# ──────────────────────────────────────────────

def test_flush_creates_file_with_correct_structure(_tmp_data_dir):
    from api.analyzers.gemini_analyst import _log_kb_usage, flush_kb_usage_to_file
    _log_kb_usage(
        ["graham_intelligent_investor", "oneil_canslim"],
        ["per_lte_15_pbr_lt_1_5", "eps_growth_qoq_gte_20"],
        {"ticker": "005930"},
    )
    flushed = flush_kb_usage_to_file()
    assert flushed == 1
    path = _tmp_data_dir / "brain_kb_usage.json"
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    # combo key 는 sorted tuple
    expected_combo = "graham_intelligent_investor+oneil_canslim"
    assert data["combinations"][expected_combo] == 1
    assert data["books"]["graham_intelligent_investor"] == 1
    assert data["books"]["oneil_canslim"] == 1
    assert data["triggers"]["per_lte_15_pbr_lt_1_5"] == 1
    assert data["total_calls"] == 1
    assert data["last_run_calls"] == 1
    assert "last_updated" in data


def test_flush_aggregates_across_runs(_tmp_data_dir):
    """여러 run 에 걸쳐 누적 — 두 번째 flush 가 첫 번째 카운터에 더해진다."""
    from api.analyzers.gemini_analyst import _log_kb_usage, flush_kb_usage_to_file

    # Run 1
    _log_kb_usage(["graham_intelligent_investor"], ["per_lte_15_pbr_lt_1_5"], {"ticker": "A"})
    _log_kb_usage(["graham_intelligent_investor", "buffett_essays"], ["roe_gt_15"], {"ticker": "B"})
    assert flush_kb_usage_to_file() == 2

    # Run 2 (세션 리셋 후 — flush 가 자동으로 비움)
    _log_kb_usage(["graham_intelligent_investor"], ["per_lte_15_pbr_lt_1_5"], {"ticker": "C"})
    flush_kb_usage_to_file()

    data = json.loads((_tmp_data_dir / "brain_kb_usage.json").read_text(encoding="utf-8"))
    assert data["books"]["graham_intelligent_investor"] == 3  # A + B + C
    assert data["books"]["buffett_essays"] == 1
    assert data["total_calls"] == 3


def test_flush_session_clears_after_write(_tmp_data_dir):
    from api.analyzers.gemini_analyst import _log_kb_usage, flush_kb_usage_to_file, _kb_usage_session
    _log_kb_usage(["graham_intelligent_investor"], [], {"ticker": "X"})
    flush_kb_usage_to_file()
    assert _kb_usage_session["calls"] == []  # 비워져야


def test_flush_empty_session_no_op(_tmp_data_dir):
    from api.analyzers.gemini_analyst import flush_kb_usage_to_file
    assert flush_kb_usage_to_file() == 0
    assert not (_tmp_data_dir / "brain_kb_usage.json").exists()


def test_flush_handles_corrupt_file(_tmp_data_dir):
    """기존 파일이 파손돼도 새로 시작 (에러 안 던짐)."""
    from api.analyzers.gemini_analyst import _log_kb_usage, flush_kb_usage_to_file
    path = _tmp_data_dir / "brain_kb_usage.json"
    path.write_text("not json garbage", encoding="utf-8")
    _log_kb_usage(["graham_intelligent_investor"], [], {"ticker": "X"})
    assert flush_kb_usage_to_file() == 1
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["books"]["graham_intelligent_investor"] == 1


def test_combo_key_is_sorted_for_consistency(_tmp_data_dir):
    """동일 조합이 책 순서만 다르게 들어와도 같은 key 로 카운트."""
    from api.analyzers.gemini_analyst import _log_kb_usage, flush_kb_usage_to_file
    _log_kb_usage(["a_book", "b_book"], [], {"ticker": "X"})
    _log_kb_usage(["b_book", "a_book"], [], {"ticker": "Y"})
    flush_kb_usage_to_file()
    data = json.loads((_tmp_data_dir / "brain_kb_usage.json").read_text(encoding="utf-8"))
    assert data["combinations"].get("a_book+b_book") == 2


# ──────────────────────────────────────────────
# 통합 — _build_knowledge_context 가 _log_kb_usage 호출하는지
# ──────────────────────────────────────────────

def test_build_knowledge_context_logs_usage(monkeypatch):
    """실 KB 사용해서 context 생성 → 세션에 인용 기록 남는지."""
    from api.analyzers import gemini_analyst as ga
    # KB 캐시 리셋 + 실파일 경로 강제 (conftest 가 DATA_DIR 격리해서 _KNOWLEDGE_BASE_PATH 가 tmp 가리킬 수 있음)
    real_kb = (
        Path(__file__).resolve().parent.parent / "data" / "brain_knowledge_base.json"
    )
    monkeypatch.setattr(ga, "_knowledge_cache", None)
    monkeypatch.setattr(ga, "_KNOWLEDGE_BASE_PATH", str(real_kb))

    # 가치주 조건 → Graham 인용
    ctx = ga._build_knowledge_context({"per": 10, "pbr": 1.2, "roe": 12, "ticker": "005930"})
    assert "Graham" in ctx
    assert len(ga._kb_usage_session["calls"]) == 1
    assert "graham_intelligent_investor" in ga._kb_usage_session["calls"][0]["books"]
