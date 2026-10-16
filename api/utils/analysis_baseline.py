"""Read a previous completed private analysis only for diagnostic comparison."""
import os

from api.utils.analysis_evidence import capture_previous_analysis


def load_previous_analysis_baseline(portfolio):
    """Do not replace the public/local portfolio used by scoring or selection."""
    baseline = capture_previous_analysis(portfolio)
    baseline["baseline_source"] = "legacy_local"
    baseline["baseline_reason"] = "private_baseline_unavailable"
    if os.environ.get("OPERATOR_BUCKET", "verity-reports") != "verity-reports":
        baseline["baseline_reason"] = "private_bucket_identity_mismatch"
        return baseline
    try:
        # Existing server-only Storage reader; no public fallback or new auth path.
        from api.intelligence import ticker_facts
        memo_token = ticker_facts._PRIVATE_DOCS.set(None)
        try:
            private = ticker_facts._private_json("_operator/portfolio_full.json")
        finally:
            ticker_facts._PRIVATE_DOCS.reset(memo_token)
        if not isinstance(private, dict):
            return baseline
        proof = private.get("analysis_provenance")
        records = private.get("recommendations")
        if (not isinstance(proof, dict) or proof.get("status") != "completed"
                or not isinstance(records, list) or any(not isinstance(r, dict) for r in records)):
            baseline["baseline_reason"] = "private_baseline_not_completed_or_invalid"
            return baseline
        current_run, current_attempt = os.environ.get("GITHUB_RUN_ID"), os.environ.get("GITHUB_RUN_ATTEMPT")
        if (current_run and current_attempt and str(proof.get("analysis_run_id")) == current_run
                and str(proof.get("analysis_run_attempt")) == current_attempt):
            baseline["baseline_reason"] = "private_baseline_is_current_run"
            return baseline
        private_baseline = capture_previous_analysis(private)
        private_baseline["baseline_source"] = "private_storage"
        private_baseline["baseline_reason"] = None
        return private_baseline
    except Exception:
        # No exception/body/header logging: credentials or private data may occur.
        return baseline
