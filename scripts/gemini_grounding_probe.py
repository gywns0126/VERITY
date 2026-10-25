"""Offline smoke check for the unconditional Google provider retirement."""
from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.utils.google_provider_policy import GoogleProviderDisabled, genai


def main() -> int:
    # A dummy argument proves the policy overrides credential presence. No env
    # credentials, SDK import, request or paid-generation attempt is involved.
    try:
        genai.Client(api_key="policy-smoke-not-a-real-key")
    except GoogleProviderDisabled:
        print(json.dumps({"provider": "google", "status": "disabled_by_policy",
                          "external_calls": 0}))
        return 0
    raise RuntimeError("Google provider retirement did not block construction")


if __name__ == "__main__":
    raise SystemExit(main())
