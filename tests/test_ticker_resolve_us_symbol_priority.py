"""US 심볼이 KR 부분일치에 가로채이지 않는지 (2026-08-23 사고).

종전 resolve_ticker 는 KR 이름 매칭(정확>접두>부분)을 US 심볼 패스스루보다 **앞**에 두어
심볼 모양 질의가 조용히 엉뚱한 KR 종목으로 끌려갔다. 실측 US 심볼 10,373 중 252건(2.43%):
  AMG → SAMG엔터 · V → NAVER · KO → KODEX 200 · GE → TIGER 200 · CMG → CMG제약
조인이 그 KR 종목 사실로 가득 차 돌아와 **틀린 것을 알아챌 신호가 0** 이었다.

🚨 이 파일은 **순서 로직만** 검사한다. 종전 판본은 실데이터(원격 유니버스)에 의존해
단독 실행은 통과하고 전체 스위트에서는 실패했다 — 초록이 안전이 아니었다
([[feedback_green_check_is_not_safety]]). 그래서 소스를 고정 픽스처로 갈아끼운다.
"""
import pytest

from api.intelligence import ticker_facts

KR_NAMES = {"419530": "SAMG엔터", "058820": "CMG제약", "035420": "NAVER", "005930": "삼성전자"}
KR_ROWS = [{"ticker": k, "name": v} for k, v in KR_NAMES.items()]
US_ROWS = [
    {"ticker": "AMG", "name": "Affiliated Managers Group, Inc."},
    {"ticker": "V", "name": "Visa Inc."},
    {"ticker": "KO", "name": "Coca Cola Co"},
    {"ticker": "CMG", "name": "Chipotle Mexican Grill, Inc."},
]


@pytest.fixture(autouse=True)
def _fixed_universe(monkeypatch):
    def fake_fetch(url, cache_key=None, headers=None):
        if cache_key == "kr_stock_names":
            return dict(KR_NAMES)
        if cache_key == "universe_kr":
            return {"stocks": list(KR_ROWS)}
        if cache_key == "universe_all":
            return {"stocks": list(US_ROWS)}
        return None
    monkeypatch.setattr(ticker_facts, "_fetch_json", fake_fetch)
    monkeypatch.setattr(ticker_facts, "_us_display_name", lambda u: "")


@pytest.mark.parametrize("q", ["AMG", "V", "KO", "CMG"])
def test_us_symbol_not_hijacked_by_kr_partial(q):
    tk, _ = ticker_facts.resolve_ticker(q)
    assert tk == q, f"{q} 가 KR 종목 {tk} 로 끌려갔다 (US 심볼 패스스루 순서 회귀)"


@pytest.mark.parametrize("q,expect", [
    ("CMG제약", "058820"),      # KR 이름 정확일치는 US 심볼보다 우선
    ("SAMG엔터", "419530"),
    ("NAVER", "035420"),        # ASCII 지만 KR 정확일치
    ("삼성전자", "005930"),
    ("419530", "419530"),       # 6자리 코드 패스스루
])
def test_kr_exact_still_wins(q, expect):
    tk, _ = ticker_facts.resolve_ticker(q)
    assert tk == expect, f"{q} → {tk} (기대 {expect}) — KR 정확일치 경로 회귀"


def test_unknown_symbol_still_passes_through_last():
    """🚨 유니버스에 없는 심볼의 패스스루는 **의도된 폴백**이다 — 되돌리지 말 것.

    신규 상장 종목(예: 상장 직후 SPCX)은 우리 유니버스 스냅샷에 아직 없다. 여기서 죽으면
    전 섹션 조인 0 이 된다. 순서 = KR 정확일치 → US 심볼(유니버스 실재) → KR 접두 →
    KR 부분 → US 이름 → **US 심볼 무조건**. 앞쪽 US 분기는 실재를 요구해 가로채기만 막고,
    맨 뒤 폴백이 신규 상장을 살린다.
    """
    tk, _ = ticker_facts.resolve_ticker("ZZZZQ")
    assert tk == "ZZZZQ", "신규 상장 대비 최종 패스스루가 사라졌다"


def test_early_us_branch_requires_existence():
    """앞쪽 US 분기가 실재를 확인하는지 — 확인을 빼면 KR 접두 질의가 전부 US 로 샌다."""
    assert ticker_facts._is_known_us_symbol("AMG") is True
    assert ticker_facts._is_known_us_symbol("ZZZZQ") is False
