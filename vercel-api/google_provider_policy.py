"""Google Gemini is retired by user policy (2026-10-25).

This is an unconditional outbound boundary, not a missing-key fallback.
Existing credentials or environment flags cannot enable Google generation,
search/grounding or paid caches. Other providers and official data GETs are
outside this policy. Mirror byte-for-byte in vercel-api/google_provider_policy.py.
"""

DISABLED_STATUS = "disabled_by_policy"
DISABLED_DETAIL = "Gemini API 사용 중단 (사용자 정책)"


class GoogleProviderDisabled(RuntimeError):
    """A deliberate provider retirement, not a transient/quota error."""


def require_google_provider() -> None:
    raise GoogleProviderDisabled(DISABLED_DETAIL)


class _DisabledGenAI:
    @staticmethod
    def Client(*args, **kwargs):
        require_google_provider()


genai = _DisabledGenAI()
