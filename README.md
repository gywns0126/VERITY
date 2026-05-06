# VERITY Terminal

AI 주식 분석 + VAMS (Virtual Asset Management System).

운영 도메인 — https://verity-terminal.framer.website

## 구조

| 폴더 | 역할 |
|---|---|
| `api/` | Brain v5 + 분석 파이프라인 (Python) |
| `vercel-api/` | 실시간 API (Vercel Serverless) |
| `framer-components/pages/` | Framer 코드 컴포넌트 (manual paste, 6 페이지 + `_shared`) |
| `data/` | portfolio.json + 분석 결과 |
| `docs/` | 시스템 spec · runbook · setup |
| `estate/` | ESTATE (부동산 추정, 별 프로젝트) |
| `scripts/` | 운영 스크립트 |
| `supabase/` | Supabase 마이그레이션 |
| `tests/` | pytest |

## 핵심 문서

- `docs/VERITY_SYSTEM_SPEC_2026.md` — 마스터 spec
- `docs/DECISION_LOG_MASTER.md` — 결정 이력
- `docs/DESIGNER_PROMPT_VERITY_v1.md` — 디자인 가이드 (펜타그램 v1.1)
- `docs/INCIDENT_RECOVERY_PLAYBOOK.md` — 사고 복구
- `docs/PHASE_0_RUNBOOK.md` — Phase 0 운영
- `docs/SUPABASE_AUTH_SETUP.md` / `KRX_OPEN_API_SETUP.md` / `VERCEL_ENV_CHECKLIST.md` — 인프라 setup

## VAMS 매매 룰 (현재)

- **매수**: Brain v5 grade ≥ BUY (75점), VCI 25-15
- **손절**: ATR(14) × 2.5 동적 손절 + profile 상한 + fallback −5%
- **익절**: 1R / 2R / 트레일링 3단계 부분 익절 (50/30/20%)
- **기간**: 14d hit_rate 50% (학습 루프)
- 상세 — 메모리 `project_atr_dynamic_stop` / `project_r_multiple_exit`

## 환경변수 — `.env.example` 참조
