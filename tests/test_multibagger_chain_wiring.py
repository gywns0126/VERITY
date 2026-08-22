"""멀티배거 체인 배선 전수 — 2026-08-22 (PM "확실히 작동하는거지? 누락사항 없이?").

🚨 이 체인은 링크가 8개인데, **하나만 끊겨도 조용히 죽는다.** 어느 것도 예외를 던지지
않고 그냥 빈 화면·오분류로 나타난다. 실제로 전수 감사에서 누락 2건이 나왔다:
  · `multibagger_promote.json` git add 미등재 → daily_analysis(**다른 run**)가 파일을
    못 읽어 승격분을 전부 `capped_out` 으로 오분류
  · `multibagger_picks.json` git add 미등재 → universe_scan 은 specific add 라 누락
    (daily_analysis 는 broad `git add data/` 라 자동)

값이 아니라 **배선 존재**를 고정한다. 리팩터로 경로가 바뀌면 여기서 먼저 걸린다.
"""
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def src():
    return {
        "admin": _read("vercel-api", "api", "admin.py"),
        "upload": _read("scripts", "upload_operator_data_to_supabase.py"),
        "panel": _read("operator-web", "app", "components", "MultibaggerPanel.tsx"),
        "page": _read("operator-web", "app", "page.tsx"),
        "scan": _read(".github", "workflows", "universe_scan.yml"),
        "daily": _read(".github", "workflows", "daily_analysis_full.yml"),
        "watch": _read("api", "intelligence", "multibagger_watch.py"),
        "builder": _read("api", "builders", "universe_scan_builder.py"),
    }


# ── 신호 → 승격 → 유니버스 ──────────────────────────────────────

def test_run_watch_emits_promote(src):
    assert "_emit_promote(rows, stocks)" in src["watch"], "run_watch 가 승격 파일을 안 만든다"


def test_builder_merges_promote(src):
    assert "merge_promoted(candidates)" in src["builder"], "빌더가 승격분을 병합하지 않는다"


# ── 🚨 영속성 — 다른 run 이 읽어야 하는 파일 ────────────────────

@pytest.mark.parametrize("path", [
    "data/metadata/multibagger_watch.jsonl",
    "data/metadata/multibagger_promote.json",   # 🚨 daily_analysis 가 다른 run 에서 읽는다
    "data/multibagger_watch.json",
    "data/multibagger_picks.json",
])
def test_universe_scan_commits_the_file(src, path):
    """universe_scan 은 specific add 라 명시하지 않으면 **조용히 유실**된다 (RULE 4)."""
    assert f"git add {path}" in src["scan"], (
        f"{path} 가 universe_scan git add 목록에 없다 — 다음 run 이 못 읽는다"
    )


# ── 빌더 → 업로드 → 라우트 → 화면 ───────────────────────────────

@pytest.mark.parametrize("builder", [
    "multibagger_operator_builder", "multibagger_picks_builder",
])
def test_scan_runs_builders(src, builder):
    assert builder in src["scan"]


def test_daily_analysis_rebuilds_picks_after_scoring(src):
    """🚨 등급이 붙는 시점은 여기다 — 없으면 리스트가 영영 미채점으로 남는다."""
    assert "multibagger_picks_builder" in src["daily"]


@pytest.mark.parametrize("name", ["multibagger_watch.json", "multibagger_picks.json"])
def test_upload_registers(src, name):
    assert f"_operator/{name}" in src["upload"]


@pytest.mark.parametrize("route", ["multibagger", "multibagger_picks"])
def test_admin_route_registered(src, route):
    assert f'"{route}": _make_operator_file_handler' in src["admin"]


@pytest.mark.parametrize("call", [
    'fetchOperator<Payload>("multibagger")',
    'fetchOperator<Picks>("multibagger_picks")',
])
def test_panel_fetches(src, call):
    assert call in src["panel"]


def test_panel_is_mounted(src):
    assert "<MultibaggerPanel />" in src["page"], "컴포넌트가 페이지에 배치되지 않았다"


# ── 🚨 관측/판단 구분 표시 ──────────────────────────────────────

def test_observation_badge_survives(src):
    """지우면 관측이 판단으로 둔갑한다 — 생산자가 '로깅 전용' 을 신고하고 있다."""
    assert "관측 전용" in src["panel"]


def test_coverage_warning_survives(src):
    assert "acceleration_uncovered_pct" in src["panel"]


def test_separation_section_survives(src):
    """분리 집계 섹션 — 없으면 승격분 성적을 화면에서 못 가린다."""
    assert "선별 경로" in src["panel"]
