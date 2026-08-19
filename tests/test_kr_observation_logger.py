# -*- coding: utf-8 -*-
"""KR cross-section 관측 적재 계약 — 2026-08-20 신설.

이 trail 은 forward IC 검증용 append-only 라 **틀린 행 한 줄이 영구 오염**이다. 두 계약을 고정한다:

① 입력 신선도 — 이 빌더는 같은 run 의 빌더 4종 산출을 읽는다. 분석이 죽어 그 빌더들이 skip 되면
   '어제 값'이 '오늘 date' 로 적재된다(as-of 거짓). generated_at 이 오늘이 아닌 입력은 컬럼을
   null 로 적고 stale_inputs 로 신고해야 하며, 4종 전부 stale 이면 적재 자체를 하지 않아야 한다
   (그래야 같은 날 뒤 run 이 date-dedupe 에 막히지 않는다).
   근거 사고 = 2026-08-14(금) daily_analysis_full 3연속 실패 → 그 주 행 영구 결손.
② insider_net_365d 병기 — 기존 insider_net 은 elestock 전 기간 누적이라 종목별로 사실상 상수다
   (000660 8주 실측 104,361 → 106,615). 기존 컬럼은 연속성 때문에 정의를 유지하고 창 컬럼을 병기한다.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.builders import kr_observation_logger as ob  # noqa: E402

TK = "000660"


def _meta(day: str):
    return {"_meta": {"generated_at": f"{day}T17:59:51+09:00"}}


def _write(tmp, name, doc):
    p = os.path.join(tmp, name)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False)
    return p


@pytest.fixture
def env(tmp_path, monkeypatch):
    """4개 입력 + 출력 경로를 tmp 로 격리. day 인자로 각 입력의 as-of 를 조작한다."""
    tmp = str(tmp_path)
    today = ob._now_kst().date().isoformat()
    yday = (ob._now_kst().date() - __import__("datetime").timedelta(days=1)).isoformat()
    monkeypatch.setenv("KR_OBS_FORCE", "1")          # 금요일 게이트 우회
    monkeypatch.setattr(ob, "OUT_DIR", tmp)
    out = os.path.join(tmp, "obs.jsonl")
    monkeypatch.setattr(ob, "OUT_PATH", out)

    def build(insider_day=None, flow_day=None, forensics_day=None, report_day=None):
        insider_day = insider_day or today
        flow_day = flow_day or today
        forensics_day = forensics_day or today
        report_day = report_day or today
        monkeypatch.setattr(ob, "INSIDER_PATH", _write(tmp, "insider.json", dict(
            _meta(insider_day), stocks=[{
                "ticker": TK, "net_change": 106_615, "buy_n": 533, "sell_n": 26,
                "net_change_365d": 2_120, "buy_n_365d": 9, "sell_n_365d": 3,
            }])))
        monkeypatch.setattr(ob, "FLOW_PATH", _write(tmp, "flow.json", dict(
            _meta(flow_day), flows={TK: [{"foreign_net": 1}, {"foreign_net": 104_642, "inst_net": -50}]})))
        monkeypatch.setattr(ob, "FORENSICS_PATH", _write(tmp, "forensics.json", dict(
            _meta(forensics_day), stocks=[{"ticker": TK, "counts": {
                "유상증자": 2, "전환사채(CB)": 1, "신주인수권부사채(BW)": 0}}])))
        monkeypatch.setattr(ob, "REPORT_PATH", _write(tmp, "report.json", dict(
            _meta(report_day), stocks=[{"ticker": TK, "ownership": {"family_pct": 30.1}}])))
        return out

    build.today, build.yday, build.out = today, yday, out
    return build


def _rows(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


class TestFreshInputs:
    def test_all_fresh_logs_full_row(self, env):
        out = env()
        assert ob.main() == 0
        rows = _rows(out)
        assert len(rows) == 1
        r = rows[0]
        assert r["ticker"] == TK
        assert r["insider_net"] == 106_615          # 전 기간 누적(정의 유지)
        assert r["insider_net_365d"] == 2_120       # 창 컬럼 병기
        assert r["insider_buy_n_365d"] == 9 and r["insider_sell_n_365d"] == 3
        assert r["foreign_net"] == 104_642 and r["inst_net"] == -50
        assert r["dilution_count"] == 3
        assert r["family_pct"] == 30.1
        assert "stale_inputs" not in r              # 정상 주엔 키 자체가 없다

    def test_date_dedupe(self, env):
        out = env()
        assert ob.main() == 0
        assert ob.main() == 0
        assert len(_rows(out)) == 1


class TestStaleInputs:
    def test_stale_insider_nulls_only_its_columns(self, env):
        out = env(insider_day=env.yday)
        assert ob.main() == 0
        r = _rows(out)[0]
        assert r["insider_net"] is None and r["insider_net_365d"] is None
        assert r["insider_buy_n"] is None and r["insider_sell_n_365d"] is None
        assert r["stale_inputs"] == ["insider"]
        # 나머지는 살아 있어야 한다 — 한 소스 stale 이 전체 행을 버리게 하면 결손이 커진다
        assert r["foreign_net"] == 104_642
        assert r["dilution_count"] == 3
        assert r["family_pct"] == 30.1

    def test_stale_forensics_and_report_null(self, env):
        out = env(forensics_day=env.yday, report_day=env.yday)
        assert ob.main() == 0
        r = _rows(out)[0]
        assert r["dilution_count"] is None
        assert r["family_pct"] is None
        assert r["stale_inputs"] == ["forensics", "report"]
        assert r["insider_net_365d"] == 2_120

    def test_all_stale_writes_nothing(self, env):
        # 🚨 핵심 — 빈 행을 남기면 같은 날 뒤 run 이 date-dedupe 에 막혀 진짜 데이터를 잃는다
        out = env(insider_day=env.yday, flow_day=env.yday,
                  forensics_day=env.yday, report_day=env.yday)
        assert ob.main() == 0
        assert _rows(out) == []

    def test_missing_meta_is_stale(self, env):
        # _meta 부재 = as-of 불명 → 신선하다고 가정하지 않는다
        out = env()
        with open(ob.INSIDER_PATH, "w", encoding="utf-8") as f:
            json.dump({"stocks": [{"ticker": TK, "net_change": 1}]}, f)
        assert ob.main() == 0
        assert _rows(out)[0]["stale_inputs"] == ["insider"]
