#!/usr/bin/env python3
"""
VERITY Chat Hybrid — 라이브 엔드포인트 스모크 테스트

Vercel 배포 후 CHAT_HYBRID_ENABLED 가 제대로 켜졌는지 + 3유형 질문이 기대대로
동작하는지 확인. stream NDJSON 을 실제로 읽어서 status/meta/delta/end 이벤트
타입별로 집계.

사용:
  python3 scripts/smoke_chat_hybrid.py                              # 기본 URL
  python3 scripts/smoke_chat_hybrid.py --url https://my-app.vercel.app/api/chat
  python3 scripts/smoke_chat_hybrid.py --only 1                     # 1번만

실패 신호:
  - sources 에 "Brain" 없음 → orchestrator 미로드 → CHAT_HYBRID_ENABLED 꺼진 상태
  - type=delta 만 오고 status/meta 없음 → legacy 경로로 폴백됨
  - HTTP 4xx/5xx → 환경변수 누락 (PERPLEXITY_API_KEY, ANTHROPIC_API_KEY)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Optional
from urllib import request as urlreq


DEFAULT_URL = "https://project-yw131.vercel.app/api/chat"

RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
DIM = "\033[2m"
RESET = "\033[0m"


CASES = [
    {
        "n": 1,
        "label": "portfolio_only — 외부 호출 0",
        "q": "내 포지션 전반 어때?",
        "must": {"has_brain": True, "no_external_ok": True},
        "hint": "Brain 배지만 기대, P/G 없어도 정상",
    },
    {
        "n": 2,
        "label": "external_only — Grounding fact",
        "q": "FOMC 다음 일정 언제야?",
        "must": {"has_brain": True, "has_citations": True},
        "hint": "G(N) 배지 + 인용 1개 이상",
    },
    {
        "n": 3,
        "label": "hybrid — Perplexity 뉴스",
        "q": "SK하이닉스 요즘 어때?",
        "must": {"has_brain": True},
        "hint": "Brain + P(N) 배지 기대 (Grounding 도 가능)",
    },
]


def stream_ndjson(url: str, question: str, timeout: float = 30.0):
    payload = json.dumps({"question": question, "stream": True}).encode("utf-8")
    req = urlreq.Request(
        url,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    resp = urlreq.urlopen(req, timeout=timeout)
    status = resp.status
    content_type = resp.headers.get("Content-Type", "")
    if "ndjson" not in content_type and "json" not in content_type:
        raise RuntimeError(f"unexpected content-type: {content_type}")

    buf = b""
    for chunk in iter(lambda: resp.read(2048), b""):
        buf += chunk
        while b"\n" in buf:
            line, _, buf = buf.partition(b"\n")
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line.decode("utf-8"))
            except json.JSONDecodeError:
                continue
    if buf.strip():
        try:
            yield json.loads(buf.decode("utf-8"))
        except json.JSONDecodeError:
            pass


def run_case(url: str, case: dict):
    t0 = time.time()
    ttfb = None
    event_counts = {"status": 0, "meta": 0, "delta": 0, "end": 0, "error": 0, "rate_limit": 0}
    final_sources: list = []
    final_citations: list = []
    intent_type: Optional[str] = None
    final_text = []
    status_stages: dict = {}

    try:
        for ev in stream_ndjson(url, case["q"]):
            etype = ev.get("type", "?")
            event_counts[etype] = event_counts.get(etype, 0) + 1
            if etype == "delta":
                if ttfb is None:
                    ttfb = int((time.time() - t0) * 1000)
                final_text.append(ev.get("text", ""))
            elif etype == "status":
                status_stages[ev.get("stage", "?")] = ev
                if ev.get("intent_type"):
                    intent_type = ev.get("intent_type")
            elif etype == "meta":
                if ev.get("sources"):
                    final_sources = ev["sources"]
            elif etype == "end":
                if ev.get("sources"):
                    final_sources = ev["sources"]
                if ev.get("citations"):
                    final_citations = ev["citations"]
                if ev.get("intent_type"):
                    intent_type = ev["intent_type"]
            elif etype == "error":
                msg = ev.get("message") or ev.get("error") or "?"
                print(f"{RED}  ✗ error event: {msg}{RESET}")
                break
    except Exception as e:
        print(f"{RED}  ✗ request failed: {type(e).__name__}: {str(e)[:150]}{RESET}")
        return False

    total_ms = int((time.time() - t0) * 1000)

    # 평가
    checks = []
    must = case["must"]
    has_brain = any(str(s).startswith("Brain") for s in final_sources)
    has_external = any(str(s).startswith(("P(", "G(")) for s in final_sources)
    has_citations = len(final_citations) > 0
    is_hybrid_route = event_counts.get("status", 0) > 0 or event_counts.get("meta", 0) > 0

    checks.append((is_hybrid_route, "hybrid 경로 사용 (status/meta 이벤트 수신)"))
    if must.get("has_brain"):
        checks.append((has_brain, "sources 에 Brain 포함"))
    if must.get("has_citations"):
        checks.append((has_citations, f"citations ≥1 (got {len(final_citations)})"))
    checks.append((event_counts["end"] >= 1, "end 이벤트 수신"))
    checks.append((len("".join(final_text).strip()) > 20, "응답 텍스트 >20자"))

    ok = all(c for c, _ in checks)
    color = GREEN if ok else RED

    print(f"  {color}{'PASS' if ok else 'FAIL'}{RESET} "
          f"{DIM}ttfb={ttfb}ms total={total_ms}ms "
          f"intent={intent_type or '—'} events={event_counts} "
          f"sources={final_sources} cites={len(final_citations)}{RESET}")
    for passed, desc in checks:
        mark = f"{GREEN}✓{RESET}" if passed else f"{RED}✗{RESET}"
        print(f"     {mark} {desc}")
    if not is_hybrid_route:
        print(f"     {YELLOW}⚠ legacy Gemini 경로 사용중 — CHAT_HYBRID_ENABLED=true 확인{RESET}")
    if not final_sources and is_hybrid_route:
        print(f"     {YELLOW}⚠ sources 비어있음 — orchestrator end 이벤트 누락 가능성{RESET}")

    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=DEFAULT_URL, help=f"엔드포인트 URL (기본 {DEFAULT_URL})")
    ap.add_argument("--only", type=int, help="특정 케이스 번호만 (1/2/3)")
    args = ap.parse_args()

    print(f"\n{CYAN}═══ Chat Hybrid 라이브 스모크 테스트 ═══{RESET}")
    print(f"{DIM}URL: {args.url}{RESET}\n")

    cases = CASES if not args.only else [c for c in CASES if c["n"] == args.only]
    results = []
    for c in cases:
        print(f"{CYAN}▶ [{c['n']}] {c['label']}{RESET}")
        print(f"  Q: {c['q']}")
        print(f"  {DIM}hint: {c['hint']}{RESET}")
        results.append(run_case(args.url, c))
        print()

    passed = sum(1 for r in results if r)
    total = len(results)
    color = GREEN if passed == total else RED
    print(f"{CYAN}═══ 결과 ═══{RESET}")
    print(f"  {color}{passed}/{total} PASS{RESET}")

    if passed != total:
        print(f"\n{YELLOW}실패시 체크리스트:{RESET}")
        print(f"  1. Vercel env: CHAT_HYBRID_ENABLED=true")
        print(f"  2. Vercel env: ANTHROPIC_API_KEY, PERPLEXITY_API_KEY, GEMINI_API_KEY")
        print(f"  3. vercel.json includeFiles 가 api/chat_hybrid/** 번들하고 있는지")
        print(f"  4. Vercel Function Logs 에서 'chat_hybrid orchestrator 로드 성공' 메시지 확인")

    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
