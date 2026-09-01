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
    assert before == 6


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
