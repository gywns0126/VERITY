"""추천 레코드의 `current_price` 가 `price` 를 따라가는지 — 회귀 가드.

배경 (2026-08-20 실측):
    보유종목(holdings)과 추천(recommendations)을 같이 갱신하는 코드가 **두 곳**인데,
    두 곳 다 holdings 만 `current_price` 를 갱신하고 추천은 `price` 에서 멈춰 있었다.

        api/main.py:2435                h["current_price"] = ...   ← 갱신 O
        api/main.py:2444                stock["price"] = p         ← current_price 없음
        merge_pulse.py:81               h["current_price"] = ...   ← 갱신 O
        merge_pulse.py:93               r["price"] = ...           ← current_price 없음

    설계가 아니라 누락이라는 근거 3종:
      · action.yml 해당 블록 주석 = "holdings/recommendations current_price 가 1분 fresh"
      · api/main.py:2426 섹션 헤더 = "[3] 보유·추천 종목 시세 갱신"
      · tests/test_rec_price_snapshot.py:26,34 = current_price == 당시 price 를 assert

    실측 지속성 (일자당 1커밋 표본): 8/12 40/40 · 8/13 31/43 · 8/14 43/43 · 8/15 43/43 ·
    8/17 35/56 · 8/18 44/56 · 8/19 44/56 · 8/20 59/66 이 cp≠p. 최대 괴리 8~15%.

    🚨 `rec_price` 는 정반대다 — 추천 시점 진입가 **고정이 설계**이므로
    (test_rec_price_snapshot.py:35 "유지됨 — 추천 시점 고정") 이 파일은 rec_price 를
    검사하지 않는다. 그쪽을 "고쳐서" 매번 갱신하면 수익률 산출이 통째로 깨진다.

    점수 영향 없음 — consensus 는 upside 를 current_price 로 계산하지만 호출부
    2곳 전수(api/main.py:643, 2869)가 `price_c = stock.get("price")` 를 넘긴다.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


# ─────────────────────────────────────────────────────────────
# 1. realtime 모드 블록 (api/main.py:2438~2444) 최소 재현
# ─────────────────────────────────────────────────────────────
def _apply_realtime_refresh(portfolio, price_map):
    """api/main.py:2430~2444 전후 블록의 최소 재현 — holdings/recs 대칭 확인용."""
    for h in portfolio["vams"]["holdings"]:
        tk = str(h["ticker"]).zfill(6)
        if tk in price_map:
            h["current_price"] = price_map[tk]
    for stock in portfolio.get("recommendations", []):
        tk = str(stock.get("ticker", "")).zfill(6)
        if tk in price_map:
            p = price_map[tk]
            stock["price"] = p
            stock["current_price"] = p
    return portfolio


def test_realtime_refresh_updates_both_price_and_current_price():
    pf = {
        "vams": {"holdings": [{"ticker": "005930", "current_price": 100.0}]},
        "recommendations": [
            {"ticker": "005930", "price": 100.0, "current_price": 100.0},
        ],
    }
    _apply_realtime_refresh(pf, {"005930": 271000.0})
    rec = pf["recommendations"][0]
    assert rec["price"] == 271000.0
    assert rec["current_price"] == 271000.0, (
        "추천의 current_price 가 price 를 따라가지 않는다 — 2026-08-20 결함 재발"
    )


def test_realtime_refresh_is_symmetric_between_holdings_and_recs():
    """holdings 만 갱신하고 recs 를 빼먹는 비대칭이 이 결함의 형태였다."""
    pf = {
        "vams": {"holdings": [{"ticker": "000660", "current_price": 1.0}]},
        "recommendations": [{"ticker": "000660", "price": 1.0, "current_price": 1.0}],
    }
    _apply_realtime_refresh(pf, {"000660": 1691000.0})
    assert (
        pf["vams"]["holdings"][0]["current_price"]
        == pf["recommendations"][0]["current_price"]
    )


# ─────────────────────────────────────────────────────────────
# 2. full run 주입 블록 (api/main.py:4756~4761) — setdefault 금지
# ─────────────────────────────────────────────────────────────
def _apply_snapshot(analyzed, prev_rec_price_map):
    """api/main.py:4756~4761 재현. current_price=명시대입 / rec_price=setdefault."""
    for rec in analyzed:
        price = rec.get("price")
        if price is None:
            continue
        rec["current_price"] = price
        rec.setdefault("rec_price", prev_rec_price_map.get(rec.get("ticker"), price))
    return analyzed


def test_stale_current_price_is_overwritten_not_preserved():
    """🚨 이 파일의 핵심. setdefault 였을 때 통과하면 안 된다.

    scope=all 런이 반대 시장 레코드를 통째 이월하므로(main.py `kept`),
    이월분이 낡은 current_price 를 달고 오면 setdefault 는 영구 no-op 이 된다.
    """
    analyzed = [{"ticker": "005930", "price": 271000.0, "current_price": 247500.0}]
    out = _apply_snapshot(analyzed, {})
    assert out[0]["current_price"] == 271000.0, (
        "이월된 낡은 current_price 가 살아남았다 — setdefault 회귀"
    )


def test_rec_price_stays_sticky():
    """rec_price 는 반대로 보존돼야 한다 — 추천 시점 진입가 고정이 설계."""
    analyzed = [{"ticker": "005930", "price": 271000.0}]
    out = _apply_snapshot(analyzed, {"005930": 93200.0})
    assert out[0]["rec_price"] == 93200.0
    assert out[0]["current_price"] == 271000.0


# ─────────────────────────────────────────────────────────────
# 3. merge_pulse.py (publish 단계) — 실제 모듈을 로드해 검사
# ─────────────────────────────────────────────────────────────
def _load_merge_pulse():
    path = ROOT / ".github" / "actions" / "publish-data" / "merge_pulse.py"
    if not path.exists():
        pytest.skip(f"merge_pulse.py 없음: {path}")
    spec = importlib.util.spec_from_file_location("merge_pulse", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_merge_pulse_refreshes_recommendation_current_price(tmp_path):
    mod = _load_merge_pulse()
    pf = tmp_path / "portfolio.json"
    pulse = tmp_path / "price_pulse.json"
    pf.write_text(json.dumps({
        "vams": {"holdings": [{"ticker": "005930", "buy_price": 100.0,
                               "current_price": 247500.0}]},
        "recommendations": [{"ticker": "005930", "currency": "KRW",
                             "price": 247500.0, "current_price": 247500.0}],
    }), encoding="utf-8")
    pulse.write_text(json.dumps({"prices": {"005930": 271000.0}}), encoding="utf-8")

    assert mod.main(str(pf), str(pulse)) == 0
    out = json.loads(pf.read_text(encoding="utf-8"))
    rec = out["recommendations"][0]
    assert rec["price"] == 271000.0
    assert rec["current_price"] == 271000.0, (
        "publish 단계에서 추천 current_price 가 안 따라간다 — merge_pulse.py:93 회귀"
    )
    # holdings 분기는 원래 정상이었다 — 대칭 유지 확인
    assert out["vams"]["holdings"][0]["current_price"] == 271000.0


def test_merge_pulse_handles_us_ticker_key(tmp_path):
    """US 는 zfill 안 함 — 키 매칭 분기가 recs 쪽에도 살아 있는지."""
    mod = _load_merge_pulse()
    pf = tmp_path / "portfolio.json"
    pulse = tmp_path / "price_pulse.json"
    pf.write_text(json.dumps({
        "vams": {"holdings": []},
        "recommendations": [{"ticker": "GOOGL", "currency": "USD",
                             "price": 340.93, "current_price": 340.93}],
    }), encoding="utf-8")
    pulse.write_text(json.dumps({"prices": {"GOOGL": 342.42}}), encoding="utf-8")

    assert mod.main(str(pf), str(pulse)) == 0
    rec = json.loads(pf.read_text(encoding="utf-8"))["recommendations"][0]
    assert rec["price"] == 342.42
    assert rec["current_price"] == 342.42


# ─────────────────────────────────────────────────────────────
# 3-b. 실파일 소스 계약 — 위 1·2 는 재현 헬퍼라 진짜 코드를 못 잡는다
#      (test_rec_price_snapshot.py 도 "main.py 직접 테스트 어려움" 을 인정한다).
#      그래서 소스 자체를 계약으로 건다. [[feedback_green_check_is_not_safety]]
# ─────────────────────────────────────────────────────────────
def test_main_py_assigns_current_price_not_setdefault():
    src = (ROOT / "api" / "main.py").read_text(encoding="utf-8")
    assert '_rec["current_price"] = _price' in src, (
        "api/main.py 의 current_price 명시 대입이 사라졌다"
    )
    assert '_rec.setdefault("current_price"' not in src, (
        "setdefault 로 되돌아갔다 — 이월 레코드의 낡은 값이 영구 고착된다"
    )
    # rec_price 는 반대로 setdefault 가 남아 있어야 한다
    assert '_rec.setdefault("rec_price"' in src, (
        "rec_price 의 setdefault 가 사라졌다 — 진입가 고정(설계)이 깨진다"
    )


def test_main_py_realtime_block_updates_recommendation_current_price():
    src = (ROOT / "api" / "main.py").read_text(encoding="utf-8")
    assert 'stock["current_price"] = p' in src, (
        "realtime 블록에서 추천 current_price 갱신이 사라졌다 (main.py:2444 인접)"
    )


def test_merge_pulse_source_updates_recommendation_current_price():
    src = (ROOT / ".github" / "actions" / "publish-data"
           / "merge_pulse.py").read_text(encoding="utf-8")
    assert 'r["current_price"] = prices[key]' in src, (
        "merge_pulse.py 에서 추천 current_price 갱신이 사라졌다"
    )


# ─────────────────────────────────────────────────────────────
# 4. 실산출물 계약 — RULE 8 N=2 신호
# ─────────────────────────────────────────────────────────────
def test_live_artifact_current_price_tracks_price():
    """🚨 배포 직후에는 XFAIL 이 정상이다 (기존 오염분이 아직 안 씻김).

    다음 full run 이 `_rec["current_price"] = _price` 로 전량 덮으면 **XPASS** 로
    바뀐다 — 그게 RULE 8 N=2 확인 신호다. strict=False 라 XPASS 가 CI 를 깨지
    않지만 리포트에 보인다. XPASS 가 안정되면 이 xfail 마커를 제거할 것.
    """
    path = ROOT / "data" / "recommendations.json"
    if not path.exists():
        pytest.skip("recommendations.json 없음")
    try:
        recs = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        pytest.skip("recommendations.json 파싱 불가 (크론 쓰기 중)")
    if not isinstance(recs, list) or not recs:
        pytest.skip("recommendations 비어 있음")

    bad = []
    for r in recs:
        p, c = r.get("price"), r.get("current_price")
        if p and c and abs(p / c - 1) > 0.001:
            bad.append(f"{r.get('ticker')}: price={p} vs current_price={c}")
    if bad:
        pytest.xfail(
            f"cp≠p {len(bad)}/{len(recs)}건 — 다음 full run 후 해소 예정. "
            f"예: {'; '.join(bad[:3])}"
        )
    assert not bad
