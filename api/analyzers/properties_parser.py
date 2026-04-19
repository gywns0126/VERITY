"""
10-K Item 2 'Properties' 섹션 → 구조화 JSON 파서.

입력: SEC EDGAR에서 추출한 Properties 섹션 원문 텍스트
출력: 보유/임차 부동산 리스트 + 본사 + 총계 요약

Gemini Flash 기본. 연 1회 공시라 accession 캐싱으로 중복 호출 방지.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Dict, Optional

from google import genai

from api.mocks import mockable
from api.config import GEMINI_API_KEY, GEMINI_MODEL_DEFAULT

logger = logging.getLogger(__name__)


_PROMPT_TEMPLATE = """너는 SEC 10-K 공시를 파싱하는 전문가다.
아래는 {company} ({ticker})의 10-K 'Item 2. Properties' 섹션 원문이다.
회사가 소유/임차한 부동산 정보를 추출하여 반드시 아래 JSON 스키마로만 응답한다.

스키마:
{{
  "headquarters": {{
    "location": "도시, 주/국가",
    "size_sqft": 숫자 또는 null,
    "status": "owned" 또는 "leased" 또는 "mixed" 또는 null,
    "description": "간단 설명"
  }},
  "owned_properties": [
    {{
      "location": "도시/주/국가 또는 상세주소",
      "size_sqft": 숫자 또는 null,
      "use": "본사/R&D/공장/물류센터/매장/데이터센터/오피스/기타 중 하나",
      "segment": "해당 사업부문 (예: Retail, Cloud 등)" 또는 null,
      "notes": "특이사항 (없으면 빈 문자열)"
    }}
  ],
  "leased_properties": [ ...owned와 동일 구조... ],
  "total_owned_sqft": 숫자 또는 null,
  "total_leased_sqft": 숫자 또는 null,
  "facility_count": {{"owned": N, "leased": N}},
  "key_insights": "투자자 관점에서 주목할 포인트 2~3문장 (한국어)",
  "summary_ko": "한국어 3~4줄 요약"
}}

규칙:
- square feet(sqft) 단위로 통일. acres·square meters가 나오면 변환 (1 acre ≈ 43560 sqft, 1 sqm ≈ 10.764 sqft).
- 숫자는 쉼표 없이 정수. 불명확하면 null.
- 자산별로 상세 리스트가 없고 합계만 있으면 owned/leased_properties는 빈 배열, total_*만 채운다.
- 본문에 부동산 정보가 거의 없거나 'none'으로 기술되면 모든 배열/숫자를 비우고 key_insights에 사유 기재.
- JSON만 출력. 설명 문구·마크다운 코드펜스 금지.

=== 원문 ===
{raw_text}
=== 끝 ==="""


def _strip_codefence(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    return s.strip()


@mockable("gemini.properties_parse")
def parse_10k_properties(
    company: str,
    ticker: str,
    raw_text: str,
    model: Optional[str] = None,
) -> Dict:
    """10-K Item 2 원문 텍스트 → 구조화 JSON."""
    if not GEMINI_API_KEY:
        return {"error": "no_api_key"}
    if not raw_text or len(raw_text) < 200:
        return {"error": "text_too_short"}

    client = genai.Client(api_key=GEMINI_API_KEY)
    use_model = model or GEMINI_MODEL_DEFAULT

    prompt = _PROMPT_TEMPLATE.format(
        company=company or ticker,
        ticker=ticker,
        raw_text=raw_text[:40000],
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
        logger.warning("Gemini properties parse failed for %s: %s", ticker, e)
        return {"error": f"gemini:{e}"}

    try:
        data = json.loads(text)
    except Exception as e:
        logger.warning("properties JSON decode failed for %s: %s | text head: %s", ticker, e, text[:200])
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
            ticker=ticker, call_type="10k_properties_parse",
        )
    except Exception:
        pass

    for key in ("owned_properties", "leased_properties"):
        if not isinstance(data.get(key), list):
            data[key] = []

    return data
