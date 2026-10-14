"""File-version cache preserves historical F-Score inputs and refresh boundaries."""
import json
import os

from api.utils import fscore_delta as mod


def row(ticker="A", quarter="2026-03-31", fetched="2026-05-01", **extra):
    return {"ticker": ticker, "quarter_end": quarter, "fetched_at": fetched, **extra}


def write(path, rows):
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")


def test_one_read_keeps_latest_duplicate_first_equal_and_isolates_mutations(tmp_path, monkeypatch):
    path = tmp_path / "snapshots.jsonl"
    records = [row(roa=1), row(fetched="2026-05-02", roa=2, nested={"x": 1}),
               row(fetched="2026-05-02", roa=99), row(quarter="2025-03-31", roa=3),
               row(quarter="2026-05-17", roa=100), row("B", roa=4)]
    write(path, records)
    with path.open("a") as f:
        f.write("invalid json\n")
    monkeypatch.setattr(mod, "QUARTERLY_SNAPSHOT_PATH", path)
    before = mod.quarterly_snapshot_cache_metrics()
    actual = mod.load_quarterly_snapshots("a")
    assert actual == [records[1], records[3]]
    actual[0]["nested"]["x"] = 99
    assert mod.load_quarterly_snapshots("A")[0]["nested"]["x"] == 1
    assert mod.load_quarterly_snapshots("B") == [records[5]]
    assert mod.load_quarterly_snapshots("MISSING") == []
    after = mod.quarterly_snapshot_cache_metrics()
    assert after["file_reads"] - before["file_reads"] == 1
    assert after["cache_hits"] - before["cache_hits"] == 3
    assert after["parse_failures"] - before["parse_failures"] == 1


def test_append_invalidates_even_with_preserved_mtime(tmp_path, monkeypatch):
    path = tmp_path / "snapshots.jsonl"
    write(path, [row(roa=1)])
    monkeypatch.setattr(mod, "QUARTERLY_SNAPSHOT_PATH", path)
    assert mod.load_quarterly_snapshots("A")[0]["roa"] == 1
    stamp = path.stat().st_mtime_ns
    with path.open("a") as f:
        f.write(json.dumps(row(fetched="2026-05-03", roa=3)) + "\n")
    os.utime(path, ns=(stamp, stamp))
    assert mod.load_quarterly_snapshots("A")[0]["roa"] == 3


def test_replace_same_size_and_mtime_and_path_switch_invalidate(tmp_path, monkeypatch):
    path = tmp_path / "snapshots.jsonl"
    write(path, [row(roa=1)])
    monkeypatch.setattr(mod, "QUARTERLY_SNAPSHOT_PATH", path)
    assert mod.load_quarterly_snapshots("A")[0]["roa"] == 1
    stamp = path.stat().st_mtime_ns
    replacement = tmp_path / "replacement.jsonl"
    write(replacement, [row(roa=2)])
    os.utime(replacement, ns=(stamp, stamp))
    os.replace(replacement, path)
    assert mod.load_quarterly_snapshots("A")[0]["roa"] == 2
    other = tmp_path / "other.jsonl"
    write(other, [row(roa=3)])
    monkeypatch.setattr(mod, "QUARTERLY_SNAPSHOT_PATH", other)
    assert mod.load_quarterly_snapshots("A")[0]["roa"] == 3
    assert mod._SNAPSHOT_CACHE["fingerprint"][0] == str(other.resolve())


def test_missing_file_does_not_reuse_old_rows(tmp_path, monkeypatch):
    path = tmp_path / "snapshots.jsonl"
    write(path, [row(roa=1)])
    monkeypatch.setattr(mod, "QUARTERLY_SNAPSHOT_PATH", path)
    assert mod.load_quarterly_snapshots("A")
    path.unlink()
    assert mod.load_quarterly_snapshots("A") == []
    assert mod._SNAPSHOT_CACHE == {}
    write(path, [row(roa=4)])
    assert mod.load_quarterly_snapshots("A")[0]["roa"] == 4


def test_bad_duplicate_fetched_at_only_invalidates_affected_ticker(tmp_path, monkeypatch):
    path = tmp_path / "snapshots.jsonl"
    write(path, [row("A"), row("A", fetched=None), row("B", roa=3)])
    monkeypatch.setattr(mod, "QUARTERLY_SNAPSHOT_PATH", path)
    assert mod.load_quarterly_snapshots("A") == []
    assert mod.load_quarterly_snapshots("B")[0]["roa"] == 3


def test_concurrent_append_during_read_is_not_cached(tmp_path, monkeypatch):
    path = tmp_path / "snapshots.jsonl"
    write(path, [row(roa=1)])
    monkeypatch.setattr(mod, "QUARTERLY_SNAPSHOT_PATH", path)
    original = mod._read_snapshot_index

    def append_after_read(p):
        result = original(p)
        with p.open("a") as f:
            f.write(json.dumps(row(fetched="2026-05-03", roa=3)) + "\n")
        return result

    monkeypatch.setattr(mod, "_read_snapshot_index", append_after_read)
    assert mod.load_quarterly_snapshots("A")[0]["roa"] == 1
    assert mod._SNAPSHOT_CACHE == {}
    monkeypatch.setattr(mod, "_read_snapshot_index", original)
    assert mod.load_quarterly_snapshots("A")[0]["roa"] == 3
