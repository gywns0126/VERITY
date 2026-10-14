# -*- coding: utf-8 -*-
"""워크플로 스케줄 충돌 가드 (2026-08-07).

사고: `universe_scan`(UTC 06:30 시작, 실측 49~66분·중앙 55분)이 같은 concurrency 그룹
(`verity-data-write`)을 점유하는 동안 `daily_analysis_full`(07:07)이 대기로 들어갔고,
GitHub 가 그룹당 대기 슬롯을 **하나만** 유지하므로 제3의 워크플로가 도착하자 밀려나 취소됐다.

실측 2026-08-07:
  Universe Scan 06:30→07:24 점유 · daily_full 07:07 대기 · Export Trade 07:16 도착
  → daily_full **취소(job 0개 = 실행된 적 없음)** = 당일 KST 16:07 장 마감 분석 누락.

같은 드리프트가 두 번째다 — 2026-07-13 에도 스캔이 35→43분으로 늘어 37분 오프셋을
추월했고, 그때는 `ref: main` 으로 stale 체크아웃 증상만 고쳤다(충돌 자체는 남았다).

계약: ① KR 마감 full 은 universe_scan 최악 소요 뒤에 시작 ② cron 문자열로 mode 를
판정하므로 스케줄 이동 시 판정부도 함께 갱신 ③ Vercel fallback 매핑도 같은 시각.
"""
import os
import re

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(rel):
    with open(os.path.join(_ROOT, rel), encoding="utf-8") as f:
        return f.read()


def _crons(yml):
    return re.findall(r"^\s*-\s*cron:\s*'([^']+)'", yml, re.M)


def _to_min(cron):
    m, h = cron.split()[0], cron.split()[1]
    return int(h) * 60 + int(m)


# universe_scan 실측: 49·53·54·55·62·66분 (2026-08-03~07). 최악 66 + 여유.
_SCAN_WORST_MIN = 66
_MARGIN_MIN = 10


def test_kr_close_starts_after_universe_scan():
    """Only producer completion may trigger KR full; elapsed-time guesses race."""
    import yaml
    doc = yaml.safe_load(_read(".github/workflows/daily_analysis_full.yml"))
    triggers = doc.get("on", doc.get(True))
    assert "Universe Scan" in triggers["workflow_run"]["workflows"]
    assert triggers["workflow_run"]["types"] == ["completed"]
    assert not any(c["cron"].endswith("* * 1-5") for c in triggers["schedule"])


def test_mode_detection_matches_actual_cron():
    """cron 문자열로 mode 를 판정한다 — 스케줄을 옮기면 판정부도 옮겨야 한다."""
    yml = _read(".github/workflows/daily_analysis_full.yml")
    for cron in _crons(yml):
        assert f'"{cron}"' in yml, f"cron '{cron}' 이 mode 판정부에 없다 — else 로 흘러간다"


def test_vercel_fallback_matches_schedule():
    """No KR full timer remains in the dispatcher; the US slot is preserved."""
    import importlib.util
    from datetime import datetime, timezone
    spec = importlib.util.spec_from_file_location(
        "schedule_dispatch", os.path.join(_ROOT, "vercel-api/api/cron/dispatch_pulse.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    kr = module._resolve_events(datetime(2026, 10, 14, 7, 50, tzinfo=timezone.utc))
    us = module._resolve_events(datetime(2026, 10, 14, 21, 30, tzinfo=timezone.utc))
    assert "daily_analysis_full" not in [e[0] if isinstance(e, tuple) else e for e in kr]
    assert ("daily_analysis_full", {"mode": "full_us"}) in us


def test_concurrency_group_still_serialized():
    """그룹 자체는 유지 — 푸시 경합 방어용이다. 이번 수리는 시각 이동만."""
    yml = _read(".github/workflows/daily_analysis_full.yml")
    assert "group: verity-data-write" in yml
    assert "cancel-in-progress: false" in yml
