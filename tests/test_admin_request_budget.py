"""admin.py 요청 예산 계약 (2026-08-23).

🚨 왜 — `vercel.json` 의 `api/admin.py` maxDuration 은 **15초**인데, 인증된 요청 하나가 타는
외부 호출의 고정 타임아웃 합이 최악 **27초**였다(인증 5 + 관리자확인 6 + 감사로그 6 +
데이터조회 10). 개별 호출은 각자 예산 안인데 **합이 함수 예산을 넘는다.**

그러면 상류가 느려질 때 우리 코드가 에러를 내기 전에 플랫폼이 먼저 끊어 **본문 없는 504**
가 나간다 — 관리자 화면에 "왜 안 되는지 모름" 만 남는다. 2026-08-23 PM 신고가 그 상태였다.

해법 = 요청 시작 기준 남은 예산 안으로 매 호출 타임아웃을 깎고, 바닥나면 **어느 단계에서
막혔는지 담아 503**. 아래는 그 계약을 기계로 고정한다.
"""
from __future__ import annotations

import importlib.util
import json
import re
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ADMIN = ROOT / "vercel-api" / "api" / "admin.py"
VERCEL_JSON = ROOT / "vercel-api" / "vercel.json"


@pytest.fixture(scope="module")
def adm():
    spec = importlib.util.spec_from_file_location("_adm_under_test", ADMIN)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# ── 설정 정합 ──────────────────────────────────────────────────

def test_budget_fits_inside_function_max_duration(adm):
    """🚨 이 테스트가 이 파일의 존재 이유다 — 예산이 플랫폼 한계를 넘으면 다시 504 가 된다."""
    cfg = json.loads(VERCEL_JSON.read_text(encoding="utf-8"))
    max_dur = cfg["functions"]["api/admin.py"]["maxDuration"]
    assert adm._REQ_BUDGET_SEC < max_dur, (
        f"요청 예산 {adm._REQ_BUDGET_SEC}s 가 maxDuration {max_dur}s 이상이다 — 504 로 돌아간다"
    )
    assert max_dur - adm._REQ_BUDGET_SEC >= 2, (
        "여유가 2초 미만 — 응답 직렬화·콜드스타트 몫이 없다"
    )


def test_no_bare_timeout_literals_remain(adm):
    """고정 타임아웃이 하나라도 남으면 그 호출만 예산을 안 지킨다."""
    src = ADMIN.read_text(encoding="utf-8")
    bare = re.findall(r"timeout=\d+", src)
    assert not bare, f"예산을 안 거치는 고정 타임아웃 {len(bare)}개소: {bare[:5]}"
    assert src.count("timeout=_t(") >= 25, "예산 헬퍼 적용이 줄었다"


# ── 예산 계산 ──────────────────────────────────────────────────

def test_outside_entrypoint_is_passthrough(adm):
    """진입점 밖(모듈 로드·배치 스크립트)에서는 예산을 적용하지 않는다."""
    adm._budget["t0"] = 0
    assert adm._t(10) == 10


def test_shrinks_to_remaining_budget(adm):
    adm._budget["t0"] = time.monotonic() - 9.0
    adm._stage("member_management")
    v = adm._t(10)
    assert 2.5 < v < 3.5, f"남은 예산으로 안 깎였다: {v}"


def test_raises_with_stage_when_exhausted(adm):
    adm._budget["t0"] = time.monotonic() - (adm._REQ_BUDGET_SEC + 0.5)
    adm._stage("audit_log")
    with pytest.raises(adm._BudgetExceeded) as ei:
        adm._t(10)
    assert ei.value.stage == "audit_log", "어느 단계에서 막혔는지 안 실린다"
    assert ei.value.spent > adm._REQ_BUDGET_SEC


def test_worst_case_chain_stays_under_budget(adm):
    """🚨 옛 27초 조합(5+6+6+10)이 예산 안에 갇히는가."""
    adm._budget_start()
    total = 0.0
    for stage, want in (("authorize", 5), ("is_super_admin", 6), ("audit", 6), ("query", 10)):
        adm._stage(stage)
        try:
            t = adm._t(want)
        except adm._BudgetExceeded:
            break
        total += t
        adm._budget["t0"] -= t          # 그 호출이 타임아웃까지 걸렸다고 가정
    assert total <= adm._REQ_BUDGET_SEC + 0.01, f"누적 {total}s 가 예산을 넘었다"


# ── 응답 계약 ──────────────────────────────────────────────────

def test_timeout_response_names_the_stage(adm):
    """504 와 달리 화면이 원인을 읽을 수 있어야 한다 — 이게 이번 수정의 목적이다."""
    captured = {}

    class _H:
        pass

    orig = adm.write_response
    try:
        adm.write_response = lambda h, status, body: captured.update(status=status, body=body)
        adm._budget_timeout_response(_H(), adm._BudgetExceeded("member_management", 12.4), "member_management")
    finally:
        adm.write_response = orig

    assert captured["status"] == 503, "504(본문 없음) 대신 503 이어야 한다"
    b = captured["body"]
    for k in ("error", "endpoint", "stage", "spent_sec", "budget_sec"):
        assert k in b, f"응답에 {k} 가 없다 — 원인 추적 불가"
    assert b["stage"] == "member_management"


def test_entrypoints_start_budget_and_catch(adm):
    """진입점에서 예산을 시작하고 소진을 잡아야 한다 — 하나라도 빠지면 그 경로가 504 로 샌다."""
    src = ADMIN.read_text(encoding="utf-8")
    assert src.count("_budget_start()") >= 3, "예산 시작이 진입점 수보다 적다"
    assert src.count("except _BudgetExceeded") >= 3, "예산 소진 캐치가 빠진 진입점이 있다"
