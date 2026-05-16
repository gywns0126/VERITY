# BRAIN v6 ROADMAP — Next-Gen Quant Brain (2026-05-16 ~ 2027 Q1)

작성: 2026-05-16 (audit BRAIN_SELF_GROWTH P0-4 + Perplexity NQ4)
연관: project_brain_v5_self_attribution / project_brain_kb_learning / feedback_continuous_evolution

---

## 비전 요약

**v5 (현재)**: fact(70%) + sentiment(30%) + VCI + macro_override + veteran triggers — 단일 모델 의사결정
**v6 (2026 Q4 ~ 2027 Q1)**: Multi-agent ensemble + RAG augmentation + Online learning + RL position sizing — **계층적 의사결정 시스템**

근거: TradingAgents 2025 / FinCon NeurIPS 2024 / AQR Asness 2024 발언 / Renaissance Medallion 공개 부분 / Two Sigma SHAP 패턴

---

## 4-Layer Stack (Brain v6 핵심 구조)

```
┌─────────────────────────────────────────────────────────┐
│ Layer 4: RL Position Sizer                              │
│   PPO/SAC agent — Sharpe + MDD 페널티 보상 + 거래세 0.2% │
├─────────────────────────────────────────────────────────┤
│ Layer 3: Multi-Agent Debate · Voting                    │
│   Bull / Bear / Risk Manager (TradingAgents 2025)       │
│   Conceptual Verbal Reinforcement (FinCon NeurIPS 2024)│
├─────────────────────────────────────────────────────────┤
│ Layer 2: Specialist Agents                              │
│   Fundamental / Technical / Macro / Sentiment / Veteran │
│   각자 RAG (학습 PDF 9권) augmented                       │
├─────────────────────────────────────────────────────────┤
│ Layer 1: Data Pipeline                                  │
│   DART 공시 파서 / KRX 가격 / FRED / KIS / sec_financials│
│   Online learning (regime change 감지 시 fast adapt)    │
└─────────────────────────────────────────────────────────┘
```

---

## P0 (즉시 ~ 2026 Q3, 65 거래일 게이트 통과 후)

### A. RAG Augmentation 파이프라인 (3개월 분량)

**기술 stack**:
- 임베딩: **BGE-M3** (한국어 recall 우수 — OpenAI embedding 보다 강점)
- Vector DB: **FAISS (로컬, ~10K docs)** → **Qdrant (확장, ~1M docs)**
- 청크: **512 token + 64 overlap** (Advanced RAG 표준)
- Hybrid Search: **Dense + BM25** (재무 전문 용어 정밀도)
- Re-ranking: **bge-reranker-v2-m3** 또는 Cohere Rerank

**데이터 source**:
- `배리티 브레인 학습 도서/` 9 PDF (저작권 보호, 로컬만)
- `터미널 보충 학습 자료. /` Perplexity 결과
- DART 사업보고서 (분기) — 미래 quarterly 자동 인덱싱
- 메모리 100+ markdown (cross-link [[name]])

**연동 위치**:
- `api/intelligence/verity_brain.py` analyze_stock 호출 시 RAG context 보강
- 종목별 "이 종목의 해자/리스크 관련 거장 발언" 자동 검색

### B. Bull/Bear/Risk Debate 에이전트 (2개월 분량)

**구조** (TradingAgents 2025 기반):
1. **Bull Researcher**: 매수 논리 추출 (Brain v5 STRONG_BUY/BUY 입력)
2. **Bear Researcher**: 매도/회피 논리 (Brain v5 AVOID/red_flags 입력)
3. **Risk Manager**: 양측 검토 후 final verdict + position size

**실증**: 단일 모델 대비 **Sharpe +14~22%, MDD 개선** (TradingAgents 2025)

**구현 위치**:
- `api/intelligence/agents/bull_researcher.py` (신규)
- `api/intelligence/agents/bear_researcher.py` (신규)
- `api/intelligence/agents/risk_manager.py` (신규)
- `api/intelligence/verity_brain.py` 통합 (analyze_stock 후 debate 호출 옵션)

### C. EWMA 기반 Batch 재학습 (P1-1 완성 후 자동 확장)

**현재 (P1-1)**: postmortem → EWMA factor weight 감쇠 + quarantine
**v6 확장**: 매 주말 cron 으로 batch EWMA 갱신 → 다음 주 가중치 자동 적용

---

## P1 (6개월 ~ 2027 Q1)

### D. Regime-Triggered Online Learning

**Hybrid 구조** (NYU Stern 2025 OGU Sharpe 1.26 기반):
- **Batch (Weekly)**: 평상시 가중치 재학습 (cron weekly)
- **Online Fast Adaptation**: regime change 감지 시 즉시 적응
  - 트리거: 환율 ±2% / 외인 순매수 역전 / 팩터 IC 급락 / VIX 급변

**구현 위치**:
- `api/intelligence/online_adaptor.py` (신규)
- `api/observability/regime_detector.py` 확장 (이미 일부)

### E. PPO Position Sizer (Shadow Mode)

**구조**:
- PPO (Stable-Baselines3) 시작 → SAC 확장
- 보상 함수: **Sharpe ratio + MDD 페널티 + 한국 거래세 0.2% 반영**
- Shadow mode (실거래 X, recommendation 만)

**구현 위치**:
- `api/intelligence/rl_position_sizer.py` (신규)
- `api/vams/sizer_rl.py` (별 sizing 라우터)

### F. SHAP × IC Cross-Validation (Two Sigma 패턴)

Postmortem 자동 진화의 고도화:
- LightGBM 학습 → SHAP value 계산
- SHAP × IC 상관 < threshold → quarantine
- Sign consistency 위반 → "Leaky Signal" 자동 격리

**구현 위치**:
- `api/quant/alpha/shap_validator.py` (신규, P1-1 확장)

---

## P2 (12개월+, 2027 Q2 ~)

### G. LLM Alpha → RL State 통합

LLM (Claude/Gemini) 종목 분석 결과를 RL agent state 로 직접 주입.
- Claude 4.7 → Claude 5/6 출시 시 자동 swap (env config)
- Multi-model ensemble voting (Bull/Bear 외 추가 layer)

### H. 500+ Factor ML 확장

현재 fact_score 약 30 sub-factor → 500+ 자동 generated factors:
- Genetic programming alpha discovery (WorldQuant BRAIN 패턴)
- Factor zoo taming (AQR 2018 L1/L2 shrinkage)

### I. 한국어 재무 LLM 파인튜닝

DART 공시 100K+ 학습 → 한국어 재무 특화 LLM:
- 기업 공시 문맥 파싱 정확도 ↑
- 한국 회계 기준 (K-IFRS) 특수성 반영

### J. Agent Memory Persistence

각 agent (Bull/Bear/Risk Manager) 가 자신의 결정 history 보존:
- 동일 종목 재분석 시 prior decision 참조
- 결정 일관성 메트릭 자동 측정

---

## 기관 비교 (2024-2026 동향)

| 기관 | 핵심 동향 | v6 적용 |
|---|---|---|
| **AQR** | ML 플래그십 신호 1/5 구동 / Asness "AI 공시 파싱 우월" | RAG (Asness 발언 정합) + ML hybrid |
| **Citadel** | 백테스트 10,000 코어화 (5분 완료) | 운영 무관 — 인프라 미충족 |
| **Jane Street** | ROC >50%, 전략 비공개 | reference only |
| **RenTec** | Medallion ~66% 연수익 / ML 강화 추정 | Bull/Bear debate + 자동 진화 핵심 |
| **Two Sigma** | SHAP / LightGBM 자동 가중치 조정 | P1-F SHAP × IC validator |

---

## v5 vs v6 차별점

| 요소 | v5 (현재) | v6 (목표) |
|---|---|---|
| 의사결정 layer | 단일 (analyze_stock) | 4 layer (data/specialist/debate/RL) |
| Sentiment sub | 13 | 13 + RAG augmented (학습 PDF 9권 검색) |
| Factor weight | 자체 정량 + IC weight (P0-2 박힘) | EWMA online + SHAP × IC validator |
| Position sizing | Kelly half | PPO/SAC RL agent (Sharpe + MDD 보상) |
| Postmortem | 생성만 | 자동 EWMA factor 감쇠 + quarantine (P1-1 박힘) |
| Multi-agent | X (단일 Claude/Gemini) | Bull/Bear/Risk debate (TradingAgents 2025) |
| Regime adaptive | macro_override 게이트만 | online fast adapt (NYU Stern OGU) |

---

## Phase 로드맵

| Phase | 기간 | 핵심 액션 |
|---|---|---|
| v5.1 | 2026-05 ~ 2026-08 | 17 Perplexity 검증 임계 + P0-P1 인프라 박힘 (현재) |
| v5.2 | 2026-08 ~ 2026-11 | 65 거래일 PRODUCTION 게이트 통과 + EWMA 자동 진화 |
| **v6.0 P0** | **2026-09 ~ 2026-12** | **RAG + Bull/Bear Debate 박힘** |
| v6.0 P1 | 2027-01 ~ 2027-03 | Regime-triggered online + PPO shadow |
| v6.0 P2 | 2027-04 ~ 2027-09 | 500 factor ML + 한국어 재무 LLM |
| v7 (vision) | 2028+ | Full auto-evolution + multi-asset (ESTATE+VAMS+commodity) |

---

## 위험 관리

### 과적합 회피
- 모든 신규 layer = shadow mode 진입 → 65 거래일 검증 → production
- Perplexity 학계 검증 cascade (이미 17건 박힘)

### 표본 부족 대응 (한국 시장 특수성)
- Bayesian Prior 주입 (Mauboussin + 자체 백테스트 사전지식)
- EWMA λ=0.94 (RiskMetrics 표준) — 소샘플 robust

### 인프라 부담
- Citadel 10,000 코어 vs 우리 GitHub Actions 무료 → 모델 경량화 우선
- 한국어 LLM 파인튜닝은 Tier 3+ 자본 단계 (~10억) 후

---

## 출처 (Perplexity NQ4 검증)

- TradingAgents 2025: papers.ssrn.com/sol3/...6354961
- FinCon NeurIPS 2024: neurips.cc/2024
- AQR Asness: bloomberg.com/2025-04-23 (ML believer)
- NYU Stern OGU 2025: stern.nyu.edu/Glucksman_Lahanis
- Two Sigma SHAP: joungnx123.tistory + nature.com/s41598-025-15783-2
- Citadel infra: x.com/zostaff/2054217434911903952
- Jane Street: linkedin.com/aideasol/7459452265821679616
- RenTec Medallion: techclubnova.com/9b569s0kd397auu

---

## 메모리 박을 후보 (v6 진입 시점)

- `project_brain_v6_kickoff` — v6 0.1 (RAG + debate 박힘 시점)
- `feedback_rag_pipeline_design` — RAG 표준 (BGE-M3 + FAISS + Hybrid)
- `project_multi_agent_debate` — Bull/Bear/Risk 패턴
- `feedback_rl_reward_design` — Sharpe + MDD + 한국 거래세 정합
