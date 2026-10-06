"""Private journal retries, concurrent appends, and prepared price timestamps."""
from __future__ import annotations

import copy
import json
import multiprocessing
from datetime import datetime

import pytest

from api.intelligence import decision_journal as dj


def _facts():
    return {
        "ticker": "005930", "name": "테스트", "missing": [],
        "_meta": {"collected_at": "2026-08-18T11:00:00+09:00"},
        "sections": [{"label": "종가", "source": "kr_close_latest.json",
                      "as_of": "2026-08-17", "data": {"close": 71500}}],
    }


def _write(path, **overrides):
    args = dict(facts=_facts(), verdict="보류", confidence="medium",
                basis_axes=["quality"], reasoning_brief="테스트 근거",
                question="테스트 질문", brain_verdict="WATCH", path=str(path),
                record_id="prepared-1", review={"status": "reviewed"},
                facts_at=datetime.fromisoformat("2026-08-18T11:00:00+09:00"))
    args.update(overrides)
    return dj.record(**args)


def _rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def test_retry_returns_original_record_after_clock_changes(tmp_path, monkeypatch):
    path = tmp_path / "journal.jsonl"
    monkeypatch.setattr(dj, "now_kst", lambda: datetime.fromisoformat("2026-08-18T18:00:00+09:00"))
    first = _write(path)
    monkeypatch.setattr(dj, "now_kst", lambda: datetime.fromisoformat("2026-08-19T18:00:00+09:00"))
    retry = _write(path)
    assert retry == first
    assert _rows(path) == [first]
    assert first["record_id"] == "prepared-1"
    assert len(first["request_digest"]) == 64
    assert first["review"] == {"status": "reviewed"}
    assert first["facts_at"] == "2026-08-18T11:00:00+09:00"


@pytest.mark.parametrize("changed", [
    {"verdict": "관심"}, {"confidence": "high"}, {"basis_axes": ["value"]},
    {"reasoning_brief": "다른 근거"}, {"question": "다른 질문"},
    {"brain_verdict": "BUY"}, {"review": {"status": "not_used"}},
    {"facts_at": datetime.fromisoformat("2026-08-18T12:00:00+09:00")},
])
def test_same_id_rejects_changed_semantic_payload(tmp_path, changed):
    path = tmp_path / "journal.jsonl"
    first = _write(path)
    with pytest.raises(dj.JournalError):
        _write(path, **changed)
    assert _rows(path) == [first]


@pytest.mark.parametrize("field", ["missing", "_meta", "sections"])
def test_request_digest_covers_complete_facts(tmp_path, field):
    path = tmp_path / "journal.jsonl"
    first = _write(path)
    facts = _facts()
    if field == "missing":
        facts[field] = ["unverified"]
    elif field == "_meta":
        facts[field]["collected_at"] = "2026-08-18T12:00:00+09:00"
    else:
        facts[field][0]["data"]["close"] = 71600
    with pytest.raises(dj.JournalError):
        _write(path, facts=facts)
    assert _rows(path) == [first]


def test_mapping_key_order_does_not_create_a_conflict(tmp_path):
    path = tmp_path / "journal.jsonl"
    first = _write(path, review={"a": 1, "b": 2})
    facts = dict(reversed(list(_facts().items())))
    assert _write(path, facts=facts, review={"b": 2, "a": 1}) == first
    assert len(_rows(path)) == 1


@pytest.mark.parametrize("record_id", ["", "   "])
def test_empty_record_id_is_rejected_without_append(tmp_path, record_id):
    path = tmp_path / "journal.jsonl"
    with pytest.raises(dj.JournalError):
        _write(path, record_id=record_id)
    assert not path.exists() or not path.read_text(encoding="utf-8")


def test_review_requires_record_id(tmp_path):
    with pytest.raises(dj.JournalError):
        _write(tmp_path / "journal.jsonl", record_id=None)


def test_naive_snapshot_time_is_rejected(tmp_path):
    path = tmp_path / "journal.jsonl"
    naive = datetime(2026, 8, 18, 11)
    with pytest.raises(dj.JournalError):
        _write(path, facts_at=naive)
    with pytest.raises(dj.JournalError):
        dj.build_record(_facts(), "보류", "medium", [], "근거", facts_at=naive)


def test_legacy_call_preserves_schema_and_append_semantics(tmp_path):
    path = tmp_path / "journal.jsonl"
    first = _write(path, record_id=None, review=None, facts_at=None)
    second = _write(path, record_id=None, review=None, facts_at=None)
    assert len(_rows(path)) == 2
    for rec in (first, second):
        assert not ({"record_id", "request_digest", "review", "facts_at"} & rec.keys())


def test_keyed_write_rejects_corrupt_existing_row(tmp_path):
    path = tmp_path / "journal.jsonl"
    path.write_text('{invalid json}\n', encoding="utf-8")
    before = path.read_bytes()
    with pytest.raises(dj.JournalError):
        _write(path)
    assert path.read_bytes() == before


def test_prepared_intraday_price_cannot_become_a_close_on_later_save(tmp_path, monkeypatch):
    facts = _facts()
    facts["sections"] = [{"label": "실시간 시세 (KIS · 본인 이용)",
                          "source": "railway:quotes", "as_of": "2026-08-18T11:00:00+09:00",
                          "data": {"현재가": 99000}}]
    before = copy.deepcopy(facts)
    monkeypatch.setattr(dj, "now_kst", lambda: datetime.fromisoformat("2026-08-19T18:00:00+09:00"))
    rec = _write(tmp_path / "journal.jsonl", facts=facts)
    assert rec["ref_price"] is None
    assert rec["ref_price_asof"] is None
    assert facts == before


def test_prepared_close_keeps_its_original_session(tmp_path, monkeypatch):
    facts = _facts()
    facts["sections"] = [{"label": "실시간 시세 (KIS · 본인 이용)",
                          "source": "railway:quotes", "as_of": "2026-08-18T18:00:00+09:00",
                          "data": {"현재가": 99000}}]
    monkeypatch.setattr(dj, "now_kst", lambda: datetime.fromisoformat("2026-08-19T18:00:00+09:00"))
    rec = _write(tmp_path / "journal.jsonl", facts=facts,
                 facts_at=datetime.fromisoformat("2026-08-18T18:00:00+09:00"))
    assert (rec["ref_price"], rec["ref_price_asof"]) == (99000, "2026-08-18")


def _concurrent_writer(path, barrier, result_queue, record_id):
    try:
        barrier.wait(timeout=15)
        kwargs = {"record_id": record_id}
        if record_id is None:
            kwargs.update(review=None, facts_at=None)
        rec = _write(path, **kwargs)
        result_queue.put(("ok", rec))
    except Exception as exc:
        result_queue.put(("error", type(exc).__name__))


@pytest.mark.parametrize("ids,expected", [
    (["prepared-1"] * 6, 1),
    (["prepared-1", "prepared-2", None, None, "prepared-3", None], 6),
])
def test_concurrent_keyed_and_legacy_writers_preserve_records(tmp_path, ids, expected):
    path = tmp_path / "journal.jsonl"
    ctx = multiprocessing.get_context("fork")
    barrier = ctx.Barrier(len(ids))
    result_queue = ctx.Queue()
    workers = [ctx.Process(target=_concurrent_writer, args=(path, barrier, result_queue, key))
               for key in ids]
    try:
        for worker in workers:
            worker.start()
        results = [result_queue.get(timeout=20) for _ in workers]
        for worker in workers:
            worker.join(timeout=10)
            assert worker.exitcode == 0
        assert all(status == "ok" for status, _ in results), results
        assert len(_rows(path)) == expected
        if expected == 1:
            assert all(rec == results[0][1] for _, rec in results)
    finally:
        for worker in workers:
            if worker.is_alive():
                worker.terminate()
            worker.join(timeout=5)
        result_queue.close()
