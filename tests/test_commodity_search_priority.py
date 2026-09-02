from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SEARCH = ROOT / "framer-components" / "public-probe" / "PublicStockSearch.tsx"


def test_direct_commodity_search_precedes_stock_partial_matches():
    text = SEARCH.read_text(encoding="utf-8")

    assert 'String(x?.market || "") === "원자재"' in text
    assert '.startsWith("CMD_")' in text
    assert "if (commodity && (n === s || k === s || words.includes(s))) return 1" in text
    assert "if (n === s || k === s) return 2" in text
    assert "if (n.startsWith(s) || k.startsWith(s)) return 5" in text


def test_enter_and_dropdown_share_the_same_search_rank():
    text = SEARCH.read_text(encoding="utf-8")

    assert text.count(".filter((x) => searchRank(x, s) < 99)") == 2
    assert text.count("searchRank(a, s) - searchRank(b, s)") == 2
    assert "String(x?.kw || \"\").toLowerCase()" in text
