#!/usr/bin/env python3
"""
VERITY Chat Hybrid — 통합 테스트 (7 시나리오)

실호출 포함 — ANTHROPIC_API_KEY / PERPLEXITY_API_KEY / GEMINI_API_KEY 필요.
예상 비용: ~$0.10 (Claude 6회 + Perplexity 2회 + Grounding 3회).

각 시나리오는 예상 조건을 PASS/FAIL 로 평가.

사용:
  python3 scripts/test_chat_hybrid.py          # 전체
  python3 scripts/test_chat_hybrid.py 1,3,5    # 특정 번호만
"""
from __future__ import annotations

import os
import sys
import time
import warnings

warnings.filterwarnings("ignore")

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# .env 로드
import api.config  # noqa

from api.chat_hybrid import cache, rate_limit
from api.chat_hybrid.orchestrator import run_hybrid
from api.chat_hybrid.intent_classifier import classify


RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
DIM = "\033[2m"
RESET = "\033[0m"


class TestResult:
    def __init__(self, name: str):
        self.name = name
        self.passed = True
        self.reasons: list[str] = []
        self.timings: dict[str, int] = {}
        self.events: list[dict] = []

    def check(self, cond: bool, why: str):
        if not cond:
            self.passed = False
            self.reasons.append(why)

    def __str__(self):
        status = f"{GREEN}PASS{RESET}" if self.passed else f"{RED}FAIL{RESET}"
        lines = [f"  [{status}] {self.name}"]
        if self.timings:
            ts = " ".join(f"{k}={v}ms" for k, v in self.timings.items())
            lines.append(f"       {DIM}{ts}{RESET}")
        for r in self.reasons:
            lines.append(f"       {RED}✗{RESET} {r}")
        return "\n".join(lines)


def run_scenario(name: str, query: str, session_id: str, expected: dict) -> TestResult:
    """orchestrator 를 실행하고 expected 조건을 체크."""
    r = TestResult(name)
    t0 = time.time()
    ttfb = None
    end_ev = None
    status_events: dict[str, dict] = {}
    text_parts: list[str] = []
    rate_limited = False

    try:
        for ev in run_hybrid(query=query, session_id=session_id):
            r.events.append(ev)
            etype = ev.get("type")
            if etype == "delta":
                if ttfb is None:
                    ttfb = int((time.time() - t0) * 1000)
                text_parts.append(ev.get("text", ""))
            elif etype == "end":
                end_ev = ev
            elif etype == "error":
                r.check(expected.get("expects_error", False), f"unexpected error: {ev.get('error')}")
            elif etype == "rate_limit":
                rate_limited = True
            elif etype == "status":
                status_events[ev.get("stage", "?")] = ev
    except Exception as e:
        r.check(False, f"exception: {type(e).__name__}: {e}")
        return r

    r.timings["total"] = int((time.time() - t0) * 1000)
    if ttfb:
        r.timings["ttfb"] = ttfb

    # 공통 체크
    if expected.get("rate_limited"):
        r.check(rate_limited, "expected rate_limit event not seen")
        return r  # rate limit 은 아래 체크 모두 스킵

    if not expected.get("expects_error"):
        r.check(end_ev is not None, "no 'end' event received")
        if end_ev is None:
            return r
        text_len = len(end_ev.get("text", ""))
        r.check(text_len > 0, f"empty response text")

    # 의도별 체크
    intent_type = (status_events.get("intent") or {}).get("intent_type")
    if "intent_type" in expected:
        r.check(
            intent_type == expected["intent_type"],
            f"intent_type expected={expected['intent_type']} got={intent_type}",
        )

    # 소스 체크
    if "must_have_source" in expected:
        sources = (end_ev or {}).get("sources", [])
        for src in expected["must_have_source"]:
            hit = any(str(s).startswith(src) for s in sources)
            r.check(hit, f"missing source prefix '{src}' in {sources}")

    # 외부 없어야 함 체크
    if expected.get("no_external"):
        sources = (end_ev or {}).get("sources", [])
        external = [s for s in sources if s != "Brain"]
        r.check(not external, f"expected no external, got {external}")

    # 캐시 히트 체크
    if expected.get("perplexity_cache_hit"):
        ext = status_events.get("external") or {}
        p = ext.get("perplexity") or {}
        r.check(p.get("cache_hit") is True, f"expected perplexity cache hit: {p}")

    if expected.get("intent_cache_hit"):
        intent = status_events.get("intent") or {}
        r.check(intent.get("cache_hit") is True, f"expected intent cache hit: {intent}")

    # TTFB 체크
    if "max_ttfb_ms" in expected and ttfb is not None:
        r.check(
            ttfb <= expected["max_ttfb_ms"],
            f"TTFB {ttfb}ms > {expected['max_ttfb_ms']}ms",
        )

    return r


def scenario_1_portfolio_only() -> TestResult:
    """포트폴리오 전용 — 외부 API 안 타야 함."""
    return run_scenario(
        name="1. portfolio_only — '내 포지션 어때?' (no external)",
        query="내 포지션 어때?",
        session_id="test-s1",
        expected={
            "intent_type": "portfolio_only",
            "must_have_source": ["Brain"],
            "no_external": True,
        },
    )


def scenario_2_hybrid_korean() -> TestResult:
    """한국 종목 hybrid — 한국 뉴스 소스 찾아야 함."""
    return run_scenario(
        name="2. hybrid — 'SK하이닉스 요즘 어때?' (Perplexity 탐)",
        query="SK하이닉스 요즘 어때?",
        session_id="test-s2",
        expected={
            "must_have_source": ["Brain"],
            # 단순 질문이라 needs_perplexity True 보통, 단 분류기 판단 따라 변동
        },
    )


def scenario_3_external_factual() -> TestResult:
    """FOMC 일정 — Gemini Grounding 가 잘 맞는 케이스."""
    return run_scenario(
        name="3. external_only — 'FOMC 다음 일정' (Grounding)",
        query="FOMC 다음 일정이 언제야?",
        session_id="test-s3",
        expected={
            "must_have_source": ["Brain"],  # Brain 도 시장 요약은 항상 제공
        },
    )


def scenario_4_cache_hit() -> TestResult:
    """#3 과 동일 질문 repeat — intent + perplexity/grounding 캐시 히트 기대."""
    return run_scenario(
        name="4. cache hit (repeat #3 within TTL)",
        query="FOMC 다음 일정이 언제야?",
        session_id="test-s4",  # 다른 세션
        expected={
            "intent_cache_hit": True,
        },
    )


def scenario_5_rate_limit() -> TestResult:
    """11번 연타 — 11번째 rate_limit 이벤트."""
    r = TestResult("5. rate limit — 동일 session 11회")
    sid = "test-s5-rl"
    # 먼저 기존 테스트 rate 기록 clear
    rate_limit.reset()
    t0 = time.time()
    caps = 0
    rl_info = None
    for i in range(11):
        ok, info = rate_limit.check_and_consume(sid)
        if not ok:
            caps += 1
            rl_info = info
    r.timings["total"] = int((time.time() - t0) * 1000)
    r.check(caps == 1, f"expected exactly 1 rate-limited call, got {caps}")
    if rl_info:
        r.check(rl_info.get("limit_type") == "per_user_minute", f"wrong limit_type: {rl_info}")
    return r


def scenario_6_classifier_fallback() -> TestResult:
    """GEMINI_API_KEY 제거 — fallback (intent=hybrid, needs_perplexity=True)."""
    r = TestResult("6. classifier fallback — no GEMINI_API_KEY")
    saved = os.environ.pop("GEMINI_API_KEY", None)
    try:
        result = classify("SK하이닉스 뉴스")
        r.check(result.get("intent_type") == "hybrid", f"intent={result.get('intent_type')}")
        r.check(result.get("needs_perplexity") is True, f"needs_perplexity={result.get('needs_perplexity')}")
        r.check("fallback" in (result.get("_source", "") or "") or "error" in (result.get("_source", "") or ""),
                f"_source={result.get('_source')}")
    finally:
        if saved:
            os.environ["GEMINI_API_KEY"] = saved
    return r


def scenario_7_brain_miss() -> TestResult:
    """포트폴리오에 없는 애매한 티커 질문 — matched_tickers 비어도 에러 없이 응답."""
    r = run_scenario(
        name="7. brain miss — 희귀 티커 (에러 없이 응답)",
        query="ZZZZ 라는 종목 내 포트폴리오에 있어?",
        session_id="test-s7",
        expected={
            "intent_type": "portfolio_only",
        },
    )
    # matched_tickers 비어있어야 함
    brain_status = None
    for ev in r.events:
        if ev.get("type") == "status" and ev.get("stage") == "brain":
            brain_status = ev
            break
    if brain_status:
        r.check(
            len(brain_status.get("matched_tickers", [])) == 0,
            f"expected empty matched_tickers, got {brain_status.get('matched_tickers')}",
        )
    return r


SCENARIOS = {
    1: scenario_1_portfolio_only,
    2: scenario_2_hybrid_korean,
    3: scenario_3_external_factual,
    4: scenario_4_cache_hit,
    5: scenario_5_rate_limit,
    6: scenario_6_classifier_fallback,
    7: scenario_7_brain_miss,
}


def main():
    selected = set(SCENARIOS.keys())
    if len(sys.argv) > 1:
        try:
            selected = {int(x.strip()) for x in sys.argv[1].split(",")}
        except ValueError:
            print(f"{RED}잘못된 인자. 예: 1,3,5{RESET}")
            sys.exit(1)

    print(f"\n{CYAN}═══ VERITY Chat Hybrid — 통합 테스트 ═══{RESET}")
    print(f"{DIM}선택: {sorted(selected)}{RESET}\n")

    results = []
    for num in sorted(selected):
        fn = SCENARIOS.get(num)
        if not fn:
            continue
        print(f"{CYAN}▶ 시나리오 {num} 실행 중...{RESET}")
        r = fn()
        results.append(r)
        print(r)
        print()

    # 요약
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed
    color = GREEN if failed == 0 else RED
    print(f"{CYAN}═══ 결과 ═══{RESET}")
    print(f"  {color}{passed}/{total} PASS{RESET}")

    # 비용 집계
    from api.chat_hybrid.search import perplexity_client, gemini_grounding
    from api.chat_hybrid.response_synthesizer import get_session_stats as synth_stats
    print(f"\n{CYAN}═══ 비용 집계 ═══{RESET}")
    print(f"  Perplexity: {perplexity_client.get_session_stats()}")
    print(f"  Grounding:  {gemini_grounding.get_session_stats()}")
    print(f"  Synthesize: {synth_stats()}")
    print(f"  Cache:      {cache.stats()}")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
