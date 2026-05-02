"""
policy_keywords.py — ESTATE 정책 키워드 사전 + prefilter (P2 Step 2)

classifier (LLM) 진입 전 무료 1차 필터링. 비-부동산 정책을 키워드 매칭으로
걸러내서 LLM 호출 비용을 줄인다 (T19 영역 정량화는 빌더에서 측정).

키워드 출처 (T16 — fabricate 금지):
1. fixture 50건의 부동산 정책 12건에서 직접 도출 (Step 1.1 WebFetch 검증):
   #1 2026년 공동주택 공시가격 ×2  →  공시가격
   #2 상반기 수도권 공공주택 분양 ×2 →  공공주택, 분양
   #3 도심 공공주택 3.4만호 공급      →  공공주택, 공급
   #4 지역주택조합 제도 개선          →  지역주택조합, 주택조합
   #5 지가 상승                        →  지가
   #6 서울·경기 주택 이상거래 ×2     →  주택, 이상거래
   #7 전세사기특별법                   →  전세사기

2. 보강 — 한국 부동산 표준 용어 (각 항목 옆 # 출처 주석):
   - 보유세제 (재산세·종부세·양도세·취득세) — 한국 부동산 보유세제 표준
   - 금융위 6.27 가계부채 대책 (LTV·DSR·DTI)
   - 정책 모기지 (디딤돌·보금자리론)
   - 시장 규제 (조정대상지역·투기과열지구·토지거래허가)
   - 정비사업 (재건축·재개발·리모델링)
   - 시장 모니터링 (미분양·급등·급락)
"""
from __future__ import annotations

import re
from typing import Dict, List


# ─── 카테고리별 키워드 사전 ───
# 매 키워드 옆 출처: "fixture" = Step 1.1 fixture 12건에서 직접 도출
#                   "표준"   = 한국 부동산 표준 용어
CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    "tax": [
        "공시가격",         # fixture #1
        "보유세",           # 표준 (재산세 + 종부세 통칭)
        "재산세",           # 표준
        "종부세",           # 표준 (종합부동산세 약칭)
        "종합부동산세",     # 표준 (정식명)
        "양도세",           # 표준
        "양도소득세",       # 표준 (정식명)
        "취득세",           # 표준
    ],
    "supply": [
        "공공주택",         # fixture #2,3
        "분양",             # fixture #2
        "공급",             # fixture #3 (도심 공공주택 공급)
        "택지",             # 표준
        "신축",             # 표준
        "입주",             # 표준
        "청약",             # 표준
        "분양가",           # 표준
        "분양권",           # 표준
    ],
    "regulation": [
        "지역주택조합",     # fixture #4
        "주택조합",         # fixture #4 (파생)
        "토지거래허가",     # 표준 (서울 강남3구·여의도 등)
        "조정대상지역",     # 표준
        "투기과열지구",     # 표준
        "거래허가",         # 표준 (파생)
    ],
    "loan": [
        "디딤돌",           # 표준 (정책 모기지)
        "보금자리론",       # 표준 (정책 모기지)
        "주택담보대출",     # 표준
        "주담대",           # 표준 (약칭)
        "전세대출",         # 표준
        "LTV",              # 표준 (6.27 대책)
        "DSR",              # 표준 (6.27 대책)
        "DTI",              # 표준
    ],
    "redev": [
        "재건축",           # 표준
        "재개발",           # 표준
        "정비사업",         # 표준
        "리모델링",         # 표준
    ],
    "rental": [
        "전세사기",         # fixture #7
        "전월세",           # 표준
        "임대차",           # 표준
        "임차인",           # 표준
        "임대인",           # 표준
        "임대주택",         # 표준
        "전세",             # 표준 (파생, '전세사기' 와 충돌 방지 위해 길이 정렬 적용)
        "월세",             # 표준
    ],
    "anomaly": [
        "이상거래",         # fixture #6
        "미분양",           # 표준
        "급등",              # 표준 (시장 모니터링)
        "급락",              # 표준 (시장 모니터링)
    ],
    "catalyst": [
        "지가",             # fixture #5
        "부동산",           # 표준 (일반)
        "주택",             # fixture (#1, #6 등 포괄)
        "아파트",           # 표준
    ],
}


# ─── 통합 KEYWORDS (rough_relevance_filter 정규식용) ───
# 길이 내림차순 — '전세사기' 가 '전세' 보다 먼저 매칭되도록.
KEYWORDS: List[str] = sorted(
    {kw for kws in CATEGORY_KEYWORDS.values() for kw in kws},
    key=len,
    reverse=True,
)

_PATTERN = re.compile("|".join(re.escape(k) for k in KEYWORDS))


def rough_relevance_filter(policy: Dict) -> bool:
    """
    1차 prefilter — 부동산 관련 정책 여부를 무료(O(n) 정규식)로 판정.

    Args:
        policy: collect_policies() 산출 dict.
                title + raw_text 가 매칭 대상.

    Returns:
        True  — KEYWORDS 중 1개 이상 매칭. classifier 호출 대상.
        False — 매칭 0건. LLM 호출 skip (비용 절감).
    """
    title = policy.get("title") or ""
    raw_text = policy.get("raw_text") or ""
    haystack = title + " " + raw_text
    return bool(_PATTERN.search(haystack))


# 키워드 → 카테고리 역인덱스 (kw 가 카테고리 사이 충돌 시 첫 등록 카테고리로)
_KW_TO_CAT: Dict[str, str] = {}
for _cat, _kws in CATEGORY_KEYWORDS.items():
    for _kw in _kws:
        _KW_TO_CAT.setdefault(_kw, _cat)


def keyword_matches(policy: Dict) -> Dict[str, List[str]]:
    """
    카테고리별 매칭된 키워드 목록 반환. classifier 1차 분류용.

    매칭 알고리즘 — substring leak 차단:
        긴 키워드부터 매칭 후 매칭 영역을 NUL 로 마스킹.
        예: '미분양' 매칭 시 그 영역의 '분양' 별도 매칭 X.
            '공공주택' 매칭 시 그 영역의 '주택' 별도 매칭 X.

    Returns:
        {category: [matched_keyword, ...]}.
        매칭 0건 카테고리도 빈 list 로 포함 (key 안정성).
    """
    title = policy.get("title") or ""
    raw_text = policy.get("raw_text") or ""
    haystack = title + " " + raw_text

    out: Dict[str, List[str]] = {cat: [] for cat in CATEGORY_KEYWORDS}
    if not haystack.strip():
        return out

    masked = list(haystack)
    for kw in KEYWORDS:  # 길이 내림차순 — 긴 것 먼저
        s = "".join(masked)
        idx = s.find(kw)
        if idx == -1:
            continue
        cat = _KW_TO_CAT[kw]
        if kw not in out[cat]:
            out[cat].append(kw)
        # 모든 매칭 영역 마스킹 (다중 등장도 처리)
        while idx != -1:
            for i in range(idx, idx + len(kw)):
                masked[i] = "\x00"
            s = "".join(masked)
            idx = s.find(kw)
    return out
