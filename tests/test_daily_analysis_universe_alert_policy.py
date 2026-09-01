from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_daily_analysis_stale_universe_does_not_send_direct_telegram():
    source = (ROOT / "api" / "main.py").read_text(encoding="utf-8")
    start = source.index("if not candidates:")
    end = source.index("print(f\"  최종 후보:", start)
    block = source[start:end]

    assert "_sys.exit(1)" in block
    assert "cron_health_monitor" in block
    assert "send_message(" not in block
    assert "dedupe=False" not in block
