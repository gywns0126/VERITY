"""
VERITY — AI 오심 포스트모텀 엔진

과거 BUY 추천이 하락하거나, AVOID 추천이 상승한 경우를 추출하여
Claude Sonnet에게 실패 원인 분석을 의뢰. 결과를 portfolio.json에 저장하고
텔레그램으로 발송.
"""
import json
from typing import Optional

from api.config import ANTHROPIC_API_KEY, now_kst
from api.workflows.archiver import load_snapshots_range

_POSTMORTEM_PROMPT_SYSTEM = """너는 15년 차 퀀트 리서치 팀장이다.
AI가 내린 추천이 왜 틀렸는지 사후 분석하는 역할이다.

원칙:
- 결과론적 판단 금지. "떨어졌으니까 나빴다"는 분석이 아니다
- 어떤 팩터가 잘못된 시그널을 냈는지 구체적으로 지적
- 매크로 환경 변화, 돌발 이벤트, 수급 반전 등 AI가 예측 불가했던 요인 분리
- 교훈은 "다음에 이 패턴이 보이면 이렇게 하자" 형식으로
- 반말 OK. 서론 금지. 핵심만."""


def _find_failures(days: int = 7, threshold_pct: float = -3.0) -> list:
    """최근 N일 스냅샷에서 AI 판정이 빗나간 종목 추출."""
    snapshots = load_snapshots_range(days)
    if len(snapshots) < 2:
        return []

    first = snapshots[0]
    last = snapshots[-1]

    first_recs = {r["ticker"]: r for r in first.get("recommendations", [])}
    last_recs = {r["ticker"]: r for r in last.get("recommendations", [])}

    failures = []
    for ticker, orig in first_recs.items():
        orig_price = orig.get("price", 0)
        if not orig_price:
            continue

        cur = last_recs.get(ticker)
        cur_price = cur.get("price", orig_price) if cur else orig_price
        ret_pct = round((cur_price - orig_price) / orig_price * 100, 2)

        rec = orig.get("recommendation", "WATCH")

        if rec == "BUY" and ret_pct <= threshold_pct:
            failures.append({
                "type": "false_buy",
                "ticker": ticker,
                "name": orig.get("name", "?"),
                "original_rec": rec,
                "actual_return": ret_pct,
                "buy_price": orig_price,
                "current_price": cur_price,
                "multi_score": orig.get("multi_factor", {}).get("multi_score", 0),
                "brain_score": orig.get("verity_brain", {}).get("brain_score", 0),
                "brain_grade": orig.get("verity_brain", {}).get("grade", "?"),
                "ai_verdict": orig.get("ai_verdict", ""),
                "risk_flags": orig.get("risk_flags", []),
                "technical_rsi": orig.get("technical", {}).get("rsi", "?"),
                "flow_score": orig.get("flow", {}).get("flow_score", "?"),
                "consensus_score": orig.get("consensus", {}).get("consensus_score", "?"),
                "prediction_up": orig.get("prediction", {}).get("up_probability", "?"),
            })

        elif rec == "AVOID" and ret_pct >= abs(threshold_pct):
            failures.append({
                "type": "missed_opportunity",
                "ticker": ticker,
                "name": orig.get("name", "?"),
                "original_rec": rec,
                "actual_return": ret_pct,
                "buy_price": orig_price,
                "current_price": cur_price,
                "multi_score": orig.get("multi_factor", {}).get("multi_score", 0),
                "brain_score": orig.get("verity_brain", {}).get("brain_score", 0),
                "brain_grade": orig.get("verity_brain", {}).get("grade", "?"),
                "ai_verdict": orig.get("ai_verdict", ""),
                "risk_flags": orig.get("risk_flags", []),
                "technical_rsi": orig.get("technical", {}).get("rsi", "?"),
                "flow_score": orig.get("flow", {}).get("flow_score", "?"),
                "consensus_score": orig.get("consensus", {}).get("consensus_score", "?"),
                "prediction_up": orig.get("prediction", {}).get("up_probability", "?"),
            })

    failures.sort(key=lambda x: x["actual_return"])
    return failures[:10]


def _build_postmortem_prompt(failures: list) -> str:
    blocks = []
    for i, f in enumerate(failures, 1):
        label = "BUY→하락" if f["type"] == "false_buy" else "AVOID→상승"
        blocks.append(f"""[오심 {i}] {f['name']} ({f['ticker']}) — {label}
  AI 판정: {f['original_rec']} | 실제 수익률: {f['actual_return']:+.1f}%
  매수가: {f['buy_price']:,.0f}원 → 현재: {f['current_price']:,.0f}원
  멀티팩터: {f['multi_score']}점 | 브레인: {f['brain_score']}점 ({f['brain_grade']})
  RSI: {f['technical_rsi']} | 수급: {f['flow_score']} | 컨센서스: {f['consensus_score']} | AI상승률: {f['prediction_up']}%
  AI근거: {f['ai_verdict'][:120]}
  리스크플래그: {', '.join(f['risk_flags'][:3]) or '없음'}""")

    prompt = "\n\n".join(blocks)
    return f"""다음은 VERITY AI가 최근 7일간 판정을 틀린 종목들이다.
왜 틀렸는지 사후 분석해라.

{prompt}

JSON으로:
{{
  "analyses": [
    {{
      "ticker": "종목코드",
      "postmortem": "50자 이내. 왜 틀렸는지 핵심 원인",
      "misleading_factor": "잘못된 시그널을 준 팩터 (technical/sentiment/flow/consensus/prediction/brain 중)",
      "unforeseeable": true/false,
      "lesson": "다음에 이 패턴이 보이면 어떻게 해야 하는지 한 줄"
    }}
  ],
  "overall_lesson": "전체 오심에서 발견된 공통 패턴 한 줄",
  "system_suggestion": "시스템 개선 제안 한 줄"
}}"""


def generate_postmortem(days: int = 7) -> dict:
    """AI 오심 포스트모텀 리포트 생성."""
    failures = _find_failures(days)
    if not failures:
        return {
            "status": "clean",
            "message": "최근 7일간 유의미한 AI 오심 없음",
            "failures": [],
            "generated_at": now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        }

    if not ANTHROPIC_API_KEY:
        for f in failures:
            f["postmortem"] = "AI 분석 불가 (API 키 미설정)"
        return {
            "status": "partial",
            "failures": failures,
            "analyzed_count": len(failures),
            "period": f"최근 {days}일",
            "summary": f"AI 오심 {len(failures)}건 감지 (Sonnet 분석 불가)",
            "lesson": "",
            "generated_at": now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        }

    import anthropic

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        prompt = _build_postmortem_prompt(failures)

        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1200,
            system=_POSTMORTEM_PROMPT_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        text = message.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            text = text.rsplit("```", 1)[0]

        result = json.loads(text)
        analyses = {a["ticker"]: a for a in result.get("analyses", [])}

        for f in failures:
            a = analyses.get(f["ticker"], {})
            f["postmortem"] = a.get("postmortem", "")
            f["misleading_factor"] = a.get("misleading_factor", "")
            f["unforeseeable"] = a.get("unforeseeable", False)
            f["lesson"] = a.get("lesson", "")

        false_buys = [f for f in failures if f["type"] == "false_buy"]
        missed = [f for f in failures if f["type"] == "missed_opportunity"]
        summary_parts = []
        if false_buys:
            summary_parts.append(f"매수→하락 {len(false_buys)}건")
        if missed:
            summary_parts.append(f"회피→상승 {len(missed)}건")

        return {
            "status": "analyzed",
            "failures": failures,
            "analyzed_count": len(failures),
            "period": f"최근 {days}일",
            "summary": f"AI 오심 {' / '.join(summary_parts)}",
            "lesson": result.get("overall_lesson", ""),
            "system_suggestion": result.get("system_suggestion", ""),
            "generated_at": now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
            "_tokens": message.usage.input_tokens + message.usage.output_tokens,
        }

    except json.JSONDecodeError:
        for f in failures:
            f["postmortem"] = "JSON 파싱 실패"
        return _fallback_report(failures, days, "Sonnet 응답 파싱 실패")
    except Exception as e:
        for f in failures:
            f["postmortem"] = f"분석 오류: {str(e)[:60]}"
        return _fallback_report(failures, days, str(e)[:80])


def _fallback_report(failures: list, days: int, error: str) -> dict:
    return {
        "status": "error",
        "failures": failures,
        "analyzed_count": len(failures),
        "period": f"최근 {days}일",
        "summary": f"AI 오심 {len(failures)}건 (Sonnet 분석 실패: {error})",
        "lesson": "",
        "generated_at": now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
    }
