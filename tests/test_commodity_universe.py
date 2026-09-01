from pathlib import Path
import ast


ROOT = Path(__file__).parents[1]
BUILDER = ROOT / "api" / "builders" / "krx_mktcap_snapshot.py"


def _commodity_rows():
    tree = ast.parse(BUILDER.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "_COMMODITY_UNIVERSE" for target in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError("_COMMODITY_UNIVERSE not found")


def test_direct_commodity_search_contract_is_complete_and_unique():
    rows = _commodity_rows()
    assert len(rows) == 12
    assert len({row[0] for row in rows}) == 12
    assert len({row[2] for row in rows}) == 12
    assert {row[0] for row in rows} >= {"CMD_GOLD", "CMD_WTI", "CMD_COPPER", "CMD_WHEAT"}
    assert all(row[4] == "USD" and row[5] and row[6] and row[7] for row in rows)


def test_commodity_report_covers_every_search_entry():
    body = (ROOT / "framer-components" / "public-probe" / "PublicCommodityReport.tsx").read_text(encoding="utf-8")
    for ticker, *_ in _commodity_rows():
        assert f'ticker: "{ticker}"' in body
    assert "선물 연속물" in body
    assert "롤오버" in body
    assert "지연 가능" in body
