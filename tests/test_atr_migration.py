"""ATR 마이그레이션 — Phase 0 P-03/P-05/P-08 단위 테스트."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from api.vams import engine as vams_engine
from api.vams.engine import check_stop_loss


# ─────────────────────────────────────────────────────────────────────
# P-03 — atr_method_at_entry holding 보호 + audit
# ─────────────────────────────────────────────────────────────────────

def _holding(method="sma_14", buy=70_000, current=70_000, stop=65_000):
    return {
        "ticker": "005930",
        "name": "테스트",
        "buy_price": buy,
        "current_price": current,
        "highest_price": max(buy, current),
        "stop_loss_price": stop,
        "atr_method_at_entry": method,
        "stop_loss_pct_individual": -7.14,
        "buy_date": datetime.now().strftime("%Y-%m-%d"),
        "currency": "KRW",
    }


def _profile():
    return {"stop_loss_pct": -8.0, "trailing_stop_pct": 5.0, "max_hold_days": 21}


class TestHoldingProtection:
    def test_method_mismatch_does_not_change_stop_price(self, monkeypatch):
        # SMA holding + Wilder runtime — 손절 트리거 안 되면 audit 도 없음
        monkeypatch.setattr(vams_engine, "_ATR_METHOD_RUNTIME", "wilder_ema_14")
        h = _holding(method="sma_14", buy=70_000, current=68_000, stop=65_000)
        original_stop = h["stop_loss_price"]
        check_stop_loss(h, _profile())
        assert h["stop_loss_price"] == original_stop  # 변경 X
        assert "audit" not in h  # 트리거 안 되면 audit 없음

    def test_method_mismatch_audit_on_stop_trigger(self, monkeypatch):
        # SMA entry + Wilder runtime — 손절 트리거 시 audit 기록
        monkeypatch.setattr(vams_engine, "_ATR_METHOD_RUNTIME", "wilder_ema_14")
        # individual=-7.14% 도달 (current 64000 → -8.57%)
        h = _holding(method="sma_14", buy=70_000, current=64_000, stop=65_000)
        should_sell, reason = check_stop_loss(h, _profile())
        assert should_sell is True
        assert "audit" in h
        audit = h["audit"]["method_mismatch_at_exit"]
        assert audit["entry_method"] == "sma_14"
        assert audit["exit_runtime_method"] == "wilder_ema_14"
        assert audit["stop_price_preserved"] == 65_000

    def test_no_audit_when_methods_match(self, monkeypatch):
        # 같은 method → audit 없음
        monkeypatch.setattr(vams_engine, "_ATR_METHOD_RUNTIME", "wilder_ema_14")
        h = _holding(method="wilder_ema_14", buy=70_000, current=64_000, stop=65_000)
        check_stop_loss(h, _profile())
        assert "audit" not in h

    def test_audit_skipped_when_entry_method_missing(self, monkeypatch):
        # 기존 holding (atr_method_at_entry 부재) → audit 없음
        monkeypatch.setattr(vams_engine, "_ATR_METHOD_RUNTIME", "wilder_ema_14")
        h = _holding(method="sma_14", buy=70_000, current=64_000, stop=65_000)
        del h["atr_method_at_entry"]
        check_stop_loss(h, _profile())
        assert "audit" not in h


# ─────────────────────────────────────────────────────────────────────
# P-05 — _should_log_migration 자동 비활성
# ─────────────────────────────────────────────────────────────────────

class TestShouldLogMigration:
    def test_default_returns_true(self, monkeypatch):
        monkeypatch.delenv("UNIVERSE_RAMP_UP_STAGE", raising=False)
        monkeypatch.delenv("ATR_MIGRATION_START_DATE", raising=False)
        # ATR_MIGRATION_LOGGING 모듈 변수 강제 재설정
        from api.analyzers import technical as tm
        monkeypatch.setattr(tm, "ATR_MIGRATION_LOGGING", True)
        monkeypatch.setattr(tm, "ATR_MIGRATION_START_DATE", "")
        assert tm._should_log_migration() is True

    def test_env_disabled(self, monkeypatch):
        from api.analyzers import technical as tm
        monkeypatch.setattr(tm, "ATR_MIGRATION_LOGGING", False)
        assert tm._should_log_migration() is False

    def test_universe_above_1000_disables(self, monkeypatch):
        from api.analyzers import technical as tm
        monkeypatch.setattr(tm, "ATR_MIGRATION_LOGGING", True)
        monkeypatch.setattr(tm, "ATR_MIGRATION_START_DATE", "")
        monkeypatch.setenv("UNIVERSE_RAMP_UP_STAGE", "1500")
        assert tm._should_log_migration() is False

    def test_universe_at_500_enabled(self, monkeypatch):
        from api.analyzers import technical as tm
        monkeypatch.setattr(tm, "ATR_MIGRATION_LOGGING", True)
        monkeypatch.setattr(tm, "ATR_MIGRATION_START_DATE", "")
        monkeypatch.setenv("UNIVERSE_RAMP_UP_STAGE", "500")
        assert tm._should_log_migration() is True

    def test_after_14_days_disabled(self, monkeypatch):
        from api.analyzers import technical as tm
        monkeypatch.setattr(tm, "ATR_MIGRATION_LOGGING", True)
        # 30일 전 시작
        thirty_days_ago = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        monkeypatch.setattr(tm, "ATR_MIGRATION_START_DATE", thirty_days_ago)
        monkeypatch.setenv("UNIVERSE_RAMP_UP_STAGE", "85")
        assert tm._should_log_migration() is False

    def test_within_14_days_enabled(self, monkeypatch):
        from api.analyzers import technical as tm
        monkeypatch.setattr(tm, "ATR_MIGRATION_LOGGING", True)
        seven_days_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        monkeypatch.setattr(tm, "ATR_MIGRATION_START_DATE", seven_days_ago)
        monkeypatch.setenv("UNIVERSE_RAMP_UP_STAGE", "85")
        assert tm._should_log_migration() is True


# ─────────────────────────────────────────────────────────────────────
# P-08 — outlier counter
# ─────────────────────────────────────────────────────────────────────

class TestOutlierCounter:
    def test_counter_increments(self, tmp_path, monkeypatch):
        from api.analyzers import technical as tm
        counter_path = tmp_path / "counter.json"
        monkeypatch.setattr(tm, "OUTLIER_COUNTER_PATH", counter_path)
        assert tm._increment_outlier_counter() == 1
        assert tm._increment_outlier_counter() == 2
        assert tm._increment_outlier_counter() == 3

    def test_counter_resets_on_new_day(self, tmp_path, monkeypatch):
        from api.analyzers import technical as tm
        counter_path = tmp_path / "counter.json"
        monkeypatch.setattr(tm, "OUTLIER_COUNTER_PATH", counter_path)
        # 어제 날짜로 5건 기록
        counter_path.write_text(json.dumps(
            {"date": "2020-01-01", "count": 5, "alerted": True}
        ))
        # 오늘 호출 → date 갱신 + count=1
        result = tm._increment_outlier_counter()
        assert result == 1
        data = json.loads(counter_path.read_text())
        assert data["date"] != "2020-01-01"
        assert data["count"] == 1
        assert data["alerted"] is False

    def test_alert_threshold_check(self, tmp_path, monkeypatch):
        from api.analyzers import technical as tm
        counter_path = tmp_path / "counter.json"
        monkeypatch.setattr(tm, "OUTLIER_COUNTER_PATH", counter_path)

        # 텔레그램 send_message mock
        sent = []
        from api.notifications import telegram
        monkeypatch.setattr(telegram, "send_message",
                            lambda txt, **kw: sent.append(txt) or True)

        # 4건은 alert 없음
        for _ in range(4):
            tm._increment_outlier_counter()
        tm._send_outlier_alert_if_needed(4)
        assert sent == []

        # 5건 도달 → alert 발송
        tm._increment_outlier_counter()
        tm._send_outlier_alert_if_needed(5)
        assert len(sent) == 1
        assert "outlier" in sent[0]

        # 6번째 호출 — alerted=True 라 추가 발송 X
        tm._increment_outlier_counter()
        tm._send_outlier_alert_if_needed(6)
        assert len(sent) == 1  # 그대로

    def test_no_alert_below_threshold(self, tmp_path, monkeypatch):
        from api.analyzers import technical as tm
        counter_path = tmp_path / "counter.json"
        monkeypatch.setattr(tm, "OUTLIER_COUNTER_PATH", counter_path)

        sent = []
        from api.notifications import telegram
        monkeypatch.setattr(telegram, "send_message",
                            lambda txt, **kw: sent.append(txt) or True)

        tm._send_outlier_alert_if_needed(3)
        assert sent == []
