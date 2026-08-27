# -*- coding: utf-8 -*-
"""verity_gate — 하네스 강제 게이트 (UserPromptSubmit + Stop + PreToolUse).

왜: 룰 준수 자체가 주의(확률)로 실행되는 것이 재발의 생성기다 (RULE 13 근본 원인 절).
재검증 실측 — 완전 하네스형 가드(Edit old_string·prereg pytest·P4 검사기) 재발 0 vs
반기계형(RULE 9 send 전 grep, 내가 기억해야 실행) 커밋 누수 2건/78일. 이 스크립트가
그 반기계 구간을 하네스로 옮긴다. 사람(모델) 쪽 절차는 바꾸지 않는다 — 어겨지면 여기서 잡힌다.

Stop 게이트 (턴 종료 차단):
  S1 직전 응답 텍스트 RULE 9 regex (전과: 응답 레벨 5차 drift — 유일하게 기계가 없던 자리)
  S2 (조건부) 지식 표면 검사 — 층1 파일 mtime 변화 시에만 knowledge_surface_check 실행
  S3 (조건부) prereg 계약 — prereg 산출물이 dirty 할 때만 계약 pytest 실행
  S4 private 동기 — docs/ + private 전용 파일. public 에 사본 없는 것이 유일본이다.
     미추적(사본 0)=차단 · 미커밋(직전본 있음)=경고. 전과: PM 승인 사전등록 3건이
     13일간 디스크 단일 사본 (8/17 발견, 디스크 188 vs 추적 185)
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

배선: 프로젝트 `.claude/settings.local.json` + `.codex/hooks.json`.
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
    os.path.join(ROOT, "AGENTS.md"),
    os.path.join(MEM, "MEMORY.md"),
    os.path.join(MEM, "project_next_session_kickoff.md"),
    os.path.join(ROOT, ".cursor", "rules", "global.mdc"),
    os.path.join(ROOT, ".cursor", "rules", "framer.mdc"),
    os.path.join(ROOT, ".cursor", "rules", "python-backend.mdc"),
    os.path.join(ROOT, ".cursor", "rules", "large-system-audit.mdc"),
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


def _check_private_docs_sync() -> tuple[str | None, str | None]:
    """docs/ 가 private repo 에 심겼는지. 반환 = (차단 사유, 경고 사유).

    🚨 2026-08-17 신설 — 실측으로 13일 미동기가 드러났다. `docs/` 는 public 에서
    gitignore 라 private repo 에만 남는데, 8/4~8/5 작성된 **PM 승인 사전등록 3건**이
    한 번도 커밋되지 않아 이 맥 디스크 단일 사본이었다 (디스크 188 vs 추적 185).

    원인 = CLAUDE.md 가 요구하는 `add -f` 누락. 실측한 git 거동:
      · 신규 파일 + plain add → 스테이징 자체가 안 됨 (경로가 통째로 무시됨)
      · 추적 파일 + plain add → **스테이징은 되지만 exit 1** → `add && commit` 체인이
        commit 전에 끊긴다. 어느 쪽도 에러가 시끄럽지 않아 13일간 미탐지였다.

    미추적(=사본 0) 은 차단, 수정만 된 것(=직전본 존재) 은 경고로 나눈다.
    사전등록은 RULE 7 임계 동결의 근거 문서라 소실 = 동결 근거 소실이다.
    """
    gd = os.path.join(ROOT, ".git-private")
    if not os.path.isdir(gd):
        return None, None                      # 다른 머신 = 해당 없음
    docs = os.path.join(ROOT, "docs")
    if not os.path.isdir(docs):
        return None, None
    disk = set()
    for dp, _dn, fn in os.walk(docs):
        for f in fn:
            rel = os.path.relpath(os.path.join(dp, f), ROOT)
            disk.add(rel)
    r = subprocess.run(["git", "--git-dir=" + gd, "--work-tree=" + ROOT,
                        "ls-files", "docs/"],
                       capture_output=True, text=True, timeout=15, cwd=ROOT)
    if r.returncode != 0:
        return None, f"private repo ls-files 실패 (exit {r.returncode}) — docs 동기 미확인"
    tracked = {l for l in r.stdout.splitlines() if l}
    missing = sorted(disk - tracked)
    if missing:
        names = "\n  ".join(missing[:8])
        more = f"\n  … 외 {len(missing) - 8}건" if len(missing) > 8 else ""
        return (f"private repo 미추적 docs {len(missing)}건 (디스크 {len(disk)} · 추적 "
                f"{len(tracked)}) — public 은 /docs/ gitignore 라 **사본이 이 디스크뿐**이다:\n"
                f"  {names}{more}\n"
                "  git --git-dir=.git-private --work-tree=. add -f <경로> && … commit && … push\n"
                "  (🚨 -f 필수 · add -A 금지 · 명시 경로만 — CLAUDE.md 하이브리드 절)"), None
    # 🚨 2026-08-17 확장 — docs/ 밖의 private 추적 파일까지. 계기: 같은 날 조사에서
    #   `private/decisions/verdicts.jsonl` 이 디스크 14행 vs private HEAD **1행**이었다.
    #   `/private/` 는 public .gitignore 라 판단 trail 13건이 이 디스크에만 있었다.
    #   docs 사전등록 3건과 **같은 클래스**인데 종전 S4 는 docs/ 만 봐서 못 잡았다
    #   (= 인스턴스만 막고 클래스를 안 막은 형태. autostash 건과 동일한 실수라 여기서 닫는다).
    #
    #   심각도는 **public 사본 유무**로 가른다. public 에도 있으면 그쪽이 SoT 라 지연이
    #   무해하지만(portfolio.json), private 전용이면 지연 = 유일 백업이 낡은 것이다.
    d = subprocess.run(["git", "--git-dir=" + gd, "--work-tree=" + ROOT,
                        "status", "--porcelain", "--untracked-files=no"],
                       capture_output=True, text=True, timeout=15, cwd=ROOT)
    dirty = [l[3:].strip().strip('"') for l in d.stdout.splitlines() if l.strip()]
    if not dirty:
        return None, None
    pub = subprocess.run(["git", "-C", ROOT, "ls-files", "--"] + dirty,
                         capture_output=True, text=True, timeout=15)
    in_public = {l for l in pub.stdout.splitlines() if l}
    only_private = [p for p in dirty if p not in in_public]
    if only_private:
        # 🚨 2026-08-19 — **방향을 본다.** 종전은 "미커밋" 만 보고 무조건 커밋을 지시했는데,
        #   워킹트리가 HEAD 보다 **낡은** 경우가 있다. 그때 지시대로 커밋하면 롤백이다.
        #   실측: data/us_analyst_consensus.json 워킹트리 generated_at 2026-08-17T08:10
        #   (5,278종목) vs private HEAD 2026-08-19T08:12(5,274종목) — 이틀 치 역행.
        #   private 전용 파일은 public 사본이 없어 **대조군이 없다** = 사람이 알아채기 어렵다.
        #   그래서 게이트가 대신 방향을 판정한다.
        stale = _older_than_head(gd, only_private)
        if stale:
            return (f"private 전용 파일 {len(stale)}건이 **HEAD 보다 낡았다** — 커밋하면 "
                    f"롤백이다. 커밋 말고 원복할 것:\n  "
                    + "\n  ".join(stale[:8])
                    + "\n  git --git-dir=.git-private --work-tree=. checkout HEAD -- <경로>"), None
        return (f"private 전용 파일 {len(only_private)}건 미커밋 — public 에 사본이 없어 "
                f"**이 디스크가 유일본**이다 (미커밋 총 {len(dirty)}건):\n  "
                + "\n  ".join(only_private[:8])
                + "\n  git --git-dir=.git-private --work-tree=. add -f <경로> && … commit && … push"), None
    return None, (f"private 미커밋 {len(dirty)}건 (전부 public 에도 있어 SoT 는 무사): "
                  + ", ".join(dirty[:5]))




def _older_than_head(gd: str, paths: list) -> list:
    """워킹트리 기준일 < HEAD 기준일인 JSON 만 골라낸다.

    판정 근거 = 파일이 스스로 적어 둔 생성 시각(`_meta.generated_at` 등). 파일 mtime 은
    쓰지 않는다 — 체크아웃·복사로 갱신돼 내용 신선도와 무관하다
    (같은 함정이 CI 이름맵 30일 게이트를 영구 무력화했다).
    시각을 못 읽으면 **판정하지 않는다**(빈 목록) — 모르는 것을 낡았다고 하지 않는다.
    """
    def _ts(blob: str):
        try:
            d = json.loads(blob)
        except Exception:
            return None
        m = d.get("_meta") if isinstance(d, dict) else None
        if not isinstance(m, dict):
            return None
        for k in ("generated_at", "collected_at", "as_of", "updated_at"):
            v = m.get(k)
            if isinstance(v, str) and len(v) >= 10:
                return v
        return None
    out = []
    for rel in paths:
        if not rel.lower().endswith(".json"):
            continue
        try:
            with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
                cur = _ts(f.read())
        except OSError:
            continue
        r = subprocess.run(["git", "--git-dir=" + gd, "--work-tree=" + ROOT,
                            "show", "HEAD:" + rel],
                           capture_output=True, text=True, timeout=20, cwd=ROOT)
        if r.returncode != 0:
            continue
        head = _ts(r.stdout)
        if cur and head and cur < head:
            out.append(f"{rel} (디스크 {cur[:19]} < HEAD {head[:19]})")
    return out


CONFLICT_RE = re.compile(r"^(<{7} |={7}$|>{7} )", re.M)


def _check_conflict_markers() -> str | None:
    """수정된 추적 파일에 병합 충돌 마커가 남았는지. 남았으면 차단.

    🚨 2026-08-17 신설 — 실측 근거: `git pull --rebase --autostash` 는 **autostash 재적용이
    충돌해도 종료코드 0 을 반환한다** (격리 repo 로 재현 확인). 따라서 `pull && push` 체인이
    그대로 진행되고, 로컬에서는 충돌 마커가 **실제 워킹트리 파일 안에 기록된 채** 남는다.
    같은 날 이 경로로 append-only 원장 2종(alert_type_ledger·telegram_volume)이 오염됐고,
    다음 커밋이 그대로 실어 보낼 수 있는 상태였다.

    CI 러너는 트리가 일회용이라 무해하지만(그래서 autostash 전수 적용은 유효하다),
    로컬은 그렇지 않다. 사람이 매번 눈으로 확인하는 방식은 이미 두 번 실패했으므로 기계로 막는다.
    """
    r = subprocess.run(["git", "-C", ROOT, "diff", "--name-only", "--diff-filter=ACMU"],
                       capture_output=True, text=True, timeout=15)
    if r.returncode != 0:
        return None
    hits = []
    for rel in [l for l in r.stdout.splitlines() if l][:400]:
        p = os.path.join(ROOT, rel)
        try:
            if os.path.getsize(p) > 40_000_000:
                continue
            with open(p, "rb") as f:
                head = f.read(TAIL_BYTES)
            if b"\0" in head[:4096]:      # 바이너리 제외
                continue
            if CONFLICT_RE.search(head.decode("utf-8", "replace")):
                hits.append(rel)
        except OSError:
            continue
    if not hits:
        return None
    return ("병합 충돌 마커가 남은 파일 " + str(len(hits)) + "건 — 이대로 커밋하면 오염이 실린다:\n  "
            + "\n  ".join(hits[:8])
            + "\n  🚨 `git pull --rebase --autostash` 는 autostash 충돌에도 **exit 0** 이라"
              " `&& push` 가 그대로 진행된다. 마커를 해소하고 `git stash list` 도 확인할 것.")


def hook_stop() -> int:
    try:
        payload = json.load(sys.stdin)
    except ValueError as e:
        return _fail_open("stop/stdin", e)
    if payload.get("stop_hook_active"):
        return 0  # 루프 가드

    # S1 — RULE 9 (응답 레벨: 유일하게 기계가 없던 자리)
    direct_text = payload.get("last_assistant_message")
    tp = payload.get("transcript_path") or ""
    if isinstance(direct_text, str):
        text = direct_text
    elif tp and os.path.exists(tp):
        try:
            text = _last_response_text(tp)
        except Exception as e:  # noqa: BLE001 — S1 실패가 S2/S3 를 막으면 안 됨
            _out({"systemMessage": f"[verity_gate:stop/S1] transcript 파싱 실패(통과): {e!r}"})
            text = ""
    else:
        text = ""
    hits = sorted({m.group(0) for m in RULE9_RE.finditer(text)})
    if hits:
        _out({"decision": "block",
              "reason": ("RULE 9 위반 — 직전 응답에 금지 동사 형태 "
                         f"{len(hits)}종: {', '.join(hits[:8])}. "
                         "루트 지침 RULE 9의 대체 동사로 바꿔 다시 응답할 것.")})
        return 0

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

    # S5 — 병합 충돌 마커 (autostash 가 exit 0 으로 조용히 남기는 자리)
    try:
        msg = _check_conflict_markers()
        if msg:
            _out({"decision": "block", "reason": msg})
            return 0
    except Exception as e:  # noqa: BLE001
        return _fail_open("stop/S5", e)

    # S4 — private docs 동기 (미추적=차단 · 미커밋=경고)
    try:
        block, warn = _check_private_docs_sync()
        if block:
            _out({"decision": "block",
                  "reason": block + "\n(세션이 만든 문서는 세션 밖에 심는다 — RULE 12.)"})
            return 0
        if warn:
            _out({"systemMessage": f"[verity_gate:stop/S4] {warn}"})
    except Exception as e:  # noqa: BLE001
        return _fail_open("stop/S4", e)
    return 0


# ── PreToolUse (Bash) ────────────────────────────────────────

_GIT_ADD_RE = re.compile(r"git\s+(?:-C\s+\S+\s+)?(?:--git-dir=\S+\s+)?(?:--work-tree=\S+\s+)?add\s+([^&|;]*)")
# P4 — autostash 체인 탐지용. `git push`, `git -C <dir> push` 등을 모두 잡는다.
_GIT_PUSH_RE = re.compile(r"\bgit\s+(?:-\S+\s+|--\S+=\S+\s+)*push\b")
# P5 — add 후 커밋 없이 끝나는 것 탐지용. `git commit`, `git --git-dir=X commit` 포함.
_GIT_COMMIT_RE = re.compile(r"\bgit\s+(?:-\S+\s+|--\S+=\S+\s+)*commit\b")
# P6 — commit -a / -am / --all 탐지. 🚨 `--amend` 는 잡지 않는다(단일 `-` 만 매칭).
#   단축 플래그 묶음(-am, -aq …) 안의 'a' 도 잡아야 하므로 문자 집합으로 본다.
_COMMIT_ALL_RE = re.compile(r"(?:^|\s)(?:-[A-Za-z]*a[A-Za-z]*|--all)(?=\s|$)")
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

    # P2/P3/P4 — git 규율 (따옴표 내부 제외 — 명령 구조만)
    bare = _strip_quoted(cmd)
    for m in _GIT_ADD_RE.finditer(bare):
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

    # P4 — `--autostash` 와 push 를 한 줄에 잇는 것 차단 (2026-08-21 실사고 클래스)
    #   🚨 `git rebase --autostash` 는 **pop 충돌에도 exit 0** 이라 `&&` 가 그대로 통과한다.
    #   실측: 작업트리 36파일이 stash 되고 data/price_pulse.json 이 충돌해 마커가 남았는데
    #   push 는 성공해, 성공 신호만 보고 오염을 놓쳤다. 공유 트리(크론·타 세션 상시 더티 37건)
    #   에서 이 조합은 구조적으로 위험하다. 검사를 사이에 끼우도록 **분리를 강제**한다.
    #   ([[feedback_autostash_conflict_exits_zero]] · 안전 경로 = scripts/git/rebase_push.sh)
    if "--autostash" in bare and _GIT_PUSH_RE.search(bare):
        return _deny("`--autostash` 와 `git push` 를 한 명령줄에 잇지 말 것 — rebase 는 "
                     "**pop 충돌에도 exit 0** 이라 체인이 통과해 오염이 남은 채 push 된다 "
                     "(2026-08-21 실사고). 안전 경로: `bash scripts/git/rebase_push.sh` "
                     "— rebase 직후 stash 잔여수·충돌 마커를 assert 하고 어긋나면 push 하지 않는다.")

    # P5 — 스테이징만 하고 커밋하지 않는 것 차단 (2026-08-21 실사고 클래스, 반대 방향)
    #   🚨 공유 인덱스에 올려둔 파일은 **다음 커밋을 하는 세션이 가져간다.**
    #   실측: 내가 가드 2파일을 add 한 뒤 커밋 전에, 타 세션이 커밋하면서 통째로 삼켰고
    #   그 커밋 메시지에는 내 작업의 출처가 없다(a029e825e). 크론·타 세션이 상시 커밋하는
    #   트리에서 add 와 commit 사이의 창은 몇 분이고, 그 창이 곧 사고 확률이다.
    #   → add 를 쓰려면 같은 명령에서 commit 까지 끝내라(창 ≈ 0). 더 나은 경로는
    #     인덱스 자체를 격리하는 scripts/git/commit_mine.sh 다.
    if _GIT_ADD_RE.search(bare) and not _GIT_COMMIT_RE.search(bare):
        return _deny("`git add` 만 하고 끝내지 말 것 — 공유 인덱스에 남은 스테이징은 "
                     "**다음에 커밋하는 세션이 가져간다**(2026-08-21 실사고: 내 가드 2파일이 "
                     "타 세션 커밋 a029e825e 에 출처 없이 딸려 들어감). "
                     "같은 명령에서 commit 까지 끝내거나, 인덱스를 격리하는 "
                     "`bash scripts/git/commit_mine.sh -m \"메시지\" -- 경로...` 를 쓸 것.")

    # P6 — commit -a/--all 차단 (2026-08-22 적대적 검증에서 발견한 구멍)
    #   🚨 `git commit -a` 는 **추적 중인 모든 수정 파일**을 자동 스테이징한다.
    #   이 저장소는 크론·타 세션 때문에 상시 30건 이상 더티라, 한 번이면 남의 작업이
    #   통째로 내 커밋에 실린다 — 이미 차단된 `git add -A` 보다 더 나쁘다(add 는 최소한
    #   명령에 흔적이라도 남지만 -a 는 커밋 메시지만 보면 무엇이 들어갔는지 안 보인다).
    #   P2/P3/P5 는 `git add` 만 보므로 이 경로는 통째로 비어 있었다.
    if _GIT_COMMIT_RE.search(bare) and _COMMIT_ALL_RE.search(bare):
        return _deny("`git commit -a/--all` 금지 — 추적 중인 **모든 수정 파일**이 자동 "
                     "스테이징된다. 이 트리는 크론·타 세션으로 상시 30건 이상 더티라 "
                     "남의 작업이 통째로 실린다(`git add -A` 보다 나쁘다: 커밋 메시지만 "
                     "봐서는 무엇이 들어갔는지 안 보인다). "
                     "`bash scripts/git/commit_mine.sh -m \"메시지\" -- 경로...` 를 쓸 것.")
    return 0


def hook_context() -> int:
    """기존 세션도 다음 사용자 프롬프트부터 최신 루트 지침을 다시 확인하게 한다."""
    try:
        payload = json.load(sys.stdin)
    except ValueError as e:
        return _fail_open("context/stdin", e)
    cwd = os.path.realpath(payload.get("cwd") or "")
    root = os.path.realpath(ROOT)
    if cwd != root and not cwd.startswith(root + os.sep):
        return 0
    try:
        import hashlib
        body = open(os.path.join(ROOT, "AGENTS.md"), "rb").read()
        digest = hashlib.sha256(body).hexdigest()[:12]
    except OSError as e:
        return _fail_open("context/read", e)
    _out({"hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit",
        "additionalContext": (
            f"VERITY 루트 지침 revision={digest}. 이번 행동 전에 현재 작업 경로의 "
            "AGENTS.md 또는 CLAUDE.md를 읽고, 오래된 세션 기억보다 현재 파일을 우선하라. "
            "두 파일은 바이트 동일 미러이며 RULE 1~13이 적용된다."
        )
    }})
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
    r = run("stop", {"last_assistant_message": "오늘 " + bad_word + " 확인",
                     "stop_hook_active": False})
    case("stop: Codex 직접 응답 필드 위반 → block", r.get("decision") == "block")
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
    # P5 (2026-08-21) — 단일 명시 경로라도 **커밋 없이 끝나면** 차단으로 바뀌었다.
    #   공유 인덱스에 남은 스테이징은 다음에 커밋하는 세션이 가져간다(실사고 a029e825e).
    r = run("pretool", {"tool_name": "Bash", "tool_input": {"command": "git add data/analysis/prereg_x.json"}})
    case("pretool: P5 — add 만 하고 끝 → deny",
         (r.get("hookSpecificOutput") or {}).get("permissionDecision") == "deny")
    r = run("pretool", {"tool_name": "Bash", "tool_input": {
        "command": "git add data/analysis/prereg_x.json && git commit -q -m x"}})
    case("pretool: 단일 명시 경로 + 같은 명령 커밋 → allow", r == {})
    r = run("pretool", {"tool_name": "Bash", "tool_input": {
        "command": "git add 'data/my file.json' && git commit -m x"}})
    case("pretool: 따옴표 경로 + 커밋 → allow", r == {})
    r = run("pretool", {"tool_name": "Bash", "tool_input": {
        "command": "bash scripts/git/commit_mine.sh -m x -- data/analysis/prereg_x.json"}})
    case("pretool: 인덱스 격리 스크립트 → allow", r == {})

    # UserPromptSubmit — 기존 세션에도 현재 루트 지침 revision을 주입한다.
    r = run("context", {"cwd": ROOT, "hook_event_name": "UserPromptSubmit", "prompt": "test"})
    ctx = (r.get("hookSpecificOutput") or {}).get("additionalContext", "")
    case("context: 프로젝트 cwd → 최신 지침 주입", "revision=" in ctx and "RULE 1~13" in ctx)
    r = run("context", {"cwd": td, "hook_event_name": "UserPromptSubmit", "prompt": "test"})
    case("context: 프로젝트 외 cwd → pass", r == {})
    r = run("pretool", {"tool_name": "Bash", "tool_input": {
        "command": "git commit -m 'DATA: 실발화 증명(git add -A --dry-run 거부) 기록'"}})
    case("pretool: 메시지 안 'git add -A' 인용 → allow (8/16 실전 오탐 재발 방지)", r == {})
    r = run("pretool", {"tool_name": "Bash", "tool_input": {"command": "git add --all"}})
    case("pretool: git add --all (비인용) → deny",
         (r.get("hookSpecificOutput") or {}).get("permissionDecision") == "deny")
    r = run("pretool", {"tool_name": "Bash", "tool_input": {"command": "ls -la && echo done"}})
    case("pretool: git 무관 명령 → allow", r == {})

    # S4 — private docs 동기 (함수 직접 호출: 실제 repo 상태를 쓴다)
    blk, wrn = _check_private_docs_sync()
    case("S4: 현 repo 미추적 docs 0 (있으면 그것이 잡아야 할 위반)", blk is None)
    case("S4: 반환 형태 = (차단|None, 경고|None)",
         (blk is None or isinstance(blk, str)) and (wrn is None or isinstance(wrn, str)))
    _saved_root = globals()["ROOT"]
    try:
        globals()["ROOT"] = td            # .git-private 없는 경로 = 다른 머신
        case("S4: .git-private 부재 → 해당 없음(통과)", _check_private_docs_sync() == (None, None))
    finally:
        globals()["ROOT"] = _saved_root
    # S4 확장 — private 전용(public 사본 없음) 파일이 더러우면 **차단**이어야 한다.
    #   2026-08-17 계기: verdicts.jsonl 이 디스크 14행 vs private HEAD 1행 (판단 trail 13건 유일본).
    _gd = os.path.join(ROOT, ".git-private")
    _priv_only = []
    if os.path.isdir(_gd):
        _t = subprocess.run(["git", "--git-dir=" + _gd, "--work-tree=" + ROOT, "ls-files"],
                            capture_output=True, text=True, timeout=15, cwd=ROOT).stdout.split("\n")
        _cands = [p for p in _t if p and not p.startswith("docs/") and p != "CLAUDE.md"]
        if _cands:
            _p = subprocess.run(["git", "-C", ROOT, "ls-files", "--"] + _cands,
                                capture_output=True, text=True, timeout=15).stdout.split("\n")
            _priv_only = [p for p in _cands if p not in set(_p)]
    case("S4: private 전용 파일이 존재한다 (없으면 이 검사 자체가 무의미)", bool(_priv_only))
    if _priv_only:
        _f = os.path.join(ROOT, _priv_only[0])
        _orig = open(_f, "rb").read()
        try:
            open(_f, "ab").write(b"\n")
            _b, _ = _check_private_docs_sync()
            case("S4: private 전용 파일 더럽히면 → 차단", bool(_b) and "유일본" in (_b or ""))
        finally:
            open(_f, "wb").write(_orig)      # 원복 — 검사가 흔적을 남기지 않는다
        _b2, _ = _check_private_docs_sync()
        case("S4: 원복 후 → 차단 해제", _b2 is None)

    # S5 — 충돌 마커. 추적 파일을 잠깐 오염시켰다가 반드시 원복한다.
    case("S5: 현 트리에 충돌 마커 없음", _check_conflict_markers() is None)
    _mk = subprocess.run(["git", "-C", ROOT, "diff", "--name-only"],
                         capture_output=True, text=True, timeout=15).stdout.splitlines()
    _txt = next((p for p in _mk if p.endswith((".json", ".jsonl", ".md", ".py", ".txt"))), None)
    if _txt:
        _fp = os.path.join(ROOT, _txt)
        _o = open(_fp, "rb").read()
        try:
            open(_fp, "ab").write(("\n<<<<<<< " + "HEAD\na\n" + "=" * 7 + "\nb\n" + ">" * 7 + " x\n").encode())
            case("S5: 마커 주입 → 차단", (_check_conflict_markers() or "").find(_txt) >= 0)
        finally:
            open(_fp, "wb").write(_o)
        case("S5: 원복 후 → 차단 해제", _check_conflict_markers() is None)
    else:
        case("S5: 주입 대상 수정파일 없음 (검사 생략, 통과 아님)", True)

    print("\n셀프테스트 " + ("전건 통과" if ok else "실패 존재"))
    return 0 if ok else 1


# ── WIRING (재구성용 기록) ─
# "hooks": {
#   "Stop": [{"hooks": [{"type": "command", "timeout": 45,
#     "command": "/usr/bin/python3 '/Users/macbookpro/Desktop/배리티 터미널/scripts/audit/verity_gate.py' --hook stop"}]}],
#   "PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "timeout": 15,
#     "command": "/usr/bin/python3 '/Users/macbookpro/Desktop/배리티 터미널/scripts/audit/verity_gate.py' --hook pretool"}]}],
#   "UserPromptSubmit": [{"hooks": [{"type": "command", "timeout": 5,
#     "command": "/usr/bin/python3 '/Users/macbookpro/Desktop/배리티 터미널/scripts/audit/verity_gate.py' --hook context"}]}]
# }

def main() -> int:
    if "--selftest" in sys.argv:
        return _selftest()
    hook = sys.argv[sys.argv.index("--hook") + 1] if "--hook" in sys.argv else ""
    if hook == "stop":
        return hook_stop()
    if hook == "pretool":
        return hook_pretool()
    if hook == "context":
        return hook_context()
    print("usage: verity_gate.py --hook stop|pretool|context | --selftest", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
