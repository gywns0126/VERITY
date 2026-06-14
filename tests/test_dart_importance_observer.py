"""dart_importance_observer — C1 DART 중요도 게이팅 관측 SHADOW 테스트 (2026-06-15).

기존 catalyst severity 재사용 + dedup + shadow 격리 + mass-fire 가드 검증. 레이크 무의존(mock).
"""
import json
import api.intelligence.dart_importance_observer as do


def _alert(rcept_no, ticker, severity, dt="20260601"):
    return {"rcept_no": rcept_no, "ticker": ticker, "name": "테스트", "severity": severity,
            "pblntf_label": "주요사항", "is_correction": False, "rcept_dt": dt}


def _setup(monkeypatch, tmp_path, alerts, prices=None):
    ap = tmp_path / "alerts.jsonl"
    ap.write_text("\n".join(json.dumps(a) for a in alerts), encoding="utf-8")
    monkeypatch.setattr(do, "ALERTS_PATH", str(ap))
    monkeypatch.setattr(do, "OBS_DIR", str(tmp_path))
    monkeypatch.setattr(do, "OBS_PATH", str(tmp_path / "obs.jsonl"))
    # 가격레이크 mock: prices dict {ticker: [(date,close),...]} or None
    monkeypatch.setattr(do, "_lake_closes", lambda t, s: (prices or {}).get(t))


def test_build_observations_joins_severity(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path, [_alert("R1", "005930", 3)],
           prices={"005930": [("2026-06-01", 100.0), ("2026-06-02", 105.0)]})
    obs = do.build_observations()
    assert len(obs) == 1
    o = obs[0]
    assert o["severity"] == 3
    assert o["price_at_event"] == 100.0
    assert o["fwd_ret"]["d1"] == 0.05   # 100→105
    assert o["fwd_ret"]["d20"] is None  # 데이터 부족
    assert o["brain_input"] is False and o["shadow"] is True


def test_dedup_by_rcept_no(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path, [_alert("R1", "005930", 2)], prices={"005930": [("2026-06-01", 100.0)]})
    do.run_shadow()           # R1 적재
    obs2 = do.build_observations()  # 재실행 → R1 이미 있음
    assert len(obs2) == 0     # dedup


def test_scored_requires_d20(monkeypatch, tmp_path):
    # d20 까지 있는 가격 → scored=True
    series = [("2026-06-01", 100.0)] + [(f"d{i}", 100.0 + i) for i in range(1, 25)]
    _setup(monkeypatch, tmp_path, [_alert("R1", "005930", 3)], prices={"005930": series})
    obs = do.build_observations()
    assert obs[0]["scored"] is True
    assert obs[0]["fwd_ret"]["d20"] is not None


def test_lake_absent_logs_event_without_price(monkeypatch, tmp_path):
    # CI 처럼 레이크 부재 → 이벤트는 로깅(price null)
    _setup(monkeypatch, tmp_path, [_alert("R1", "005930", 2)], prices=None)
    obs = do.build_observations()
    assert len(obs) == 1
    assert obs[0]["price_at_event"] is None
    assert obs[0]["severity"] == 2   # 이벤트 사실은 보존


def test_severity_distribution_mass_fire_guard(monkeypatch, tmp_path):
    alerts = [_alert(f"R{i}", "005930", 2) for i in range(5)]  # 전부 sev2 = mass-fire
    _setup(monkeypatch, tmp_path, alerts)
    obs = do.build_observations()
    dist = do.severity_distribution(obs)
    assert dist == {"2": 5}   # 변별력 0 감시 가능


def test_run_shadow_caveat_sign_warning(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path, [_alert("R1", "005930", 3)])
    r = do.run_shadow()
    assert "역" in r["caveat"] or "부호" in r["caveat"]  # 부호 역전 경고 명시
    assert "N<50" in r["caveat"] or "N≥50" in r["caveat"]


def test_score_observations_recomputes_from_lake(monkeypatch, tmp_path):
    # 로그엔 price null 이어도 score_observations 가 레이크에서 재계산
    _setup(monkeypatch, tmp_path, [_alert("R1", "005930", 3)], prices=None)
    do.run_shadow()  # price null 로 적재
    # 이제 레이크 가용 → 재계산
    series = [("2026-06-01", 100.0)] + [("x", 100.0), ("x", 100.0), ("x", 100.0),
                                         ("x", 100.0), ("x", 110.0)]
    monkeypatch.setattr(do, "_lake_closes", lambda t, s: series)
    sc = do.score_observations()
    assert sc["status"] == "ok"
    assert sc["scorable_d5"] == 1
    assert "3" in sc["severity_avg_fwd_d5"]   # sev3 평균 forward 계산됨
