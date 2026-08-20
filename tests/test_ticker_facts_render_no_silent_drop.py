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


def test_us_가격축이_실호출로_존재한다():
    """🚨 PM 지적 2026-08-09 — 조인은 바닥이지 천장이 아니다.

    발행물에 US 가격이 없다고 "us_chart_history 배선이 필요한 신규 과제" 로 보고했던 건
    오판이다. 이 챗의 설계는 발행물로 못 채우는 축을 **그 자리에서 연결 소스 실호출**로
    채우는 것이다(같은 날 JEPQ 분석에서 내가 손으로 야후를 호출해 답을 만들었으면서
    코드에는 "가격 언급 금지" 가드를 넣었다 — 손으로 되는 걸 코드가 못 하게 한 셈).
    """
    q = tf._us_quote("QQQ")
    if not q:
        # 🚨 2026-08-20 — 이 단언이 CI 를 빨갛게 만들고 있었다. 야후는 GitHub 러너 IP 를
        #   막는데(같은 뿌리 = kr_chart_daily 17:23·20:23 슬롯 실패), 로컬 한국 IP 에서는
        #   통과해 **로컬 초록 / CI 빨강** 이 됐다. 그대로 두면 CI 빨강이 신호를 잃는다.
        #   🚨 그렇다고 skip 으로 뭉개면 경로가 진짜 죽어도 모른다 — 두 경우를 가른다:
        #     벤더가 안 닿음  → skip(사유 기록)   ·   닿는데 값이 없음 → 진짜 결함, fail
        #   판별은 `_us_quote` 와 **같은 URL·같은 헤더**로 한 번 더 때려서 한다.
        doc = tf._fetch_json(
            "https://query1.finance.yahoo.com/v8/finance/chart/QQQ?range=1mo&interval=1d",
            None, {"User-Agent": "Mozilla/5.0"},
        )
        if not doc:
            import pytest
            pytest.skip("야후가 이 러너에서 안 닿는다(러너 IP 차단 추정) — 경로 결함과 구분 불가")
        raise AssertionError("US 시세 실호출 경로가 죽었다 — 벤더는 닿는데 값이 안 나온다")
    assert q.get("현재가"), "현재가 축이 비었다"
    assert q.get("통화") == "USD" and q.get("_as_of")
    assert tf._us_quote("005930") is None, "KR 은 KIS·금융위 담당 — 이 경로를 타면 안 된다"


def test_kis_해외_실호출은_실패해도_조인을_막지_않는다():
    """KIS 해외 경로(Railway /us_quotes)는 야후와 2층이다.

    배포 전·장 마감·네트워크 실패 어느 쪽이든 None 을 돌려주고 야후 층이 답을 낸다.
    한 소스가 죽어서 가격 축 전체가 사라지면 안 된다.
    """
    assert tf._us_realtime("005930") is None, "KR 은 KIS 국내 경로가 담당한다"
    assert tf._us_realtime("ZZZZINVALID") is None, "미해석 심볼에서 예외가 새면 안 된다"


def test_가격_부재_문구는_금지가_아니라_실호출_지시다():
    """문구가 '언급 금지' 로 되돌아가면 다음 세션이 그대로 입을 닫는다."""
    src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "api/intelligence/ticker_facts.py"), encoding="utf-8").read()
    i = src.index("가격 축이 하나도 잡히지 않았다")
    guard = src[i:i + 400]
    assert "실호출" in guard, "결손 문구가 실호출 지시를 잃었다"
    assert "언급하지 말 것" not in guard, "금지 문구로 되돌아갔다 — 설계는 '채워라' 다"


def test_로컬파일도_시장_게이팅을_받는다():
    """KR 조회에 us_* 로컬 파일을 파싱하지 않는다 (KR 조회 35s → 12s 로 준 근거)."""
    us_local = [r for r, _, _ in tf.LOCAL_FILES if os.path.basename(r).startswith("us_")]
    assert us_local, "US 로컬 파일이 하나도 배선돼 있지 않다 — 전제가 깨졌다"
