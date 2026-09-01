# -*- coding: utf-8 -*-
"""규칙 변경 경계 양쪽 자기신고 (2026-08-25 신설 · PM 승인 ③안).

🚨 사고 = VAMS 게이트가 `expectancy_r −0.336R` 로 FAIL 을 내고 있는데, 27거래 중 **22거래가
이미 고친 결함(손절 캡 −5%)의 산물**이었다. 캡은 2026-08-09 에 −20% 로 복원됐고(`4a2c3f4ee`),
경계로 자르면 before −0.588R / after +1.386R 로 **부호가 뒤집힌다**.

그런데 `rule_change_at` 이 `null` 이었다 — 변경이 어디에도 기록되지 않아 원장이 경계를 몰랐고,
나는 섞인 평균을 "현재 시스템 성적" 으로 읽었다(RULE 13 ⑤ 창 안의 변경 경계).

The active gate uses the post-change segment; the earlier segment remains a
legacy diagnostic so mixed-rule performance cannot return.
"""
import json
import os

from api.main import _rule_change_segments

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_RULE_LOG = os.path.join(_ROOT, "data", "metadata", "rule_change_log.jsonl")


def _ep(date, pnl):
    return {"date": date, "pnl": pnl}


def test_splits_at_boundary_with_gate_metrics():
    sells = [
        _ep("2026-07-01", -100), _ep("2026-07-02", -100), _ep("2026-07-03", 50),
        _ep("2026-08-20", 400), _ep("2026-08-21", -100),
    ]
    out = _rule_change_segments(sells, "2026-08-09")
    assert out["before"]["trades"] == 3 and out["after"]["trades"] == 2
    # 게이트와 같은 지표를 낸다 — 거래수·손익만이 아니라 승률·손익비·기대값
    for seg in ("before", "after"):
        for k in ("win_rate", "pl_ratio", "expectancy_r", "realized_pnl"):
            assert k in out[seg], f"{seg}.{k} 가 없다"
    # before: 1승2패 · 평균승 50 / 평균패 -100 → 손익비 0.5 · 기대값 0.333*0.5-0.667
    assert out["before"]["pl_ratio"] == 0.5
    assert out["after"]["pl_ratio"] == 4.0


def test_post_change_segment_is_the_active_gate_window():
    out = _rule_change_segments([_ep("2026-07-01", -100)], "2026-08-09")
    assert out["used_by_gate"] is True
    assert "현행 게이트 정본" in out["note"]
    assert "legacy diagnostic" in out["note"]


def test_missing_boundary_is_reported_not_silent():
    """경계 미기록이 조용히 넘어가면 오늘 사고가 그대로 재발한다."""
    out = _rule_change_segments([_ep("2026-07-01", -100)], None)
    assert out["boundary"] is None
    assert "rule_change_log.jsonl" in out["note"]


def test_stoploss_cap_change_is_recorded():
    """🚨 8/09 손절 캡 변경 기록이 원장에 살아 있어야 경계가 잡힌다.

    🚨 이 파일은 **append-only 공유 원장**이다(2026-08-25 실측 124행 · fx_hedge 122).
       통째로 덮으면 fx_hedge 이력이 날아간다 — 실제로 이 세션이 한 번 덮었다가 복원했다.
    """
    assert os.path.exists(_RULE_LOG), "규칙 변경 로그가 사라졌다"
    rows = [json.loads(x) for x in open(_RULE_LOG, encoding="utf-8") if x.strip()]
    caps = [r for r in rows if r.get("rule") == "VAMS_PROFILES['moderate'].stop_loss_pct"]
    assert caps, "손절 캡 변경 기록이 없다"
    r = caps[0]
    assert r["at"][:10] == "2026-08-09"
    assert r.get("commit") == "4a2c3f4ee"
    assert (r.get("from"), r.get("to")) == (-5.0, -20.0)
    # 공유 원장이 통째로 덮이지 않았는지 — fx_hedge 이력이 함께 살아 있어야 한다
    assert sum(1 for x in rows if x.get("rule") == "fx_hedge_regime") > 50, (
        "fx_hedge 이력이 사라졌다 — 원장을 통째로 덮은 흔적")


def test_boundary_filter_excludes_noise_and_no_change():
    """🚨 공유 원장이라 max(at) 을 그냥 잡으면 안 된다.

    실측: 124행 중 122행이 fx_hedge 운영 이벤트라 그대로 세면 경계가 8/17 로 밀린다.
    8/16 `vams_stoploss_priority` 는 '기각 확정 · 코드·임계 변경 0' 이라 행동 경계가 아니다.
    """
    from api.main import _vams_behavior_boundaries
    rows = [
        {"at": "2026-08-09T22:05:53+09:00", "rule": "VAMS_PROFILES['moderate'].stop_loss_pct",
         "from": -5.0, "to": -20.0},
        {"at": "2026-08-16T21:05:23+09:00", "rule": "vams_stoploss_priority",
         "to": "❌ 기각 확정 — 현행 유지. 코드·임계 변경 0"},
        {"at": "2026-08-17T13:08:32+09:00", "rule": "fx_hedge_regime", "to": "ON"},
    ]
    assert _vams_behavior_boundaries(rows) == ["2026-08-09T22:05:53+09:00"]

    # 실제 원장에서도 같은 결과여야 한다
    real = [json.loads(x) for x in open(_RULE_LOG, encoding="utf-8") if x.strip()]
    b = _vams_behavior_boundaries(real)
    assert b and b[-1][:10] == "2026-08-09", f"실제 원장 경계가 {b[-1][:10] if b else None}"


def test_main_reads_dedicated_log_not_only_legacy():
    """portfolio.json 은 크론 재생성물이라 기록이 안 남는다 — 전용 파일을 읽어야 한다."""
    import inspect
    from api import main as M
    src = inspect.getsource(M)
    assert "rule_change_log.jsonl" in src, "전용 로그 읽기가 사라졌다"
