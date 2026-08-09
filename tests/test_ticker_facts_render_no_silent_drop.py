# -*- coding: utf-8 -*-
"""렌더가 사실을 조용히 버리지 않는다는 계약 (2026-08-09 JEPQ 사고 회귀 방지).

사고 경위:
  PM 이 JEPQ(미국 커버드콜 ETF) 분석을 요청했는데 조인이 `섹션 0개` 를 냈다. 원인이 두 겹이었다.

  ① 배선 누락 — `us_etf.json` 이 SCAN_FILES 에 없어 682 종의 ETF 사실을 한 건도 안 봤다.
  ② 🚨 렌더 누락 — ①을 고치자 섹션은 떴는데 **구성종목·섹터·자산배분·배당률·3년수익률이
     전부 사라진 채** 출력됐다. 단일 레코드가 리스트로 감싸여 오다 보니 시계열 행 포맷
     (스칼라 앞 8개)에 걸려 중첩 필드가 통째로 버려졌고, 버렸다는 표시조차 없었다.

  ②가 더 위험하다. ①은 "섹션 0" 이라 눈에 띄지만 ②는 **멀쩡한 섹션으로 보인다**. 조인은
  성공했는데 출력에서 잃는 형태라 소비자(사람·LLM)는 "우리 데이터엔 이것뿐" 이라고 믿는다.
  없는 것보다 나쁘다 — [[feedback_silent_total_failure_guard]] 와 같은 계열.

지키는 선:
  · 단일 레코드는 시계열이 아니다 — 접지 말고 펼친다
  · 잘라낸 것은 반드시 신고한다 (미표시 N: 키 이름)
  · 가격 축이 하나도 안 잡히면 침묵하지 않는다 (가격 환각 차단이 이 레이어의 존재 이유)
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.intelligence import ticker_facts as tf  # noqa: E402

# 사고 당시 JEPQ 레코드의 실제 모양 (us_etf.json etfs[] 에서 1건 매칭 → 길이 1 리스트로 전달됨)
JEPQ_REC = {
    "ticker": "JEPQ", "name": "JPMorgan Nasdaq Equity Premium ",
    "category": "Derivative Income", "aum_usd": 40656678912, "family": "JPMorgan",
    "expense": 0.35, "legal_type": "Exchange Traded Fund", "inception": "2022-05-03",
    "returns": {"ytd": 10.84, "y3": 17.48},
    "yield_pct": 9.95, "beta3y": 0.78,
    "assets": {"stock": 82.74, "cash": 0.89, "convertible": 16.37},
    "sectors": {"technology": 60.61, "communication_services": 12.78},
    "top_holdings": [{"t": "NVDA", "n": "NVIDIA Corp", "w": 6.62},
                     {"t": "AAPL", "n": "Apple Inc", "w": 5.77}],
    "as_of": "2026-08-04T15:53:11+09:00",
}


def test_단일레코드_리스트는_중첩필드를_잃지_않는다():
    """사고 재현 케이스 — 이 테스트가 있었으면 JEPQ 가 조용히 비지 않았다."""
    text = "\n".join(tf._fmt_data([JEPQ_REC]))
    # 앞 8개 스칼라 뒤로 밀려 사라졌던 것들
    for missing_before in ("yield_pct", "beta3y", "top_holdings", "sectors", "assets", "returns"):
        assert missing_before in text, f"{missing_before} 가 렌더에서 사라졌다"
    # 중첩 안쪽 실제 값까지 도달하는가
    assert "NVDA" in text and "6.62" in text, "구성종목 비중이 렌더에 없다"
    assert "60.61" in text, "섹터 비중이 렌더에 없다"


def test_레코드_나이가_렌더에_남는다():
    """회전 수집기라 파일 mtime ≠ 레코드 기준일. as_of 를 잃으면 5일 전 구성을 현재로 읽는다."""
    assert "2026-08-04" in "\n".join(tf._fmt_data([JEPQ_REC]))


def test_다행_리스트는_잘라낸_키를_신고한다():
    """행 포맷을 유지하되 버린 것을 숨기지 않는다."""
    rows = [{f"k{i}": i for i in range(12)} | {"nested": {"a": 1}} for _ in range(2)]
    text = "\n".join(tf._fmt_data(rows, depth=1))
    assert "미표시" in text, "8개 초과 스칼라와 중첩 필드를 신고 없이 버렸다"
    assert "nested" in text, "버린 키 이름을 알려주지 않는다"


def test_긴_dict_도_잘라낸_키를_신고한다():
    text = "\n".join(tf._fmt_data({f"k{i}": i for i in range(26)}))
    assert "미표시 키" in text


def test_us_etf_가_조인_대상이다():
    """배선 회귀 방지 — 이 한 줄이 빠져 US ETF 전체가 조인 0 이었다."""
    assert "us_etf.json" in tf.SCAN_FILES


def test_etf_이름이_해석된다():
    """'JEPQ (JEPQ)' 로 나오던 갭. us_etf_universe.names 에 정식명이 이미 있었다."""
    name = tf._us_display_name("JEPQ")
    assert name and name != "JEPQ", "ETF 정식명 해석 실패"


def test_로컬파일도_시장_게이팅을_받는다():
    """KR 조회에 us_* 로컬 파일을 파싱하지 않는다 (KR 조회 35s → 12s 로 준 근거)."""
    us_local = [r for r, _, _ in tf.LOCAL_FILES if os.path.basename(r).startswith("us_")]
    assert us_local, "US 로컬 파일이 하나도 배선돼 있지 않다 — 전제가 깨졌다"
