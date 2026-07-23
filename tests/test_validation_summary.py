"""test_validation_summary — forward trail 검증 상태 집계 단위 검증.

사전등록 spec (docs/validation_summary_spec_v0_2026_06_13.md) 정합:
read-only 재집계만 / RULE 7 라벨 강제값 / hit_rate 병기 강제 / graceful skip /
신규 산식 0 (기존 *_ic_history 산출값 그대로).
"""
import json

import pytest

from api.observability import validation_summary as VS


@pytest.fixture
def brain_ic_records():
    # prediction_scoring._aggregate 산출 스냅샷 형태 (append-only, 마지막=최신)
    return [
        {"scored_at": "2026-06-08T17:20:03+09:00", "horizon": "short",
         "target_type": "stock", "n": 58, "effective_n": 11.6, "overlap_k": 5,
         "ic": -0.1, "ic_tstat": -0.35, "ic_pvalue": 0.36, "hit_rate": 0.3,
         "hit_n": 40, "hit_pvalue": 0.99, "brier_score": 0.37, "expectancy": -3.1,
         "ci95": [-4.8, -1.4], "label": "Trail 누적 초기", "spec_version": "v0"},
        {"scored_at": "2026-06-13T22:00:00+09:00", "horizon": "short",
         "target_type": "stock", "n": 388, "effective_n": 77.6, "overlap_k": 5,
         "ic": -0.045, "ic_tstat": -0.4, "ic_pvalue": 0.35, "hit_rate": 0.49,
         "hit_n": 300, "hit_pvalue": 0.5, "brier_score": 0.26, "expectancy": 0.2,
         "ci95": [-0.5, 0.9], "label": "예비", "spec_version": "v0"},
    ]


def _write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


# ── 라벨 강제값 (RULE 7) ──────────────────────────────────────────────────────


def test_maturity_label_gates():
    assert VS._maturity_label(None) == "데이터 없음"
    assert "통계 무의미" in VS._maturity_label(10)       # N<30
    assert "예비" in VS._maturity_label(50)              # 30<=N<100
    # N>=100 = 표본 마일스톤일 뿐, 유의성과 별개 (RULE 7, 2026-06-19 정직화)
    label_100 = VS._maturity_label(120)
    assert "N≥100" in label_100                          # 마일스톤 도달
    assert "유의성 미검증" in label_100                  # 유의성 오독 금지
    assert "유의 표본" not in label_100                  # 과대표현 회귀 차단


def test_gate_status_progress_monotone():
    s_low = VS._gate_status(50, None)
    s_mid = VS._gate_status(200, None)
    assert "미도달" in s_low and "미도달" in s_mid
    # 게이트 도달 + 유의
    assert "p<0.05" in VS._gate_status(300, 0.01)
    # 게이트 도달 + 유의성 미달 = 가설 유지
    assert "가설 유지" in VS._gate_status(300, 0.5)
    assert VS._gate_status(None, None).startswith("가설")


# ── ic_history 재집계 (신규 산식 0) ──────────────────────────────────────────


def test_latest_per_horizon_picks_last(brain_ic_records):
    latest = VS._latest_per_horizon(brain_ic_records)
    assert set(latest) == {"short"}
    # 마지막 append 가 최신 — n=388 선택 (n=58 아님)
    assert latest["short"]["n"] == 388


def test_ic_record_signal_carries_scored_values(brain_ic_records):
    latest = VS._latest_per_horizon(brain_ic_records)
    sig = VS._ic_record_to_signal("brain_production", "src", latest)
    # 재집계만 — 채점된 값 그대로 (재계산 아님)
    assert sig["ic"] == -0.045
    assert sig["ic_pvalue"] == 0.35
    h = sig["horizons"]["short"]
    # hit_rate 병기 강제 — expectancy + ci95 + n 동반 (RULE 7)
    assert h["hit_rate"] == 0.49
    assert h["expectancy"] == 0.2
    assert h["ci95"] == [-0.5, 0.9]
    assert h["n"] == 388
    # N_eff=77.6 < 100 → 예비 (raw N=388 아닌 중첩보정 N_eff 기준 강제)
    assert "예비" in h["maturity_label"]
    assert "예비" in sig["label"]


def test_empty_ic_history_is_graceful():
    sig = VS._ic_record_to_signal("x", "src", {})
    assert sig["status"] == "trail 누적, 채점 도달 0"
    assert sig["label"] == "데이터 없음"
    assert sig["horizons"] == {}


# ── 빌더 통합 (실 1차 자료 경로 isolation) ────────────────────────────────────


def test_build_summary_shape(monkeypatch, tmp_path, brain_ic_records):
    brain_p = tmp_path / "brain.jsonl"
    _write_jsonl(brain_p, brain_ic_records)
    factor_p = tmp_path / "factor.json"
    with open(factor_p, "w", encoding="utf-8") as f:
        json.dump([{"date_key": "2026-06-13", "forward_days": 30, "factors": {
            "momentum": {"ic_mean": 0.1, "icir": 0.38, "sample_count": 52,
                         "significant": False, "decay": True}}}], f)
    shadow_p = tmp_path / "shadow.jsonl"
    _write_jsonl(shadow_p, [{"source": "shadow_funnel.v0", "scored": False,
                             "realized_return": None}])
    pred_p = tmp_path / "pred.jsonl"
    _write_jsonl(pred_p, [{"target_type": "sector"}, {"target_type": "stock"}])

    monkeypatch.setattr(VS, "_BRAIN_IC_PATH", str(brain_p))
    monkeypatch.setattr(VS, "_ML_IC_PATH", str(tmp_path / "missing_ml.jsonl"))  # 결손
    monkeypatch.setattr(VS, "_FACTOR_IC_PATH", str(factor_p))
    monkeypatch.setattr(VS, "_SHADOW_TRAIL_PATH", str(shadow_p))
    monkeypatch.setattr(VS, "_PRED_TRAIL_PATH", str(pred_p))

    s = VS.build_summary()
    by_name = {x["signal"]: x for x in s["signals"]}
    assert set(by_name) == {"brain_production", "xgb_ml", "shadow_funnel", "factor", "sector"}
    # 결손 ML = graceful (예외 없이 데이터 없음)
    assert by_name["xgb_ml"]["label"] == "데이터 없음"
    # factor per-factor 재집계
    assert by_name["factor"]["factors"]["momentum"]["icir"] == 0.38
    # sector = 채점 보류 정직 보고
    assert by_name["sector"]["scored"] == 0
    assert "DEFERRED" in by_name["sector"]["status"]
    # 게이트 진척 = 최대 N (brain n=388 vs n_eff=77.6 → n_eff 우선 77.6)
    assert s["gate"]["target_n"] == 252
    assert 0 < s["gate"]["progress_pct"] < 100
    # RULE 7 disclaimer 존재 + hit_rate 단독 금지 명문
    assert "hit_rate 단독" in s["rule7_disclaimer"]


def test_write_summary_atomic(monkeypatch, tmp_path, brain_ic_records):
    brain_p = tmp_path / "brain.jsonl"
    _write_jsonl(brain_p, brain_ic_records)
    monkeypatch.setattr(VS, "_BRAIN_IC_PATH", str(brain_p))
    monkeypatch.setattr(VS, "_ML_IC_PATH", str(tmp_path / "m.jsonl"))
    monkeypatch.setattr(VS, "_FACTOR_IC_PATH", str(tmp_path / "f.json"))
    monkeypatch.setattr(VS, "_SHADOW_TRAIL_PATH", str(tmp_path / "s.jsonl"))
    monkeypatch.setattr(VS, "_PRED_TRAIL_PATH", str(tmp_path / "p.jsonl"))

    out = tmp_path / "validation_summary.json"
    s = VS.write_summary(out_path=str(out))
    assert out.exists()
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded["spec_version"] == "v0"
    assert "_write_error" not in s
    # public_slim = funnel 신호(VERITY wide-scan = 비공개 크라운주얼) 공개 slim 에서 제외 →
    # 공개 발행 4개 (full build_summary 는 shadow_funnel 포함 5개 유지, 위 test 참조).
    assert len(loaded["signals"]) == 4
    assert all("funnel" not in x["signal"].lower() for x in loaded["signals"])


def test_no_decision_feedback_pure_read(monkeypatch, tmp_path, brain_ic_records):
    """RULE 7 — build_summary 가 입력 파일을 수정하지 않음 (read-only 보장)."""
    brain_p = tmp_path / "brain.jsonl"
    _write_jsonl(brain_p, brain_ic_records)
    before = brain_p.read_bytes()
    monkeypatch.setattr(VS, "_BRAIN_IC_PATH", str(brain_p))
    monkeypatch.setattr(VS, "_ML_IC_PATH", str(tmp_path / "m.jsonl"))
    monkeypatch.setattr(VS, "_FACTOR_IC_PATH", str(tmp_path / "f.json"))
    monkeypatch.setattr(VS, "_SHADOW_TRAIL_PATH", str(tmp_path / "s.jsonl"))
    monkeypatch.setattr(VS, "_PRED_TRAIL_PATH", str(tmp_path / "p.jsonl"))
    VS.build_summary()
    assert brain_p.read_bytes() == before  # 입력 무변경
