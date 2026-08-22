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


# ── 계산 전제 명시 (2026-08-22) ──────────────────────────────
def test_tax_tab_states_full_liquidation_assumption():
    """🚨 usGainSum 은 보유 전 종목 손익의 **단순 합**이다.

    실제 해외 양도세는 그 해에 **실현한 것만** 통산한다. 일부만 팔면 미실현 손실이
    차감되지 않아 실제 세금이 더 크다 — 즉 이 화면은 **낙관 쪽으로 치우친다**.
    계산을 바꾸는 대신 전제를 명시했다. 그 문구가 사라지면 숫자가 사실로 읽힌다.
    """
    s = TSX.read_text(encoding="utf-8")
    flat = re.sub(r"\s+", " ", s)
    assert "<b>전량 매도</b> 가정" in flat, "헤더의 전량 매도 전제 표기가 사라졌다"
    assert "일부만 팔면 손실 종목이 차감되지 않아" in flat, (
        "손익통산 전제 설명이 사라졌다 — 세금이 실제보다 적게 보인다"
    )


def test_us_tax_math_is_progressive_with_deduction():
    """공제·누진 구조가 유지되는지 — 상수만 맞고 식이 틀리면 가드가 무의미하다."""
    s = TSX.read_text(encoding="utf-8")
    flat = re.sub(r"\s+", " ", s)
    assert "Math.max(0, usGainSum - TAX.US_DEDUCT)" in flat, "기본공제 차감이 사라졌다"
    assert "TAX.US_BRACKET * TAX.US_CGT" in flat, "3억 분기점 누진 계산이 사라졌다"
    assert "usTaxable <= TAX.US_BRACKET" in flat, "분기 조건이 사라졌다"


# ── 외부 사실 고정 (2026-08-22 신설) ──────────────────────────────────────────
# 🚨 위 동기 테스트는 **SoT 와 복제본이 같은가**만 잰다. SoT 자체가 맞는지는 안 잰다.
#    그 구멍이 실제로 열려 있었다 — 6개 상수가 완벽히 동기화된 채로
#    `KR_MAJOR_SHAREHOLDER_AMOUNT` 만 **10억(틀림)** 이었다. 근거는 "2025-12 환원 통과"
#    였는데 실제로는 **채택되지 않았다**(기재부 보도자료 제목이 "현행 기준 유지").
#    동기화는 정합의 필요조건이지 충분조건이 아니다.
#
# 그래서 외부 확정 값은 **출처·확인일과 함께 못 박는다.** 값을 바꾸려면 이 테스트가 먼저
# 깨지고, 고치려면 출처를 새로 적어야 한다 — 조용한 드리프트가 불가능해진다.
EXTERNAL_PINS = {
    # 상수명: (값, 확인일, 출처)
    "KR_MAJOR_SHAREHOLDER_AMOUNT": (
        5_000_000_000, "2026-08-22",
        "기재부 보도자료 '대주주 범위 현행 기준 유지' · 정책브리핑 '종목당 50억원 유지' "
        "· 국회예산정책처 2025 개정세법 심의결과 · KDI (4출처 교차)"),
    "US_CAPITAL_GAINS_TAX": (0.22, "2026-06-19", "해외주식 양도세 과표 3억 이하 20%+지방세 2%"),
    "US_CAPITAL_GAINS_TAX_HIGH": (0.275, "2026-06-19", "과표 3억 초과 25%+지방세 2.5%"),
    "US_CAPITAL_GAINS_DEDUCTION": (2_500_000, "2026-06-19", "해외 양도소득 기본공제 연 250만"),
}


def test_external_pins_match_sot():
    """🚨 SoT 값이 **외부 확정 사실**과 일치하는가 — 동기화와 별개 축."""
    import importlib
    mod = importlib.import_module("api.trading.account_profile")
    bad = []
    for name, (want, asof, src) in EXTERNAL_PINS.items():
        got = getattr(mod, name, None)
        if got != want:
            bad.append(f"{name}: SoT={got} vs 확정={want} (확인 {asof} · {src})")
    assert not bad, (
        "세제 상수가 외부 확정 사실과 어긋난다. 🚨 동기 테스트는 이걸 못 잡는다 "
        "— 복제본까지 같이 틀리면 '일치' 로 초록이 뜬다.\n  " + "\n  ".join(bad))


def test_every_pin_carries_source_and_date():
    """출처·확인일 없는 pin 금지 — 근거 없는 숫자는 다음 세션이 못 검증한다."""
    for name, (val, asof, src) in EXTERNAL_PINS.items():
        assert val is not None, name
        assert len(asof) == 10 and asof[4] == "-", f"{name} 확인일 형식"
        assert len(src) >= 15, f"{name} 출처가 너무 짧다"


def test_major_shareholder_is_not_the_retracted_1b():
    """🚨 10억으로 되돌아가는 것을 명시적으로 막는다.

    10억 환원안은 2025-07-31 세제개편안 **발표 단계에 그쳤고** 시행령 개정이 공포된 적이 없다.
    다만 이건 국회 법률이 아니라 기재부 소관 시행령(소득세법 §157④)이라 **정부가 바꾸면 바뀐다** —
    그때는 이 테스트를 출처와 함께 갱신하는 것이 정당한 경로다. 조용히 값만 바꾸는 것은 아니다.
    """
    import importlib
    mod = importlib.import_module("api.trading.account_profile")
    assert mod.KR_MAJOR_SHAREHOLDER_AMOUNT != 1_000_000_000, (
        "대주주 기준이 10억으로 되돌아갔다. 실제 시행령이 개정됐다면 EXTERNAL_PINS 의 "
        "값·확인일·출처를 함께 갱신할 것. 근거 없이 바뀐 것이면 회귀다.")
