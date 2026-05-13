"""
test_estate_macro_bridge.py — _build_bridge 산식 + narrative 검증.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
EP = ROOT / "vercel-api" / "api" / "estate_macro_bridge.py"
spec = importlib.util.spec_from_file_location("estate_macro_bridge", str(EP))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def _snapshot(policy_rate=2.5, gov10y=4.0, gov10y_yoy=0.5, usd_krw=1450, usd_chg=0.5, vix=18.0, vix_1m=-0.5):
    return {
        "collected_at": "2026-05-13T20:00:00+09:00",
        "macro": {
            "usd_krw": {"value": usd_krw, "change_pct": usd_chg, "as_of": "2026-05-13T20:00:00+09:00"},
            "ecos": {
                "korea_policy_rate": {"value": policy_rate, "date": "202604", "unit": "연%"},
                "korea_gov_10y": {"value": gov10y, "yoy_pp": gov10y_yoy, "date": "2026-05-13"},
            },
            "fred": {
                "vix_close": {"value": vix, "date": "2026-05-12", "trend": {"1m": {"change": vix_1m}}},
            },
        },
    }


def test_build_bridge_extracts_4_indicators():
    s = _snapshot()
    out = mod._build_bridge(s)
    assert set(out["indicators"].keys()) == {"korea_policy_rate", "korea_gov_10y", "usd_krw", "vix"}
    assert out["indicators"]["korea_policy_rate"]["value"] == 2.5
    assert out["indicators"]["korea_gov_10y"]["value"] == 4.0
    assert out["indicators"]["usd_krw"]["value"] == 1450
    assert out["indicators"]["vix"]["value"] == 18.0


def test_policy_rate_narrative_high():
    s = _snapshot(policy_rate=4.0)
    out = mod._build_bridge(s)
    assert "고금리" in out["indicators"]["korea_policy_rate"]["narrative"]


def test_policy_rate_narrative_low():
    s = _snapshot(policy_rate=1.0)
    out = mod._build_bridge(s)
    assert "저금리" in out["indicators"]["korea_policy_rate"]["narrative"]


def test_gov10y_yoy_surge_marks_pressure():
    s = _snapshot(gov10y=4.5, gov10y_yoy=1.5)
    out = mod._build_bridge(s)
    narr = out["indicators"]["korea_gov_10y"]["narrative"]
    assert "급등" in narr
    assert "valuation discount" in narr


def test_usd_krw_surge_invites_foreign_buy():
    s = _snapshot(usd_krw=1500, usd_chg=2.0)
    out = mod._build_bridge(s)
    narr = out["indicators"]["usd_krw"]["narrative"]
    assert "원화 급락" in narr
    assert "외국인" in narr


def test_vix_high_safe_haven():
    s = _snapshot(vix=28.0)
    out = mod._build_bridge(s)
    assert "고변동" in out["indicators"]["vix"]["narrative"]
    assert "안전자산" in out["indicators"]["vix"]["narrative"]


def test_overall_verdict_pressure_when_multiple_high():
    s = _snapshot(policy_rate=4.0, gov10y_yoy=1.5, usd_krw=1500, usd_chg=2.0, vix=18.0)
    out = mod._build_bridge(s)
    assert out["pressure_count"] >= 1


def test_missing_value_falls_back():
    s = {"collected_at": "2026-05-13T20:00:00+09:00", "macro": {}}
    out = mod._build_bridge(s)
    for k in ("korea_policy_rate", "korea_gov_10y", "usd_krw", "vix"):
        narr = out["indicators"][k]["narrative"]
        assert "데이터 부재" in narr
