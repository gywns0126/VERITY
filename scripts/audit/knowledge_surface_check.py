# -*- coding: utf-8 -*-
"""knowledge_surface_check — 지식 표면·재검증 달력 자가검사 (지식통합 P4, 2026-08-16).

왜: P0~P3 이 만든 규율(층1 소형·전 도달·등록부·재검증 기한)은 사람이 지키면 3일이면
퇴화한다는 게 실측이다 (RULE 12 — 검정력 규율 8/10→8/13 소멸). 이 스크립트가 상태를
기계로 재고, 위반이면 exit 1 로 시끄럽게 만든다. 선례 = #373 계약·RULE 9 grep·jsonl 가드.

검사 7종:
  1 kickoff ≤60줄 + 필수 섹션(진입어·SoT 지도·죽은 전제)
  2 CLAUDE.md·AGENTS.md 바이트 동일 + 13룰 헤더 전부 존재 (+30KB 경고)
  3 MEMORY.md [[링크]] 전수 → 파일 존재 (인덱스 dangling 0)
  4 메모리 BFS 전 도달(고아 0) + frontmatter name=파일명 + P2 스텁→클러스터 섹션 무결
  5 docs/*.md 전수 ↔ INDEX.md 등재 대조 (미등재·유령)
  6 model_registry 스키마 + next_review 기한 초과 신고
  7 상설 감사 신선도 (ic_overlap_audit ≤100일)

🚨 로컬 전용 — 메모리 디렉터리(~/.claude)는 CI 러너에 없다. cron 편입 금지.
사용: python3 scripts/audit/knowledge_surface_check.py  (세션 시작/종료 시 1회 권장)
산출: data/metadata/knowledge_surface_report.json (자기신고, RULE 12)
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys
from collections import deque
from datetime import date, datetime

ROOT = "/Users/macbookpro/Desktop/배리티 터미널"
MEM = os.path.expanduser(
    "~/.claude/projects/-Users-macbookpro-Desktop--------/memory")
KICKOFF = os.path.join(MEM, "project_next_session_kickoff.md")
REPORT = os.path.join(ROOT, "data", "metadata", "knowledge_surface_report.json")

KICKOFF_MAX_LINES = 60
AGENT_RULES_WARN_BYTES = 30_000
MEMORY_WARN_BYTES = 20_000
AUDIT_STALE_DAYS = 100

issues: list[dict] = []
warns: list[dict] = []


def issue(check: str, msg: str) -> None:
    issues.append({"check": check, "msg": msg})


def warn(check: str, msg: str) -> None:
    warns.append({"check": check, "msg": msg})


def read(p: str) -> str:
    return open(p, encoding="utf-8", errors="ignore").read()


# ── 1 kickoff ────────────────────────────────────────────────
def check_kickoff() -> dict:
    s = read(KICKOFF)
    n = len(s.splitlines())   # count("\n")+1 은 말미 개행을 한 줄로 오산 (첫 실행에서 자가 적발)
    if n > KICKOFF_MAX_LINES:
        issue("kickoff", f"{n}줄 > 상한 {KICKOFF_MAX_LINES} — 아카이브로 밀 것 (P0 규칙)")
    for sec in ("진입어", "SoT 지도", "죽은 전제"):
        if sec not in s:
            issue("kickoff", f"필수 섹션 '{sec}' 부재")
    return {"lines": n, "max": KICKOFF_MAX_LINES}


# ── 2 런타임 루트 지침 ──────────────────────────────────────
def check_agent_rules() -> dict:
    claude = os.path.join(ROOT, "CLAUDE.md")
    agents = os.path.join(ROOT, "AGENTS.md")
    s = read(claude)
    a = read(agents)
    if s != a:
        issue("agent_rules", "CLAUDE.md와 AGENTS.md 바이트 불일치 — 같은 턴에 동기화할 것")
    rules = sorted(int(x) for x in re.findall(r"^## 🚨 RULE (\d+)", s, re.M))
    expected = list(range(1, 14))
    missing = [r for r in expected if r not in rules]
    if missing:
        issue("agent_rules", f"RULE 헤더 부재: {missing}")
    sizes = {"CLAUDE.md": os.path.getsize(claude), "AGENTS.md": os.path.getsize(agents)}
    for name, size in sizes.items():
        if size > AGENT_RULES_WARN_BYTES:
            warn("agent_rules", f"{name} {size:,}B > {AGENT_RULES_WARN_BYTES:,}B — P3 다이어트 재검토")
    return {"rules": rules, "bytes": sizes, "byte_identical": s == a}


# ── 3·4 메모리 ───────────────────────────────────────────────
def check_memory() -> dict:
    files = {os.path.basename(f)[:-3]: f for f in glob.glob(MEM + "/*.md")
             if os.path.basename(f) != "MEMORY.md"}
    idx_path = MEM + "/MEMORY.md"
    idx = read(idx_path)
    isz = os.path.getsize(idx_path)
    if isz > MEMORY_WARN_BYTES:
        warn("memory", f"MEMORY.md {isz:,}B > {MEMORY_WARN_BYTES:,}B")

    direct = (set(re.findall(r"\[\[([\w\-]+)\]\]", idx))
              | set(re.findall(r"\(([\w\-]+)\.md\)", idx)))
    dangling = sorted(direct - set(files))
    if dangling:
        issue("memory", f"MEMORY.md dangling 링크 {len(dangling)}: {dangling[:5]}")

    refs = {}
    for n, p in files.items():
        s = read(p)
        refs[n] = set(re.findall(r"\[\[([\w\-]+)\]\]", s)) & set(files)
        m = re.search(r"^name:\s*([\w\-]+)", s, re.M)
        if not m:
            issue("memory", f"{n}.md — frontmatter name 부재")
        elif m.group(1) != n:
            issue("memory", f"{n}.md — name '{m.group(1)}' ≠ 파일명")

    reach = set(direct & set(files))
    q = deque(reach)
    while q:
        c = q.popleft()
        for t in refs.get(c, ()):
            if t not in reach:
                reach.add(t)
                q.append(t)
    orphans = sorted(set(files) - reach)
    if orphans:
        issue("memory", f"BFS 고아 {len(orphans)}: {orphans[:5]}")

    # P2 스텁 무결 — 스텁이 가리키는 클러스터에 해당 섹션 존재
    stub_bad = []
    for n, p in files.items():
        s = read(p)
        m = re.search(r"본문은 \[\[(feedback_cluster_\w+)\]\] 의 `## ([\w\-]+)` 절", s)
        if m:
            cpath = files.get(m.group(1))
            if not cpath or f"## {m.group(2)}" not in read(cpath):
                stub_bad.append(n)
    if stub_bad:
        issue("memory", f"스텁→클러스터 섹션 부재 {len(stub_bad)}: {stub_bad[:5]}")

    return {"files": len(files), "direct": len(direct & set(files)),
            "reachable": len(reach), "orphans": len(orphans)}


# ── 5 docs ↔ INDEX ───────────────────────────────────────────
def check_docs_index() -> dict:
    docs = {os.path.basename(f) for f in glob.glob(os.path.join(ROOT, "docs", "*.md"))}
    idx = read(os.path.join(ROOT, "docs", "INDEX.md"))
    listed = set(re.findall(r"`([\w.\-]+\.md)`", idx))
    unlisted = sorted(docs - listed - {"INDEX.md"})
    ghosts = sorted(listed - docs)
    if unlisted:
        issue("index", f"INDEX 미등재 docs {len(unlisted)}: {unlisted[:6]}")
    if ghosts:
        issue("index", f"INDEX 유령 항목(파일 없음) {len(ghosts)}: {ghosts[:6]}")
    return {"docs": len(docs), "listed": len(listed & docs),
            "unlisted": len(unlisted), "ghosts": len(ghosts)}


# ── 6 model_registry ─────────────────────────────────────────
def check_registry() -> dict:
    p = os.path.join(ROOT, "data", "metadata", "model_registry.json")
    if not os.path.exists(p):
        issue("registry", "model_registry.json 부재")
        return {}
    try:
        reg = json.load(open(p, encoding="utf-8"))
    except ValueError as e:
        issue("registry", f"JSON 파싱 실패: {e}")
        return {}
    today = date.today()
    overdue, bad = [], []
    tiers = {"critical", "active", "research"}
    # 🚨 2026-08-16 — 개정 주기 규율 (registry._meta.revision_cadence).
    #   개정일이 임의로 흩어지면 "지금 고칠 때인가" 가 매일 판단 대상이 되고, 조정이 상시화된다.
    #   실측: 정렬 전 16모델이 날짜 4종으로 흩어져 있었고 11/15·11/16 은 등록 시점의 우연이었다.
    kinds = {"revision", "health_check", "event_verdict"}
    annual = (reg.get("_meta", {}).get("revision_cadence", {}) or {}).get("policy", "")
    for m in reg.get("models", []):
        mid = m.get("id", "?")
        if m.get("tier") not in tiers:
            bad.append(f"{mid}: tier '{m.get('tier')}'")
        for k in ("status", "sot", "next_review", "kill_criteria_ref"):
            if not m.get(k):
                bad.append(f"{mid}: {k} 부재")
        if m.get("review_kind") not in kinds:
            bad.append(f"{mid}: review_kind 미분류 (revision|health_check|event_verdict)")
        if "미정" in str(m.get("kill_criteria_ref") or ""):
            bad.append(f"{mid}: kill_criteria 미정 — 관측변수·수치·시점·자동행동 4요소로 채울 것")
        # 정기 개정 대상은 연례 고정일에만 (사건 판정은 예외)
        if m.get("review_kind") in ("revision", "health_check") and \
                str(m.get("next_review", ""))[5:] != "12-31":
            bad.append(f"{mid}: next_review {m.get('next_review')} — 정기 개정은 연례 고정일(12-31)만")
        try:
            nr = datetime.strptime(m["next_review"], "%Y-%m-%d").date()
            if nr < today:
                overdue.append(f"{mid} (기한 {m['next_review']}, tier {m.get('tier')})")
        except (KeyError, ValueError):
            bad.append(f"{mid}: next_review 형식")
    if bad:
        issue("registry", f"스키마 위반 {len(bad)}: {bad[:5]}")
    if overdue:
        issue("registry", f"재검증 기한 초과 {len(overdue)}: {overdue[:6]}")
    return {"models": len(reg.get("models", [])), "overdue": len(overdue)}


# ── 7 상설 감사 신선도 ────────────────────────────────────────
def check_audit_freshness() -> dict:
    p = os.path.join(ROOT, "data", "analysis", "ic_overlap_audit.json")
    if not os.path.exists(p):
        warn("freshness", "ic_overlap_audit.json 부재 — 분기 감사 미실행?")
        return {}
    try:
        g = json.load(open(p, encoding="utf-8"))["_meta"]["generated_at"][:10]
        age = (date.today() - datetime.strptime(g, "%Y-%m-%d").date()).days
        if age > AUDIT_STALE_DAYS:
            issue("freshness", f"ic_overlap_audit {age}일 경과 (>{AUDIT_STALE_DAYS}) — 분기 재실행")
        return {"ic_overlap_age_days": age}
    except (KeyError, ValueError) as e:
        warn("freshness", f"ic_overlap_audit 메타 파싱 실패: {e}")
        return {}


def main() -> int:
    stats = {
        "kickoff": check_kickoff(),
        "agent_rules": check_agent_rules(),
        "memory": check_memory(),
        "docs_index": check_docs_index(),
        "registry": check_registry(),
        "freshness": check_audit_freshness(),
    }
    print("═" * 64)
    print("지식 표면 자가검사 (P4)")
    print("═" * 64)
    k = stats["kickoff"]; m = stats["memory"]; d = stats["docs_index"]; r = stats["registry"]
    ar = stats["agent_rules"]
    print(f"층1  kickoff {k.get('lines')}/{k.get('max')}줄 · 루트 지침 "
          f"{ar.get('bytes', {}).get('CLAUDE.md', 0):,}B · 동일 {ar.get('byte_identical')} "
          f"(룰 {len(ar.get('rules', []))}) ")
    print(f"층3  메모리 {m.get('files')} · 도달 {m.get('reachable')} · 고아 {m.get('orphans')}")
    print(f"층2  docs {d.get('docs')} · 등재 {d.get('listed')} · 미등재 {d.get('unlisted')} · 유령 {d.get('ghosts')}")
    print(f"달력 registry {r.get('models',0)}모델 · 기한초과 {r.get('overdue',0)} · "
          f"ic_overlap {stats['freshness'].get('ic_overlap_age_days','?')}일 경과")
    if warns:
        print(f"\n경고 {len(warns)}:")
        for w in warns:
            print(f"  ⚠ [{w['check']}] {w['msg']}")
    if issues:
        print(f"\n🚨 위반 {len(issues)}:")
        for i in issues:
            print(f"  ✗ [{i['check']}] {i['msg']}")
    else:
        print("\n위반 0 — 표면 정합 ✓")

    payload = {"_meta": {"artifact": "knowledge_surface_report",
                         "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                         "checks": 7, "local_only": True},
               "stats": stats, "issues": issues, "warns": warns}
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    json.dump(payload, open(REPORT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n기록 → {REPORT}")
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
