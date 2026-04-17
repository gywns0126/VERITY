"""
DART 사업보고서 "II. 사업의 내용" → 구조화 JSON 파서.

대상:
- 일반 상장사: 국내/해외 사업장·공장·R&D·물류센터·매장 리스트
- 상장 REITs: 투자부동산(건물) 리스트 (주소·면적·감정가·임대율·주요 임차인)

산출:
- 국가별 노출 비중 → 관세·지정학 리스크 분석에 활용
- 사업부문별 매핑

연 1회 공시 기준 rcept_no 캐싱으로 중복 LLM 호출 방지.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Dict, Optional

from google import genai

from api.config import GEMINI_API_KEY, GEMINI_MODEL_DEFAULT

logger = logging.getLogger(__name__)


_PROMPT_TEMPLATE = """너는 한국 상장사 사업보고서를 분석하는 전문가다.
아래는 {company} ({ticker}) 사업보고서의 'II. 사업의 내용' 섹션 원문이다.
회사의 물리적 자산(사업장·공장·투자부동산)을 추출하여 반드시 아래 JSON 스키마로만 응답한다.

스키마:
{{
  "company_type": "reit" 또는 "manufacturer" 또는 "retail" 또는 "financial" 또는 "service" 또는 "other",
  "headquarters": {{
    "location": "본사 주소 또는 도시·구",
    "ownership": "소유" 또는 "임차" 또는 null
  }},
  "domestic_facilities": [
    {{
      "name": "사업장명 또는 건물명",
      "location": "소재지 (시·도 + 구/시)",
      "use": "본사/공장/R&D/물류센터/매장/투자부동산/오피스/기타 중 하나",
      "segment": "해당 사업부문명 또는 null",
      "size_sqm": 숫자 또는 null,
      "ownership": "소유" 또는 "임차" 또는 null,
      "notes": "특이사항 (감정가·임대율·주요 임차인·가동률 등, 없으면 빈 문자열)"
    }}
  ],
  "overseas_facilities": [
    {{
      "country": "국가명 (한국어)",
      "country_code": "ISO 2자리 (CN/US/VN/JP 등)",
      "name": "사업장명",
      "location": "도시 또는 상세주소",
      "use": "...(위와 동일)",
      "segment": "...",
      "size_sqm": 숫자 또는 null,
      "ownership": "소유/임차/합작/null",
      "notes": "..."
    }}
  ],
  "investment_properties": [
    {{
      "name": "건물명",
      "location": "주소",
      "size_sqm": 숫자 또는 null,
      "book_value_krw": 숫자 또는 null,
      "fair_value_krw": 숫자 또는 null,
      "occupancy_rate": "임대율 % (숫자)" 또는 null,
      "major_tenants": ["임차인1", "임차인2"],
      "notes": ""
    }}
  ],
  "country_exposure": {{
    "KR": 국내 비중 (0-100, 사업장 수/면적/매출 중 가용한 기준으로 추정),
    "CN": ...,
    "US": ...,
    "VN": ...
  }},
  "total_domestic_sqm": 숫자 또는 null,
  "total_overseas_sqm": 숫자 또는 null,
  "geopolitical_risk": "중국·미국·대만 등 지정학 민감 지역 노출 평가 2~3문장",
  "key_insights": "투자자 관점 주목 포인트 2~3문장",
  "summary_ko": "3~4줄 한국어 요약"
}}

규칙:
- 면적은 ㎡(sqm) 단위로 통일. 평(坪)이 나오면 1평 ≈ 3.3㎡로 변환. ㎢는 1,000,000배.
- 숫자는 쉼표 없이 정수 또는 null.
- 국내 사업장만 있으면 overseas_facilities=[], country_exposure={{"KR": 100}}.
- REITs·부동산 전문 기업이면 company_type="reit"로 설정하고 investment_properties에 건물별 상세 채운다.
- 일반 제조업이면 investment_properties는 보통 빈 배열.
- 세그먼트명은 원문의 사업부문 명칭을 그대로 사용 (예: "반도체", "디스플레이", "Harman").
- JSON만 출력. 설명·마크다운 코드펜스·주석 금지.

=== 원문 ===
{raw_text}
=== 끝 ==="""


def _strip_codefence(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    return s.strip()


def parse_business_facilities(
    company: str,
    ticker: str,
    raw_text: str,
    model: Optional[str] = None,
) -> Dict:
    """사업보고서 원문 → 구조화 JSON (사업장·해외거점·투자부동산)."""
    if not GEMINI_API_KEY:
        return {"error": "no_api_key"}
    if not raw_text or len(raw_text) < 300:
        return {"error": "text_too_short"}

    client = genai.Client(api_key=GEMINI_API_KEY)
    use_model = model or GEMINI_MODEL_DEFAULT

    prompt = _PROMPT_TEMPLATE.format(
        company=company or ticker,
        ticker=ticker,
        raw_text=raw_text[:60000],
    )

    try:
        resp = client.models.generate_content(
            model=use_model,
            contents=prompt,
            config={
                "temperature": 0.1,
                "response_mime_type": "application/json",
            },
        )
        text = _strip_codefence((resp.text or "").strip())
    except Exception as e:
        logger.warning("Gemini facilities parse failed for %s: %s", ticker, e)
        return {"error": f"gemini:{e}"}

    try:
        data = json.loads(text)
    except Exception as e:
        logger.warning("facilities JSON decode failed for %s: %s | %s", ticker, e, text[:200])
        return {"error": f"json_decode:{e}", "raw_response": text[:500]}

    try:
        from api.tracing import get_tracer
        usage = getattr(resp, "usage_metadata", None)
        pt = getattr(usage, "prompt_token_count", 0) if usage else 0
        ct = getattr(usage, "candidates_token_count", 0) if usage else 0
        get_tracer().log_ai(
            provider="gemini", model=use_model,
            prompt_tokens=pt, completion_tokens=ct,
            prompt_preview=prompt[:300], response_preview=text[:300],
            ticker=ticker, call_type="dart_facilities_parse",
        )
    except Exception:
        pass

    for key in ("domestic_facilities", "overseas_facilities", "investment_properties"):
        if not isinstance(data.get(key), list):
            data[key] = []
    if not isinstance(data.get("country_exposure"), dict):
        data["country_exposure"] = {}

    return data
