# -*- coding: utf-8 -*-
"""KR 소형주 외국인 순매수 급증 관측 계약.

🚨 이 관측기의 존재 이유는 "데이터가 늦어서" 가 아니다. 제이엠티 094970 추적 결과
   08-03 급등 당일 외국인 +104,642주가 같은 날 21:44 KST 에 이미 수집돼 있었다.
   갭은 **표면화**였다 — 파일 안에 있었는데 아무도 안 봤다.

   그래서 지키는 선이 "많이 잡는다" 가 아니라 "쓸 수 있는 밀도로 잡는다" 다:
     · 단일 게이트는 종목의 29.5% 가 걸려 알림이 안 된다 → 이중 게이트 필수
     · 임계는 전부 기존 상수 재사용 — 새 숫자 0개가 설계 의도다(곡선 맞추기 방지)
     · 입력 부재는 "이벤트 0건" 과 다르다 → exit 1 (#46 계열)
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.builders import kr_flow_spike_observer as ob  # noqa: E402

_EOK = 100_000_000


def _rows(spike_idx=2, spike=100_000, base=10_000, closes=(1000, 1010, 1200, 1210, 1220)):
    out = []
    for i, c in enumerate(closes):
        out.append({
            "date": f"2026-08-0{i + 3}",
            "foreign_net": float(spike if i == spike_idx else base),
            "inst_net": 0.0,
            "close": float(c),
        })
    return out


def _mkt(mktcap_eok=500):
    return {"094970": {"mktcap": mktcap_eok * _EOK, "close": 3100}}


# ── 임계 동결 (사전등록 대상) ───────────────────────────────────────────────

def test_thresholds_are_reused_constants_not_new_numbers():
    """🚨 새 숫자를 만들면 이 종목에 맞춘 곡선 맞추기가 된다.

    flow_x 3.0 · move_pct 7.0 = us_demand_chain 관측기의 상수 그대로.
    시총 300~3000억 = smallcap_corner_builder 의 MKTCAP_MIN/MAX 그대로.
    변경은 사전등록 대상이므로 여기서 동결한다.
    """
    assert ob.FLOW_X == 3.0
    assert ob.MOVE_PCT == 7.0
    assert ob.MKTCAP_MIN == 300 * _EOK
    assert ob.MKTCAP_MAX == 3000 * _EOK


# ── 이중 게이트 ──────────────────────────────────────────────────────────────

def test_both_gates_required_fires(mkt=None):
    flows = {"094970": _rows()}          # 3번째 날 급증 + 1010→1200 = +18.8%
    got = ob.detect(flows, _mkt())
    assert len(got) == 1
    e = got[0]
    assert e["ticker"] == "094970"
    assert e["flow_x"] >= ob.FLOW_X
    assert e["move_pct"] >= ob.MOVE_PCT


def test_flow_spike_without_price_move_does_not_fire():
    """단일 게이트로는 종목의 29.5% 가 걸린다 — 가격 조건이 없으면 알림이 안 된다."""
    flows = {"094970": _rows(closes=(1000, 1010, 1020, 1030, 1040))}  # +1% 만
    assert ob.detect(flows, _mkt()) == []


def test_price_move_without_flow_spike_does_not_fire():
    flows = {"094970": _rows(spike=10_000)}  # 급증 없음(전부 동일)
    assert ob.detect(flows, _mkt()) == []


# ── 유니버스 ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("eok", [299, 3000, 5000])
def test_outside_smallcap_range_excluded(eok):
    assert ob.detect({"094970": _rows()}, _mkt(eok)) == []


def test_missing_mktcap_excluded():
    assert ob.detect({"094970": _rows()}, {}) == []


def test_first_row_has_no_previous_close_so_skipped():
    """창의 첫 행은 전일 종가가 없다. 실운영의 최신일에는 항상 전일이 있다."""
    flows = {"094970": _rows(spike_idx=0)}
    assert ob.detect(flows, _mkt()) == []


def test_short_series_skipped():
    flows = {"094970": [{"date": "2026-08-03", "foreign_net": 1e6, "close": 100}]}
    assert ob.detect(flows, _mkt()) == []


# ── 산출 규율 ────────────────────────────────────────────────────────────────

def test_no_score_or_rank_in_output():
    """RULE 7 — 사실만. 점수·순위·추천 필드가 있으면 안 된다."""
    got = ob.detect({"094970": _rows()}, _mkt())
    banned = {"score", "rank", "grade", "recommendation", "verdict", "target"}
    assert not (set(got[0]) & banned)


def test_sorted_by_date_not_by_magnitude():
    flows = {
        "094970": _rows(),
        "000660": _rows(closes=(1000, 1010, 1500, 1510, 1520)),
    }
    mkt = {"094970": {"mktcap": 500 * _EOK}, "000660": {"mktcap": 800 * _EOK}}
    got = ob.detect(flows, mkt)
    assert [g["date"] for g in got] == sorted(g["date"] for g in got)


# ── 전량 실패 가드 (#46) ────────────────────────────────────────────────────

def test_empty_input_is_failure_not_zero_events(monkeypatch, tmp_path):
    """입력 부재와 '이벤트 0건' 은 다르다. 정상 종료하면 mtime 만 갱신되어 보드가 통과시킨다."""
    monkeypatch.setattr(ob, "_load", lambda p: {"flows": {}, "map": {}})
    monkeypatch.setattr(ob, "OUT_PATH", str(tmp_path / "out.jsonl"))
    assert ob.main() == 1
    assert not (tmp_path / "out.jsonl").exists()


def test_load_error_is_failure(monkeypatch, tmp_path):
    def _boom(p):
        raise OSError("없음")

    monkeypatch.setattr(ob, "_load", _boom)
    monkeypatch.setattr(ob, "OUT_PATH", str(tmp_path / "out.jsonl"))
    assert ob.main() == 1
