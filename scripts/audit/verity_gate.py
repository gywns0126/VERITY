# -*- coding: utf-8 -*-
"""verity_gate — 하네스 강제 게이트 (Stop + PreToolUse). 2026-08-16 구조 재검증 후 시행.

왜: 룰 준수 자체가 주의(확률)로 실행되는 것이 재발의 생성기다 (RULE 13 근본 원인 절).
재검증 실측 — 완전 하네스형 가드(Edit old_string·prereg pytest·P4 검사기) 재발 0 vs
반기계형(RULE 9 send 전 grep, 내가 기억해야 실행) 커밋 누수 2건/78일. 이 스크립트가
그 반기계 구간을 하네스로 옮긴다. 사람(모델) 쪽 절차는 바꾸지 않는다 — 어겨지면 여기서 잡힌다.

Stop 게이트 (턴 종료 차단):
  S1 직전 응답 텍스트 RULE 9 regex (전과: 응답 레벨 5차 drift — 유일하게 기계가 없던 자리)
  S2 (조건부) 지식 표면 검사 — 층1 파일 mtime 변화 시에만 knowledge_surface_check 실행
  S3 (조건부) prereg 계약 — prereg 산출물이 dirty 할 때만 계약 pytest 실행
PreToolUse(Bash) 게이트 (도구 실행 전 차단):
  P1 git commit 메시지 RULE 9 regex (커밋 누수 2건/78일이 닫히는 자리)
  P2 git add -A / --all / '.' 차단 (feedback_cluster_git_commit)
  P3 git add 다중 경로 + 글롭 혼합 차단 (8/9 락 동결 사고 클래스 — 글롭 미매칭 = add 전체 원자 실패)

설계 제약 (재검증 확정분):
  - 결정론 코드만. LLM 판정(prompt/agent hook) 금지 — 확률적 주의 재도입이다.
  - Stop 은 매 턴 종료마다 발화 → 무거운 검사는 조건부(mtime 스탬프·dirty 검사)로만.
  - fail-open + 자기신고: 게이트 자체 오류는 통과시키되 systemMessage 로 시끄럽게.
    (조용히 죽는 가드 = RULE 1 8/9 학습. 벽돌 게이트 = 모든 턴 차단이라 fail-closed 불가.)
  - 루프 가드: stop_hook_active=true 면 즉시 통과 (차단→재시도→재차단 무한루프 방지).

배선: .claude/settings.local.json (gitignored — 본 파일 하단 WIRING 참조로 재구성 가능).
셀프테스트: python3 scripts/audit/verity_gate.py --selftest
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time

ROOT = "/Users/macbookpro/Desktop/배리티 터미널"
MEM = os.path.expanduser(
    "~/.claude/projects/-Users-macbookpro-Desktop--------/memory")
STAMP = os.path.join(ROOT, "data", "metadata", ".verity_gate_stamp.json")
SURFACE_CHECK = os.path.join(ROOT, "scripts", "audit", "knowledge_surface_check.py")
PREREG_TEST = os.path.join(ROOT, "tests", "test_prereg_artifact_contract.py")

# 층1 자동로드 파일 — 이들이 변한 턴에서만 표면 검사를 돈다
WATCH_L1 = [
    os.path.join(ROOT, "CLAUDE.md"),
    os.path.join(MEM, "MEMORY.md"),
    os.path.join(MEM, "project_next_session_kickoff.md"),
]

# RULE 9 — CLAUDE.md 의 정규식과 동일 어미 집합 + 복합어 오탐 제외(임박/압박/촉박/속박/쪽박/수박/대박).
# 어간은 유니코드 이스케이프로 두어 이 파일 자체가 grep 스윕에 걸리지 않게 한다.
_STEM = "박"
RULE9_RE = re.compile(
    "(?<![임압촉속쪽수대])"   # 임 압 촉 속 쪽 수 대
    + _STEM + "[으이아았혀힘은는지하한히음면]"
)

TAIL_BYTES = 2_000_000


def _out(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False))


def _fail_open(where: str, err: Exception) -> int:
    # 조용한 죽음 금지 — 통과시키되 반드시 자기신고
    _out({"systemMessage": f"[verity_gate:{where}] 게이트 자체 오류로 통과 처리 — 점검 필요: {err!r}"})
    return 0


# ── Stop ─────────────────────────────────────────────────────

def _last_response_text(transcript_path: str) -> str:
    """직전(마지막 실제 사용자 프롬프트 이후) assistant text 블록 전부 이어붙임."""
    size = os.path.getsize(transcript_path)
    with open(transcript_path, "rb") as f:
        if size > TAIL_BYTES:
            f.seek(size - TAIL_BYTES)
            f.readline()  # 잘린 첫 줄 버림
        raw = f.read().decode("utf-8", errors="ignore")

    entries = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except ValueError:
            continue

    last_user = -1
    for i, e in enumerate(entries):
        if e.get("type") != "user":
            continue
        c = (e.get("message") or {}).get("content")
        if isinstance(c, str) and c.strip():
            last_user = i
        elif isinstance(c, list) and any(
                isinstance(b, dict) and b.get("type") == "text" for b in c):
            last_user = i

    texts = []
    for e in entries[last_user + 1:]:
        if e.get("type") != "assistant":
            continue
        c = (e.get("message") or {}).get("content")
        if isinstance(c, list):
            for b in c:
                if isinstance(b, dict) and b.get("type") == "text":
                    texts.append(b.get("text") or "")
    return "\n".join(texts)


def _check_surface_conditional() -> str | None:
    """층1 파일이 스탬프 이후 변했을 때만 표면 검사. 위반 요약 반환(없으면 None)."""
    try:
        stamp = json.load(open(STAMP, encoding="utf-8"))
    except (OSError, ValueError):
        stamp = {}
    mt = max((os.path.getmtime(p) for p in WATCH_L1 if os.path.exists(p)), default=0.0)
    if mt <= stamp.get("surface_ok_mtime", 0.0):
        return None
    r = subprocess.run([sys.executable, SURFACE_CHECK],
                       capture_output=True, text=True, timeout=30)
    if r.returncode == 0:
        os.makedirs(os.path.dirname(STAMP), exist_ok=True)
        json.dump({"surface_ok_mtime": mt, "checked_at": time.time()},
                  open(STAMP, "w", encoding="utf-8"))
        return None
    tail = "\n".join((r.stdout or "").splitlines()[-8:])
    return f"지식 표면 검사 위반 (knowledge_surface_check exit {r.returncode}):\n{tail}"


def _check_prereg_conditional() -> str | None:
    """prereg 산출물이 dirty 할 때만 계약 pytest."""
    r = subprocess.run(["git", "-C", ROOT, "status", "--porcelain"],
                       capture_output=True, text=True, timeout=10)
    dirty = [l for l in r.stdout.splitlines()
             if re.search(r"prereg_[\w\-]+\.json|PREREG_[\w\-]+\.md", l)]
    if not dirty:
        return None
    if not os.path.exists(PREREG_TEST):
        return None
    t = subprocess.run([sys.executable, "-m", "pytest", PREREG_TEST, "-q"],
                       capture_output=True, text=True, timeout=60, cwd=ROOT)
    if t.returncode == 0:
        return None
    tail = "\n".join((t.stdout or "").splitlines()[-6:])
    return f"prereg 계약 위반 (dirty {len(dirty)}건, pytest 실패):\n{tail}"


def hook_stop() -> int:
    try:
        payload = json.load(sys.stdin)
    except ValueError as e:
        return _fail_open("stop/stdin", e)
    if payload.get("stop_hook_active"):
        return 0  # 루프 가드

    # S1 — RULE 9 (응답 레벨: 유일하게 기계가 없던 자리)
    tp = payload.get("transcript_path") or ""
    if tp and os.path.exists(tp):
        try:
            text = _last_response_text(tp)
            hits = sorted({m.group(0) for m in RULE9_RE.finditer(text)})
            if hits:
                _out({"decision": "block",
                      "reason": ("RULE 9 위반 — 직전 응답에 금지 동사 형태 "
                                 f"{len(hits)}종: {', '.join(hits[:8])}. "
                                 "대체 동사 정답표(CLAUDE.md RULE 9)로 바꿔 다시 응답할 것.")})
                return 0
        except Exception as e:  # noqa: BLE001 — S1 실패가 S2/S3 를 막으면 안 됨
            _out({"systemMessage": f"[verity_gate:stop/S1] transcript 파싱 실패(통과): {e!r}"})

    # S2 — 지식 표면 (조건부)
    try:
        msg = _check_surface_conditional()
        if msg:
            _out({"decision": "block",
                  "reason": msg + "\n(층1 파일을 만졌으면 표면 정합까지가 그 작업의 일부다 — RULE 12.)"})
            return 0
    except Exception as e:  # noqa: BLE001
        return _fail_open("stop/S2", e)

    # S3 — prereg 계약 (조건부)
    try:
        msg = _check_prereg_conditional()
        if msg:
            _out({"decision": "block", "reason": msg})
            return 0
    except Exception as e:  # noqa: BLE001
        return _fail_open("stop/S3", e)
    return 0


# ── PreToolUse (Bash) ────────────────────────────────────────

_GIT_ADD_RE = re.compile(r"git\s+(?:-C\s+\S+\s+)?(?:--git-dir=\S+\s+)?(?:--work-tree=\S+\s+)?add\s+([^&|;]*)")
_GIT_COMMIT_RE = re.compile(r"git\s+(?:-C\s+\S+\s+)?(?:--git-dir=\S+\s+)?(?:--work-tree=\S+\s+)?commit\b")


def _deny(reason: str) -> int:
    _out({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason,
    }})
    return 0


def _split_paths(argstr: str) -> list[str]:
    """따옴표 인지 토크나이즈 — 플래그 제외한 경로 토큰만."""
    toks, cur, q = [], "", ""
    for ch in argstr:
        if q:
            if ch == q:
                q = ""
            else:
                cur += ch
        elif ch in "'\"":
            q = ch
        elif ch.isspace():
            if cur:
                toks.append(cur)
                cur = ""
        else:
            cur += ch
    if cur:
        toks.append(cur)
    return toks


def _strip_quoted(cmd: str) -> str:
    """따옴표 내부(=인자 텍스트, 커밋 메시지 등)를 공백으로 치환 — 명령 구조만 남긴다.

    첫 실전 커밋 오탐 학습 (2026-08-16): 커밋 메시지 본문의 'git add -A' *인용*이
    P2 add 파서에 걸렸다. add 규율은 명령 위치의 토큰만 봐야 한다 (RULE 9 는 예외 —
    메시지 텍스트 자체가 검사 대상이라 원문 cmd 를 쓴다)."""
    out, q = [], ""
    for ch in cmd:
        if q:
            if ch == q:
                q = ""
            out.append(" ")
        elif ch in "'\"":
            q = ch
            out.append(" ")
        else:
            out.append(ch)
    return "".join(out)


def hook_pretool() -> int:
    try:
        payload = json.load(sys.stdin)
    except ValueError as e:
        return _fail_open("pretool/stdin", e)
    cmd = ((payload.get("tool_input") or {}).get("command")) or ""
    if "git" not in cmd:
        return 0

    # P1 — git commit 메시지 RULE 9
    if _GIT_COMMIT_RE.search(cmd):
        hits = sorted({m.group(0) for m in RULE9_RE.finditer(cmd)})
        if hits:
            return _deny("RULE 9 위반 — commit 명령 텍스트에 금지 동사 형태 "
                         f"{len(hits)}종: {', '.join(hits[:8])}. 대체 동사 정답표로 수정 후 재시도.")

    # P2/P3 — git add 규율 (따옴표 내부 제외 — 명령 구조만)
    for m in _GIT_ADD_RE.finditer(_strip_quoted(cmd)):
        toks = _split_paths(m.group(1))
        flags = [t for t in toks if t.startswith("-")]
        paths = [t for t in toks if not t.startswith("-")]
        if any(f in ("-A", "--all") for f in flags):
            return _deny("git add -A/--all 금지 (feedback_cluster_git_commit) — 명시 경로만 add.")
        if "." in paths:
            return _deny("git add . 금지 — 명시 경로만 add (의도치 않은 전체 스테이징 방지).")
        if len(paths) >= 2 and any(re.search(r"[*?\[]", p) for p in paths):
            return _deny("git add 한 줄에 다중 경로+글롭 혼합 금지 (RULE 1, 8/9 사고 — 글롭 "
                         "미매칭 시 add 전체가 원자 실패해 멀쩡한 경로까지 미스테이징). 파일별로 나눠 add.")
    return 0


# ── 셀프테스트 ────────────────────────────────────────────────

def _selftest() -> int:  # noqa: C901 — 케이스 나열
    import tempfile
    ok = True

    def run(hook: str, payload: dict) -> dict:
        r = subprocess.run([sys.executable, __file__, "--hook", hook],
                           input=json.dumps(payload), capture_output=True,
                           text=True, timeout=90)
        try:
            return json.loads(r.stdout) if r.stdout.strip() else {}
        except ValueError:
            return {"_raw": r.stdout}

    def case(name: str, cond: bool) -> None:
        nonlocal ok
        print(("PASS " if cond else "FAIL ") + name)
        ok = ok and cond

    bad_word = _STEM + "음"          # 금지 형태 (어간+음) — 소스에 원문 미기재
    quote_ok = "임" + _STEM + "이라"  # '임박이라' — 오탐 제외 확인

    td = tempfile.mkdtemp(prefix="vgate_")

    def mk_transcript(assistant_text: str) -> str:
        p = os.path.join(td, f"t{abs(hash(assistant_text)) % 10**8}.jsonl")
        lines = [
            {"type": "user", "message": {"role": "user", "content": "질문"}},
            {"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "text", "text": assistant_text}]}},
        ]
        with open(p, "w", encoding="utf-8") as f:
            for e in lines:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        return p

    # Stop — S1 만 격리 검증하기 위해 존재하는 transcript 만 주고 층1/prereg 는 실제 상태 사용.
    # (전제: 셀프테스트 시점의 repo 는 표면 정합 — 아니라면 그것 자체가 잡아야 할 위반이다.)
    r = run("stop", {"transcript_path": mk_transcript("오늘 " + bad_word + " 확인"), "stop_hook_active": False})
    case("stop: 위반 응답 → block", r.get("decision") == "block")
    r = run("stop", {"transcript_path": mk_transcript("정상 응답 텍스트. 고정했다."), "stop_hook_active": False})
    case("stop: 정상 응답 → pass", r.get("decision") != "block")
    r = run("stop", {"transcript_path": mk_transcript("오늘 " + bad_word), "stop_hook_active": True})
    case("stop: stop_hook_active 루프 가드 → pass", r == {})
    r = run("stop", {"transcript_path": mk_transcript("문장 " + quote_ok + " 배포"), "stop_hook_active": False})
    case("stop: 복합어(임박) 오탐 없음", r.get("decision") != "block")
    garbage = os.path.join(td, "g.jsonl")
    open(garbage, "w").write("not json at all\n{broken")
    r = run("stop", {"transcript_path": garbage, "stop_hook_active": False})
    case("stop: 깨진 transcript → fail-open(비차단)", r.get("decision") != "block")

    # PreToolUse
    r = run("pretool", {"tool_name": "Bash", "tool_input": {"command": "git commit -m '결과 " + bad_word + "'"}})
    case("pretool: 위반 커밋 메시지 → deny",
         (r.get("hookSpecificOutput") or {}).get("permissionDecision") == "deny")
    r = run("pretool", {"tool_name": "Bash", "tool_input": {"command": "cd /x && git commit -m 'fix: 정상 메시지'"}})
    case("pretool: 정상 커밋 → allow", r == {})
    r = run("pretool", {"tool_name": "Bash", "tool_input": {"command": "git add -A && git commit -m x"}})
    case("pretool: git add -A → deny",
         (r.get("hookSpecificOutput") or {}).get("permissionDecision") == "deny")
    r = run("pretool", {"tool_name": "Bash", "tool_input": {"command": "git add ."}})
    case("pretool: git add . → deny",
         (r.get("hookSpecificOutput") or {}).get("permissionDecision") == "deny")
    r = run("pretool", {"tool_name": "Bash", "tool_input": {"command": "git add data/a.txt data/b_*.json"}})
    case("pretool: 다중 경로+글롭 → deny (8/9 클래스)",
         (r.get("hookSpecificOutput") or {}).get("permissionDecision") == "deny")
    r = run("pretool", {"tool_name": "Bash", "tool_input": {"command": "git add data/analysis/prereg_x.json"}})
    case("pretool: 단일 명시 경로 → allow", r == {})
    r = run("pretool", {"tool_name": "Bash", "tool_input": {"command": "git add 'data/my file.json' && git push"}})
    case("pretool: 따옴표 경로 → allow", r == {})
    r = run("pretool", {"tool_name": "Bash", "tool_input": {
        "command": "git commit -m 'DATA: 실발화 증명(git add -A --dry-run 거부) 기록'"}})
    case("pretool: 메시지 안 'git add -A' 인용 → allow (8/16 실전 오탐 재발 방지)", r == {})
    r = run("pretool", {"tool_name": "Bash", "tool_input": {"command": "git add --all"}})
    case("pretool: git add --all (비인용) → deny",
         (r.get("hookSpecificOutput") or {}).get("permissionDecision") == "deny")
    r = run("pretool", {"tool_name": "Bash", "tool_input": {"command": "ls -la && echo done"}})
    case("pretool: git 무관 명령 → allow", r == {})

    print("\n셀프테스트 " + ("전건 통과" if ok else "실패 존재"))
    return 0 if ok else 1


# ── WIRING (재구성용 기록 — settings.local.json 은 gitignored) ─
# "hooks": {
#   "Stop": [{"hooks": [{"type": "command", "timeout": 45,
#     "command": "/usr/bin/python3 '/Users/macbookpro/Desktop/배리티 터미널/scripts/audit/verity_gate.py' --hook stop"}]}],
#   "PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "timeout": 15,
#     "command": "/usr/bin/python3 '/Users/macbookpro/Desktop/배리티 터미널/scripts/audit/verity_gate.py' --hook pretool"}]}]
# }

def main() -> int:
    if "--selftest" in sys.argv:
        return _selftest()
    hook = sys.argv[sys.argv.index("--hook") + 1] if "--hook" in sys.argv else ""
    if hook == "stop":
        return hook_stop()
    if hook == "pretool":
        return hook_pretool()
    print("usage: verity_gate.py --hook stop|pretool | --selftest", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
