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
import re
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


# ── 브리핑 섹션 (2026-08-22) ────────────────────────────────
BRIEF = ROOT / "framer-components" / "public-probe" / "PublicMorningBriefing.tsx"


def test_briefing_section_hides_when_no_overlap():
    """🚨 절충안의 핵심 — 보유∩색인이 0이면 섹션을 통째로 안 그린다.

    전용 섹션을 처음에 반대했던 이유가 "겹침 0인 날 빈 섹션이 뜬다" 였고,
    이 조건이 그 반대를 보장한다. 조건을 풀면 매일 빈 섹션이 뜬다.
    """
    if not BRIEF.exists():
        pytest.skip("브리핑 컴포넌트 없음")
    s = BRIEF.read_text(encoding="utf-8")
    assert "myNews" in s, "내 종목 소식 파생값이 사라졌다"
    assert "myNews.length > 0 &&" in s, "겹침 0일 때 섹션을 숨기는 조건이 사라졌다"
    assert "!isDemo &&" in s, "데모 상태에서 가짜 개인화가 보이면 안 된다"


def test_briefing_reads_index_not_raw_feeds():
    if not BRIEF.exists():
        pytest.skip("브리핑 컴포넌트 없음")
    s = BRIEF.read_text(encoding="utf-8")
    assert "nest_briefing_index.json" in s
    assert "us_disclosure_feed.json" not in s, "원본 4.1MB 피드 직접 사용 금지"


def test_briefing_never_claims_nps_absence():
    if not BRIEF.exists():
        pytest.skip("브리핑 컴포넌트 없음")
    s = BRIEF.read_text(encoding="utf-8")
    for bad in ("국민연금 미보유", "국민연금 없음"):
        assert bad not in s, f"부재를 단정하는 문구: {bad}"


def test_badges_do_not_grow_row_height():
    """🚨 PM 2026-08-22 — "세로로 배치하지 말고 스택 높이 변화 없이".

    종전 NestBadges 가 flexWrap:"wrap" + marginTop 이라 칩이 줄바꿈되며 보유 행이
    4줄까지 늘었다(국민연금 1 + 공시 2 + "+1"). 보유 목록은 행 높이가 고정이어야
    스캔이 된다 — 새 줄을 만들지 않고 한 줄 안에서 넘치면 자른다.
    """
    if not TSX.exists():
        pytest.skip("컴포넌트 없음")
    s = TSX.read_text(encoding="utf-8")
    i = s.find("function NestBadges")
    assert i > 0
    # 🚨 함수 경계로 정확히 자른다. `\nfunction ` 로 찾으면 파일 끝까지 잡히고(199KB),
    #    고정 길이로 자르면 함수 밖 코드가 섞인다 — 둘 다 내가 1차에 겪은 오탐이다.
    end = s.find("\n}\n", i)
    blk = s[i:end]
    # 🚨 주석 제외 — 이 함수의 경고 주석이 "flexWrap:\"wrap\" 을 되돌리지 말 것" 이라
    #    주석째로 검사하면 경고문 자체가 위반으로 잡힌다(별 테스트에서 같은 형태를 겪었다).
    code = re.sub(r"\s+", " ", re.sub(r"^\s*//.*$", "", blk, flags=re.M))
    assert 'flexWrap: "wrap"' not in code, "배지가 줄바꿈된다 — 행 높이가 늘어난다"
    assert "marginTop" not in code, "배지가 새 줄로 내려간다 — 인라인이어야 한다"
    assert 'display: "inline-flex"' in code, "인라인 배치가 아니다"
    assert 'overflow: "hidden"' in code, "넘칠 때 자르지 않으면 부모를 밀어낸다"
    # 배지를 품는 서브라인도 한 줄로 고정돼야 한다.
    # 🚨 프레이머 포매터가 `whiteSpace:` 와 `"nowrap"` 을 **줄바꿈으로 쪼갠다**
    #    (`size={ 17 }` 처럼 공백도 넣는다). 원문 문자열로 찾으면 라이브 판에서
    #    없는 것처럼 보인다 — 실제로 2026-08-22 에 "속성이 빠졌다" 고 오진할 뻔했다.
    #    그래서 **공백 평탄화 후** 검사한다. 거리 기준(앞 N자)도 주석 길이에 흔들려 못 쓴다.
    j = s.find("<NestBadges")
    assert j > 0, "배지가 어디에도 부착되지 않았다"
    flat = re.sub(r"\s+", " ", s[:j])
    i = flat.rfind("fontSize: 11.5")
    assert i > 0, "배지를 담는 서브라인을 못 찾았다"
    subline = flat[i:]
    assert 'whiteSpace: "nowrap"' in subline, (
        "배지를 담는 줄에 nowrap 이 없다 — 긴 공시 제목에서 줄바꿈된다"
    )
