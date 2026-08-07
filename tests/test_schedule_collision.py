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
    """🚨 핵심 — 스캔이 끝난 뒤 시작해야 대기 슬롯에 들어가지 않는다."""
    scan = _crons(_read(".github/workflows/universe_scan.yml"))
    full = _crons(_read(".github/workflows/daily_analysis_full.yml"))
    scan_start = _to_min(scan[0])
    kr_close = min(c for c in (_to_min(x) for x in full) if c > scan_start)
    gap = kr_close - scan_start
    assert gap >= _SCAN_WORST_MIN + _MARGIN_MIN, (
        f"간격 {gap}분 < 최악 {_SCAN_WORST_MIN}+여유 {_MARGIN_MIN}분 — 대기 슬롯 충돌 재발")


def test_mode_detection_matches_actual_cron():
    """cron 문자열로 mode 를 판정한다 — 스케줄을 옮기면 판정부도 옮겨야 한다."""
    yml = _read(".github/workflows/daily_analysis_full.yml")
    for cron in _crons(yml):
        assert f'"{cron}"' in yml, f"cron '{cron}' 이 mode 판정부에 없다 — else 로 흘러간다"


def test_vercel_fallback_matches_schedule():
    """Vercel fallback 이 옛 시각으로 쏘면 같은 충돌이 재현된다."""
    yml = _read(".github/workflows/daily_analysis_full.yml")
    disp = _read("vercel-api/api/cron/dispatch_pulse.py")
    kr = [c for c in _crons(yml) if c.endswith("* * 1-5")]
    assert kr, "KR 마감 cron 미발견"
    mm, hh = kr[0].split()[0], kr[0].split()[1]
    assert re.search(rf"hour\s*==\s*{hh}\s+and\s+minute\s*==\s*{mm}", disp), (
        f"dispatch_pulse 에 UTC {hh}:{mm} 매핑 없음 — 워크플로 cron 과 어긋난다")


def test_concurrency_group_still_serialized():
    """그룹 자체는 유지 — 푸시 경합 방어용이다. 이번 수리는 시각 이동만."""
    yml = _read(".github/workflows/daily_analysis_full.yml")
    assert "group: verity-data-write" in yml
    assert "cancel-in-progress: false" in yml
