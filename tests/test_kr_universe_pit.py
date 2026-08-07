# -*- coding: utf-8 -*-
"""시점별 유니버스 수집 — 생존 편향 해소 (2026-08-07).

사고: 백테스트 자산을 점검하니 분기 스냅샷(2016~ 52분기, 1,989종목)에서
**2016년 분기를 가진 1,080종목이 전부 현재 상장 상태, 사라진 종목 0** 이었다.
10년간 상폐 0건은 불가능하다 — 오늘 살아남은 종목만 골라 과거를 채운 것이다.

이 데이터로 백테스트하면 망한 회사가 표본에서 빠져 수익률이 부풀고, 그 숫자를 믿고
실전에 가면 정확히 그만큼 잃는다. **백테스트가 없는 것보다 나쁘다.**

해법: 금융위 API 가 `basDt`(기준일자)로 **그 날의 전체 상장 종목**을 준다.
실측 2026-08-07 — 20200102 2,475종 · 20230102 2,690 · 20260806 2,872.
과거 유니버스를 모으면 사라진 종목이 복원된다(3.5년 수집 시 171건 확인).

계약: ① 휴장(빈 리스트)과 실패(None)를 구분 ② 부분 페이지 수집은 폐기
③ 사유 단정 금지 — 상폐·합병·티커변경 혼재 ④ 멱등.
"""
import json

import api.collectors.kr_universe_pit as U


def test_month_ends_covers_range():
    import datetime
    out = U.month_ends(datetime.date(2020, 1, 1), datetime.date(2020, 4, 30))
    assert out == ["20200131", "20200229", "20200331", "20200430"]


def test_holiday_and_failure_are_distinguished(monkeypatch):
    """🚨 실패를 '그날 상장 0'으로 기록하면 전 종목이 상폐된 것처럼 보인다."""
    monkeypatch.setattr(U, "_call", lambda p: None)
    assert U.fetch_universe("20200101") is None            # 실패
    monkeypatch.setattr(U, "_call", lambda p: {"totalCount": 0})
    assert U.fetch_universe("20200101") == []              # 휴장


def test_partial_page_failure_discards_snapshot(monkeypatch):
    """부분 유니버스는 상폐 오판을 낳는다 — 통째로 버린다."""
    calls = {"n": 0}

    def fake(p):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"totalCount": 9000,
                    "items": {"item": [{"srtnCd": "000001"}]}}
        return None                                        # 2페이지 실패
    monkeypatch.setattr(U, "_call", fake)
    monkeypatch.setattr(U.time, "sleep", lambda s: None)
    assert U.fetch_universe("20200101") is None


def test_ticker_normalisation(monkeypatch):
    monkeypatch.setattr(U, "_call", lambda p: {
        "totalCount": 3,
        "items": {"item": [{"srtnCd": "A005930"}, {"srtnCd": "000660"},
                           {"srtnCd": "BAD"}]}})
    assert U.fetch_universe("20200101") == ["000660", "005930"]


def test_delisting_records_facts_not_causes(tmp_path, monkeypatch):
    """🚨 사유 단정 금지 — 상폐·합병·티커변경이 같은 형태로 보인다."""
    p = tmp_path / "pit.jsonl"
    p.write_text("\n".join(json.dumps(x) for x in [
        {"as_of": "20200131", "tickers": ["000001", "000002"]},
        {"as_of": "20200229", "tickers": ["000001"]},
    ]), encoding="utf-8")
    monkeypatch.setattr(U, "PIT_PATH", str(p))
    monkeypatch.setattr(U, "DELIST_PATH", str(tmp_path / "d.json"))
    d = U.build_delisting()
    assert d["disappeared"] == 1
    assert d["last_seen"]["000002"] == "20200131"
    assert d["first_seen"]["000001"] == "20200131"
    assert "단정 금지" in d["note"]


def test_collect_is_idempotent(tmp_path, monkeypatch):
    """같은 기준일을 두 번 수집하지 않는다 — API 쿼터 낭비 + 중복 행."""
    p = tmp_path / "pit.jsonl"
    p.write_text(json.dumps({"as_of": "20200131", "bas_dt": "20200131",
                             "tickers": ["000001"]}) + "\n", encoding="utf-8")
    monkeypatch.setattr(U, "PIT_PATH", str(p))
    monkeypatch.setattr(U, "fetch_universe", lambda d: ["000001"])
    monkeypatch.setattr(U.time, "sleep", lambda s: None)
    r = U.collect("20200101", "20200131", max_calls=5)
    assert r["skipped"] == 1 and r["added"] == 0


def test_empty_store_reports_no_data(tmp_path, monkeypatch):
    monkeypatch.setattr(U, "PIT_PATH", str(tmp_path / "none.jsonl"))
    assert U.build_delisting()["status"] == "no_data"


def test_workflow_commits_the_output():
    """🚨 RULE 4 — 이 워크플로는 Blob 전용이라 git add 가 없었다.

    신 파일을 그냥 만들면 러너 소멸과 함께 사라진다. 백테스트 유니버스의 정본이라
    반드시 커밋돼야 한다(6.5년 누적 ~1.9MB, git 부담 없음).
    """
    import os
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(repo, ".github/workflows/kr_chart_history.yml"), encoding="utf-8") as f:
        yml = f.read()
    assert "api.collectors.kr_universe_pit" in yml          # 수집 배선
    assert "git add data/kr_universe_pit.jsonl" in yml      # 산출물 전달
    assert "data/kr_delisting.json" in yml
