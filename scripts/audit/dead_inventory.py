# -*- coding: utf-8 -*-
"""dead_inventory — 폐기 후보 전수 재고 (주의 아닌 기계 열거). 2026-08-16 신설.

왜: "지울 게 더 있나" 를 눈으로 세면 매번 다른 답이 나온다. 실측 —
같은 질문에 감사(8/15)는 DEAD 13, 1차 스캐너는 12, 정본은 아래 수치다. 차이의 원인이
전부 **도구가 분모를 잘못 잰 것**이었다 (정규식 상대 import 미해석 → 패키지 __init__
재수출 미해석). 그래서 열거를 코드로 고정한다 (RULE 13 · STRUCTURAL_GUARD 층C).

🚨 이 스캐너가 과거에 틀린 방식 3종 (재도입 금지):
  1. 정규식 import 매칭 — 상대 import(`from .x import y`) 못 읽어 DEAD 과다
  2. 패키지 import 미해석 — `from api.observability import X` 가 __init__.py 로 가야 한다.
     안 하면 __init__ 재수출 모듈(trust_score·run_tracer·fixtures)이 DEAD 로 오분류
  3. basename substring 검색 — `portfolio`·`regime` 같은 흔한 낱말이 대량 오탐

분류: LIVE(워크플로·서버·vercel 도달) / TEST_ONLY / ORPHAN_CLI(__main__ 수동실행) / DEAD.
추가 스캔: constitution 키 소비 · data 참조(디렉터리+동적명) · 0바이트 · 중복 · 워크플로 무결.
사용: python3 scripts/audit/dead_inventory.py [--json]
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PKG_DIRS = ["api", "scripts", "server", "vercel-api", "tests"]
EXTRA_PY_DIRS = [".github/actions"]          # 워크플로 액션 파이썬 (진입점 취급)
SKIP = ("__pycache__", "/.venv", "/node_modules", "/.next/", "/.git/", "/estate/")


def _walk_py(dirs: list[str]) -> list[str]:
    out = []
    for d in dirs:
        base = os.path.join(ROOT, d)
        if not os.path.isdir(base):
            continue
        for dp, _, fs in os.walk(base):
            if any(s in dp + "/" for s in SKIP):
                continue
            out += [os.path.join(dp, f) for f in fs if f.endswith(".py")]
    return sorted(out)


def rel(p: str) -> str:
    return os.path.relpath(p, ROOT)


def dotted(p: str) -> str:
    d = rel(p)[:-3].replace("/", ".")
    return d[:-len(".__init__")] if d.endswith(".__init__") else d


def build_graph(files: list[str]):
    src = {}
    for p in files:
        try:
            src[p] = open(p, encoding="utf-8", errors="ignore").read()
        except OSError:
            pass
    by_dotted: dict[str, str] = {}
    for p in src:                       # 패키지명 → __init__.py 로 해석 (오분류 원인 #2)
        by_dotted[dotted(p)] = p
    by_leaf: dict[str, set] = defaultdict(set)
    for p in src:
        by_leaf[dotted(p).split(".")[-1]].add(p)

    imports: dict[str, set] = defaultdict(set)
    parse_fail = []
    for p, s in src.items():
        try:
            tree = ast.parse(s)
        except SyntaxError as e:
            parse_fail.append((rel(p), str(e)[:60]))
            continue
        pkg = dotted(p) if p.endswith("__init__.py") else dotted(p).rsplit(".", 1)[0]
        for node in ast.walk(tree):
            targets: list[str] = []
            if isinstance(node, ast.Import):
                targets = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level:                                   # 상대 import (원인 #1)
                    parts = pkg.split(".")
                    parts = parts[:len(parts) - (node.level - 1)] if node.level > 1 else parts
                    mod = ".".join(parts + ([node.module] if node.module else []))
                elif node.module:
                    mod = node.module
                else:
                    continue
                targets = [mod] + [f"{mod}.{a.name}" for a in node.names]
            for t in targets:
                if t in by_dotted and by_dotted[t] != p:
                    imports[p].add(by_dotted[t])
                    continue
                for anc in [".".join(t.split(".")[:i]) for i in range(len(t.split(".")), 0, -1)]:
                    if anc in by_dotted and by_dotted[anc] != p:  # 부모 패키지 __init__ 도달
                        imports[p].add(by_dotted[anc])
                        break
                else:
                    cand = by_leaf.get(t.split(".")[-1], set()) - {p}
                    if len(cand) == 1:
                        imports[p] |= cand
    return src, imports, by_dotted, by_leaf, parse_fail


def workflow_entries(src, by_dotted, by_leaf):
    wf_dir = os.path.join(ROOT, ".github", "workflows")
    wfs = sorted(os.path.join(wf_dir, f) for f in os.listdir(wf_dir)
                 if f.endswith((".yml", ".yaml")))
    entries, broken, norefs = set(), [], []
    for f in wfs:
        t = open(f, encoding="utf-8", errors="ignore").read()
        refs = set()
        for m in re.finditer(r"(?:python3?|uv run)\s+(?:-m\s+([\w.]+)|([\w./\-]+\.py))", t):
            mod, path = m.group(1), m.group(2)
            if mod:
                if mod in by_dotted:
                    refs.add(by_dotted[mod])
                else:
                    c = by_leaf.get(mod.split(".")[-1], set())
                    if len(c) == 1:
                        refs.add(next(iter(c)))
                continue
            ap = os.path.join(ROOT, path)
            if ap in src:
                refs.add(ap)
            elif not os.path.exists(ap):
                broken.append((os.path.basename(f), path))
        if not refs:
            norefs.append(os.path.basename(f))
        entries |= refs
    return wfs, entries, broken, norefs


def closure(seeds: set, imports) -> set:
    seen, stack = set(seeds), list(seeds)
    while stack:
        for nxt in imports.get(stack.pop(), ()):
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return seen


def scan_modules(report: dict) -> None:
    files = _walk_py(PKG_DIRS) + _walk_py(EXTRA_PY_DIRS)
    src, imports, by_dotted, by_leaf, parse_fail = build_graph(files)
    wfs, entry_wf, broken, norefs = workflow_entries(src, by_dotted, by_leaf)
    entry_serverless = {p for p in src if rel(p).startswith(("vercel-api/api/", "server/", ".github/actions/"))}
    entry_main = {p for p in src if re.search(r'^if __name__\s*==\s*[\'"]__main__', src[p], re.M)}
    entry_tests = {p for p in src if rel(p).startswith("tests/")}

    live = closure(entry_wf | entry_serverless, imports)
    test_only = closure(entry_tests, imports) - live - entry_tests
    cli = closure(entry_main, imports) - live - test_only
    dead = {p for p in set(src) - live - test_only - cli - entry_tests
            if not p.endswith("__init__.py")}

    report["modules"] = {
        "denominator": len(src), "live": len(live), "test_only": len(test_only),
        "orphan_cli": len(cli), "dead": len(dead), "parse_fail": parse_fail,
        "dead_files": [{"f": rel(p), "lines": src[p].count("\n")} for p in sorted(dead)],
        "test_only_files": [rel(p) for p in sorted(test_only)],
        "workflows": len(wfs), "workflow_broken_refs": broken,
        "workflow_no_python": len(norefs),
    }


def scan_constitution(report: dict) -> None:
    """헌법 키 소비 실측 — 리터럴 접근만 셈. 동적 접근은 못 재므로 '미확인' 으로 표기."""
    cpath = os.path.join(ROOT, "data", "verity_constitution.json")
    const = json.load(open(cpath, encoding="utf-8"))
    corpus = []
    for d in ["api", "scripts", "server", "vercel-api", ".github"]:
        for dp, _, fs in os.walk(os.path.join(ROOT, d)):
            if any(s in dp + "/" for s in SKIP):
                continue
            for f in fs:
                if f.endswith((".py", ".yml", ".yaml")):
                    try:
                        corpus.append(open(os.path.join(dp, f), encoding="utf-8",
                                           errors="ignore").read())
                    except OSError:
                        pass
    blob = "\n".join(corpus)
    rows = []
    for k, v in const.items():
        if k.startswith("_"):
            continue
        hits = len(re.findall(rf'["\']{re.escape(k)}["\']', blob))
        subs = []
        if isinstance(v, dict):
            for sk in v:
                if sk.startswith("_") or sk == "description":
                    continue
                subs.append({"key": sk, "hits": len(re.findall(rf'["\']{re.escape(sk)}["\']', blob))})
        rows.append({"key": k, "hits": hits, "subs": subs})
    report["constitution"] = {"denominator": len(rows), "rows": rows}


def scan_data(report: dict) -> None:
    """추적 data 파일 참조 — 최상위는 개별, 하위는 디렉터리 단위(동적 파일명 대응)."""
    import subprocess
    tracked = subprocess.run(["git", "-C", ROOT, "ls-files", "data"],
                             capture_output=True, text=True).stdout.split("\n")
    tracked = [t for t in tracked if t]
    corpus = []
    for d in ["api", "scripts", "server", "vercel-api", ".github", "framer-components", "operator-web/app"]:
        base = os.path.join(ROOT, d)
        if not os.path.isdir(base):
            continue
        for dp, _, fs in os.walk(base):
            if any(s in dp + "/" for s in SKIP):
                continue
            for f in fs:
                if f.endswith((".py", ".yml", ".yaml", ".tsx", ".ts", ".sh")):
                    try:
                        corpus.append(open(os.path.join(dp, f), encoding="utf-8",
                                           errors="ignore").read())
                    except OSError:
                        pass
    blob = "\n".join(corpus)
    top = [t for t in tracked if t.count("/") == 1]
    subdirs = sorted({"/".join(t.split("/")[:2]) for t in tracked if t.count("/") >= 2})
    dead_top, dead_dir = [], []
    for t in top:
        b = os.path.basename(t)
        stem = b.rsplit(".", 1)[0]
        if b not in blob and stem not in blob:
            dead_top.append(t)
    for d in subdirs:
        name = d.split("/")[-1]
        if d not in blob and f'"{name}"' not in blob and f"/{name}" not in blob:
            n = len([t for t in tracked if t.startswith(d + "/")])
            dead_dir.append({"dir": d, "files": n})
    report["data"] = {"tracked": len(tracked), "top_level": len(top), "subdirs": len(subdirs),
                      "unreferenced_top": dead_top, "unreferenced_dirs": dead_dir}


def scan_files(report: dict) -> None:
    """0바이트 · 내용 중복 · 복사 아티팩트."""
    zero, seen, dups, copies = [], {}, [], []
    for dp, _, fs in os.walk(ROOT):
        if any(s in dp + "/" for s in SKIP):
            continue
        for f in fs:
            p = os.path.join(dp, f)
            r = rel(p)
            if r.startswith(("data/history/", "data/cache/")):
                continue
            try:
                sz = os.path.getsize(p)
            except OSError:
                continue
            if re.search(r" \d+\.\w+$", f):
                copies.append(r)
            if sz == 0 and not f.endswith(("__init__.py", ".gitkeep")):
                zero.append(r)
            if 0 < sz < 2_000_000 and f.endswith((".py", ".json", ".yml", ".tsx", ".sql", ".sh")):
                try:
                    h = hashlib.md5(open(p, "rb").read()).hexdigest()
                except OSError:
                    continue
                if h in seen:
                    dups.append((seen[h], r))
                else:
                    seen[h] = r
    report["files"] = {"zero_byte": zero, "duplicate_pairs": dups, "copy_artifacts": copies}


def main() -> int:
    report: dict = {}
    scan_modules(report)
    scan_constitution(report)
    scan_data(report)
    scan_files(report)
    if "--json" in sys.argv:
        print(json.dumps(report, ensure_ascii=False, indent=1))
        return 0

    m = report["modules"]
    print("═" * 72)
    print(f"① 파이썬 모듈 {m['denominator']} — LIVE {m['live']} · TEST_ONLY {m['test_only']} "
          f"· ORPHAN_CLI {m['orphan_cli']} · 🚨 DEAD {m['dead']}")
    if m["parse_fail"]:
        print(f"   AST 실패 {len(m['parse_fail'])}: {m['parse_fail'][:2]}")
    for d in m["dead_files"]:
        print(f"     {d['f']:56s} {d['lines']:5d}줄")
    print(f"   워크플로 {m['workflows']} · 깨진 참조 {len(m['workflow_broken_refs'])} "
          f"· python 미참조 {m['workflow_no_python']}")
    for b in m["workflow_broken_refs"][:8]:
        print(f"     🚨 {b[0]} → {b[1]} (파일 없음)")

    c = report["constitution"]
    print(f"\n② 헌법 키 {c['denominator']} — 리터럴 참조 0 인 항목")
    for r in c["rows"]:
        if r["hits"] == 0:
            print(f"     🚨 {r['key']} (블록 전체 참조 0)")
        for s in r["subs"]:
            if s["hits"] == 0:
                print(f"       - {r['key']}.{s['key']} 참조 0")

    d = report["data"]
    print(f"\n③ data 추적 {d['tracked']} (최상위 {d['top_level']} · 하위 디렉터리 {d['subdirs']})")
    print(f"   무참조 최상위 {len(d['unreferenced_top'])}: {d['unreferenced_top'][:8]}")
    print(f"   무참조 디렉터리 {len(d['unreferenced_dirs'])}: "
          f"{[x['dir'] + f'({x[chr(102)+chr(105)+chr(108)+chr(101)+chr(115)]})' for x in d['unreferenced_dirs'][:8]]}")

    f = report["files"]
    print(f"\n④ 파일 위생 — 0바이트 {len(f['zero_byte'])} · 중복쌍 {len(f['duplicate_pairs'])} "
          f"· 복사 아티팩트 {len(f['copy_artifacts'])}")
    for z in f["zero_byte"][:8]:
        print(f"     0B  {z}")
    for a, b in f["duplicate_pairs"][:8]:
        print(f"     중복 {a}  ==  {b}")
    for cp in f["copy_artifacts"][:8]:
        print(f"     사본 {cp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
