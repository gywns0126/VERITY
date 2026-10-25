"""Bounded document reading through the Mini's existing signed-in Codex CLI.

No API-key fallback, automatic retry, shell commands supplied by a model, or
Google transport. Source receipts survive failure so an uncertain run is not
silently charged to the account again on the next calendar event.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any


def strict_json(raw: str | bytes) -> Any:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate_json_key")
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite_json")))


def protocol_event(raw: str, counters: dict[str, int]) -> dict:
    """Read control fields strictly; opaque CLI search metadata is not evidence.

    The CLI can repeat fields inside its search payload. We consume only event
    type and item type, and never derive source facts from this event payload.
    Ambiguous control fields still fail closed; result/source JSON stays strict.
    """
    class Pairs(list):
        pass

    def convert(value, path=()):
        if isinstance(value, Pairs):
            result = {}
            for key, child in value:
                child = convert(child, path + (key,))
                if key in result:
                    controlling = (path == () and key in {"type", "item"}) or (path == ("item",) and key == "type")
                    same = json.dumps(result[key], sort_keys=True) == json.dumps(child, sort_keys=True)
                    if controlling and not same:
                        raise ValueError("ambiguous_protocol_control")
                    name = "identical" if same else "unused_metadata"
                    counters[name] = counters.get(name, 0) + 1
                result[key] = child
            return result
        if isinstance(value, list):
            return [convert(child, path + ("[]",)) for child in value]
        return value

    value = convert(json.loads(raw, object_pairs_hook=Pairs,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite_json"))))
    if not isinstance(value, dict) or not isinstance(value.get("type"), str):
        raise ValueError("codex_protocol_shape")
    item = value.get("item")
    if item is not None and (not isinstance(item, dict) or not isinstance(item.get("type"), str)):
        raise ValueError("codex_protocol_shape")
    return value


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink():
        raise ValueError("receipt_symlink")
    body = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()
    descriptor, name = tempfile.mkstemp(prefix=".receipt-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            os.fchmod(handle.fileno(), 0o600)
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def cli_environment(source: dict[str, str] | None = None) -> dict[str, str]:
    source = os.environ if source is None else source
    # CLI account authentication stays in its original HOME. Provider secrets
    # from the collector/uploader environment never enter the model subprocess.
    return {key: source[key] for key in
            ("HOME", "PATH", "TMPDIR", "LANG", "LC_ALL", "USER") if key in source}


def command(cli: Path, directory: Path, *, model: str, search: bool) -> list[str]:
    arguments = [str(cli)]
    # The managed CLI requires its internal host even with code_mode disabled.
    # Owner approved this bridge on 2026-10-26; shell/MCP/apps stay disabled.
    arguments += ["--enable", "code_mode_host"]
    for feature in ("shell_tool", "unified_exec", "shell_snapshot", "code_mode",
                    "apps", "plugins", "multi_agent", "multi_agent_v2", "browser_use", "browser_use_external",
                    "computer_use", "image_generation", "view_image", "hooks", "memories",
                    "skill_mcp_dependency_install", "skill_search", "workspace_dependencies"):
        arguments += ["--disable", feature]
    if search:
        arguments.append("--search")
    arguments += ["exec", "--ephemeral", "--skip-git-repo-check", "--sandbox", "read-only",
                  "--model", model, "-c", 'model_provider="openai"',
                  "-c", "mcp_servers={}", "-c", "mcp_servers.node_repl.enabled=false",
                  "-c", 'web_search="live"' if search else 'web_search="disabled"',
                  "-c", 'model_reasoning_effort="low"', "-c", 'approval_policy="never"',
                  "--color", "never", "--json", "--output-schema", str(directory / "schema.json"),
                  "--output-last-message", str(directory / "result.json"), "--cd", str(directory), "-"]
    return arguments


def read_json_with_codex(prompt: str, *, cli: Path, model: str, runtime: Path,
                         identity: str, search: bool = False, timeout: int = 240,
                         executor=subprocess.run) -> tuple[dict, dict]:
    fingerprint = hashlib.sha256(identity.encode()).hexdigest()
    directory = runtime / "requests" / fingerprint
    receipt_path = directory / "receipt.json"
    if receipt_path.exists():
        previous = strict_json(receipt_path.read_bytes())
        if previous.get("status") == "done":
            allowed = {"agent_message", "reasoning", "todo_list"} | ({"web_search"} if search else set())
            if (set(previous.get("item_types", [])) - allowed
                    or previous.get("completed_events", 0) < 1):
                raise ValueError("saved_receipt_requires_review")
            body = (directory / "result.json").read_bytes()
            if hashlib.sha256(body).hexdigest() != previous.get("result_sha256"):
                raise ValueError("saved_result_changed")
            return strict_json(body), dict(previous, reused=True)
        raise ValueError("previous_request_requires_review")
    directory.mkdir(parents=True, mode=0o700)
    schema = {"type": "object", "properties": {"result_json": {"type": "string"}},
              "required": ["result_json"], "additionalProperties": False}
    atomic_json(directory / "schema.json", schema)
    receipt = {"schema": "mini-document-request-v1", "status": "running", "model": model,
               "provider": "codex-cli", "google_calls": 0, "identity_sha256": fingerprint,
               "ai_invocations": 1, "search": search, "reused": False}
    atomic_json(receipt_path, receipt)  # Durable before the single invocation.
    try:
        result = executor(command(cli, directory, model=model, search=search),
                          input=prompt + "\nReturn the requested JSON serialized as result_json.\n",
                          text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          env=cli_environment(), timeout=timeout, check=False)
        if result.returncode != 0:
            receipt["child_returncode"] = result.returncode
            diagnostic = (result.stderr or "").lower()
            receipt["diagnostics"] = [name for name, marker in (
                ("unsupported_argument", "unexpected argument"),
                ("authentication", "authentication"), ("usage_limit", "usage limit"),
                ("model_unavailable", "not supported"), ("sandbox", "sandbox")) if marker in diagnostic]
            raise ValueError("codex_nonzero")
        duplicates: dict[str, int] = {}
        events = [protocol_event(line, duplicates)
                  for line in result.stdout.splitlines() if line.strip()]
        receipt["protocol_identical_duplicate_keys"] = duplicates.get("identical", 0)
        receipt["protocol_unused_metadata_duplicate_keys"] = duplicates.get("unused_metadata", 0)
        if (not any(event.get("type") == "turn.completed" for event in events)
                or any(event.get("type") in ("turn.failed", "error") for event in events)):
            raise ValueError("codex_protocol_incomplete")
        item_types = {event.get("item", {}).get("type") for event in events if isinstance(event.get("item"), dict)}
        if "error" in item_types:
            receipt["diagnostics"] = ["reader_item_error"]
            raise ValueError("codex_reader_item_error")
        allowed = {"agent_message", "reasoning", "todo_list"} | ({"web_search"} if search else set())
        if item_types - allowed:
            raise ValueError("unexpected_reader_tool")
        body = (directory / "result.json").read_bytes()
        if len(body) > 1_048_576:
            raise ValueError("result_too_large")
        envelope = strict_json(body)
        if set(envelope) != {"result_json"} or not isinstance(envelope["result_json"], str):
            raise ValueError("invalid_codex_result")
        value = strict_json(envelope["result_json"])
        if not isinstance(value, dict):
            raise ValueError("result_must_be_object")
        # Retain only the structured result and small protocol counters, never
        # model reasoning, tool output, authentication or raw command logs.
        atomic_json(directory / "result.json", value)
        saved = (directory / "result.json").read_bytes()
        receipt.update(status="done", completed_at=datetime.now(timezone.utc).isoformat(),
                       result_sha256=hashlib.sha256(saved).hexdigest(),
                       item_types=sorted(t for t in item_types if isinstance(t, str)),
                       completed_events=sum(e.get("type") == "turn.completed" for e in events))
        atomic_json(receipt_path, receipt)
        return value, receipt
    except Exception as exc:
        receipt.update(status="uncertain", error_type=type(exc).__name__)
        if isinstance(exc, ValueError) and str(exc).replace("_", "").isalpha() and len(str(exc)) <= 80:
            receipt["reason"] = str(exc)
        atomic_json(receipt_path, receipt)
        raise
