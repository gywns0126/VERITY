# -*- coding: utf-8 -*-
"""ipo_scout 전량 실패 가드 (#46 마지막 건).

🚨 두 개의 0 을 구분해야 한다.
   · count == 0          = IPO 후보 없음 → 정상 (증분 성격)
   · raw_c001_count == 0 = DART 조회 실패 → 사고

   `_call` 이 실패 시 빈 dict 를 돌려주므로 rows=[] 만 보면 둘이 같아 보인다.
   옛 코드는 `main() -> None` 을 그냥 호출해 어떤 경우든 exit 0 이었다.
   [[feedback_silent_total_failure_guard]]
"""
from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.collectors import ipo_scout  # noqa: E402


@pytest.fixture
def _out(tmp_path, monkeypatch):
    out = tmp_path / "ipo_watch.json"
    monkeypatch.setattr(ipo_scout, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(ipo_scout, "OUTPUT_PATH", str(out))
    return out


def _result(raw: int, watch: list) -> dict:
    return {
        "updated_at": "2026-08-09T00:00:00+09:00",
        "raw_c001_count": raw,
        "count": len(watch),
        "watch": watch,
    }


def test_dart_fetch_failure_returns_1_and_skips_output(_out, monkeypatch):
    monkeypatch.setattr(ipo_scout, "scout", lambda: _result(0, []))

    assert ipo_scout.main() == 1
    assert not _out.exists(), "조회 실패에 산출을 새로 쓰면 보드가 오통과한다"


def test_no_candidates_is_normal(_out, monkeypatch):
    """원시 공시는 받았고 IPO 후보만 0 = 정상. 산출을 기록하고 0 을 돌려준다."""
    monkeypatch.setattr(ipo_scout, "scout", lambda: _result(137, []))

    assert ipo_scout.main() == 0
    assert _out.exists()
    assert json.loads(_out.read_text(encoding="utf-8"))["count"] == 0


def test_candidates_recorded(_out, monkeypatch):
    watch = [{"corp_name": "테스트기업", "stage": "예비", "offering": {}}]
    monkeypatch.setattr(ipo_scout, "scout", lambda: _result(137, watch))

    assert ipo_scout.main() == 0
    assert json.loads(_out.read_text(encoding="utf-8"))["count"] == 1
