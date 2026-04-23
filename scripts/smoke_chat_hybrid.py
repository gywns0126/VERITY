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

try:
    import requests
except ImportError:
    print("ERROR: requests 모듈 필요 — pip install requests")
    sys.exit(2)


DEFAULT_URL = "https://vercel-api-alpha-umber.vercel.app/api/chat"

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


def stream_ndjson(url: str, question: str, connect_timeout: float = 10.0, read_timeout: float = 25.0):
    """NDJSON stream 을 안전하게 읽음.

    requests.iter_lines 가 chunk-level timeout 을 연결된 socket 에 강제 —
    urllib 은 response 수신 후 read() block 무방어였음.
    """
    try:
        resp = requests.post(
            url,
            json={"question": question, "stream": True},
            stream=True,
            timeout=(connect_timeout, read_timeout),
        )
    except requests.Timeout as e:
        raise RuntimeError(f"connect/read timeout: {e}") from e
    except requests.RequestException as e:
        raise RuntimeError(f"network error: {type(e).__name__}: {e}") from e

    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")

    content_type = resp.headers.get("Content-Type", "")
    if "ndjson" not in content_type and "json" not in content_type:
        raise RuntimeError(f"unexpected content-type: {content_type}")

    try:
        for line in resp.iter_lines(decode_unicode=True):
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue
    except requests.Timeout as e:
        raise RuntimeError(f"stream read timeout: {e}") from e
    finally:
        resp.close()


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


def preflight_diag(chat_url: str) -> bool:
    """배포 상태 먼저 확인 — hybrid 로드됐는지."""
    diag_url = chat_url.rstrip("/").replace("/chat", "/chat_diag")
    print(f"{CYAN}▶ Preflight /chat_diag 조회{RESET}  {DIM}{diag_url}{RESET}")
    try:
        resp = requests.get(diag_url, timeout=10)
    except Exception as e:
        print(f"  {RED}✗ diag endpoint 응답 실패: {e}{RESET}")
        return False
    if resp.status_code != 200:
        print(f"  {YELLOW}⚠ HTTP {resp.status_code} — chat_diag.py 미배포 가능{RESET}")
        return False
    try:
        data = resp.json()
    except Exception:
        print(f"  {RED}✗ JSON 파싱 실패{RESET}")
        return False

    hyb = data.get("hybrid", {})
    enabled = hyb.get("enabled_flag")
    loaded = hyb.get("module_loaded")
    err = hyb.get("import_error")

    marks = [
        ("CHAT_HYBRID_ENABLED=true", enabled, RED if not enabled else GREEN),
        ("orchestrator import 성공", loaded, RED if not loaded else GREEN),
    ]
    for label, ok, color in marks:
        mark = "✓" if ok else "✗"
        print(f"  {color}{mark} {label}{RESET}")
    if err:
        print(f"  {RED}import_error: {err}{RESET}")

    # 핵심 env 키 존재 여부
    env_present = data.get("env_keys_present", {})
    required = ["ANTHROPIC_API_KEY", "PERPLEXITY_API_KEY", "GEMINI_API_KEY"]
    for k in required:
        info = env_present.get(k, {})
        present = info.get("present", False)
        color = GREEN if present else RED
        print(f"  {color}{'✓' if present else '✗'} {k} present={present}{RESET}")

    runtime = data.get("runtime", {})
    if not runtime.get("chat_hybrid_path_exists"):
        print(f"  {RED}✗ Vercel 번들에 api/chat_hybrid/ 미포함 — includeFiles 설정 확인{RESET}")

    return bool(enabled and loaded)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=DEFAULT_URL, help=f"엔드포인트 URL (기본 {DEFAULT_URL})")
    ap.add_argument("--only", type=int, help="특정 케이스 번호만 (1/2/3)")
    ap.add_argument("--skip-preflight", action="store_true", help="/chat_diag 사전확인 스킵")
    args = ap.parse_args()

    print(f"\n{CYAN}═══ Chat Hybrid 라이브 스모크 테스트 ═══{RESET}")
    print(f"{DIM}URL: {args.url}{RESET}\n")

    if not args.skip_preflight:
        preflight_ok = preflight_diag(args.url)
        print()
        if not preflight_ok:
            print(f"{YELLOW}⚠ preflight 실패 — 스트림 테스트는 legacy 경로로 돌 가능성 높음{RESET}\n")

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
