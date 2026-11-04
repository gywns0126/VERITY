from api.notifications.essential_policy import (
    essential_only_enabled, is_essential_alert, should_send_notification,
)


def test_default_policy_and_explicit_opt_out(monkeypatch):
    monkeypatch.delenv("TELEGRAM_NOTIFICATION_MODE", raising=False)
    assert essential_only_enabled()
    assert not should_send_notification("completed", kind="routine")
    monkeypatch.setenv("TELEGRAM_NOTIFICATION_MODE", "all")
    assert not essential_only_enabled()
    assert should_send_notification("completed", kind="routine")


def test_routine_titles_cannot_claim_quiet_hour_bypass(monkeypatch):
    monkeypatch.setenv("TELEGRAM_NOTIFICATION_MODE", "essential")
    for text in ("📊 <b>MarketHorizon Signal 변경</b>\n변화 내용",
                 "📊 <b>brain_audit @ 2026-11-04T07:25</b>",
                 "✅ <b>VERITY 채권·ETF 업데이트</b>",
                 "<b>📋 일일 브리핑</b>",
                 "<b>[배리티 속보]</b> 회사 관련 뉴스",
                 "🚨 *SEC 8-K 신규 filing* (1건)",
                 "📊 MarketHorizon Cycle 변경",
                 "📊 <b>VAMS 월간 검증 리포트</b>",
                 "<b>⚠️ 섹터 로테이션 vs Quadrant 정합성 경고</b>"):
        assert not should_send_notification(text)


def test_critical_labels_do_not_promote_information(monkeypatch):
    monkeypatch.setenv("TELEGRAM_NOTIFICATION_MODE", "essential")
    for category in ("macro", "earnings", "geopolitical"):
        assert not is_essential_alert({"level": "CRITICAL", "category": category})
    assert is_essential_alert({"type": "STOP_LOSS", "category": "macro", "level": "CRITICAL"})
    assert is_essential_alert({"type": "ORDER_FAILED", "level": "CRITICAL"})
    assert is_essential_alert({"category": "holding", "level": "CRITICAL"})
    assert is_essential_alert({"category": "holding", "level": "WARNING"})
    assert is_essential_alert({"category": "sec_risk", "level": "WARNING"})
    assert is_essential_alert({"category": "new-critical-incident", "level": "CRITICAL"})
    assert not is_essential_alert({"category": "new-info", "level": "INFO"})


def test_essential_and_direct_commands_are_preserved(monkeypatch):
    monkeypatch.setenv("TELEGRAM_NOTIFICATION_MODE", "essential")
    assert should_send_notification("주문 실패", kind="essential")
    assert should_send_notification("일일 브리핑", kind="command")
    assert should_send_notification("인증 경로의 새로운 장애")


def test_new_measurement_failure_is_not_routine():
    assert should_send_notification("<b>🚨 측정 감사 신규 검출</b> (1종)")


def test_hourly_pulse_policy_skips_before_reading_holdings(monkeypatch):
    from scripts import hourly_pulse_send
    monkeypatch.setenv("TELEGRAM_NOTIFICATION_MODE", "essential")
    def forbidden(*args, **kwargs):
        raise AssertionError("routine pulse must not load data or reach the network")
    monkeypatch.setattr(hourly_pulse_send, "_load_json", forbidden)
    monkeypatch.setattr(hourly_pulse_send, "_resolve_slot", forbidden)
    assert hourly_pulse_send.main() == 0
