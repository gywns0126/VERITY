"""2Q 연속가속 보강 배선 검증 (PM 승인 2026-08-19 "2Q 보강 배선").

설계돼 있었으나 **입력을 만드는 곳이 없어** watch 448/448 전량 미작동이던 보강을 살린다.
여기서 지키는 계약 3가지:
  ① 같은 회계분기를 연도만 바꿔 뽑는다 (계절성·DART 누적공시 두 함정 동시 회피)
  ② 3점 미만은 판정하지 않는다 (성장률 2개가 안 나오면 '가속' 을 말할 수 없다)
  ③ 붙였는지 아닌지를 **센다** — 안 세면 또 조용히 죽는다
"""
import json

import pytest

from api.analyzers.multi_bagger_signals import detect_revenue_acceleration
from api.utils import quarterly_revenue as QR


def _write(tmp_path, rows):
    p = tmp_path / "snap.jsonl"
    with open(p, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return str(p)


def _row(tk, qe, rc, rev):
    return {"ticker": tk, "quarter_end": qe, "reprt_code": rc, "revenue": rev}


def test_series_is_same_quarter_across_years_descending(tmp_path):
    """🚨 계절성·누적 함정 회피의 핵심 — 인접 항목은 '이웃 분기' 가 아니라 '작년 같은 분기'."""
    path = _write(tmp_path, [
        _row("000001", "2024-06-30", "11012", 100.0),
        _row("000001", "2025-06-30", "11012", 120.0),
        _row("000001", "2026-06-30", "11012", 160.0),
    ])
    series, meta = QR.build_series(path)
    assert series["000001"] == [160.0, 120.0, 100.0]      # 최신 → 과거
    assert meta["basis"] == "same_reprt_code_year_over_year"
    assert meta["tickers_usable"] == 1


def test_mixed_quarters_use_only_the_latest_quarter_code(tmp_path):
    """분기를 섞으면 계절성이 되돌아온다 — 최신 분기의 reprt_code 하나만 쓴다."""
    path = _write(tmp_path, [
        # 상반기 계열 (최신 = 2026-06-30)
        _row("000002", "2024-06-30", "11012", 50.0),
        _row("000002", "2025-06-30", "11012", 60.0),
        _row("000002", "2026-06-30", "11012", 90.0),
        # 1분기 계열 (더 오래됨) — 섞이면 안 된다
        _row("000002", "2024-03-31", "11013", 10.0),
        _row("000002", "2025-03-31", "11013", 11.0),
        _row("000002", "2026-03-31", "11013", 12.0),
    ])
    series, _ = QR.build_series(path)
    assert series["000002"] == [90.0, 60.0, 50.0], "분기가 섞였다"


def test_fewer_than_three_points_is_not_a_judgement(tmp_path):
    path = _write(tmp_path, [
        _row("000003", "2025-06-30", "11012", 100.0),
        _row("000003", "2026-06-30", "11012", 130.0),
    ])
    series, meta = QR.build_series(path)
    assert "000003" not in series
    assert meta["tickers_usable"] == 0


def test_missing_or_zero_revenue_rows_are_dropped(tmp_path):
    """0 은 성장률 분모가 될 수 없다. 결측과 0 을 둘 다 뺀다."""
    path = _write(tmp_path, [
        _row("000004", "2024-06-30", "11012", 0.0),
        {"ticker": "000004", "quarter_end": "2025-06-30", "reprt_code": "11012"},
        _row("000004", "2026-06-30", "11012", 100.0),
    ])
    series, meta = QR.build_series(path)
    assert "000004" not in series
    assert meta["rows_with_revenue"] == 1


def test_attach_reports_coverage(tmp_path):
    """🚨 커버리지 반환이 계약이다 — 448/448 죽은 걸 아무도 몰랐던 이유가 미계수였다."""
    path = _write(tmp_path, [
        _row("000005", "2024-06-30", "11012", 100.0),
        _row("000005", "2025-06-30", "11012", 110.0),
        _row("000005", "2026-06-30", "11012", 140.0),
    ])
    stocks = {"000005": {"ticker": "000005"}, "000006": {"ticker": "000006"}}
    meta = QR.attach(stocks, path)
    assert stocks["000005"]["dart_financials"]["quarterly_revenue"] == [140.0, 110.0, 100.0]
    assert "dart_financials" not in stocks["000006"]
    assert meta["attached"] == 1 and meta["attach_target"] == 2
    assert meta["attach_pct"] == 50.0


def test_signal_actually_wakes_up_with_the_series():
    """배선의 목적 — consecutive_acceleration 이 None 을 벗어나야 한다.

    🚨 rev_growth=16% 를 쓴다. 30% 로는 **통과하지 않는다** — 아래 포화 계약이 그 이유다.
    """
    dead = detect_revenue_acceleration({"revenue_growth": 16.0})
    assert dead["consecutive_acceleration"] is None      # 배선 전 상태 (448/448)

    fast = detect_revenue_acceleration({      # YoY 10% → 27.3% 가속
        "revenue_growth": 16.0,
        "dart_financials": {"quarterly_revenue": [140.0, 110.0, 100.0]},
    })
    assert fast["consecutive_acceleration"] is True
    assert fast["score"] > dead["score"], "가속 가산(+10)이 반영되지 않았다"

    slow = detect_revenue_acceleration({      # YoY 40% → 7.1% 감속 = 스파이크 의심
        "revenue_growth": 16.0,
        "dart_financials": {"quarterly_revenue": [150.0, 140.0, 100.0]},
    })
    assert slow["consecutive_acceleration"] is False
    assert slow["score"] < dead["score"], "감속 감점(−5)이 반영되지 않았다"


def test_score_saturation_limits_where_the_reinforcement_can_move_score():
    """🚨 배선해도 **점수는 대부분 안 움직인다** — 상한 100 포화 때문이다.

    score = min(100, 50 + rev_growth*2 + boost) 라 rev_growth ≥ 25% 면 boost 없이도 100.
    실측(2026-08-18 watch 448종목): ≥25% 가 **59.8%**, ≥20%(+10 가산이 상한에 먹히는
    구간)가 **69.9%** → +10 이 점수에 실제 반영되는 건 **30.1%** 뿐이다.

    즉 배선의 산출은 '점수 이동' 이 아니라 **`consecutive_acceleration` 플래그 자체**다
    (기저효과 의심 종목을 식별 가능하게 만든다). 상한·기울기 조정은 산식 변경이라 별건.
    이 성질을 문서가 아니라 **계약으로** 고정한다 — "왜 점수가 안 움직이지" 를 다시 파지 않도록.
    """
    high = {"revenue_growth": 30.0}
    assert detect_revenue_acceleration(high)["score"] == 100
    boosted = detect_revenue_acceleration(
        {**high, "dart_financials": {"quarterly_revenue": [140.0, 110.0, 100.0]}})
    assert boosted["consecutive_acceleration"] is True
    assert boosted["score"] == 100, "포화 성질이 바뀌었다 — 산식 변경 여부를 확인할 것"


def test_snapshot_writer_persists_revenue():
    """🚨 상류가 revenue 를 안 실으면 위 전부가 무의미하다 — 소스로 확인한다.

    이게 정확히 8/19 이전 상태였다: 수집기는 매출을 파싱해 asset_turnover=rev/ta 까지
    쓰고도 스냅샷에 안 실었고, 그래서 보강이 448/448 죽어 있었다.
    """
    import inspect

    from api.builders import dart_batch_builder as B
    src = inspect.getsource(B._append_quarterly_snapshots)
    assert '"revenue": fund.get("revenue")' in src, "스냅샷에서 revenue 적재가 사라졌다"


def test_build_watch_reports_attach_coverage(capsys):
    """붙였는지를 **센다**. 미계수가 죽은 보강을 448/448 방치한 원인이었다(RULE 12)."""
    from api.intelligence.multibagger_watch import build_watch

    build_watch([{"ticker": "000007", "name": "x", "market_cap": 5e10,
                  "revenue_growth": 30.0, "sector": "IT"}])
    err = capsys.readouterr().err
    assert "quarterly_revenue 부착" in err, "커버리지 신고가 사라졌다"
