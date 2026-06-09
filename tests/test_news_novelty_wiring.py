"""news_headlines novelty wiring (관측 only) — near_duplicate 부착 + 불간섭 검증.

2026-06-10 (2ba73ad0 follow-up, news_impact 3축 Sub-spec 2 인프라 활성).
  - is_duplicate(MinHash 유사도) 사용 — timestamp 무관. novelty_score(시간감쇠)는 batch 단일
    timestamp 에서 degenerate(전부 1.0)라 미사용.
  - 관측 only — near_duplicate 는 데이터 필드, composite_score/정렬/필터 불간섭.
"""
import api.collectors.news_headlines as nh


def _wire(monkeypatch, titles):
    items = [{"title": t, "link": "x", "source": "", "time": "", "category": "market"}
             for t in titles]
    monkeypatch.setattr(nh, "_naver_market_news", lambda: items)
    monkeypatch.setattr(nh, "_naver_economy_news", lambda: [])
    return nh.collect_headlines(max_items=20)


def test_near_duplicate_attached_and_discriminates(monkeypatch):
    out = _wire(monkeypatch, [
        "삼성전자 4분기 어닝 서프라이즈 영업이익 급증 코스피 상승",
        "삼성전자 4분기 어닝 서프라이즈 영업이익 급증 코스피 상승세",  # near-dup
        "엔비디아 AI 반도체 신제품 발표 나스닥 사상 최고",            # 신규
    ])
    assert all("near_duplicate" in it for it in out)
    flags = [it["near_duplicate"] for it in out]
    # 변별력 — 전부 같은 값이면 무용
    assert any(flags) and not all(flags)


def test_near_duplicate_does_not_affect_composite(monkeypatch):
    # near_duplicate 가 composite_score 계산에 들어가지 않음 (관측 only, decision 불간섭)
    out = _wire(monkeypatch, ["코스피 외국인 순매수 환율 하락 반도체 강세 기관 매수"])
    it = out[0]
    expected = (
        it["credibility"] * 0.4
        + it["urgency"] * 0.3
        + (1.0 if it["sentiment"] != "neutral" else 0.3) * 0.3
    )
    assert abs(it["composite_score"] - expected) < 1e-9
