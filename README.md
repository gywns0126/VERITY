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

- `CLAUDE.md` — 5 RULE hardcoded 가드 (KIS 1일 1토큰 / Vercel deploy / 인프라 회신 / git add 정합 / drift sentinel)
- `docs/VERITY_SYSTEM_SPEC_2026.md` — 마스터 spec
- `docs/DECISION_LOG_MASTER.md` — 결정 이력
- `docs/DESIGNER_PROMPT_VERITY_v1.md` — 디자인 가이드 (펜타그램 v1.1)
- `docs/INCIDENT_RECOVERY_PLAYBOOK.md` — 사고 복구
- `docs/PHASE_0_RUNBOOK.md` — Phase 0 운영
- **`docs/PHASE_2_5_MODULE_ROADMAP_v0.1.md`** — Phase 2 (1인 기관급) 5 모듈 8월~1월 로드맵
- **`docs/BRAIN_V6_DESIGN_v0.1.md`** — Brain v5 → v6 진화 (3-axis + Tier 차별 + Regime + Pool ensemble + 통계 게이트)
- **`docs/GOLDEN_GOOSE_VISION_2028_v0.1.md`** — 2028 Vision (Calmar 1.0+ / MDD <20% / Anti-fragile / Anti-FOMO 산식)
- **`docs/MASTER_RULE_DRIFT_AUDIT_v0.1.md`** — 9권 마스터 룰 silent drift audit Phase B (Lynch/Ackman/Druckenmiller/Hohn/Nison/Rokos)
- `docs/SUPABASE_AUTH_SETUP.md` / `KRX_OPEN_API_SETUP.md` / `VERCEL_ENV_CHECKLIST.md` — 인프라 setup

## VAMS 매매 룰 (현재)

- **매수**: Brain v5 grade ≥ BUY (75점), VCI 25-15
- **손절**: ATR(14) × 2.5 동적 손절 + profile 상한 + fallback −5%
- **익절**: 1R / 2R / 트레일링 3단계 부분 익절 (50/30/20%)
- **기간**: 14d hit_rate 50% (학습 루프)
- **Capital 3-Tier** (Perplexity Q3 자문): 60% 보수 / 30% 중간 / 10% 공격. sub-PnL 추적. hard cap optional.
- 상세 — 메모리 `project_atr_dynamic_stop` / `project_r_multiple_exit` / `project_capital_3tier_mode`

## Brain 산식 (현재)

- **brain_score** = fact_score × 0.7 + sentiment_score × 0.3 + bonuses − penalties
- **fact 14 components** (multi_factor / consensus / prediction / backtest / timing / commodity / export / moat / graham / canslim / analyst_report / dart_health / perplexity_risk / **equity_brief_verdict**)
- **sentiment 13-source hard-wire** (Perplexity 자문, ce36c470 — news 0.175 / x 0.125 / mood 0.125 / consensus 0.10 / crypto 0.065 / fear_greed 0.065 / social 0.085 / fx 0.050 / commodity 0.040 / GID 0.040 / **geo 0.060** / macro 0.050 / horizon 0.020)
- **grade 임계**: 75 (STRONG_BUY) / 60 (BUY) / 45 (WATCH) / 25 (CAUTION) / <25 (AVOID)
- v6 진화 = 8월 Phase 2 Module 1 (Factor) 진입 시 (BRAIN_V6_DESIGN docs)

## 2028 Vision Metric

- **Calmar** ≥ 1.0 / **MDD** <20% / **Anti-fragile** (Skew >0 + Kurt >3 + VBR >1.5 + AI >1) / **Anti-FOMO** (FOMO Score <0.1)
- 측정 인프라: `api/quant/antifragility.py` + `api/quant/fomo_score.py` + cron_health_monitor 분기별 hook
- 운영 누적 시점 = 2027 ~ 측정 가능

## 환경변수 — `.env.example` 참조
