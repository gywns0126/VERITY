"""Paid analyst-report AI generation stays retired."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_scheduled_paid_analyst_report_workflow_is_absent():
    assert not (ROOT / ".github/workflows/analyst_reports.yml").exists()


def test_generated_analyst_ai_summary_ledger_is_absent():
    assert not (ROOT / "data/report_summaries.json").exists()


def test_paid_analyst_ai_runtime_is_absent():
    assert not (ROOT / "scripts/analyst_reports_cron.py").exists()
    assert not (ROOT / "api/analyzers/report_summarizer.py").exists()


def test_no_workflow_invokes_report_summarizer():
    workflow_dir = ROOT / ".github/workflows"
    active = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(workflow_dir.glob("*.y*ml"))
    )
    assert "run_report_summarizer" not in active
    assert "scripts/analyst_reports_cron.py" not in active
