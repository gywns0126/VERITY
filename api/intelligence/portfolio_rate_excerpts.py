"""Conservative, verbatim interest-rate excerpts from already-cached filing text.

Only three audited declarative forms are accepted. This does not bind an issuer
or date, establish today's borrowing balance, or infer a benchmark or impact.
Offsets are Python Unicode character indices into the unchanged input string.
"""
from __future__ import annotations

import re
from typing import Iterator

from .portfolio_public_sources import safe_public_text


_SUBJECT = r"(?:연결회사|연결기업|연결실체|당사|회사)(?:는|은)"
_ASSERTIONS = tuple(re.compile(pattern) for pattern in (
    _SUBJECT + r"\s*(?:고정(?:금리|이자율)\s*(?:과|와|및)\s*)?"
    r"변동(?:금리|이자율)로\s*자금을\s*차입하고\s*있으며[,，]?\s*"
    r"이로\s*인하여\s*이자율\s*위험에\s*노출되어\s*있습니다\.",
    _SUBJECT + r"\s*변동금리부\s*(?:단[ㆍ·,]?장기)?차입금과\s*관련된\s*"
    r"시장이자율변동위험에\s*노출되어\s*있습니다\.",
    r"변동이자율로\s*발행된\s*차입금으로\s*인하여\s*" + _SUBJECT +
    r"\s*현금흐름\s*이자율\s*위험에\s*노출되어\s*있습니다\.",
))
# Remove only the known section heading, never arbitrary prose before a match.
# DART text can put the heading and the first sentence on the same line.
_HEADING = re.compile(
    r"\s*(?:(?:\([0-9A-Za-z가-힣]+\)|[0-9A-Za-z가-힣]+[.)])\s*)?"
    r"(?:이자율|금리)\s*위험(?:\s*관리(?:\s*정책)?)?\s*"
)
_NON_ISSUER_CONTEXT = re.compile(
    r"경쟁사|타사|고객사|다른\s*회사|인용|예시|예문|가정|가상|"
    r"향후|예정|계획|과거|전기(?:에는|의|말)|정의|다음\s*문구|"
    r"사실이\s*아닙|사실과\s*다릅|해당하지\s*않"
)
_QUOTE_PAIRS = {'"': '"', "'": "'", '“': '”', '‘': '’',
                '「': '」', '『': '』', '«': '»'}


def _sentence_spans(text: str) -> Iterator[tuple[int, int]]:
    """Do not split quoted examples into apparently unquoted assertions."""
    start = 0
    quotes: list[str] = []
    for index, char in enumerate(text):
        if quotes and char == quotes[-1]:
            quotes.pop()
        elif char in _QUOTE_PAIRS:
            quotes.append(_QUOTE_PAIRS[char])
        elif not quotes and (
            char in "!?" or (char == "." and index and "가" <= text[index - 1] <= "힣")
        ):
            yield start, index + 1
            start = index + 1


def extract_interest_rate_excerpts(text: str) -> list[dict]:
    """Return only complete <=600-character audited assertions, in source order.

    Unsupported compounds (including deposit/hedge continuations) are rejected
    as a whole, not cropped to a positive subclause. Newlines remain verbatim.
    A heading is not evidence; the complete sentence must match an audited form.
    Caller must separately validate filing identity, dates and reporting scope.
    """
    if not isinstance(text, str) or not text:
        return []
    excerpts = []
    previous = ""
    for start, end in _sentence_spans(text):
        segment = text[start:end]
        context = previous
        previous = segment
        if _NON_ISSUER_CONTEXT.search(context):
            continue
        start += len(segment) - len(segment.lstrip())
        heading = _HEADING.match(text, start, end)
        if heading:
            start = heading.end()
        quote = text[start:end]
        if not quote or len(quote) > 600:
            continue
        if not any(pattern.fullmatch(quote) for pattern in _ASSERTIONS):
            continue
        # Validation only: never replace whitespace or mutate the returned quote.
        if safe_public_text(quote.replace("\r", " ").replace("\n", " "), 600) is None:
            continue
        excerpts.append({"role": "floating-rate-borrowing", "quote": quote,
                         "char_start": start, "char_end": end})
    return excerpts
