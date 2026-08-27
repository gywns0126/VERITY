import json

from api.builders import freshness_board_builder


def test_board_excludes_its_own_previous_output(tmp_path, monkeypatch):
    manifest = tmp_path / "freshness_sla.json"
    manifest.write_text(json.dumps({"streams": [
        {"id": "freshness_board", "file": "freshness_board.json", "criticality": "P2",
         "schedule": "always", "max_age_minutes": 240}
    ]}), encoding="utf-8")
    monkeypatch.setattr(freshness_board_builder, "MANIFEST", str(manifest))

    board = freshness_board_builder.build_board()

    assert board["streams"] == []
    assert board["summary"]["stale"] == 0
