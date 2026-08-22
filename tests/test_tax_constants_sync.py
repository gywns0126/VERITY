"""세제 상수 3소스 동기 — 회귀 가드 (2026-08-22).

둥지 "예상 세금" 탭이 쓰는 `TAX` 상수가 **SoT 를 복제**하고 있다:
  SoT   `api/trading/account_profile.py`
  복제   `framer-components/public-probe/PublicHoldingsTab.tsx` 의 `const TAX = {...}`

컴포넌트 헤더가 *"세제 SoT = account_profile.py (변경 시 TAX 상수 동기화)"* 라고
적어두었지만 **문구일 뿐 강제가 없었다.** 지금 6개 전부 일치하는 건 운이 좋아서가 아니라
SoT 가 2026-06-29 이후 안 바뀌었기 때문이다 — 다음 세제 개정 때 한쪽만 고쳐질 확률이 높다.

🚨 왜 중요한가: 틀린 세금액은 **사용자가 그걸로 판단**한다. 그리고 틀려도 아무도 모른다
(에러가 안 나고 그럴듯한 숫자가 나온다) — 오늘 평단 0 사고와 같은 형태다.

🚨 이 파일의 설계 원칙: **파싱이 빈손이면 통과시키지 않는다.** 정규식이 안 맞아 0개를
읽고 "불일치 0" 으로 초록이 뜨는 게 이 종류 가드의 대표적 실패다
([[feedback_green_check_is_not_safety]] · 분모 먼저).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SOT = ROOT / "api" / "trading" / "account_profile.py"
TSX = ROOT / "framer-components" / "public-probe" / "PublicHoldingsTab.tsx"

# 복제 키 → SoT 키
PAIRS = {
    "KR_TXN": "KR_TRANSACTION_TAX",
    "KR_MAJOR_AMT": "KR_MAJOR_SHAREHOLDER_AMOUNT",
    "US_CGT": "US_CAPITAL_GAINS_TAX",
    "US_CGT_HIGH": "US_CAPITAL_GAINS_TAX_HIGH",
    "US_DEDUCT": "US_CAPITAL_GAINS_DEDUCTION",
    "US_BRACKET": "US_CAPITAL_GAINS_HIGH_THRESHOLD",
}


def _f(s: str) -> float:
    return float(s.replace("_", ""))


def _sot() -> dict:
    src = SOT.read_text(encoding="utf-8")
    out = {}
    for m in re.finditer(r"^([A-Z][A-Z0-9_]+)\s*=\s*([0-9][0-9_.]*)\s*(?:#.*)?$", src, re.M):
        out[m.group(1)] = _f(m.group(2))
    return out


def _tsx() -> dict:
    src = TSX.read_text(encoding="utf-8")
    i = src.find("const TAX = {")
    if i < 0:
        return {}
    blk = src[i:src.find("}", i)]
    # 🚨 프레이머 포매터가 공백·줄바꿈을 넣으므로 평탄화 후 파싱한다(오늘 3번 빗나갔다)
    flat = re.sub(r"\s+", " ", blk)
    return {m.group(1): _f(m.group(2))
            for m in re.finditer(r"([A-Z][A-Z0-9_]*)\s*:\s*([0-9][0-9_.]*)", flat)}


def test_parsers_actually_read_values():
    """🚨 분모 먼저 — 파싱이 빈손이면 아래 대조가 무의미하게 통과한다."""
    sot, tsx = _sot(), _tsx()
    assert len(sot) >= 6, f"SoT 상수 파싱 실패({len(sot)}개) — 정규식이 형식과 안 맞는다"
    assert len(tsx) == len(PAIRS), (
        f"컴포넌트 TAX 블록 파싱 {len(tsx)}개, 기대 {len(PAIRS)}개. "
        f"키가 늘거나 줄었으면 PAIRS 를 갱신할 것: {sorted(tsx)}"
    )


@pytest.mark.parametrize("dup,sot_key", sorted(PAIRS.items()))
def test_tax_constant_matches_sot(dup, sot_key):
    sot, tsx = _sot(), _tsx()
    assert sot_key in sot, f"SoT 에 {sot_key} 가 없다 — 이름이 바뀌었으면 PAIRS 갱신"
    assert dup in tsx, f"컴포넌트에 {dup} 가 없다"
    assert tsx[dup] == sot[sot_key], (
        f"세제 상수 불일치: 컴포넌트 {dup}={tsx[dup]} vs SoT {sot_key}={sot[sot_key]}. "
        f"세제 개정 시 **양쪽 다** 고쳐야 한다 (SoT = api/trading/account_profile.py)"
    )


def test_component_still_declares_sot():
    """SoT 표기가 사라지면 다음 사람이 어디를 고쳐야 할지 모른다."""
    src = TSX.read_text(encoding="utf-8")
    assert "account_profile.py" in src, "세제 SoT 표기가 헤더에서 사라졌다"
