from pathlib import Path

import yaml

from scripts.upload_operator_data_to_supabase import UPLOADS


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "daily_analysis.yml"


def _steps() -> list[dict]:
    doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return doc["jobs"]["analyze"]["steps"]


def test_quick_uploads_operator_portfolio_after_origin_push_before_public_publish():
    steps = _steps()
    names = [step.get("name") for step in steps]
    analysis_i = names.index("Run analysis")
    promote_i = names.index("Promote paper summary to operator portfolio")
    private_i = names.index("Private data sync (Tranche B)")
    commit_i = names.index("Commit & push results")
    upload_i = names.index("Upload operator portfolio to private Supabase Storage")
    publish_i = names.index("Publish hot data to VERITY-data")

    assert analysis_i < promote_i < private_i < commit_i < upload_i < publish_i
    promote = steps[promote_i]
    assert "git diff --quiet -- data/portfolio.dev.json" in promote["run"]
    assert "python scripts/promote_exec_paper_to_portfolio.py" in promote["run"]
    assert 'grep -qx "exec paper promote: 1/1"' in promote["run"]
    upload = steps[upload_i]
    assert upload["env"] == {
        "SUPABASE_URL": "${{ secrets.SUPABASE_URL || vars.SUPABASE_URL }}",
        "SUPABASE_SERVICE_ROLE_KEY": "${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}",
    }
    assert "--only portfolio_full" in upload["run"]
    assert 'grep -qx "operator upload: 1/1"' in upload["run"]


def test_portfolio_full_selector_matches_one_private_object_only():
    selected = [
        item
        for item in UPLOADS
        if "portfolio_full" in item[0] or "portfolio_full" in item[1]
    ]
    assert selected == [
        ("data/portfolio.json", "_operator/portfolio_full.json", "application/json")
    ]
