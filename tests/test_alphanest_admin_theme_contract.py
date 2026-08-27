from pathlib import Path
import re


ROOT = Path(__file__).resolve().parent.parent
SECURITY = ROOT / "framer-components/pages/admin/SecurityCard.tsx"
TOGGLE = ROOT / "framer-components/public-probe/PublicThemeToggle.tsx"


def _function(source: str, name: str) -> str:
    match = re.search(rf"function {name}\([^)]*\)(?:: [^{{]+)? \{{.*?\n\}}", source, re.S)
    assert match, f"missing function: {name}"
    return match.group(0)


def test_security_card_uses_prepaint_theme_signal_first():
    body = _function(SECURITY.read_text(encoding="utf-8"), "readBodyDark")
    executable = "\n".join(
        line for line in body.splitlines() if not line.strip().startswith("//")
    )
    assert executable.index("anTheme") < executable.index("framerTheme") < executable.index("verity_theme")
    assert "matchMedia" not in executable


def test_public_toggle_restores_system_theme_only_without_saved_preference():
    source = TOGGLE.read_text(encoding="utf-8")
    assert 'let initial: Theme = systemTheme()' in source
    assert 'localStorage.getItem(THEME_KEY)' in source
    assert 'document.documentElement.dataset.anTheme = initial' in source
    assert 'document.body.dataset.framerTheme = initial' in source
    assert 'const pref = prefTheme()' in source
