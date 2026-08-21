"""둥지 브리핑 색인 — 계약 가드 (2026-08-21).

PM 요청: 회원이 둥지에 보유한 종목의 최근 공시 + 국민연금 보유 여부를 둥지에서 보이게.
설계: 회원별 서버 발행이 아니라 **전역 티커 색인 1개** + 브라우저가 본인 티커만 조회.

🚨 지키는 계약 3개
 1. 색인은 압축돼야 한다 — 원본 피드(US 4.1MB + KR 862KB)를 브라우저가 못 받는다
 2. 자기신고 — "색인에 없음 = 창 안에 공시 없음(미수집 아님)" 을 _meta 가 말해야 한다
 3. 🚨 국민연금 배지는 **없을 때 아무것도 안 그린다** — 원천이 5% 대량보유 공시라
    부재는 "미보유" 가 아니라 "5% 미만" 이다. "미보유" 라고 쓰면 거짓이 된다
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
IDX = ROOT / "data" / "nest_briefing_index.json"
SRC = ROOT / "api" / "builders" / "nest_briefing_index_builder.py"
TSX = ROOT / "framer-components" / "public-probe" / "PublicHoldingsTab.tsx"


def test_builder_caps_window_and_per_ticker():
    s = SRC.read_text(encoding="utf-8")
    assert "WINDOW_DAYS" in s and "MAX_PER_TICKER" in s, "크기 방어 상한이 사라졌다"


def test_index_shape_and_selfreport():
    if not IDX.exists():
        pytest.skip("색인 없음 — 빌더 미실행")
    d = json.loads(IDX.read_text(encoding="utf-8"))
    m = d["_meta"]
    assert "coverage_note" in m, "부재 의미(공시 없음 vs 미수집) 신고가 없다"
    assert "news" in m, "뉴스 미포함 사유 신고가 없다"
    assert m["counts"]["total"] == len(d["tickers"])
    for tk, v in list(d["tickers"].items())[:20]:
        assert v["m"] in ("KR", "US")
        assert 1 <= len(v["ev"]) <= m["max_per_ticker"]
        for e in v["ev"]:
            assert e["d"] >= m["cutoff"], "창 밖 항목이 실렸다"


def test_index_stays_browser_sized():
    """🚨 브라우저가 받는 파일이다. 원본 피드로 되돌리면 4MB 가 된다."""
    if not IDX.exists():
        pytest.skip("색인 없음")
    mb = IDX.stat().st_size / 1024 / 1024
    assert mb < 1.5, f"색인이 {mb:.2f}MB — 압축 상한(WINDOW_DAYS/MAX_PER_TICKER)이 풀렸다"


def test_component_never_claims_nps_absence():
    """🚨 이 파일의 핵심. '국민연금 미보유' 표기가 생기면 거짓이 된다."""
    if not TSX.exists():
        pytest.skip("컴포넌트 없음")
    s = TSX.read_text(encoding="utf-8")
    assert "NestBadges" in s, "둥지 배지 컴포넌트가 사라졌다"
    for bad in ("국민연금 미보유", "국민연금 없음", "연금 미보유"):
        assert bad not in s, f"부재를 단정하는 문구가 있다: {bad}"
    assert "5% 미만" in s, "부재 의미(5% 미만)를 설명하는 주석/문구가 사라졌다"


def test_component_reads_index_not_raw_feeds():
    if not TSX.exists():
        pytest.skip("컴포넌트 없음")
    s = TSX.read_text(encoding="utf-8")
    assert "nest_briefing_index.json" in s
    assert "us_disclosure_feed.json" not in s, "원본 4.1MB 피드를 직접 받으면 안 된다"


def test_publish_allowlist_registered():
    y = (ROOT / ".github" / "actions" / "publish-data" / "action.yml").read_text(encoding="utf-8")
    assert "nest_briefing_index.json" in y, "발행 목록 미등재 = 컴포넌트가 404 를 받는다"


def test_workflow_registered():
    w = (ROOT / ".github" / "workflows" / "daily_briefing.yml").read_text(encoding="utf-8")
    assert "nest_briefing_index_builder" in w, "빌더가 어느 워크플로에도 없다(RULE 4/8)"
