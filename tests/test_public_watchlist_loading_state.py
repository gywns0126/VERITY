from pathlib import Path


COMPONENT = Path("framer-components/public-probe/PublicWatchlist.tsx")


def source() -> str:
    return COMPONENT.read_text(encoding="utf-8")


def test_empty_state_waits_for_both_personal_sources() -> None:
    text = source()
    assert "watchHydrated" in text
    assert 'holdingsStatus === "loading" && rows.length === 0' in text
    assert '!personalDataPending && holdingsStatus === "ready" && rows.length === 0' in text


def test_holdings_refresh_preserves_previous_rows_on_failure() -> None:
    text = source()
    marker = '} catch {\n                if (alive && currentRequest === requestId) setHoldingsStatus("error")'
    start = text.index(marker)
    catch_block = text[start:text.index("        }\n        load()", start)]
    assert 'setHoldingsStatus("error")' in catch_block
    assert "setHeld([])" not in catch_block


def test_stale_holdings_requests_cannot_overwrite_newer_state() -> None:
    text = source()
    assert "const currentRequest = ++requestId" in text
    assert text.count("currentRequest === requestId") >= 3


def test_loading_and_error_copy_are_distinct_from_true_empty_copy() -> None:
    text = source()
    assert "내 종목 불러오는 중" in text
    assert "내 종목을 불러오지 못했어요" in text
    assert "아직 관심종목이 없어요" in text
