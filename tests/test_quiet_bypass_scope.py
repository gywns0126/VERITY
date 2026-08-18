# -*- coding: utf-8 -*-
"""야간(quiet hours) 통과 자격 — 돈이 움직이는 것만 깨운다.

## 왜 (2026-08-17 실측, PM "알림이 너무 많다")

최근 8일 실발송 98건 중 **야간(23~07시) 30건(31%)** 이고 그중 28건이 "🚨 긴급" 묶음이었다.
CRITICAL 내역 = macro 125 · earnings 63 · STOP_LOSS 40 · unknown 19 — 즉 **macro+earnings
가 CRITICAL 의 76%** 인데, 이 둘이 새벽 0·2·4·5시에 깨웠다.

종전 코드는 CRITICAL 묶음을 **무조건** `bypass_quiet=True` 로 보냈다. 레벨만 보고
성격을 안 봤다.

## 기준

집행 계열(손절·노출차단·부분청산·신규매수)만 야간 통과. 거시 국면·실적은 정보성이고
같은 국면이면 며칠씩 반복되므로 장 열릴 때 봐도 늦지 않다.

🚨 **레벨(CRITICAL)은 안 건드린다** — 다른 소비처가 읽는다. 바꾸는 것은 야간 통과 자격뿐이고
낮에는 종전과 동일하게 전부 발송된다.

실데이터 예측: 야간 배치 89 → 26 (71% 감소) · 낮 배치 95개 무변경.
"""
from __future__ import annotations

from api.notifications.telegram import _QUIET_BYPASS_KEYS, _alert_key, _may_bypass_quiet


def test_execution_alerts_wake_you():
    """🚨 돈이 움직이는 것은 새벽에도 깨운다."""
    for k in ("STOP_LOSS", "EXPOSURE_BLOCK", "PARTIAL_EXIT", "NEW_BUY"):
        assert _may_bypass_quiet([{"type": k}]) is True, k


def test_informational_alerts_do_not_wake_you():
    """거시·실적은 정보성 — 아침에 봐도 된다 (야간 소음의 76%)."""
    assert _may_bypass_quiet([{"category": "macro"}]) is False
    assert _may_bypass_quiet([{"category": "earnings"}]) is False
    assert _may_bypass_quiet([{"category": "macro"}, {"category": "earnings"}]) is False


def test_mixed_batch_passes_on_execution():
    """🚨 손절 1건이 거시 5건과 묶였다고 아침까지 묻어두면 안 된다 — OR 판정."""
    batch = [{"category": "macro"}, {"category": "earnings"}, {"type": "STOP_LOSS"}]
    assert _may_bypass_quiet(batch) is True


def test_unknown_does_not_bypass():
    """유형 미상은 통과시키지 않는다 — 모르는 것을 긴급으로 대우하면 자격이 다시 넓어진다."""
    assert _may_bypass_quiet([{"message": "무언가"}]) is False
    assert _may_bypass_quiet([]) is False


def test_key_fallback_matches_ledger():
    """장부(`_append_alert_type_ledger`)와 **같은 폴백 순서** — 어긋나면 집계와 판정이 갈린다."""
    assert _alert_key({"type": "STOP_LOSS", "category": "macro"}) == "STOP_LOSS"
    assert _alert_key({"category": "macro"}) == "macro"
    assert _alert_key({}) == "unknown"


def test_bypass_set_is_execution_only():
    """자격 집합이 조용히 넓어지지 않게 고정한다 — 넓어지면 이 교정이 무효가 된다."""
    assert _QUIET_BYPASS_KEYS == {"STOP_LOSS", "EXPOSURE_BLOCK", "PARTIAL_EXIT", "NEW_BUY"}
    for noisy in ("macro", "earnings", "unknown", "INFO", "WARNING"):
        assert noisy not in _QUIET_BYPASS_KEYS
