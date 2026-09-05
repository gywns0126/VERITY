from pathlib import Path


COMPONENT = Path("framer-components/public-probe/PublicMorningBriefing.tsx")


def source() -> str:
    return COMPONENT.read_text(encoding="utf-8")


def test_update_panel_is_versioned_and_read_once() -> None:
    text = source()
    assert 'SITE_UPDATE_VERSION = "2026-09-01-home-pulse-v1"' in text
    assert 'localStorage.getItem(SITE_UPDATE_READ_KEY)' in text
    assert 'localStorage.setItem(SITE_UPDATE_READ_KEY, SITE_UPDATE_VERSION)' in text


def test_activity_strip_reuses_brief_without_new_fetch() -> None:
    text = source()
    before = text.count("fetch(")
    pulse = text[text.index("const pulseItems = useMemo"):text.index("const markUpdatesRead")]
    assert "fetch(" not in pulse
    assert "brief.sections" in pulse
    assert before == 7


def test_activity_rotation_respects_motion_and_pause() -> None:
    text = source()
    assert 'matchMedia("(prefers-reduced-motion: reduce)")' in text
    assert "reduceMotion || pulsePaused" in text
    assert "7000" in text
    assert 'onMouseEnter={() => setPulsePaused(true)}' in text


def test_update_surface_has_no_outline_and_keeps_factual_routes() -> None:
    text = source()
    block = text[text.index('id="site-update-panel"'):text.index("{/* ── ① 내 자산 카드 ── */}")]
    assert "borderTop" not in block
    assert 'href: "/nest"' in text
    assert 'href: "/market"' in text
    assert 'href: "/stock"' in text


def test_important_news_uses_existing_public_fact_feed() -> None:
    text = source()
    builder = Path("api/builders/urgent_alerts_builder.py").read_text(encoding="utf-8")
    publish = Path(".github/actions/publish-data/action.yml").read_text(encoding="utf-8")
    workflow = Path(".github/workflows/dart_catalyst_pulse.yml").read_text(encoding="utf-8")
    assert 'urgent_alerts.json' in text
    assert 'OUTPUT_PATH = os.path.join(DATA_DIR, "urgent_alerts.json")' in builder
    assert 'urgent_alerts.json' in publish
    assert 'api.builders.urgent_alerts_builder' in workflow


def test_important_news_is_static_and_bounded() -> None:
    text = source()
    block = text[
        text.index("{/* 중요 소식 — 정지형 목록"):
        text.index("{/* 1면 배너")
    ]
    assert "setInterval" not in block
    assert "pulseIndex" not in block
    assert "animation" not in block
    assert ".slice(0, IMPORTANT_LIMIT)" in text
    assert "const IMPORTANT_LIMIT = 3" in text


def test_important_news_requires_fresh_dart_source() -> None:
    text = source()
    assert "IMPORTANT_MAX_AGE_MS = 72 * 60 * 60 * 1000" in text
    assert 'url.hostname === "dart.fss.or.kr"' in text
    assert "Date.now() - generated > IMPORTANT_MAX_AGE_MS" in text
    assert 'rel="noopener noreferrer"' in text
