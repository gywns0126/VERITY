"""
VERITY Brain Observatory — 측정 모듈 (Phase 1).

선행 문서:
  docs/BRAIN_MONITOR_SPEC.md (Phase 1 §1)
  docs/BRAIN_MONITOR_WIREFRAME.md

가드 정책 (spec §6):
  - 모든 진입점 try/except + logger.warning
  - 실패 시 None / 안전 기본값 반환, 메인 흐름 영향 0
  - 메타데이터 jsonl 누적 (1주일 후 의미 시작)
"""
from __future__ import annotations

from .data_health import check_data_health
from .feature_drift import compute_drift
from .explainability import explain_brain_score
from .trust_score import report_readiness

__all__ = [
    "check_data_health",
    "compute_drift",
    "explain_brain_score",
    "report_readiness",
]
