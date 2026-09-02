"""Vercel dispatch 가 워크플로 모드를 실어 보내는지 고정한다 (2026-08-20).

## 왜

`daily_analysis_full` 의 모드 분기는 `github.event.schedule` **문자열 매칭**이다.
그런데 실제 트리거는 GH schedule 이 아니라 **Vercel `repository_dispatch`** 다
(schedule silent miss 회피용 fallback 이 사실상 주 경로가 됐다).

dispatch 경로에서는 `github.event.schedule` 이 **빈 문자열**이므로 모든 `elif` 가
불일치하고 `else → mode=full` 로 흐른다. KST 06:30(UTC 21:30) 슬롯은 `full_us`
(미장 전체)여야 하는데 매번 `full`(미장 **상위 10개**)로 돌았다.

🚨 실측 2026-08-20 06:30 run(32304227272):
    ANALYSIS_MODE: full
    [5.71] 미장 데이터 수집 — 상위 10개 (10종목, Finnhub/SEC/yfinance)
Finnhub 커버가 US 29/49 로 보이던 원인이 이것이다. mock 도 rate limit 도 아니었다
(같은 run 의 MOCK CENSUS = finnhub 0건 · rate_limit=0).

워크플로 주석이 이미 경고했다 — *"cron 문자열 매칭이라 스케줄을 옮기면 else 로 흘러간다"*.
dispatch 는 schedule 이 아니므로 그 매칭이 **구조적으로** 성립하지 않는다.
"""
from __future__ import annotations

import importlib.util
import pathlib
from datetime import datetime, timezone

import yaml

_ROOT = pathlib.Path(__file__).resolve().parent.parent


def _dp():
    spec = importlib.util.spec_from_file_location(
        "dp", _ROOT / "vercel-api" / "api" / "cron" / "dispatch_pulse.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _full_events(dt):
    out = []
    for e in _dp()._resolve_events(dt):
        name = e[0] if isinstance(e, tuple) else e
        if name == "daily_analysis_full":
            out.append(e)
    return out


def test_us_close_slot_carries_full_us_mode():
    """🚨 KST 06:30 슬롯은 full_us 를 payload 로 실어야 한다."""
    ev = _full_events(datetime(2026, 8, 19, 21, 30, tzinfo=timezone.utc))  # UTC 수 21:30
    assert ev, "US 마감 슬롯에서 daily_analysis_full 이 발화하지 않는다"
    assert isinstance(ev[0], tuple), f"payload 없이 보낸다: {ev[0]!r} — full 로 흘러간다"
    assert ev[0][1].get("mode") == "full_us", ev[0]


def test_kr_close_slot_stays_default():
    """KST 16:50 슬롯은 full(KR) — payload 없이 보내 기본값을 쓴다."""
    ev = _full_events(datetime(2026, 8, 20, 7, 50, tzinfo=timezone.utc))  # UTC 목 07:50
    assert ev and not isinstance(ev[0], tuple), f"KR 슬롯에 모드가 붙었다: {ev}"


def test_workflow_reads_client_payload_before_cron():
    """워크플로가 client_payload.mode 를 CRON 매칭보다 **먼저** 본다."""
    src = (_ROOT / ".github" / "workflows" / "daily_analysis_full.yml").read_text(encoding="utf-8")
    assert "github.event.client_payload.mode" in src, "payload 를 읽지 않는다"
    i_pay = src.index("DISPATCH_MODE")
    i_cron = src.index('elif [ "$CRON" =')
    assert i_pay < i_cron, "CRON 분기가 payload 보다 먼저다 — dispatch 모드가 무시된다"
    yaml.safe_load(src)


def test_dispatch_sends_client_payload_field():
    """`_dispatch` 가 payload 를 GitHub 규격 필드명으로 싣는다."""
    src = (_ROOT / "vercel-api" / "api" / "cron" / "dispatch_pulse.py").read_text(encoding="utf-8")
    assert '"client_payload"' in src, "client_payload 키가 없다 — GitHub 이 모드를 못 받는다"


# ──────────────────────────────────────────────────────────────────────────
# 🚨 2026-08-20 추가 — 위 4건은 전부 **소스 문자열 grep** 이라, 분기가 지워져도
#    통과한다. 그런데 페이로드를 싣는 슬롯은 UTC 21:30 화~금 **하나뿐**이라
#    8/20 수정 이후 첫 발화가 8/21 06:30 KST 다. 즉 실제로 나가는 바이트를
#    아무도 본 적이 없는 상태로 첫 운영 발화를 맞게 된다.
#    아래는 urlopen 을 가로채 **전송 바디를 직접 검사**한다.
#    ([[feedback_green_check_is_not_safety]] — 통과가 안전을 뜻하지 않는다)
# ──────────────────────────────────────────────────────────────────────────

def _capture_dispatch(evt_item):
    """`_split_event` → `_dispatch` 를 실제로 태우고 전송 바디를 돌려준다."""
    import json as _json

    m = _dp()
    m.GH_PAT = "test-pat"
    sent = {}

    class _Resp:
        status = 204
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def _fake_urlopen(req, timeout=None):
        sent["url"] = req.full_url
        sent["method"] = req.get_method()
        sent["body"] = _json.loads(req.data.decode("utf-8"))
        return _Resp()

    m.urllib.request.urlopen = _fake_urlopen
    evt, payload = m._split_event(evt_item)
    status, _ = m._dispatch(evt, payload)
    sent["status"] = status
    return sent


def test_us_slot_wire_body_carries_mode():
    """🚨 실제 US 슬롯 항목을 그대로 태워, GitHub 에 나가는 바디를 검사한다."""
    ev = _full_events(datetime(2026, 8, 19, 21, 30, tzinfo=timezone.utc))
    sent = _capture_dispatch(ev[0])

    assert sent["method"] == "POST"
    assert sent["url"].endswith("/dispatches"), sent["url"]
    # event_type 이 str 이 아니면 GitHub 이 422 를 낸다 (튜플 미해체 회귀)
    assert isinstance(sent["body"]["event_type"], str), sent["body"]
    assert sent["body"]["event_type"] == "daily_analysis_full", sent["body"]
    assert sent["body"]["client_payload"] == {"mode": "full_us"}, sent["body"]
    assert sent["status"] == 204


def test_kr_slot_wire_body_omits_client_payload():
    """KR 슬롯은 client_payload 키 자체가 없어야 한다 — 빈 dict 도 아니다.

    빈 dict 를 보내면 워크플로의 `-n "$DISPATCH_MODE"` 는 어차피 거짓이라 결과는
    같지만, '모드를 의도적으로 안 실었다' 와 '실었는데 비었다' 가 구분되지 않는다.
    """
    ev = _full_events(datetime(2026, 8, 20, 7, 50, tzinfo=timezone.utc))
    sent = _capture_dispatch(ev[0])
    assert "client_payload" not in sent["body"], sent["body"]
    assert sent["body"] == {"event_type": "daily_analysis_full"}


def test_split_event_handles_both_shapes():
    """문자열 항목과 튜플 항목 양쪽 — 핸들러가 쓰는 그 함수를 직접 검사한다."""
    m = _dp()
    assert m._split_event("price_pulse") == ("price_pulse", None)
    assert m._split_event(("daily_analysis_full", {"mode": "full_us"})) == (
        "daily_analysis_full", {"mode": "full_us"})


def test_handler_uses_split_event_not_inline_unpack():
    """핸들러가 헬퍼를 쓰는지 고정 — 인라인으로 되돌리면 위 테스트가 무력해진다."""
    src = (_ROOT / "vercel-api" / "api" / "cron" / "dispatch_pulse.py").read_text(encoding="utf-8")
    assert "_split_event(raw_evt)" in src, "핸들러가 _split_event 를 거치지 않는다"


def test_cron_fallback_string_matches_actual_schedule():
    """🚨 fallback 이 죽지 않았는지 — 워크플로 cron 목록과 분기 문자열을 대조한다.

    dispatch 가 주 경로이고 GH schedule 은 fallback 이다. 그런데 fallback 분기는
    cron **문자열 완전일치**라, 스케줄을 옮기면 조용히 `else → full` 로 떨어진다
    (에러도 알림도 없다). 실제 cron 목록에 없는 문자열을 분기가 기다리고 있으면 실패시킨다.
    """
    wf = _ROOT / ".github" / "workflows" / "daily_analysis_full.yml"
    src = wf.read_text(encoding="utf-8")
    doc = yaml.safe_load(src)
    # 🚨 YAML 1.1 은 `on:` 을 **불리언 True** 로 읽는다. doc["on"] 은 KeyError 다.
    on = doc.get("on", doc.get(True))
    schedules = {c["cron"] for c in on["schedule"]}

    import re
    branch_strings = set(re.findall(r'\$CRON" = "([^"]+)"', src))
    # 신·구 병기가 허용된 것들(주석에 사유 기재)은 실제 목록에 없어도 무해하다.
    us_slot = "30 21 * * 2-5"
    assert us_slot in branch_strings, "미장 fallback 분기 문자열이 사라졌다"
    assert us_slot in schedules, (
        f"미장 cron 이 옮겨졌는데 분기가 그대로다 — schedule 경로가 full 로 떨어진다: {schedules}")


# ──────────────────────────────────────────────────────────────────────────
# 보정 슬롯 (2026-08-20) — 30분 수집기가 하루 27~36회만 돌던 것(기대 48).
# 워크플로 실패 0건 = 고장이 아니라 **dispatch 호출 누락**. 5분 뒤 한 번 더 기회를 주되,
# 정규 슬롯이 이미 돌았으면 건너뛴다.
# ──────────────────────────────────────────────────────────────────────────

def test_backup_slot_fires_at_5_and_35():
    m = _dp()
    for minute in (5, 35):
        got = m._resolve_backup_events(datetime(2026, 8, 20, 13, minute, tzinfo=timezone.utc))
        assert [e for e, _ in got] == ["macro_collect", "crypto_collect"], (minute, got)
        assert all(w.endswith(".yml") for _, w in got), got


def test_backup_slot_is_empty_on_regular_and_other_minutes():
    m = _dp()
    for minute in (0, 30, 7, 10, 50, 55):
        assert m._resolve_backup_events(
            datetime(2026, 8, 20, 13, minute, tzinfo=timezone.utc)) == [], minute


def test_dividend_backup_slots_are_time_scoped():
    """KSD 보정은 UTC 05:55/06:15에만 있고 매시간 발화하지 않는다."""
    m = _dp()
    for hour, minute in ((5, 55), (6, 15)):
        got = m._resolve_backup_events(
            datetime(2026, 8, 27, hour, minute, tzinfo=timezone.utc))
        assert ("dividend_ksd", "dividend_ksd.yml") in got
    assert ("dividend_ksd", "dividend_ksd.yml") not in m._resolve_backup_events(
        datetime(2026, 8, 27, 7, 55, tzinfo=timezone.utc))


def test_dividend_workflow_accepts_repository_dispatch():
    src = (_ROOT / ".github" / "workflows" / "dividend_ksd.yml").read_text(encoding="utf-8")
    assert "repository_dispatch:" in src
    assert "types: [dividend_ksd]" in src
    yaml.safe_load(src)


def test_backup_never_touches_the_us_slot():
    """🚨 미장 full_us 는 21:30. 보정 슬롯이 그 자리에 끼어들면 안 된다."""
    m = _dp()
    assert m._resolve_backup_events(datetime(2026, 8, 20, 21, 30, tzinfo=timezone.utc)) == []
    # 보정 대상에 무거운 파이프라인이 섞이지 않았는지도 고정
    names = {e for slot in m._BACKUP_SLOTS.values() for e, _ in slot}
    assert names == {"macro_collect", "crypto_collect"}, names


def test_ran_recently_is_fail_open():
    """판단 실패 = False(= 보정 발화). 모를 때 메우는 쪽이 이 슬롯의 목적이다."""
    m = _dp()
    m.GH_PAT = "test-pat"

    def _boom(req, timeout=None):
        raise OSError("network down")

    m.urllib.request.urlopen = _boom
    assert m._ran_recently("crypto_collect.yml", 20,
                           datetime(2026, 8, 20, 13, 35, tzinfo=timezone.utc)) is False

    m.GH_PAT = ""      # 토큰 부재도 같은 방향
    assert m._ran_recently("crypto_collect.yml", 20,
                           datetime(2026, 8, 20, 13, 35, tzinfo=timezone.utc)) is False


def test_ran_recently_reads_created_at_window():
    """정규 슬롯 발화(5분 전) = True → 건너뜀 / 35분 전 = False → 보정 발화."""
    import io
    import json as _json
    m = _dp()
    m.GH_PAT = "test-pat"
    now = datetime(2026, 8, 20, 13, 35, tzinfo=timezone.utc)

    def _mk(created_iso):
        class _R:
            def read(self): return _json.dumps(
                {"workflow_runs": [{"created_at": created_iso}]}).encode()
            def __enter__(self): return self
            def __exit__(self, *a): return False
        return lambda req, timeout=None: _R()

    m.urllib.request.urlopen = _mk("2026-08-20T13:30:12Z")   # 5분 전 = 정규 슬롯
    assert m._ran_recently("crypto_collect.yml", 20, now) is True
    m.urllib.request.urlopen = _mk("2026-08-20T13:00:09Z")   # 35분 전 = 앞앞 슬롯
    assert m._ran_recently("crypto_collect.yml", 20, now) is False


def test_quick_busy_gate_sees_any_shared_writer_and_allows_completed():
    import json as _json
    m = _dp()
    m.GH_PAT = "test-pat"
    now = datetime(2026, 9, 2, 14, 7, tzinfo=timezone.utc)

    def _response(status, path=".github/workflows/daily_analysis_full.yml"):
        class _R:
            def read(self):
                return _json.dumps({"workflow_runs": [{
                    "status": status, "path": path,
                    "created_at": "2026-09-02T13:07:30Z"
                }]}).encode()
            def __enter__(self): return self
            def __exit__(self, *a): return False
        return lambda req, timeout=None: _R()

    m.urllib.request.urlopen = _response("queued")
    assert m._data_write_group_busy(now) is True
    m.urllib.request.urlopen = _response("in_progress", ".github/workflows/bond_etf_analysis.yml")
    assert m._data_write_group_busy(now) is True
    m.urllib.request.urlopen = _response("completed")
    assert m._data_write_group_busy(now) is False
    m.urllib.request.urlopen = _response("in_progress", ".github/workflows/price_pulse.yml")
    assert m._data_write_group_busy(now) is False


def test_quick_busy_gate_fails_safe_but_ignores_ancient_run():
    import json as _json
    m = _dp()
    m.GH_PAT = "test-pat"
    now = datetime(2026, 9, 2, 14, 7, tzinfo=timezone.utc)

    def _boom(req, timeout=None):
        raise OSError("network down")

    m.urllib.request.urlopen = _boom
    assert m._data_write_group_busy(now) is True

    class _R:
        def read(self):
            return _json.dumps({"workflow_runs": [{
                "status": "in_progress", "path": ".github/workflows/daily_analysis_full.yml",
                "created_at": "2026-08-01T00:00:00Z"
            }]}).encode()
        def __enter__(self): return self
        def __exit__(self, *a): return False

    m.urllib.request.urlopen = lambda req, timeout=None: _R()
    assert m._data_write_group_busy(now) is False


def test_data_write_workflow_registry_matches_yaml():
    import re
    m = _dp()
    workflow_dir = _ROOT / ".github" / "workflows"
    actual = set()
    for path in workflow_dir.glob("*.yml"):
        src = path.read_text(encoding="utf-8")
        if re.search(r"(?m)^\s+group:\s*verity-data-write\s*$", src):
            actual.add(path.name)
    assert m.DATA_WRITE_WORKFLOWS == actual
