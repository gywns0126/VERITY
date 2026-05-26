#!/usr/bin/env python3
"""sync_memory_to_vault — Claude 메모리 → verity-methodology-vault Quartz content mirror.

frontmatter `publish: true` 박힌 메모리만 vault content/ 로 mirror.

CLAUDE.md RULE 6 정합:
  - 자기 trail (Brain v5 임계 / Phase 0 / Lynch 등) 공개 노출 = LLM 무료 tier 못 가지는 차별점
  - 사용자 메타 / 사고 history / PM 발화 trail = 영구 비공개

PM 결정 trail: [[project_brain_self_trail_strengthening_2026_05_25]]
Sprint plan: docs/Q2_OBSIDIAN_QUARTZ_SPRINT_PLAN_20260526.md (단계 4-4)
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import yaml

DEFAULT_MEMORY_DIR = Path.home() / ".claude" / "projects" / "-Users-macbookpro-Desktop--------" / "memory"
DEFAULT_VAULT_DIR = Path.home() / "Desktop" / "verity-methodology-vault"

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def parse_frontmatter(text: str) -> Tuple[Dict[str, str], str]:
    """frontmatter 를 dict 로 파싱 + body 분리. 메모리는 비표준 YAML (콜론/따옴표 mix)
    가 흔해서 line-based parse 사용 (PyYAML strict 실패 회피).
    """
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    raw = m.group(1)
    fm: Dict[str, str] = {}
    for line in raw.split("\n"):
        if not line or line.startswith(" ") or line.startswith("\t"):
            continue
        if ":" in line:
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip()
    return fm, text[m.end():]


def is_published(fm: Dict[str, str]) -> bool:
    return fm.get("publish", "").lower() == "true"


def emit_frontmatter(fm: Dict[str, str]) -> str:
    """Quartz 호환 frontmatter — PyYAML safe_dump 으로 escape 보장."""
    # Quartz 권장: title 필드. description / publish / type 만 박음.
    safe = {
        "title": fm.get("name", ""),
        "description": fm.get("description", ""),
        "publish": True,
    }
    for k in ("type", "originSessionId"):
        if k in fm:
            safe[k] = fm[k]
    body = yaml.safe_dump(safe, allow_unicode=True, sort_keys=False, default_flow_style=False)
    return f"---\n{body}---\n"


def collect_published(memory_dir: Path) -> List[Tuple[Path, Dict[str, str], str]]:
    """publish: true 박힌 .md 파일들 수집. MEMORY.md (index) 는 항상 제외."""
    out = []
    for p in sorted(memory_dir.glob("*.md")):
        if p.name == "MEMORY.md":
            continue
        text = p.read_text(encoding="utf-8")
        fm, body = parse_frontmatter(text)
        if fm and is_published(fm):
            out.append((p, fm, body))
    return out


def write_index(vault_content: Path, entries: List[Tuple[Path, Dict[str, str], str]]) -> None:
    """vault content/index.md 생성 — whitelist 목차."""
    head_fm = {"title": "VERITY Methodology"}
    fm_block = "---\n" + yaml.safe_dump(head_fm, allow_unicode=True, sort_keys=False) + "---\n"
    lines = [
        fm_block,
        "# VERITY Methodology — 자기 trail",
        "",
        "1인 베타 단계 (38일+) 의 자기 산식 / 자기 운영 trail / Brain v5 임계 / Phase 0 KIS 정책.",
        "LLM 무료 tier 가 못 가지는 차별점 자산.",
        "",
        "> 모든 자기 산식 = **가설 (N=Phase 0 ~14일, VAMS reset 5/17 후)**. 365일 trail 도달 (~2027-05) 전 통계 무의미.",
        "> hit rate 는 expectancy + sample size + CI 와 병기 의무.",
        "",
        "## Topic index",
        "",
    ]
    for p, fm, _ in entries:
        stem = p.stem
        desc = fm.get("description", "")
        lines.append(f"- [[{stem}]] — {desc}")
    lines.append("")
    (vault_content / "index.md").write_text("\n".join(lines), encoding="utf-8")


def sync(memory_dir: Path, vault_dir: Path, dry_run: bool = False) -> int:
    if not memory_dir.exists():
        print(f"❌ memory dir 미존재: {memory_dir}", file=sys.stderr)
        return 1
    if not vault_dir.exists():
        print(f"❌ vault dir 미존재: {vault_dir}", file=sys.stderr)
        return 1

    vault_content = vault_dir / "content"
    entries = collect_published(memory_dir)
    print(f"publish: true 박힌 메모리: {len(entries)} 건")

    if dry_run:
        for p, _, _ in entries:
            print(f"  [DRY] {p.name}")
        return 0

    # 기존 content 비우기 (Quartz 가 자동 처리)
    for old in vault_content.glob("*.md"):
        old.unlink()
    print(f"기존 .md cleared")

    # 메모리 파일 sanitize-emit (frontmatter YAML safe_dump)
    for p, fm, body in entries:
        dst = vault_content / p.name
        out = emit_frontmatter(fm) + body
        dst.write_text(out, encoding="utf-8")
        print(f"  ✓ {p.name}")

    # index.md 생성
    write_index(vault_content, entries)
    print(f"  ✓ index.md (목차)")

    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--memory-dir", type=Path, default=DEFAULT_MEMORY_DIR)
    ap.add_argument("--vault-dir", type=Path, default=DEFAULT_VAULT_DIR)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    return sync(args.memory_dir, args.vault_dir, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
