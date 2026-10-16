"""Keep new private analysis evidence out of the public source repository.

Capture the completed final portfolio outside the checkout before stripping the
changed data files that the existing broad staging step will include. No private
copy is ever restored into the tracked tree.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

PRIVATE_ANALYSIS_KEYS = frozenset({
    "source_alignment", "fundamental_source_evidence", "_source_evidence", "_source_identity",
    "analysis_change", "analysis_changes", "evidence_snapshot", "rec_price_evidence",
    "input_snapshot", "input_field_hashes",
})


def strip_private_fields(value):
    if isinstance(value, dict):
        return {key: strip_private_fields(item) for key, item in value.items()
                if key not in PRIVATE_ANALYSIS_KEYS}
    if isinstance(value, list):
        return [strip_private_fields(item) for item in value]
    return value


def final_source_paths(root: Path, runner_temp: str, run_id: str, run_attempt: str) -> tuple:
    if not runner_temp or not re.fullmatch(r"[0-9]+", run_id) or not re.fullmatch(r"[0-9]+", run_attempt):
        raise ValueError("private capture context required")
    checkout = root.resolve()
    temp = Path(runner_temp).resolve()
    if temp == checkout or checkout in temp.parents or "\n" in str(temp) or "\r" in str(temp):
        raise ValueError("private capture must be outside checkout")
    directory = temp / f"operator-final-{run_id}-{run_attempt}"
    if directory.is_symlink():
        raise ValueError("private capture directory must not be a symlink")
    return directory / "portfolio.json", directory / "universe_candidates.json"


def _exclusive_copy(path: Path, body: bytes):
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    try:
        with path.open("xb") as handle:
            os.chmod(path, 0o600)
            handle.write(body)
    except FileExistsError:
        if path.is_symlink() or path.read_bytes() != body:
            raise ValueError("private capture conflicts with existing bytes") from None


def capture_final_sources(root: Path, env: dict, now: datetime) -> tuple:
    from scripts.ci.operator_portfolio_delivery import prepare_portfolio_delivery
    portfolio = (root / "data/portfolio.json").read_bytes()
    snapshot = (root / "data/universe_candidates.json").read_bytes()
    # Reuse exactly the uploader's completed/run/scan/hash/freshness contract.
    prepare_portfolio_delivery(portfolio, snapshot,
        run_id=env.get("GITHUB_RUN_ID", ""), run_attempt=env.get("GITHUB_RUN_ATTEMPT", ""),
        expected_scan_id=env.get("UNIVERSE_EXPECTED_SCAN_ID", ""),
        analysis_mode=env.get("ANALYSIS_MODE", ""), verity_mode=env.get("VERITY_MODE", ""),
        phase="final", now=now)
    paths = final_source_paths(root, env.get("RUNNER_TEMP", ""),
                               env.get("GITHUB_RUN_ID", ""), env.get("GITHUB_RUN_ATTEMPT", ""))
    for path, body in zip(paths, (portfolio, snapshot)):
        _exclusive_copy(path, body)
    return paths


def changed_data_paths(root: Path) -> list:
    paths = set()
    for arguments in (["ls-files", "--modified", "--others", "--exclude-standard", "-z", "--", "data/"],
                      ["diff", "--cached", "--name-only", "-z", "--", "data/"]):
        result = subprocess.run(["git", *arguments], cwd=root, check=True, capture_output=True)
        paths.update(item.decode("utf-8") for item in result.stdout.split(b"\0") if item)
    return sorted(paths)


def sanitize_changed_data(root: Path) -> int:
    writes = []
    data_root = (root / "data").resolve()
    for relative in changed_data_paths(root):
        path = root / relative
        if path.is_symlink() or data_root not in path.resolve().parents:
            raise ValueError("data path rejected")
        if not path.exists():
            continue  # Staged/unstaged deletion has no body to publish.
        body = path.read_bytes()
        suffix = path.suffix.lower()
        if suffix not in (".json", ".jsonl"):
            if any((f'"{key}"').encode() in body for key in PRIVATE_ANALYSIS_KEYS):
                raise ValueError("private evidence in unsupported data format")
            continue
        if suffix == ".json":
            document = json.loads(body)
            clean = strip_private_fields(document)
            if clean != document:
                writes.append((path, json.dumps(clean, ensure_ascii=False, indent=2).encode("utf-8")))
        else:
            clean_lines, changed = [], False
            for line in body.splitlines(keepends=True):
                if not line.strip():
                    clean_lines.append(line)
                    continue
                document = json.loads(line)
                clean = strip_private_fields(document)
                if clean != document:
                    changed = True
                    clean_lines.append(json.dumps(clean, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n")
                else:
                    clean_lines.append(line)
            if changed:
                writes.append((path, b"".join(clean_lines)))
    # Parse and validate every path before changing any body.
    for path, body in writes:
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".private-git.tmp", delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(body)
            temporary.replace(path)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()
    return len(writes)


def main() -> int:
    root = Path.cwd()
    try:
        if ("--capture-final" in sys.argv and os.environ.get("ANALYSIS_MODE") in ("full", "full_us")
                and os.environ.get("VERITY_MODE") == "prod"):
            capture_final_sources(root, dict(os.environ), datetime.now(timezone(timedelta(hours=9))))
        changed = sanitize_changed_data(root)
        output = os.environ.get("GITHUB_OUTPUT")
        if output:
            with open(output, "a", encoding="utf-8") as handle:
                handle.write("ready=true\n")
        print(f"private analysis Git boundary: ready; sanitized_files={changed}")
        return 0
    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError):
        print("ERROR: private analysis Git boundary failed; commit blocked", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    sys.exit(main())
