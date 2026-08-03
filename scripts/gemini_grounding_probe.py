"""gemini_grounding_probe — Gemini 구글 검색 그라운딩 거시 정보 품질 1회 실험 (PM 2026-08-03).

PM: "재미나이를 통해 구글에서 얻을 수 있는 거시 경제 정보가 뭐가 있는지 봐봐.
     노이즈인지 아닌지 확인해야 하고."

판정 설계:
  ① 거시 5축 질의(중앙은행·미10년물·달러/원·오늘 코스피 급락 원인·원자재) — 수치+날짜+출처 요구
  ② grounding_metadata 실출처(도메인) 로깅 — 통신사/1차 vs 블로그 노이즈 구분
  ③ 우리 1차 실측(portfolio.json macro/market_summary)을 기준값으로 병행 출력 — 수치 대조
LLM 1콜(비용 ~$0.01). 채점/발행 미투입 — 순수 관측 (RULE 6/7 무관 레이어).
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def baseline() -> str:
    try:
        with open("data/portfolio.json", encoding="utf-8") as f:
            p = json.load(f)
        mac = p.get("macro") or {}
        ms = p.get("market_summary") or {}
        lines = ["[우리 1차 실측 기준값 — 대조용]"]
        for k in ("usd_krw", "wti_oil", "gold", "vix"):
            n = mac.get(k) or {}
            if isinstance(n, dict) and n.get("value") is not None:
                lines.append(f"  {k} = {n.get('value')} ({n.get('change_pct')}%)")
        ks = ms.get("kospi") or {}
        if isinstance(ks, dict):
            lines.append(f"  kospi = {ks.get('value')}")
        return "\n".join(lines)
    except Exception as e:
        return f"[기준값 로드 실패: {e}]"


def main() -> int:
    from google import genai
    from google.genai import types

    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        print("GEMINI_API_KEY 없음")
        return 1

    # grounding 지원 확실한 2.5 flash 명시 (flash-lite 지원 불확실 — 실험 변수 제거)
    model = os.environ.get("PROBE_MODEL", "gemini-2.5-flash")
    client = genai.Client(api_key=key)

    prompt = (
        "오늘은 2026-08-03(월, KST)이다. 글로벌 거시경제 사실만 — 의견·전망 금지, "
        "각 항목에 수치·기준일·출처(매체명)를 병기하라. 평문 개조식:\n"
        "1) 연준·한국은행·BOJ 최신 결정/발언 (최근 1주)\n"
        "2) 미 10년물 국채 금리 현재 수준\n"
        "3) 달러/원 환율 현재 수준\n"
        "4) 오늘 코스피 급락(-5%대)의 보도된 원인\n"
        "5) WTI 유가·금 가격 현재 수준"
    )

    resp = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
        ),
    )

    print("=" * 70)
    print(f"[모델] {model}")
    print("=" * 70)
    print(resp.text or "(빈 응답)")
    print("=" * 70)

    # grounding 출처 — 도메인 품질이 노이즈 판정 핵심
    try:
        gm = resp.candidates[0].grounding_metadata
        qs = getattr(gm, "web_search_queries", None) or []
        print(f"[검색 질의 {len(qs)}건] {qs}")
        chunks = getattr(gm, "grounding_chunks", None) or []
        print(f"[grounding 출처 {len(chunks)}건]")
        for ch in chunks[:20]:
            web = getattr(ch, "web", None)
            if web is not None:
                print(f"  - {getattr(web, 'title', '')} :: {getattr(web, 'uri', '')[:110]}")
    except Exception as e:
        print(f"[grounding metadata 접근 실패: {e}]")

    print("=" * 70)
    print(baseline())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
