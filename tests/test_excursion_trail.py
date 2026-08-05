# -*- coding: utf-8 -*-
"""청산 episode MAE/MFE 상시 계측 (2026-08-06).

배경: 2026-08-05 집행 감사에서 KR 청산 12건의 MAE/MFE 를 손으로 계산해 사슬을 규명했다
(MFE +5.8% / MAE −9.6% / 손절 −5% = 노이즈 안). 그 계산이 일회성이라 표본이 안 쌓였고,
손절·익절 임계 재등록의 판정 근거가 전부 이 지표에서 나온다. → 매 청산마다 자동 기록.

계약: ① 점수·집행 입력 0(관측 전용) ② 진입가는 청산 직전 BUY ③ MAE/MFE 는 보유 구간
일봉 고저 기준 ④ N<30 "통계 무의미" 라벨 의무 ⑤ 봉 부족·데이터 결손 = 조용히 제외(오염 금지).
"""
import json

import api.observability.excursion_trail as EX


def _bars(rows):
    """[(yyyymmdd, high, low)] → 일봉 형식 [d,o,h,l,c,v]."""
    return [[d, 0, h, lo, 0, 0] for d, h, lo in rows]


def _iso(monkeypatch, tmp_path):
    monkeypatch.setattr(EX, "TRAIL_PATH", str(tmp_path / "t.jsonl"))
    monkeypatch.setattr(EX, "SUMMARY_PATH", str(tmp_path / "s.json"))
    monkeypatch.setattr(EX, "DATA_DIR", str(tmp_path))


# ── 산출 정의 ────────────────────────────────────────────────────────

def test_excursion_math():
    """진입 10,000 · 구간 고가 11,000 · 저가 9,000 → MFE +10% · MAE −10%."""
    b = _bars([(20260601, 10_500, 9_800), (20260602, 11_000, 9_000)])
    r = EX._excursion(b, "2026-06-01", "2026-06-02", 10_000)
    assert r["mfe_pct"] == 10.0 and r["mae_pct"] == -10.0 and r["bars"] == 2


def test_excursion_needs_two_bars():
    b = _bars([(20260601, 11_000, 9_000)])
    assert EX._excursion(b, "2026-06-01", "2026-06-01", 10_000) is None


def test_excursion_window_is_inclusive_and_bounded():
    """구간 밖 봉은 무시 — 청산 이후 급등이 MFE 를 오염시키면 안 된다."""
    b = _bars([(20260601, 10_100, 9_900), (20260602, 10_200, 9_800),
               (20260610, 99_000, 100)])          # 청산 후
    r = EX._excursion(b, "2026-06-01", "2026-06-02", 10_000)
    assert r["mfe_pct"] == 2.0 and r["mae_pct"] == -2.0


# ── 진입 매칭 ────────────────────────────────────────────────────────

def test_entry_picks_latest_buy_before_exit():
    hist = [
        {"type": "BUY", "ticker": "A", "date": "2026-05-01", "price": 8_000},
        {"type": "BUY", "ticker": "A", "date": "2026-06-01", "price": 10_000},
        {"type": "BUY", "ticker": "A", "date": "2026-07-01", "price": 12_000},   # 청산 이후
    ]
    assert EX._entry_of(hist, "A", "2026-06-15") == ("2026-06-01", 10_000.0)


def test_entry_none_when_no_prior_buy():
    hist = [{"type": "BUY", "ticker": "A", "date": "2026-07-01", "price": 1}]
    assert EX._entry_of(hist, "A", "2026-06-01") is None


# ── 종합 ────────────────────────────────────────────────────────────

def _wire(monkeypatch, tmp_path, hist, bars):
    _iso(monkeypatch, tmp_path)
    monkeypatch.setattr("api.vams.engine.load_history", lambda: hist)
    monkeypatch.setattr(EX, "_load_bars", lambda: bars)


def test_build_records_episode_and_labels_small_n(monkeypatch, tmp_path):
    hist = [{"type": "BUY", "ticker": "000001", "date": "2026-06-01", "quantity": 10,
             "price": 10_000},
            {"type": "SELL", "ticker": "000001", "date": "2026-06-05", "pnl": -5_000}]
    bars = {"000001": _bars([(20260601, 10_600, 9_500), (20260605, 10_200, 9_100)])}
    _wire(monkeypatch, tmp_path, hist, bars)
    s = EX.build(since=None)
    assert s["n_episodes"] == 1
    assert s["mfe"]["mean"] == 6.0 and s["mae"]["mean"] == -9.0
    assert any("통계 무의미" in x for x in s["labels"])
    assert s["brain_input"] is False
    rows = [json.loads(l) for l in open(EX.TRAIL_PATH, encoding="utf-8")]
    assert rows[0]["ticker"] == "000001" and rows[0]["hold_bars"] == 2


def test_build_flags_mae_exceeding_mfe(monkeypatch, tmp_path):
    """진입 후 하락이 상승보다 크면 진입 축 점검 라벨 — 2026-08-05 실측 패턴."""
    hist = [{"type": "BUY", "ticker": "000001", "date": "2026-06-01", "quantity": 10,
             "price": 10_000},
            {"type": "SELL", "ticker": "000001", "date": "2026-06-05", "pnl": -5_000}]
    bars = {"000001": _bars([(20260601, 10_100, 9_000), (20260605, 10_100, 9_000)])}
    _wire(monkeypatch, tmp_path, hist, bars)
    s = EX.build(since=None)
    assert any("MAE 평균이 MFE 평균보다" in x for x in s["labels"])


def test_build_skips_us_and_missing_bars(monkeypatch, tmp_path):
    """US(비6자리)·일봉 결손은 조용히 제외 — 오염된 값을 넣지 않는다."""
    hist = [{"type": "BUY", "ticker": "AAPL", "date": "2026-06-01", "quantity": 1, "price": 100},
            {"type": "SELL", "ticker": "AAPL", "date": "2026-06-05", "pnl": 10},
            {"type": "BUY", "ticker": "999999", "date": "2026-06-01", "quantity": 1, "price": 100},
            {"type": "SELL", "ticker": "999999", "date": "2026-06-05", "pnl": -10}]
    _wire(monkeypatch, tmp_path, hist, {})       # 일봉 없음
    assert EX.build(since=None)["n_episodes"] == 0


def test_build_is_idempotent(monkeypatch, tmp_path):
    """매 run 전수 재계산 — 두 번 돌려도 행이 늘지 않는다."""
    hist = [{"type": "BUY", "ticker": "000001", "date": "2026-06-01", "quantity": 10,
             "price": 10_000},
            {"type": "SELL", "ticker": "000001", "date": "2026-06-05", "pnl": -5_000}]
    bars = {"000001": _bars([(20260601, 10_600, 9_500), (20260605, 10_200, 9_100)])}
    _wire(monkeypatch, tmp_path, hist, bars)
    EX.build(since=None)
    EX.build(since=None)
    assert sum(1 for _ in open(EX.TRAIL_PATH, encoding="utf-8")) == 1


def test_phantom_sells_excluded_via_ledger(monkeypatch, tmp_path):
    """보유 0 매도(유령)는 trade_ledger 가 걸러 episode 가 되지 않는다."""
    hist = [{"type": "BUY", "ticker": "000001", "date": "2026-06-01", "quantity": 10,
             "price": 10_000},
            {"type": "SELL", "ticker": "000001", "date": "2026-06-05", "pnl": -5_000},
            {"type": "SELL", "ticker": "000001", "date": "2026-06-06", "pnl": -9_999}]  # 유령
    # 봉은 청산일(06-05)까지 덮어야 한다 — 구간 밖 봉만 있으면 산출 불가로 제외된다
    bars = {"000001": _bars([(20260601, 10_600, 9_500), (20260605, 10_200, 9_100)])}
    _wire(monkeypatch, tmp_path, hist, bars)
    assert EX.build(since=None)["n_episodes"] == 1
