# -*- coding: utf-8 -*-
"""대주주 판정 2경로 계약 — 2026-08-22 신설.

## 왜

세금 탭의 대주주 판정을 오늘 두 번 고쳤다. 그 규칙이 TSX 안에만 있으면 다음 세션이
소리 없이 되돌린다 — 여기서 **규칙 자체를 못 박는다**(TSX 는 이 규칙의 구현체다).

소득세법 시행령 §157 이 정한 경로가 **둘**이다:

  ① 기준일 판정 (§157⑥)
     직전 사업연도 종료일 종가 × 보유수 ≥ 기준금액
     "없으면 직전거래일" 단서 — 2025-12-31 은 연말 폐장이라 실제로 12-30 을 쓴다.

  ② 연중 취득 (§157④ 단서)
     "직전 사업연도 종료일에 미달했더라도 그 후 취득으로 기준을 충족하게 되면
      **그 취득일 이후부터** 대주주로 본다"
     → 취득 평가액(평단 × 보유수)으로 판정.

🚨 ②는 **신규 상장 전용이 아니다.** 기준일에 미달했다가 연중 매수로 넘어선 보유도 포함이다.
   ①만 구현하면 그 구간이 통째로 빠진다 — 실제로 종전 코드가 ①조차 없이 **현재가**로 쟀다.

🚨 한계를 숨기지 않는다: 우리는 **현재 보유수**만 갖고 있어 ①이 근사다(기준일 보유수 미상).
   화면에 그 사실을 적는다. 숨기면 정확한 판정으로 오독된다.
"""
from __future__ import annotations

import os
import re

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TAB = os.path.join(_ROOT, "framer-components", "public-probe", "PublicHoldingsTab.tsx")
THRESHOLD = 5_000_000_000


def judge(shares: float, basis_px: float, avg_cost: float, limit: int = THRESHOLD) -> str:
    """TSX `majorPath` 와 동일 규칙의 참조 구현. 둘이 어긋나면 아래 테스트가 잡는다."""
    if shares <= 0:
        return ""
    if basis_px > 0 and shares * basis_px >= limit:
        return "basis"
    if avg_cost > 0 and shares * avg_cost >= limit:
        return "acq"
    return ""


class TestBasisPath:
    def test_meets_by_basis_price(self):
        assert judge(50_000, 120_000, 90_000) == "basis"   # 60억

    def test_below_basis_and_below_cost_is_not_major(self):
        assert judge(1_000, 120_000, 100_000) == ""        # 1.2억

    def test_current_price_is_irrelevant(self):
        """🚨 현재가는 판정에 들어가지 않는다 — 그게 원래 결함이었다.

        기준가 12만·평단 10만인 4만주(=48억, 미달)는 현재가가 27만(=108억)이어도 대주주가 아니다.
        """
        assert judge(40_000, 120_000, 100_000) == ""


class TestAcquisitionPath:
    def test_new_listing_judged_by_cost(self):
        """2026 상장 = 기준가 없음. ②로 판정한다(보류 아님)."""
        assert judge(100_000, 0, 60_000) == "acq"          # 60억

    def test_year_end_short_but_bought_more_during_year(self):
        """🚨 ②의 본체 — 기준일 미달인데 연중 취득으로 넘어선 경우.

        기준가 5만 × 8만주 = 40억(미달)인데 평단 7만 × 8만주 = 56억(충족).
        ①만 보면 이 보유가 통째로 빠진다.
        """
        assert judge(80_000, 50_000, 70_000) == "acq"

    def test_basis_wins_when_both_qualify(self):
        """둘 다 충족이면 ①로 표기 — 더 이른 시점 기준이 우선이다."""
        assert judge(100_000, 60_000, 70_000) == "basis"


class TestUnjudgeable:
    def test_no_basis_no_cost_is_deferred(self):
        """🚨 판정 불가는 '대주주 아님' 이 아니라 **보류**다. 화면에 신고해야 한다."""
        assert judge(100_000, 0, 0) == ""

    def test_zero_shares(self):
        assert judge(0, 120_000, 100_000) == ""


class TestTsxImplementationMatchesRule:
    """TSX 구현이 위 규칙과 같은 형태인지 — 구조를 고정한다(값 비교는 위에서 했다)."""

    @pytest.fixture
    def src(self):
        return open(TAB, encoding="utf-8").read()

    def test_uses_basis_price_not_val(self, src):
        m = re.search(r"const majorPath[\s\S]{0,700}?\n    \}", src)
        assert m, "majorPath 가 없다 — 판정 로직이 사라졌거나 이름이 바뀌었다"
        body = m.group(0)
        assert "basisPx" in body, "기준가를 안 쓴다"
        assert "avg_cost" in body, "연중 취득 경로가 없다"
        assert "_val" not in body, "🚨 현재가(_val)로 판정하고 있다 — 되돌아간 것이다"

    def test_threshold_comes_from_tax_const(self, src):
        m = re.search(r"const majorPath[\s\S]{0,700}?\n    \}", src)
        assert "TAX.KR_MAJOR_AMT" in m.group(0), "임계를 하드코딩하면 SoT 동기가 깨진다"

    def test_deferred_count_is_surfaced(self, src):
        assert "krMajorUnknown" in src and "판정 보류" in src, \
            "🚨 판정 불가 종목을 화면에 신고하지 않으면 '대주주 아님' 으로 오독된다"

    def test_approximation_is_disclosed(self, src):
        assert "현재 보유수로 근사" in src, \
            "🚨 기준일 보유수 미상이라는 한계를 화면에 적어야 한다"
