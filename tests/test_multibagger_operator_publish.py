"""멀티배거 알파콘솔 발행물 계약 — 2026-08-21.

🚨 이 발행물의 위험은 "관측이 판단으로 둔갑하는 것" 이다.
   생산자(`multibagger_watch.jsonl`)가 `note = "로깅 전용 — 결정 0 (active gate 2026-09)"`
   를 달고 있는데, 화면에 옮기는 과정에서 그 표시가 빠지면 오퍼레이터가 매매 신호로 읽는다.
   그래서 값이 아니라 **자기신고가 살아 있는지**를 고정한다.

같은 이유로 커버리지도 고정한다 — `revenue_acceleration` 의 연속가속 방어는
`quarterly_revenue` 를 요구하는데 DART 백필이 미완이면 꺼진 채 발화한다
(2026-08-21 실측 429/429 = 100%). 그 비율이 산출물에서 사라지면 화면이
"검증된 신호" 처럼 보인다.
"""
import json
import os

import pytest

from api.builders.multibagger_operator_builder import build

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPLOAD = os.path.join(ROOT, "scripts", "upload_operator_data_to_supabase.py")
ADMIN = os.path.join(ROOT, "vercel-api", "api", "admin.py")
PANEL = os.path.join(ROOT, "operator-web", "app", "components", "MultibaggerPanel.tsx")


@pytest.fixture(scope="module")
def out():
    d = build()
    if not d.get("items"):
        pytest.skip("multibagger_watch.jsonl 미생성 — 생산자 미실행 환경")
    return d


def test_denominator_is_reported(out):
    """RULE 13 — 목록만 실으면 전수처럼 읽힌다. 분모가 같이 가야 한다."""
    m = out["_meta"]
    assert m["universe_n"] >= m["published_n"], "발행 수가 유니버스보다 클 수 없다"
    assert m["published_n"] == len(out["items"])


def test_decision_use_is_false_and_producer_note_survives(out):
    """🚨 관측/판단 구분의 유일한 표시 — 이게 빠지면 화면이 신호로 둔갑한다."""
    m = out["_meta"]
    assert m["decision_use"] is False
    assert m.get("producer_note"), "생산자 note 가 발행물에서 사라졌다"
    assert "로깅" in str(m["producer_note"]) or "결정 0" in str(m["producer_note"])


def test_coverage_is_self_reported(out):
    """꺼진 방어를 숨기면 '검증된 신호' 처럼 보인다."""
    m = out["_meta"]
    assert "acceleration_uncovered_n" in m and "acceleration_uncovered_pct" in m
    pct = m["acceleration_uncovered_pct"]
    assert pct is None or 0.0 <= pct <= 100.0


def test_only_fired_signals_are_shipped(out):
    """미발화까지 실으면 페이로드가 4배가 되고 화면에도 안 쓴다."""
    for it in out["items"]:
        assert isinstance(it.get("fired"), dict)
        assert len(it["fired"]) <= (it.get("alert_count") or 0) or it["fired"] == {}


def test_ranked_by_alert_count_desc(out):
    counts = [it.get("alert_count") or 0 for it in out["items"]]
    assert counts == sorted(counts, reverse=True), "정렬이 깨지면 상단이 대표 신호가 아니게 된다"


def test_payload_stays_small(out):
    """오퍼레이터 full 페이로드가 Safari 메모리 킬을 낸 선례가 있다(3.57MB)."""
    size = len(json.dumps(out, ensure_ascii=False, separators=(",", ":")).encode())
    assert size < 400_000, f"발행물이 {size:,}B — TOP_N 을 줄이거나 필드를 더 쳐낼 것"


# ── 배선 정합 (RULE 4 등가 — 한 곳이라도 빠지면 화면에 영영 안 뜬다) ──

def test_upload_list_registers_the_file():
    with open(UPLOAD, encoding="utf-8") as f:
        s = f.read()
    assert "data/multibagger_watch.json" in s
    assert "_operator/multibagger_watch.json" in s


def test_admin_route_registered():
    with open(ADMIN, encoding="utf-8") as f:
        s = f.read()
    assert '"multibagger": _make_operator_file_handler("multibagger_watch.json")' in s


def test_panel_keeps_the_observation_badge():
    """🚨 배지 제거 = 관측이 판단으로 둔갑. 코드에서 사라지면 여기서 걸린다."""
    with open(PANEL, encoding="utf-8") as f:
        s = f.read()
    assert "관측 전용" in s, "관측 전용 배지가 컴포넌트에서 사라졌다"
    assert "acceleration_uncovered_pct" in s, "커버리지 경고가 화면에서 사라졌다"
    assert 'fetchOperator<Payload>("multibagger")' in s
