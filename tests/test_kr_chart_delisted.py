# -*- coding: utf-8 -*-
"""소멸 종목 일봉 수집 (2026-08-08) — 생존 편향 해소의 마지막 조각.

사고: 기존 일봉 레이크는 **현재 상장 유니버스 기준**으로 수집돼 소멸 종목 가격이 0/415.
가격이 없으면 상폐를 유니버스에 넣어도 수익률을 못 매겨 생존 편향이 그대로 남는다.

되는 이유: 금융위 API 가 소멸 종목 시세를 **마지막 거래일까지** 보유한다.
실수집 415/415 · 309,982행 · 실패 0 · 소멸 연도 2020~2026 고르게 분포(46~82/년).
구성: 보통주 264(64%) · 스팩 133(32%) · 우선주 14 · 리츠 4.

계약: ① likeSrtnCd 부분일치를 정확 티커로 걸러낸다 ② 오름차순 정렬
③ 멱등(이미 받은 종목 재수집 안 함) ④ 🚨 last_bar 노출 — 그 이후를 지어내지 않는다
⑤ kr_chart_daily 와 동일 스키마(같은 로더로 읽힌다).
"""
import json

import api.collectors.kr_chart_delisted as D


def _item(code, d, close, name="테스트"):
    return {"srtnCd": code, "basDt": str(d), "clpr": str(close), "mkp": "1",
            "hipr": "2", "lopr": "0", "trqu": "10", "itmsNm": name}


def test_partial_match_filtered(monkeypatch):
    """🚨 likeSrtnCd 는 부분일치 — 다른 종목이 섞이면 가격이 오염된다."""
    monkeypatch.setattr(D, "_call", lambda p: {"items": {"item": [
        _item("A000060", 20200102, 100), _item("A0000601", 20200102, 999)]}})
    r = D.fetch_one("000060")
    assert len(r["c"]) == 1 and r["c"][0][4] == 100


def test_rows_sorted_ascending(monkeypatch):
    monkeypatch.setattr(D, "_call", lambda p: {"items": {"item": [
        _item("A000060", 20200103, 110), _item("A000060", 20200102, 100)]}})
    c = D.fetch_one("000060")["c"]
    assert [x[0] for x in c] == [20200102, 20200103]


def test_no_data_returns_none(monkeypatch):
    monkeypatch.setattr(D, "_call", lambda p: {"items": {"item": []}})
    assert D.fetch_one("000060") is None
    monkeypatch.setattr(D, "_call", lambda p: None)
    assert D.fetch_one("000060") is None


def test_schema_matches_current_lake(monkeypatch):
    """kr_chart_daily 와 같은 [d,o,h,l,c,v] — 백테스트가 한 로더로 읽는다."""
    monkeypatch.setattr(D, "_call", lambda p: {"items": {"item": [
        _item("A000060", 20200102, 100)]}})
    row = D.fetch_one("000060")["c"][0]
    assert len(row) == 6 and row[0] == 20200102 and row[4] == 100


def test_idempotent_skips_collected(tmp_path, monkeypatch):
    monkeypatch.setattr(D, "OUT_DIR", str(tmp_path / "out"))
    monkeypatch.setattr(D, "META_PATH", str(tmp_path / "meta.json"))
    monkeypatch.setattr(D, "DELIST_PATH", str(tmp_path / "dl.json"))
    (tmp_path / "dl.json").write_text(json.dumps(
        {"as_of": "20260731", "last_seen": {"000060": "20200131", "000070": "20260731"}}),
        encoding="utf-8")
    seen = []
    monkeypatch.setattr(D, "fetch_one", lambda tk: seen.append(tk) or
                        {"t": tk, "n": "x", "c": [[20200102, 1, 1, 1, 100, 1]]})
    D.collect(limit=10)
    assert seen == ["000060"]           # 최신에 살아있는 000070 은 대상 아님
    seen.clear()
    D.collect(limit=10)
    assert seen == []                   # 두 번째는 재수집 없음


def test_meta_exposes_last_bar_without_fabricating(tmp_path, monkeypatch):
    """🚨 last_bar 이후를 0 이나 마지막 가격으로 채우면 상폐 손실이 지워진다."""
    monkeypatch.setattr(D, "OUT_DIR", str(tmp_path / "out"))
    monkeypatch.setattr(D, "META_PATH", str(tmp_path / "meta.json"))
    monkeypatch.setattr(D, "DELIST_PATH", str(tmp_path / "dl.json"))
    (tmp_path / "dl.json").write_text(json.dumps(
        {"as_of": "20260731", "last_seen": {"000060": "20200131"}}), encoding="utf-8")
    monkeypatch.setattr(D, "fetch_one", lambda tk: {
        "t": tk, "n": "x", "c": [[20200102, 1, 1, 1, 100, 1], [20200710, 1, 1, 1, 50, 1]]})
    D.collect(limit=5)
    meta = json.loads((tmp_path / "meta.json").read_text(encoding="utf-8"))
    assert meta["last_bar"]["000060"] == 20200710
    assert "지어" not in json.dumps(meta["note"]) or "지워진다" in meta["note"]
    assert "상폐 손실" in meta["note"]


def test_no_input_is_explicit(tmp_path, monkeypatch):
    monkeypatch.setattr(D, "DELIST_PATH", str(tmp_path / "missing.json"))
    assert D.collect()["status"] == "no_input"


def test_workflow_wires_collector_and_commits():
    """🚨 RULE 4 — 이 워크플로는 Blob 전용이라 git add 가 없었다. 산출물이 사라진다."""
    import os
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(repo, ".github/workflows/kr_chart_history.yml"), encoding="utf-8") as f:
        yml = f.read()
    assert "api.collectors.kr_chart_delisted" in yml
    assert "git add data/kr_chart_delisted/" in yml
    # 유니버스 수집이 먼저여야 한다(그 산출이 입력)
    assert yml.index("kr_universe_pit") < yml.index("api.collectors.kr_chart_delisted")
