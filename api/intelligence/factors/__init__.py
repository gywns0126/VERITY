"""verity_brain 의 factor 모듈 — analyze_stock 분해 결과.

원본: api/intelligence/verity_brain.py (3,738줄 단일 파일, 2026-05-24 분해).
분해 원칙:
  - 산식/임계/가중치 변경 X (CLAUDE.md RULE 7 정합)
  - stock dict schema 변경 X (VAMS trail 보존)
  - 함수 시그니처 변경 X (기존 caller — verity_brain.analyze_stock — 그대로)
  - re-export 보장 (tests/ 가 verity_brain 에서 _compute_fact_score / _compute_sentiment_score 직접 import)
"""
