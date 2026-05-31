"""
Gemini generate_content cost 로깅 헬퍼 — usage_metadata 추출 + llm_cost 기록.

2026-05-30 — logging coverage 부재 발견 (llm_cost.jsonl entries 42건 한 달,
실 사용 5만원/월 추정 = coverage 1-5%). 2026-05-31 정정: cost 84.7% 지배 경로는
raw generate_content 가 아니라 gemini_cache.generate_with_cache 단일 함수 경유.
→ 핵심 = log_gemini_usage() 헬퍼를 cache 경로 + raw 경로 양쪽에서 재사용.
usage_metadata.prompt_token_count + candidates_token_count 우선, fallback = len//4.

사용 example (raw 경로):
    from api.utils.gemini_tracked import tracked_generate
    resp = tracked_generate(client, model, contents, call_type="commodity_narrator")

사용 example (response 만 로깅):
    from api.utils.gemini_tracked import log_gemini_usage
    log_gemini_usage(resp, model, "stock_analysis", contents=prompt)
"""
from __future__ import annotations

from typing import Any, Optional


def _approx_tokens(contents: Any) -> int:
    """문자열 길이 // 4 추정 (영문 평균). dict/list 는 repr 길이."""
    try:
        if isinstance(contents, str):
            return len(contents) // 4
        return len(str(contents)) // 4
    except Exception:
        return 0


def log_gemini_usage(
    resp: Any,
    model: str,
    call_type: str,
    contents: Any = None,
    provider: str = "google",
    success: bool = True,
) -> None:
    """response 에서 usage_metadata 추출 → llm_cost.log_call 1줄 append. 실패 무시.

    usage_metadata 우선, 없으면 contents/resp.text 길이 // 4 fallback.
    cache 경로(generate_with_cache) + raw 경로(tracked_generate) 공용.
    """
    try:
        from api.metadata import llm_cost
    except Exception:
        return

    in_t = 0
    out_t = 0
    try:
        usage = getattr(resp, "usage_metadata", None)
        if usage is not None:
            in_t = int(getattr(usage, "prompt_token_count", 0) or 0)
            out_t = int(getattr(usage, "candidates_token_count", 0) or 0)
    except Exception:
        pass

    if in_t == 0 and contents is not None:
        in_t = _approx_tokens(contents)
    if out_t == 0:
        try:
            out_t = len(getattr(resp, "text", "") or "") // 4
        except Exception:
            pass

    try:
        llm_cost.log_call(
            provider=provider,
            model=model,
            call_type=call_type,
            input_tokens=in_t,
            output_tokens=out_t,
            success=success,
        )
    except Exception:
        pass


def tracked_generate(
    client: Any,
    model: str,
    contents: Any,
    call_type: str,
    config: Optional[Any] = None,
    provider: str = "google",
):
    """raw generate_content wrapper + llm_cost 로깅 (저빈도 call site 용).

    고빈도 cost 경로는 gemini_cache.generate_with_cache(call_type=...) 사용.

    Args:
        client: genai.Client
        model: 모델 ID (예: "gemini-2.5-flash")
        contents: prompt (str 또는 dict/list)
        call_type: 로깅 식별자 (예: "commodity_narrator", "dart_report_analyzer")
        config: 옵션 genai.types.GenerateContentConfig
        provider: 기본 "google"

    Returns:
        response (genai SDK Response)

    Side effect:
        data/metadata/llm_cost.jsonl 1줄 append (success / fail 모두).
    """
    try:
        if config is not None:
            resp = client.models.generate_content(
                model=model, contents=contents, config=config
            )
        else:
            resp = client.models.generate_content(model=model, contents=contents)
        log_gemini_usage(resp, model, call_type, contents=contents, provider=provider, success=True)
        return resp
    except Exception:
        # fail 도 로깅 — 진단 path
        log_gemini_usage(None, model, call_type, contents=contents, provider=provider, success=False)
        raise
