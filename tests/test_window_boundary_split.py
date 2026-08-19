"""창 안에 변경 경계가 있으면 통짜 비율이 현재를 말하지 않는다 (2026-08-19).

## 왜 — 하루에 세 번 같은 오답

시계열 원장을 "최근 N일" 로 자르고 그 비율을 **현재 상태**로 읽었다. 창 안에 코드·설정이
바뀐 시점이 있으면 앞뒤가 섞여 현재를 말하지 않는다.

| 보고한 답 | 실제 |
|---|---|
| `factor_version` 도장률 402중 201 → "실질 1순위" | 배포 8/17 23:44. **배포 후 100%** |
| LLM `stock_analysis` 30일 1,823회 → "최대 절감 후보" | 스위치 OFF 8/16. **이후 0회 $0** |
| `self_assets` 7일 fail 45~55% → ALERT | 8/15~17 잔상. 8/17 이후 **8.2%** |

셋 다 **결함 아닌 것을 결함으로**, 또는 **이미 고친 것을 미해결로** 보고했다.

🚨 RULE 13(분모 먼저)의 사각이다 — 분모는 셌는데 **그 분모가 두 시기의 혼합**이었다.
도구 = `scripts/audit/window_split_at_boundary.py`.
"""
from __future__ import annotations

import json
import pathlib
import sys
from datetime import datetime, timedelta, timezone

_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts" / "audit"))

import window_split_at_boundary as W  # noqa: E402


def _write(tmp_path, rows):
    p = tmp_path / "led.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    return str(p)


def _iso(days_ago, hour=12):
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).replace(
        hour=hour, minute=0, second=0, microsecond=0).isoformat()


def test_split_separates_before_and_after(tmp_path):
    """경계 전 0% · 경계 후 100% 를 섞지 않고 갈라 보여준다."""
    rows = [{"ts": _iso(3), "v": None} for _ in range(200)] \
         + [{"ts": _iso(1), "v": "x"} for _ in range(600)]
    b = datetime.now(timezone.utc) - timedelta(days=2)
    r = W.split(_write(tmp_path, rows), "ts", b, field="v", days=10)
    assert r["before"]["pct"] == 0.0, r["before"]
    assert r["after"]["pct"] == 100.0, r["after"]
    # 🚨 통짜로 세면 25% — 그 숫자를 현재 상태로 읽는 것이 사고였다
    naive = 600 / 800 * 100
    assert abs(naive - r["after"]["pct"]) > 20, "통짜와 현재가 크게 다른 케이스여야 의미가 있다"


def test_boundary_from_git_path_resolves():
    """`--boundary-path` 는 그 경로의 마지막 커밋 시각을 경계로 쓴다."""
    b = W.boundary_from_path("api/quant/factors/version.py")
    assert b is not None, "git 이력에서 경계를 못 뽑았다"
    assert b.tzinfo is not None


def test_real_case_factor_version_stamping():
    """🚨 실사례 — 이 도구가 있었으면 R7 오판을 안 했다.

    `factor_version` 은 배포(2026-08-17 23:44) 이후 100% 다. 창을 날짜로만 자르면
    배포 전 실행 1회가 섞여 "절반만 찍힌다" 로 보인다.
    """
    led = _ROOT / "data" / "metadata" / "prediction_trail.jsonl"
    if not led.exists():
        return
    b = W.boundary_from_path("api/quant/factors/version.py")
    if b is None:
        return
    r = W.split(str(led), "created_at", b, field="factor_version", days=3)
    if not r["after"]["n"]:
        return
    assert r["after"]["pct"] == 100.0, (
        f"배포 후 도장률이 100% 가 아니다: {r['after']} — 진짜 결함이거나 도구 파손")


def test_no_boundary_inside_window_is_fine(tmp_path):
    """경계가 창 밖이면 한쪽만 차는 게 정상 (오탐 아님)."""
    rows = [{"ts": _iso(1), "v": "x"} for _ in range(50)]
    b = datetime.now(timezone.utc) - timedelta(days=30)
    r = W.split(_write(tmp_path, rows), "ts", b, field="v", days=10)
    assert r["before"]["n"] == 0 and r["after"]["n"] == 50
