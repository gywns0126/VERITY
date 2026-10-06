#!/usr/bin/env python3
"""Export harness summaries; --upload explicitly publishes to existing PRIVATE storage.

No data/ artifact, public Blob, scheduled job, model call or trading action.
Publication verifies the bucket is private and reads the exact object back.
"""
import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from api.intelligence import analysis_console, analysis_harness as h, operator_context as ctx


class PublishError(ValueError):
    """Only fixed labels, HTTP status and allowlisted storage codes reach the CLI."""
    def __init__(self, stage, status=None, code="unknown_error"):
        labels = {"metadata": "private bucket verification failed", "upload": "private upload failed",
                  "readback": "private readback mismatch"}
        super().__init__(f"{labels[stage]} [stage={stage} http={status} code={code}]")
        self.stage, self.status, self.code = stage, status, code


def _storage_error(stage, response):
    allowed = {"DatabaseTimeout", "database_timeout", "InvalidJWT", "AccessDenied", "NoSuchBucket",
               "NoSuchKey", "InternalError", "DatabaseError", "SlowDown", "ResourceLocked"}
    try:
        body = response.json()
    except ValueError:
        body = None
    code = "unknown_error"
    if isinstance(body, dict):
        for field in ("code", "error"):
            candidate = body.get(field)
            if isinstance(candidate, str) and candidate in allowed:
                code = candidate
                break
    return PublishError(stage, response.status_code, code)


def _request(stage, method, *args, **kwargs):
    import requests
    try:
        return method(*args, **kwargs)
    except requests.RequestException:
        raise PublishError(stage, code="transport_error") from None


def _json(stage, response):
    try:
        return response.json()
    except ValueError:
        raise PublishError(stage, response.status_code, "invalid_json") from None


def publish(payload):
    import requests
    base = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    # Must match the read-only API's fixed private object location.
    bucket = "verity-reports"
    if not base or not key:
        raise ValueError("private storage credentials missing")
    headers = {"apikey": key, "Authorization": "Bearer " + key}
    check = _request("metadata", requests.get, f"{base}/storage/v1/bucket/{bucket}", headers=headers,
                     timeout=20, allow_redirects=False)
    if check.status_code != 200:
        raise _storage_error("metadata", check)
    metadata = _json("metadata", check)
    if not isinstance(metadata, dict) or metadata.get("public") is not False:
        raise PublishError("metadata", check.status_code, "bucket_not_private")
    url = f"{base}/storage/v1/object/{bucket}/_operator/analysis_reviews.json"
    result = _request("upload", requests.post, url, headers={**headers, "Content-Type": "application/json",
        "x-upsert": "true", "Cache-Control": "no-store"}, data=ctx.encode(payload), timeout=30,
        allow_redirects=False)
    if result.status_code not in (200, 201):
        raise _storage_error("upload", result)
    readback = _request("readback", requests.get, url, headers={**headers, "Cache-Control": "no-store"},
                        timeout=20, allow_redirects=False)
    if readback.status_code != 200:
        raise _storage_error("readback", readback)
    if _json("readback", readback) != payload:
        raise PublishError("readback", readback.status_code, "payload_mismatch")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upload", action="store_true")
    args = parser.parse_args()
    payload = analysis_console.build()
    if not payload["items"]:
        raise ValueError("no prepared packets; refusing to replace console with empty state")
    target = h.RUNTIME / "analysis_reviews.json"
    ctx.atomic_json(target, payload)
    if args.upload:
        publish(payload)
    print(json.dumps(dict(path=str(target), tickers=list(payload["items"]),
        uploaded=args.upload, private_only=True), ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Never print network exception text containing credentials or response bodies.
        detail = str(exc) if isinstance(exc, PublishError) else type(exc).__name__
        print("analysis console export failed: " + detail, file=sys.stderr)
        raise SystemExit(2)
