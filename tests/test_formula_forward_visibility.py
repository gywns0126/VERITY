import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADMIN = ROOT / "vercel-api" / "api" / "admin.py"


def _load_admin():
    spec = importlib.util.spec_from_file_location("verity_admin_formula_run_test", ADMIN)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_terminal_slim_payload_includes_formula_forward_run(monkeypatch):
    admin = _load_admin()
    payload = {
        "updated_at": "2026-09-01T22:00:00+09:00",
        "exec_paper": {"version": "v1-ranked-forward-20260901", "equity": 10_000_000},
        "recommendations": [],
    }
    monkeypatch.setattr(admin, "fetch_portfolio", lambda: payload)
    out = admin.handle_portfolio_terminal(None)
    assert out["_status"] == 200
    assert out["_body"]["exec_paper"]["version"] == "v1-ranked-forward-20260901"


def test_system_page_renders_formula_forward_card():
    page = (ROOT / "operator-web" / "app" / "system" / "page.tsx").read_text(encoding="utf-8")
    types = (ROOT / "operator-web" / "lib" / "types.ts").read_text(encoding="utf-8")
    assert 'import FormulaRunCard from "../components/FormulaRunCard"' in page
    assert "<FormulaRunCard run={pf?.exec_paper} status={pfStatus} />" in page
    assert "exec_paper?: FormulaRun" in types
    assert "price_snapshot?:" in types
