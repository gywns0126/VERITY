"""보유종목 수량·평단 입력 파싱 — 회귀 가드 (2026-08-22).

🚨 PM 실사고: "하이닉스 10주를 **2,000,000원**에 샀다고 올렸는데 자동으로
**1,690,000원**으로 되더라".

진짜 일어난 일은 "값이 바뀐 것" 이 아니다:
  1. `Number("2,000,000")` = NaN → 프론트 `|| 0` 이 **0** 으로 만든다
  2. 서버 `float("2,000,000")` = ValueError → `default 0` 으로 **0** 이 저장된다
  3. 서버 검증이 `avg_cost >= 0` 이라 0 이 **정상값으로 통과**한다 (에러 0)
  4. `avg_cost=0` 이면 평가 화면이 현재가로 대체 표시 → 1,690,000(= 000660 현재가)로 보인다
DB 실측(2026-08-22): 삼성전자·SK하이닉스 **둘 다 avg_cost 0.0**. 7월부터 그 상태였다.

🚨 핵심은 **조용한 실패**다. 사용자는 저장됐다고 믿는다.
되돌리지 말 것: 정규화(쉼표·단위 제거) + **0/파싱실패는 저장 거부**.
"""
from __future__ import annotations

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
API = ROOT / "vercel-api" / "api" / "holdings.py"
TSX = ROOT / "framer-components" / "public-probe" / "PublicHoldingsTab.tsx"


def _load_num():
    src = API.read_text(encoding="utf-8")
    i, j = src.find("def _num("), src.find("\nclass handler")
    ns: dict = {}
    exec(src[i:j], ns)
    return ns["_num"]


@pytest.mark.parametrize("raw,expect", [
    ("2,000,000", 2000000.0),
    ("2000000", 2000000.0),
    ("2,000,000원", 2000000.0),
    ("₩1,690,000", 1690000.0),
    (" 150 ", 150.0),
    ("150.5", 150.5),
])
def test_server_normalizes_formatted_numbers(raw, expect):
    assert _load_num()(raw) == expect


@pytest.mark.parametrize("raw", ["abc", "", None, "  "])
def test_server_returns_none_not_zero_on_failure(raw):
    """🚨 파싱 실패가 0 이 되면 조용히 잘못 저장된다 — None 이어야 게이트가 잡는다."""
    assert _load_num()(raw) is None


def test_server_rejects_zero_and_missing():
    src = API.read_text(encoding="utf-8")
    assert "shares <= 0 or avg_cost is None or avg_cost <= 0" in src, (
        "0 을 정상값으로 받으면 조용한 실패가 재발한다"
    )
    assert "_num(body.get(\"avg_cost\"))" in src, (
        "default 0 을 되돌리면 파싱 실패가 0 으로 통과한다"
    )


def test_frontend_normalizes_and_blocks():
    if not TSX.exists():
        pytest.skip("컴포넌트 없음")
    s = TSX.read_text(encoding="utf-8")
    assert "const parseNum" in s, "프론트 정규화 파서가 사라졌다"
    assert "setPopErr" in s, "파싱 실패 시 사용자에게 알리지 않으면 조용한 실패다"
    code = re.sub(r"^\s*//.*$", "", s, flags=re.M)
    assert "Number(pop.avg_cost) || 0" not in code, (
        "`|| 0` 이 되살아났다 — 쉼표 입력이 다시 0 으로 저장된다"
    )
    assert "Number(pop.shares) || 0" not in code
