from pathlib import Path


COMPONENT = Path("framer-components/public-probe/PublicMorningBriefing.tsx")


def source() -> str:
    return COMPONENT.read_text(encoding="utf-8")


def test_now_and_embedded_editorial_are_removed() -> None:
    text = source()
    for retired in ("SITE_UPDATE_VERSION", "setUpdatesOpen", "pulseItems", "pulseIndex", "pulsePaused", "HomeMasterStocks", "EditorialNews"):
        assert retired not in text


def test_reorganized_home_keeps_existing_seven_fetch_sites() -> None:
    text = source()
    assert text.count("fetch(") == 7
    assert "nest_briefing_index.json" in text
    assert "nps_holdings.json" in text


def test_only_existing_data_refresh_and_search_css_motion_remain() -> None:
    text = source()
    assert "prefers-reduced-motion:reduce" in text
    assert "setPulseIndex" not in text
    assert "setNowTick" in text


def test_order_and_anchor_contract() -> None:
    text = source()
    assert text.index("<PublicHomeSearch") < text.index("{!authReady ?") < text.index("<PublicHomeOverview")
    for anchor in ("home-search", "home-filing-example", "home-changes"):
        assert f'id="{anchor}"' in text
    assert 'href="/nest"' in text
    assert 'href="/market"' in text


def test_important_news_uses_existing_public_fact_feed() -> None:
    text = source()
    builder = Path("api/builders/urgent_alerts_builder.py").read_text(encoding="utf-8")
    publish = Path(".github/actions/publish-data/action.yml").read_text(encoding="utf-8")
    workflow = Path(".github/workflows/dart_catalyst_pulse.yml").read_text(encoding="utf-8")
    assert 'urgent_alerts.json' in text
    assert 'OUTPUT_PATH = os.path.join(DATA_DIR, "urgent_alerts.json")' in builder
    assert 'urgent_alerts.json' in publish
    assert 'api.builders.urgent_alerts_builder' in workflow


def test_additional_briefing_is_unique_static_and_bounded() -> None:
    text = source()
    block = text[text.index("<details style={card} data-home-briefing>"):]
    assert "setInterval" not in block
    assert "pulseIndex" not in block
    assert "animation" not in block
    assert ".slice(0, PER_SECTION)" in text
    assert "const PER_SECTION = 3" in text
    assert 'new Set(["밤사이 미국 공시", "최근 7일 내부자 변동", "이번 주 실적 공시 예상"])' in text


def test_important_news_requires_fresh_dart_source() -> None:
    text = source()
    assert "IMPORTANT_MAX_AGE_MS = 72 * 60 * 60 * 1000" in text
    assert 'url.hostname !== "dart.fss.or.kr"' in text
    assert "now - generated <= IMPORTANT_MAX_AGE_MS" in text
    assert "briefFresh && importantFresh" in text
    assert 'rel="noopener noreferrer"' in text
