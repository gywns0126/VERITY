"""미국 수요 체인 관측 회귀 테스트.

지키는 것:
  1. **데코레이터 소유권** — 2026-08-07 실제 사고. `_build_demand_chain_block` 을
     `@mockable("gemini.daily_report")` 와 `generate_daily_report` **사이**에 끼워 넣어
     데코레이터가 헬퍼를 감쌌다. 결과: 헬퍼가 목 리포트 dict 를 반환하고 진짜 리포트
     함수는 목 래퍼를 잃어 dev 모드에서도 실호출로 샜다. 프롬프트 렌더 테스트에서
     발각. 함수 사이 삽입은 이 파일 아래 조립 순서 테스트가 아니면 조용히 통과한다.
  2. **관측-only 계약** — shadow/brain_input 플래그가 뒤집히면 점수 오염
     ([[feedback_methodology_pre_registration]]).
  3. **임계 이론 고정** — 3σ / 7% / 3배 / 2.5%. 사전등록 없는 조정 차단
     ([[feedback_threshold_calibration_overfit_guard]]).
  4. **인과 단정 금지** — 프롬프트 블록이 '때문에/원인은' 을 요구하지 않아야 한다(RULE 7).
  5. **네트워크 없이도 안전** — 스냅샷 부재 시 빈 문자열(리포트 종전 동작 유지).
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.collectors import us_demand_chain as M  # noqa: E402


# ── 1. 데코레이터 소유권 ──────────────────────────────────────────────
def test_mockable_decorates_generate_daily_report_not_helper():
    """@mockable 은 리포트 생성 함수에 붙어야 한다 — 헬퍼가 가로채면 안 된다."""
    src = open(
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "api", "analyzers", "gemini_analyst.py"),
        encoding="utf-8",
    ).read().split("\n")

    dec_idx = [i for i, l in enumerate(src) if l.strip() == '@mockable("gemini.daily_report")']
    assert len(dec_idx) == 1, "gemini.daily_report 데코레이터는 정확히 1개여야 한다"
    following_def = src[dec_idx[0] + 1]
    assert following_def.startswith("def generate_daily_report("), (
        f"@mockable('gemini.daily_report') 바로 아래가 generate_daily_report 가 아니다: {following_def!r}. "
        "함수를 데코레이터와 def 사이에 삽입하면 목 래퍼를 가로챈다(2026-08-07 사고)."
    )


def test_chain_block_helper_returns_string():
    """헬퍼는 항상 str 을 돌려준다 — dict 가 나오면 데코레이터에 먹힌 것."""
    from api.analyzers.gemini_analyst import _build_demand_chain_block
    assert isinstance(_build_demand_chain_block(False), str)
    assert isinstance(_build_demand_chain_block(True), str)


# ── 2. 관측-only 계약 ────────────────────────────────────────────────
def test_observation_is_shadow_only(monkeypatch):
    monkeypatch.setattr(M, "fetch_daily_bars", lambda t, metrics=None: {
        "NVDA": {"close": 100.0, "change_pct": 1.0, "z": 0.3, "volume": 10, "vol_ratio": 1.0, "date": "2026-08-06"},
    })
    monkeypatch.setattr(M, "fetch_surprises", lambda t, k: {})
    rec = M.build_observation()
    assert rec["shadow"] is True
    assert rec["brain_input"] is False, "관측-only 계약 위반 — 점수 편입은 사전등록 통과 후에만"


# ── 3. 임계 이론 고정 ────────────────────────────────────────────────
def test_thresholds_are_pinned():
    assert M.EVENT_Z == 3.0
    assert M.EVENT_MOVE_PCT == 7.0
    assert M.EVENT_VOL_RATIO == 3.0
    assert M.CHAIN_SIGNAL_PCT == 2.5


@pytest.mark.parametrize("z,chg,vr,expect", [
    (8.46, 29.45, 4.85, "sigma+move+volume"),   # PLTR 2026-08-04 실측
    (3.20, 4.0, 1.0, "sigma"),                  # 저변동주의 4% = 3σ 초과 → 절대 임계만으론 놓친다
    (1.03, 7.62, 0.8, "move"),                  # MU 2026-08-04 실측 — σ 안전망
    (0.5, 1.0, 3.5, "volume"),
    (0.5, 1.0, 1.0, None),                      # 이벤트 아님
])
def test_event_trigger_matrix(monkeypatch, z, chg, vr, expect):
    monkeypatch.setattr(M, "fetch_daily_bars", lambda t, metrics=None: {
        "NVDA": {"close": 100.0, "change_pct": chg, "z": z, "volume": 10, "vol_ratio": vr, "date": "2026-08-06"},
    })
    monkeypatch.setattr(M, "fetch_surprises", lambda t, k: {})
    evs = [e for e in M.build_observation()["events"] if e["ticker"] == "NVDA"]
    if expect is None:
        assert not evs
    else:
        assert evs and evs[0]["trigger"] == expect


def test_chain_signal_uses_average_not_individual(monkeypatch):
    """개별 임계를 아무도 못 넘어도 체인 평균이 넘으면 '확장' — 8/4 의 CAT·AVGO 를 잡은 경로."""
    bars = {t: {"close": 100.0, "change_pct": 5.6, "z": 1.2, "volume": 10, "vol_ratio": 1.1, "date": "2026-08-04"}
            for t in M.CHAINS["datacenter_infra"]["tickers"]}
    monkeypatch.setattr(M, "fetch_daily_bars", lambda t, metrics=None: bars)
    monkeypatch.setattr(M, "fetch_surprises", lambda t, k: {})
    rec = M.build_observation()
    dc = rec["chains"]["datacenter_infra"]
    assert dc["signal"] == "확장"
    assert dc["breadth"] == f"{len(bars)}/{len(bars)}"
    assert not rec["events"], "개별 임계는 넘지 않아야 이 테스트가 체인 경로를 검증한다"


# ── 4. 인과 단정 금지 (RULE 7) ───────────────────────────────────────
def test_prompt_block_forbids_causation(tmp_path, monkeypatch):
    import api.analyzers.gemini_analyst as G
    snap = {
        "chains": {"ai_semi": {"label": "AI 반도체", "avg_change_pct": 6.19, "breadth": "6/6",
                               "signal": "확장", "coverage": 6,
                               "kr_link": [{"code": "005930", "name": "삼성전자"}]}},
        "events": [{"ticker": "PLTR", "change_pct": 29.45, "z": 8.46, "vol_ratio": 4.85,
                    "chain_label": "AI 소프트웨어", "kr_link": ["NAVER"]}],
    }
    (tmp_path / "us_demand_chain.json").write_text(json.dumps(snap), encoding="utf-8")
    monkeypatch.setattr(G, "DATA_DIR", str(tmp_path))
    block = G._build_demand_chain_block(False)
    assert "삼성전자" in block and "PLTR" in block
    assert "인과 단정은 쓰지 마라" in block
    for banned in ("때문에", "원인은"):
        assert block.count(banned) <= 1, f"금지어 {banned} 가 지시문 밖에서 쓰였다"


# ── 5. 스냅샷 부재 안전 ──────────────────────────────────────────────
def test_missing_snapshot_returns_empty(tmp_path, monkeypatch):
    import api.analyzers.gemini_analyst as G
    monkeypatch.setattr(G, "DATA_DIR", str(tmp_path))
    assert G._build_demand_chain_block(False) == ""


def test_zero_coverage_does_not_write(tmp_path, monkeypatch):
    """전량 수집 실패 시 원장·스냅샷을 건드리지 않아 stale 이 그대로 드러나야 한다."""
    monkeypatch.setattr(M, "fetch_daily_bars", lambda t, metrics=None: {})
    monkeypatch.setattr(M, "fetch_surprises", lambda t, k: {})
    written = []
    monkeypatch.setattr(M, "_append_jsonl", lambda r: written.append("jsonl"))
    monkeypatch.setattr(M, "_write_snapshot", lambda r: written.append("snapshot"))
    M.run()
    assert written == []
