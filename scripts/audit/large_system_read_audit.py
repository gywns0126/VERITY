#!/usr/bin/env python3
"""대형 시스템 정독 체크포인트 생성·검증.

자연어 "읽음" 대신 파일 분모, 전체 줄 범위, 읽기 전후 SHA-256을 증거로 남긴다.
비밀파일은 존재와 역할만 세며 본문·값·해시를 기록하지 않는다.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[2]
LARGE_BYTES = 50_000
LARGE_LINES = 1_000

SCOPES = {
    "alpha-console-front": ("operator-web/",),
    "alpha-console-backend": ("api/", "vercel-api/api/"),
    "alphanest-front": ("framer-components/public-probe/",),
    "alphanest-backend": (
        "api/builders/", "api/collectors/", "vercel-api/api/", ".github/workflows/",
    ),
    "all-sites": (
        "operator-web/", "framer-components/public-probe/", "api/",
        "vercel-api/api/", ".github/workflows/",
    ),
}

_SECRET_PARTS = re.compile(
    r"(^|/)(\.env(?:\.|$)|.*(?:secret|credential|recovery[_-]?key|복구[_ ]?키).*)",
    re.I,
)


def is_sensitive(rel: str) -> bool:
    return bool(_SECRET_PARTS.search(rel))


def sha256_bytes(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def ranges_cover(ranges: Iterable[Iterable[int]], lines: int) -> bool:
    """1-based inclusive ranges의 합집합이 1..lines를 끊김 없이 덮는지."""
    clean = sorted((max(1, int(a)), min(lines, int(b))) for a, b in ranges if int(a) <= int(b))
    if lines <= 0:
        return True
    cursor = 1
    for start, end in clean:
        if end < cursor:
            continue
        if start > cursor:
            return False
        cursor = max(cursor, end + 1)
        if cursor > lines:
            return True
    return cursor > lines


def _git_paths(prefixes: tuple[str, ...]) -> list[str]:
    out = subprocess.check_output(
        ["git", "ls-files", "--", *prefixes], cwd=ROOT, text=True
    ).splitlines()
    return sorted({p for p in out if p and (ROOT / p).is_file()})


def _last_commit_map(prefixes: tuple[str, ...]) -> dict[str, str | None]:
    out = subprocess.check_output(
        ["git", "log", "--format=@@%H", "--name-only", "--", *prefixes],
        cwd=ROOT, text=True, errors="replace",
    )
    current = None
    found: dict[str, str | None] = {}
    for line in out.splitlines():
        if line.startswith("@@"):
            current = line[2:]
        elif line and current and line not in found:
            found[line] = current
    return found


def _symbol_counts(text: str, suffix: str) -> dict[str, int]:
    if suffix == ".py":
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return {"parse_error": 1}
        return {
            "functions": sum(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) for n in ast.walk(tree)),
            "classes": sum(isinstance(n, ast.ClassDef) for n in ast.walk(tree)),
            "imports": sum(isinstance(n, (ast.Import, ast.ImportFrom)) for n in ast.walk(tree)),
        }
    if suffix in {".ts", ".tsx", ".js", ".jsx"}:
        return {
            "functions": len(re.findall(r"\bfunction\s+[A-Za-z_$]", text)),
            "classes": len(re.findall(r"\bclass\s+[A-Za-z_$]", text)),
            "imports": len(re.findall(r"^\s*import\b", text, re.M)),
            "exports": len(re.findall(r"\bexport\b", text)),
            "fetches": len(re.findall(r"\bfetch\s*\(", text)),
        }
    return {}


def file_record(rel: str, last_commit: str | None) -> dict:
    p = ROOT / rel
    size = p.stat().st_size
    base = {"path": rel, "bytes": size, "last_commit": last_commit}
    if is_sensitive(rel):
        return {**base, "kind": "sensitive", "status": "restricted"}
    body = p.read_bytes()
    if b"\0" in body[:8192]:
        return {**base, "kind": "binary", "status": "binary"}
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        return {**base, "kind": "binary_or_non_utf8", "status": "binary"}
    lines = text.count("\n") + (0 if text.endswith("\n") else 1)
    return {
        **base,
        "kind": "text",
        "lines": lines,
        "sha256": sha256_bytes(body),
        "large": size >= LARGE_BYTES or lines >= LARGE_LINES,
        "symbols": _symbol_counts(text, p.suffix.lower()),
        "read_ranges": [],
        "status": "unread",
    }


def inventory(scope: str) -> dict:
    prefixes = SCOPES[scope]
    paths = _git_paths(prefixes)
    commits = _last_commit_map(prefixes)
    files = [file_record(p, commits.get(p)) for p in paths]
    kinds: dict[str, int] = {}
    for rec in files:
        kinds[rec["kind"]] = kinds.get(rec["kind"], 0) + 1
    return {
        "_meta": {
            "schema": "large-system-read-v1",
            "scope": scope,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "large_threshold": {"bytes": LARGE_BYTES, "lines": LARGE_LINES},
            "total_files": len(files),
            "kinds": kinds,
        },
        "files": files,
    }


def verify(checkpoint: dict) -> tuple[dict, int]:
    rows = checkpoint.get("files") or []
    complete = invalidated = incomplete = handled = 0
    problems = []
    for rec in rows:
        rel = str(rec.get("path") or "")
        p = ROOT / rel
        if rec.get("kind") != "text":
            handled += 1
            continue
        if not p.is_file():
            invalidated += 1
            problems.append({"path": rel, "reason": "missing"})
            continue
        body = p.read_bytes()
        current = sha256_bytes(body)
        if current != rec.get("sha256"):
            invalidated += 1
            problems.append({"path": rel, "reason": "sha256_changed"})
            continue
        lines = int(rec.get("lines") or 0)
        if ranges_cover(rec.get("read_ranges") or [], lines):
            complete += 1
        else:
            incomplete += 1
            problems.append({"path": rel, "reason": "line_coverage_incomplete"})
    total = len(rows)
    report = {
        "total": total, "complete_text": complete, "handled_nontext": handled,
        "invalidated": invalidated, "incomplete_text": incomplete,
        "accepted": complete + handled, "problems": problems,
    }
    return report, 0 if complete + handled == total else 1


def _write_or_print(doc: dict, output: str | None) -> None:
    text = json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
    if output:
        Path(output).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    inv = sub.add_parser("inventory")
    inv.add_argument("--scope", choices=sorted(SCOPES), default="all-sites")
    inv.add_argument("--output")
    ver = sub.add_parser("verify")
    ver.add_argument("checkpoint")
    args = ap.parse_args()
    if args.cmd == "inventory":
        _write_or_print(inventory(args.scope), args.output)
        return 0
    checkpoint = json.loads(Path(args.checkpoint).read_text(encoding="utf-8"))
    report, code = verify(checkpoint)
    _write_or_print(report, None)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
