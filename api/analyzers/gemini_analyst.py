"""
Gemini API 기반 최종 의사결정 모듈
- 종목별 1줄 투자평
- 리스크 키워드 감지
- Gold/Silver 데이터 분류
"""
import json
import time
from typing import List
from google import genai
from api.config import GEMINI_API_KEY, RISK_KEYWORDS


def init_gemini():
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY 환경변수가 설정되지 않았습니다.")
    return genai.Client(api_key=GEMINI_API_KEY)


def analyze_stock(client, stock_info: dict) -> dict:
    """
    단일 종목에 대한 AI 분석 수행
    반환: { ai_verdict, risk_flags, recommendation, data_sources }
    """
    prompt = f"""당신은 한국 주식 시장 전문 분석가입니다. 아래 종목 데이터를 보고 분석해주세요.

[종목 정보]
- 종목명: {stock_info['name']} ({stock_info['ticker']})
- 시장: {stock_info['market']}
- 현재가: {stock_info['price']:,.0f}원
- PER: {stock_info['per']:.1f}
- PBR: {stock_info['pbr']:.2f}
- 배당수익률: {stock_info['div_yield']:.1f}%
- 52주 고점 대비: {stock_info['drop_from_high_pct']:.1f}%
- 안심 점수: {stock_info['safety_score']}/100
- 거래대금: {stock_info['trading_value']:,.0f}원

다음 JSON 형식으로만 답변하세요. 다른 텍스트 없이 JSON만 출력하세요:
{{
  "ai_verdict": "30자 이내의 한줄 투자 의견",
  "recommendation": "BUY" 또는 "HOLD" 또는 "WATCH" 또는 "AVOID",
  "risk_flags": ["감지된 리스크가 있다면 여기에 나열"],
  "confidence": 0부터 100 사이의 확신도,
  "gold_insight": "공시/재무제표 기반 핵심 팩트 1줄",
  "silver_insight": "시장 심리/수급 기반 참고 의견 1줄"
}}"""

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
        )
        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            text = text.rsplit("```", 1)[0]

        result = json.loads(text)

        detected_risks = []
        for kw in RISK_KEYWORDS:
            if kw in result.get("ai_verdict", "") or kw in str(result.get("risk_flags", [])):
                detected_risks.append(kw)
        result["detected_risk_keywords"] = detected_risks

        return result

    except json.JSONDecodeError:
        return {
            "ai_verdict": "AI 분석 파싱 실패 - 수동 확인 필요",
            "recommendation": "WATCH",
            "risk_flags": [],
            "confidence": 0,
            "gold_insight": "데이터 확인 필요",
            "silver_insight": "데이터 확인 필요",
            "detected_risk_keywords": [],
        }
    except Exception as e:
        return {
            "ai_verdict": f"AI 분석 오류: {str(e)[:50]}",
            "recommendation": "WATCH",
            "risk_flags": [],
            "confidence": 0,
            "gold_insight": "분석 실패",
            "silver_insight": "분석 실패",
            "detected_risk_keywords": [],
        }


def analyze_batch(candidates: List[dict]) -> List[dict]:
    """후보 종목 일괄 분석"""
    if not candidates:
        return []

    client = init_gemini()
    results = []

    for i, stock_info in enumerate(candidates):
        if i > 0:
            time.sleep(6)
        print(f"[Gemini] 분석 중 ({i+1}/{len(candidates)}): {stock_info['name']} ({stock_info['ticker']})")

        analysis = None
        for attempt in range(3):
            analysis = analyze_stock(client, stock_info)
            if "429" not in analysis.get("ai_verdict", ""):
                break
            wait = 15 * (attempt + 1)
            print(f"  ⏳ 속도 제한 → {wait}초 대기 후 재시도 ({attempt+2}/3)")
            time.sleep(wait)

        results.append({
            **stock_info,
            **analysis,
        })

    results.sort(key=lambda x: x.get("confidence", 0), reverse=True)
    return results
