from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "operator-web" / "app" / "globals.css"
THEME = ROOT / "operator-web" / "lib" / "theme.ts"
LAYOUT = ROOT / "operator-web" / "app" / "layout.tsx"

TOKENS = {
    "bg", "card", "ink", "sub", "faint", "line", "track", "hi", "vt", "vt-s",
    "up", "down", "up-s", "down-s", "green", "green-s", "amber", "amber-s",
    "field", "hover",
}


def test_theme_tokens_cover_light_dark_and_system_fallbacks():
    css = CSS.read_text(encoding="utf-8")
    for token in TOKENS:
        declarations = re.findall(rf"--af-{re.escape(token)}\s*:", css)
        assert len(declarations) == 4, (token, len(declarations))
    assert ':root[data-theme="dark"]' in css
    assert ':root[data-theme="light"]' in css
    assert "@media (prefers-color-scheme: dark)" in css


def test_component_palette_uses_css_variables_only():
    source = THEME.read_text(encoding="utf-8")
    palette = source.split("const CSS_PALETTE = {", 1)[1].split("}\n\nexport type Palette", 1)[0]
    refs = set(re.findall(r"var\(--af-([a-z-]+)\)", palette))
    assert refs == TOKENS - {"hover"}
    assert 'return "var(--af-hover)"' in source


def test_theme_is_selected_before_hydration():
    layout = LAYOUT.read_text(encoding="utf-8")
    assert "data-verity-theme-bootstrap" in layout
    assert 'localStorage.getItem("verity_theme")' in layout
    assert 'matchMedia("(prefers-color-scheme: dark)")' in layout
    assert "suppressHydrationWarning" in layout


def test_fields_and_hover_do_not_depend_on_delayed_react_state():
    files = list((ROOT / "operator-web" / "app").rglob("*.tsx"))
    source = "\n".join(path.read_text(encoding="utf-8") for path in files)
    assert "dark ? c.bg : c.track" not in source
    assert 'dark ? "rgba(169,155,255' not in source


def test_iframe_receives_resolved_color_value():
    chart = (ROOT / "operator-web" / "app" / "components" / "TVChart.tsx").read_text(encoding="utf-8")
    assert "rawPalette(dark)" in chart
    assert "tvWidgetHtml(sym, dark, raw.card)" in chart
