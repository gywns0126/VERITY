"""novelty — MinHash + LSH 24h sliding window news novelty 분류 (인프라).

목적:
  news pipeline 안 같은 사건 다중 보도 (1차 통신사 → 2차 매체) 자동 dedup +
  신선도 score. 정확 일치 dedup (seen_titles set) 한계 = 유사 문장 통과 (제목
  표현 차이 / 부분 인용). MinHash + LSH = Jaccard threshold 0.5 기준 유사 매치
  → dedup layer.

산식 design (Perplexity Q3 자문 정합, 2026-05-30):
  shingle size = 3 글자 n-gram (한글/영문 동일 처리)
  MinHash 서명 = 128 hash (datasketch default)
  LSH threshold (Jaccard) = 0.5 = 유사 일치 (의제 0.5~0.7 중 보수치)
  24h sliding window = 만료 entry 자동 cleanup
  novelty score = exp(-λ·Δt_to_nearest_match), λ = ln(2)/half_life_h (default 9h)

RULE 7 정합 (2026-05-30 사전등록):
  본 module = 인프라 layer (LSH dedup + novelty 산식 함수 정의).
  활성 호출 (news_headlines.py 통합 / novelty score field 산출) = 별 commit,
  N=14 telegram_volume baseline 측정 후 결정.
  cross-link: [[project_news_impact_3axis_sprint_2026_05_30]] Sub-spec 2

cross-link:
  [[feedback_methodology_pre_registration]] — 사전등록 규율
  [[feedback_decision_logging_separation]] — 결정 룰 단순, 로깅 풍부 (직교)
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from datasketch import MinHash, MinHashLSH

from api.config import now_kst


_NON_ALNUM_KR = re.compile(r"[^가-힣a-zA-Z0-9]")


def _normalize(text: str) -> str:
    """공백/특수문자 제거 후 lowercase. 한글 + 영숫자만 남김."""
    return _NON_ALNUM_KR.sub("", (text or "")).lower()


def _shingles(text: str, k: int = 3) -> List[str]:
    """k-글자 shingle 생성. 한글 character-level n-gram.

    text 길이 < k 시 = 전체 텍스트 1개 shingle (degenerate but valid).
    """
    norm = _normalize(text)
    if len(norm) <= k:
        return [norm] if norm else []
    return [norm[i:i + k] for i in range(len(norm) - k + 1)]


def _minhash(text: str, num_perm: int = 128, shingle_size: int = 3) -> MinHash:
    """text → MinHash signature."""
    m = MinHash(num_perm=num_perm)
    for sh in _shingles(text, shingle_size):
        m.update(sh.encode("utf-8"))
    return m


class NoveltyTracker:
    """24h sliding window news novelty tracker.

    Usage (인프라 dedup):
      tracker = NoveltyTracker()
      if not tracker.is_duplicate("애플 4Q 어닝 서프라이즈"):
          tracker.add("애플 4Q 어닝 서프라이즈")
          # 신규 처리

    Usage (산식 layer, 본 sprint 활성 X):
      score = tracker.novelty_score("애플 4Q 어닝 서프라이즈")  # 0.0~1.0
    """

    def __init__(
        self,
        shingle_size: int = 3,
        num_perm: int = 128,
        threshold: float = 0.5,
        window_hours: int = 24,
        decay_half_life_hours: float = 9.0,
    ) -> None:
        self.shingle_size = shingle_size
        self.num_perm = num_perm
        self.threshold = threshold
        self.window_hours = window_hours
        self.decay_lambda = math.log(2.0) / decay_half_life_hours
        self._lsh = MinHashLSH(threshold=threshold, num_perm=num_perm)
        self._entries: List[Tuple[str, datetime, MinHash]] = []
        self._counter = 0

    def _cleanup_expired(self, ref_ts: datetime) -> None:
        """24h 윈도우 밖 entry 제거."""
        cutoff = ref_ts - timedelta(hours=self.window_hours)
        keep: List[Tuple[str, datetime, MinHash]] = []
        for key, ts, mh in self._entries:
            if ts >= cutoff:
                keep.append((key, ts, mh))
            else:
                try:
                    self._lsh.remove(key)
                except KeyError:
                    pass
        self._entries = keep

    def _nearest_match(
        self, mh: MinHash, ref_ts: datetime,
    ) -> Optional[Tuple[str, datetime, float]]:
        """LSH query → 가장 최근 매치 (key, ts, jaccard estimate). 없으면 None."""
        candidate_keys = self._lsh.query(mh)
        if not candidate_keys:
            return None
        best: Optional[Tuple[str, datetime, float]] = None
        for key, ts, stored_mh in self._entries:
            if key not in candidate_keys:
                continue
            jaccard = mh.jaccard(stored_mh)
            if best is None or ts > best[1]:
                best = (key, ts, jaccard)
        return best

    def is_duplicate(self, text: str, ts: Optional[datetime] = None) -> bool:
        """24h 윈도우 안 Jaccard >= threshold 매치 시 True (dedup layer)."""
        ref_ts = ts or now_kst()
        self._cleanup_expired(ref_ts)
        mh = _minhash(text, self.num_perm, self.shingle_size)
        return self._nearest_match(mh, ref_ts) is not None

    def add(self, text: str, ts: Optional[datetime] = None) -> str:
        """text 등록. internal key 반환 (dedup tracking)."""
        ref_ts = ts or now_kst()
        self._cleanup_expired(ref_ts)
        mh = _minhash(text, self.num_perm, self.shingle_size)
        self._counter += 1
        key = f"n{self._counter}"
        self._lsh.insert(key, mh)
        self._entries.append((key, ref_ts, mh))
        return key

    def novelty_score(self, text: str, ts: Optional[datetime] = None) -> float:
        """novelty score 산식 (산식 layer, 본 sprint 활성 X).

        novelty(t) = 1.0 if no match in 24h window
                   = exp(-λ·Δt_to_nearest_match) if match exists
                     where λ = ln(2) / half_life_hours

        매치 시 = 시간 가까울수록 score ↓ (강한 중복) / 시간 멀수록 score ↑.
        매치 없음 = 1.0 (완전 신규).

        RULE 7 정합: 본 함수 호출 = 산식 적용 = 별 commit + quota 1.
        cross-link: [[project_news_impact_3axis_sprint_2026_05_30]] Sub-spec 2/5
        """
        ref_ts = ts or now_kst()
        self._cleanup_expired(ref_ts)
        mh = _minhash(text, self.num_perm, self.shingle_size)
        match = self._nearest_match(mh, ref_ts)
        if match is None:
            return 1.0
        _key, match_ts, _jaccard = match
        delta_hours = max(0.0, (ref_ts - match_ts).total_seconds() / 3600.0)
        return math.exp(-self.decay_lambda * delta_hours)
