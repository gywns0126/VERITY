"""공개 발행 strip 계약 — 내부 진단 필드가 공개 Blob 으로 새지 않는지 (2026-08-21).

사고: `_carried`(이월 자기신고 스탬프) 를 `api/main.py` MERGE 에 추가하면서
`sanitize_recommendations.py` 갱신을 빠뜨렸다. 그 스탬프의 `frozen_fields` 가
`verity_brain` · `overrides_applied` · `multi_factor` 를 **이름으로** 담는데
셋 다 이미 STRIP_KEYS 대상이라, **값은 막고 구조 이름은 새는** 형태가 된다.
sanitize 파일 헤더가 "신규 held 점수 필드 추가 시 STRIP_KEYS 갱신" 을 명시하는데
그 의무를 놓쳤다 — 문구만으로는 안 막힌다(RULE 12).

🚨 이 파일은 **인스턴스가 아니라 클래스**를 지킨다. `_carried` 하나만 막으면
다음에 `_foo` 를 추가할 때 같은 사고가 반복된다.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SAN = ROOT / ".github" / "actions" / "publish-data" / "sanitize_recommendations.py"

# 밑줄 접두인데 공개가 허용된 기존 키 — 신규 추가 시 여기 넣지 말고 STRIP_KEYS 로 갈 것.
# (동작 변경을 피하려 현행 상태를 그대로 고정한다. 공개 필요성은 별도 PM 판단.)
_ALLOWED_UNDERSCORE = {"_from_watchlist"}


def _strip_contract():
    src = SAN.read_text(encoding="utf-8")
    body = src.split("STRIP_KEYS = {", 1)[1].split("}", 1)[0]
    keys = set(re.findall(r'"([A-Za-z_][A-Za-z0-9_]*)"', body))
    m = re.search(r'STRIP_PAT = re\.compile\(r"([^"]+)"', src)
    pat = re.compile(m.group(1), re.IGNORECASE) if m else re.compile(r"(?!)")
    return keys, pat


def _is_stripped(key, keys, pat):
    return key in keys or bool(pat.search(key))


def test_carried_stamp_is_stripped():
    keys, pat = _strip_contract()
    assert _is_stripped("_carried", keys, pat), (
        "_carried 가 공개 Blob 으로 나간다 — frozen_fields 가 내부 산식 필드명을 노출한다"
    )


def test_no_new_underscore_keys_leak_to_public():
    """🚨 클래스 가드 — 밑줄 접두 키는 내부 진단이라는 관례를 강제한다."""
    path = ROOT / "data" / "recommendations.json"
    if not path.exists():
        pytest.skip("recommendations.json 없음")
    try:
        recs = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        pytest.skip("파싱 불가 (크론 쓰기 중)")
    if not isinstance(recs, list) or not recs:
        pytest.skip("비어 있음")

    keys, pat = _strip_contract()
    all_keys = set()
    for r in recs:
        all_keys |= set(r.keys())
    leaking = sorted(
        k for k in all_keys
        if k.startswith("_")
        and k not in _ALLOWED_UNDERSCORE
        and not _is_stripped(k, keys, pat)
    )
    assert not leaking, (
        f"밑줄 접두 내부 필드가 공개로 나간다: {leaking}. "
        f"STRIP_KEYS 에 추가하거나, 공개가 의도라면 _ALLOWED_UNDERSCORE 에 사유와 함께 등재할 것"
    )


def test_internal_scoring_keys_still_stripped():
    """회귀 — 기존 strip 대상이 실수로 빠지지 않았는지 (표본 아닌 전수 대조는 과함)."""
    keys, pat = _strip_contract()
    for k in ("verity_brain", "overrides_applied", "multi_factor", "score_breakdown",
              "rec_price", "trade_plan", "consensus"):
        assert _is_stripped(k, keys, pat), f"{k} 가 strip 대상에서 빠졌다"
