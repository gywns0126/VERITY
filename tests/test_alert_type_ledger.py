# -*- coding: utf-8 -*-
"""알림 유형 장부 (2026-08-07, C-4).

사고: volume 장부가 **배치 헤더만** 기록해, 3주간 "🚨 VERITY 긴급 알림" 83건이 어느
유형에서 나왔는지 셀 수 없었다. 어느 알림이 시끄러운지 모르면 정비도 못 한다.

CRITICAL 안에 성격이 다른 둘이 섞여 있다:
  · 매크로 국면 서술 — VIX·리세션확률·미장급락. 같은 국면이면 며칠씩 반복, 행동 불가
  · 보유 종목 액션 — 손절 접근·매도 권고·매입가 대비 하락. 1회성, 행동 가능
비율을 모르면 어느 쪽을 낮출지 정할 수 없다.

계약: ① 유형·선언 레벨을 행 단위로 기록 ② **발송 여부와 무관**하게 생성 시점에 기록
(quiet/dedupe 로 안 간 것도 "긴급이라 판단한 횟수") ③ 가변 수치는 마스킹해 유형 집계
가능 ④ 장부 실패가 알림 경로를 죽이지 않는다.
"""
import json
import os
import tempfile

import api.notifications.telegram as T


def _tmp(monkeypatch):
    d = tempfile.mkdtemp()
    p = os.path.join(d, "alert_type_ledger.jsonl")
    monkeypatch.setattr(T, "_ALERT_TYPE_LEDGER_PATH", p)
    return p


def _rows(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def test_records_type_and_level(monkeypatch):
    p = _tmp(monkeypatch)
    T._append_alert_type_ledger(
        [{"type": "STOP_LOSS", "level": "CRITICAL", "message": "A 수익률 -8.3%"}],
        [{"type": "PARTIAL_EXIT", "level": "WARNING", "message": "B 1R 도달"}])
    r = _rows(p)
    assert [x["level"] for x in r] == ["CRITICAL", "OTHER"]
    assert [x["type"] for x in r] == ["STOP_LOSS", "PARTIAL_EXIT"]
    assert r[0]["declared_level"] == "CRITICAL"


def test_shape_groups_same_rule_across_stocks():
    """🚨 종목명·수치가 다르면 같은 규칙이 다른 줄로 흩어져 집계가 안 된다.

    수치만 지우면 종목명이 남아 여전히 흩어진다 — 선행 고유명사도 제거해야 모인다.
    """
    a = T._alert_shape("삼성전자 수익률 -8.3% — 손절선 접근")
    b = T._alert_shape("기아 수익률 -12.7% — 손절선 접근")
    assert a == b, f"{a!r} != {b!r}"


def test_dual_schema_key_fallback(monkeypatch):
    """🚨 발신원이 스키마 둘을 쓴다 — vams=`type`, alert_engine=`category`.

    하나만 읽으면 alert_engine 알림(긴급의 대부분)이 전부 unknown 이 된다.
    """
    p = _tmp(monkeypatch)
    T._append_alert_type_ledger(
        [{"type": "STOP_LOSS", "level": "CRITICAL", "message": "A -1%"},
         {"category": "macro", "level": "CRITICAL", "message": "VIX 41"}], [])
    keys = [r["key"] for r in _rows(p)]
    assert keys == ["STOP_LOSS", "macro"]
    assert "unknown" not in keys


def test_recorded_regardless_of_send_outcome(monkeypatch):
    """🚨 quiet/dedupe 로 안 나가도 '긴급이라 판단한 횟수'는 남아야 한다."""
    p = _tmp(monkeypatch)
    monkeypatch.setattr(T, "send_message", lambda *a, **k: False)   # 전송 실패/차단
    T.send_alerts([{"type": "VIX_PANIC", "level": "CRITICAL", "message": "VIX 41"}])
    assert len(_rows(p)) == 1


def test_empty_input_writes_nothing(monkeypatch):
    p = _tmp(monkeypatch)
    T._append_alert_type_ledger([], [])
    assert not os.path.exists(p)


def test_missing_type_recorded_as_unknown(monkeypatch):
    """type 누락도 기록한다 — 안 보이면 정비 대상에서 빠진다."""
    p = _tmp(monkeypatch)
    T._append_alert_type_ledger([{"level": "CRITICAL", "message": "x"}], [])
    assert _rows(p)[0]["key"] == "unknown"


def test_ledger_failure_does_not_break_alerts(monkeypatch):
    """장부가 죽어도 알림은 나간다 — 관측이 본 기능을 막지 않는다."""
    monkeypatch.setattr(T, "_ALERT_TYPE_LEDGER_PATH", "/proc/nonexistent/x.jsonl")
    sent = []
    monkeypatch.setattr(T, "send_message", lambda m, **k: sent.append(m) or True)
    assert T.send_alerts([{"type": "X", "level": "CRITICAL", "message": "m"}]) is True
    assert sent


def test_send_alerts_wires_the_ledger():
    import inspect
    assert "_append_alert_type_ledger" in inspect.getsource(T.send_alerts)
