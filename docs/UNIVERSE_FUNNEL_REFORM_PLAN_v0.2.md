# UNIVERSE FUNNEL REFORM v0.2

작성: 2026-05-12 (v0.1 + Perplexity Q1-Q4 통합)
적용 게이트: 5/17 sprint (ATR verdict 후)
근거 자료:
- v0.1: `터미널 보충 학습 자료. /터미널 학습 자료 3.pdf` (Perplexity 학계+실무 backing)
- v0.2: 채팅 내 Perplexity Q1-Q4 응답 (4 결정 closure + 우선순위 4단 + 세후 hurdle layer)

---

## v0.2 변경 요약 (v0.1 대비)

| # | 변경 | 출처 |
|---|---|---|
| 1 | Stage 0 US: ADV ≥ $10M **AND** 시총 ≥ $500M (병행) | Perplexity Q2 |
| 2 | Stage 1 신규상장: 12개월 절대 → **6개월 + 3 보완 필터** | Perplexity Q4 |
| 3 | Stage 5 Tier 1: KR 5+US 3 → **KR 6+US 2 + 베타 테스트 구역** | Perplexity Q1 (5+3 회수) |
| 4 | 리밸런싱 **factor-aware 이원화** | Perplexity Q3 + 학습자료 3 IC half-life |
| 5 | 신규 **세후 alpha hurdle layer** | Perplexity Q1 부산물 |
| 6 | 우선순위 4단 명시 | Perplexity 결론부 |

---

## 1. Stage 0 — Tradable Universe

```
KR: KOSPI 전체 + KOSDAQ 전체 (KONEX 제외)
US: tradable from KRX 계좌 AND ADV ≥ $10M AND 시총 ≥ $500M
결과: ~5,000-5,500 (raw)
```

**v0.2 변경**: US 단일 ADV → AND 조건. $5M ADV = 한국 환산 ~70억 (중소형) — 슬리피지·체결·Tier 정합성 모두 문제. AND 시총 floor 가 *유동성 + 기업규모* 동시 통제.

## 2. Stage 1 — Hard Exclusion

KR 실무 표준 + v0.2 신규상장 완화:

| 카테고리 | 기준 |
|---|---|
| 관리종목 / 투자주의 / 매매정지 / 상장폐지위험 | KRX 지정 D+1 즉시 제거 |
| 자본잠식률 ≥ 50% / 감사의견 비적정 | 동일 |
| SPAC | 합병 완료 후 6개월 재편입 검토 |
| 우선주 | 보통주 only |
| **신규 상장 < 6개월** | **절대 제외** (보호예수 해제 일시적 가격 왜곡 회피) |
| **신규 상장 6-12개월** | **조건부 허용** (아래 3 필터 동시 충족) |
| 금융업 | P/B·ROE·레버리지 팩터 왜곡 |
| 유동성 절벽 | 시총 < 100억 OR 일평균 거래대금 < 1억 |
| 외국 기업 국내 상장 | 세제/공시 상이 |

**신규상장 6-12개월 조건부 허용 3 필터** (Perplexity Q4):
1. 분기 실적 공시 ≥ 2회
2. IPO 공모가 대비 현재가 괴리율 ±30% 이내 (공모 과열/공매도 집중 배제)
3. **포지션 한도 0.5x** (Tier 별 종목당 평균의 절반 상한)

첫 1년 끝나면 자동 1.0x ramp-up.

**결과: ~1,500-1,800** (~73% 제거)

## 3. Stage 2 — Coarse Filter (Top Quintile, sector-relative)

v0.1 유지. composite z-score (sector-neutral):
- Value: B/P, EV/EBITDA, E/P — sector rolling 3y z-score
- Quality: Piotroski F≥4 + GP/A + ROE
- Momentum: 12-1M return, top 30% (KR short half-life)
- Accruals: Sloan 하위 30-40%

**결과: ~300-360**

## 4. Stage 3 — Medium Filter (Top Decile of remaining)

v0.1 유지:
- Brain v5 quick scoring
- Sector neutralization
- Altman Z safety floor
- Commodity exposure 60%+ 별도 버킷

**결과: ~30-36**

## 5. Stage 4 — Fine Filter (Brain v5 full)

v0.1 유지 + KCMI cycle check.

**결과: ~15-20** (final candidate basket)

## 6. Stage 5 — Conviction Portfolio (Tier-aware + 베타 테스트 구역)

### 6.1 Tier 별 종목수 & 시장 split

| Tier | 자본 | 권장 총 | KR | US (베타) | 종목당 |
|---|---|---|---|---|---|
| **Tier 1 (현재)** | ≤ 1억 | **8** | **6** | **2** | 125만 |
| Tier 2 | 1-10억 | 15-25 | 12 | 3-13 | — |
| Tier 3 | 10-100억 | 30-50 | 20 | 10-30 | — |
| Tier 4 | 100억+ | 50-120 | 40+ | 10-80+ | — |

### 6.2 US Slot = "베타 테스트 구역" (Perplexity Q1 핵심)

**구조적으로 KR slot 과 분리**:
- 독립 성과 추적 (Sharpe/IR/MDD/IC/Hit rate 별도 산출)
- 진입 hurdle = KR Brain v5 score + **5%p** (단순 근사) 또는 정밀 산식 (§7.2)
- 청산 hurdle = KR 보다 strict (US 22% 세금 복리 잠식 회피)
- Tier 1 단계에서 US slot 은 *학습 모드* — 데이터 누적 후 Tier 2 진입 시 확대

**운영 표준 (2026-05-12 박힘)**: AQR 멀티스트래트 + Brinson-Fachler 계층 attribution + Singer-Karnosky 다중통화 분해 전부 **`docs/SLEEVE_TRACKING_SPEC.md`** 에 정착.

핵심:
- Sleeve Sharpe: 로컬 통화 기준 (KR=KOFR, US=SOFR), AQR baseline 0.3
- IR: KR 벤치 KOSPI 200 / US 벤치 S&P 500
- MDD: Calendar + Rolling 12m 둘 다
- **잔차 상관 < 0.4 유지**: 0.4 초과 시 실질 분산 효과 소멸 (실무 임계, US 축소 검토)
- Brinson-Fachler L1 (시장 배분) / L2 (팩터) / L3 (종목) 분해
- 데이터: `data/sleeve_tracking/kr_sleeve.jsonl` + `us_sleeve.jsonl` 분리

### 6.3 진입 조건 (Tier 1 공통)

- 종목당 배분액 ≥ 100만원 (왕복 거래비용 × 50배 floor)
- Brain v5 score: KR ≥ 75 / US ≥ 80 (5%p 허들)
- half-Kelly sizing, 단일 종목 비중 ≤ 20%

## 7. 세후 Alpha Hurdle Layer

**문제**: Brain v5 score 가 세전 alpha. KR 비과세 종목과 US 22% 종목을 같은 score 로 비교하면 US 가 unfair.

**해결**: 모든 funnel 단계 score 를 **세후 환산** 으로 비교.

### 7.1 단순 근사 (Tier 1 운영용)

```
KR (Tier 1, 대주주 아님): 세율 0% → 세후 = 세전 × 1.00
US: 세율 22% × (1 - 250만 공제 효과) ≈ 18.7% → 세후 ≈ 세전 × 0.81
→ US 진입 hurdle: KR 75 와 동등하려면 75 / 0.81 ≈ 92.5 (매우 strict)
→ 운영 단순화: **+5%p 허들** (75 → 80) 채택, 완화된 근사
```

### 7.2 정밀 산식 (분리 spec)

위 단순 근사 = 운영 시작용. 정밀 산식은 **`docs/COST_MODEL_SPEC.md` Part II** 에 통합 (2026-05-12 박힘):

- **CFA Level III 표준**: r_AT = r_PT × (1 - t_eff)
- **실효 세율 분해**: t_eff = w_ST·t_ST + w_LT·t_LT (회전율 가중)
- **Post-liquidation**: r_AT,liq = r_AT - (embedded_gain × t_LT) / V
- **교체 hurdle (intelliflo)**: α_new > α_existing + (t_ST·G_ST + t_LT·G_LT) / V / T_horizon
- **AQR 2023 발견**: 세후 alpha 주된 원천 = TLH 가 아닌 **gain deferral** (multi-bagger 결정 22 정합)
- **TER (Tier 1 예상)**: ≈ 0.945 (패시브 인덱스 상단 수준 세금 효율)
- **Greenblatt Magic Formula tax-aware 변형**: 이익 1년+1일 후 매도 / 손실 1년 전 매도 / 12개월 분산 매수
- **Wash-sale rule**: 한국 거주자 미적용 (TLH 자유)

5/17 sprint 진입 시 `api/portfolio/conviction_selector.py` 가 정밀 산식 사용. 단순 +5%p 는 *fallback* 으로 보존.

## 8. 리밸런싱 주기 — Factor-aware 이원화 (Perplexity Q3)

| 시장 | Factor | 주기 | 근거 |
|---|---|---|---|
| KR | Momentum (12-1M) | **월 1회** | 학습자료 3: KR Momentum half-life 가장 짧음 (글로벌의 30-60%) |
| KR | Value (B/P, EV/EBITDA) | **분기** | 학습자료 3: KR Value half-life ~0 (역설적이지만 분기 충분, 거래비용 회피) |
| KR | Quality (Piotroski, ROE) | **분기** | 학습자료 3: KR Quality 10-14개월 half-life |
| US | 모든 Factor | **분기** | Perplexity Q3: 22% 세금 복리 잠식 회피 |

**한국 KOSDAQ 소형 거래비용 계산** (왕복 2-4%):
- 월 12회 × 평균 30% turnover × 3% = 연 10.8% drag (Momentum만)
- 분기 4회 × 평균 30% turnover × 3% = 연 3.6% drag (Value/Quality)
- US 분기 × 평균 30% × 2.7% (왕복 0.5% + 세금 effective 2.2%) = 연 3.2% drag

월 1회 운영은 *Momentum factor 단독* 으로 제한.

## 9. 우선순위 4단 (Perplexity 결론부)

운영·결함 우선순위 (시스템 리스크 관점):

1. **ADV/시총 컷** — 실행 불가 리스크. 타협 X (Stage 0)
2. **신규상장 필터** — 보호예수·공모과열 리스크 (Stage 1)
3. **미장 슬롯 베타 구역** — 세금 hurdle 미달 시 위장 alpha (Stage 5 + 세후 layer)
4. **리밸런싱 이원화** — 세금 복리 잠식 회피 (운영 layer)

## 10. 마이그레이션 (PRODUCTION 0일 — 손실 없음)

5/17 sprint 진입 시점 변경:

```
api/builders/universe_scan_builder.py
  → Stage 0 criteria-based (5,000 hardcode 제거, ADV+시총 AND)
  → Stage 1 hard exclusion 분리 (신규상장 6m + 조건부 3필터)

api/filters/hard_exclusion.py (신규)
  → KRX 관리종목 일일 동기화
  → 자본잠식률 + 거래대금 floor
  → 신규상장 조건부 허용 + 0.5x position flag

api/filters/coarse_filter.py
  → Stage 2 quintile composite (기존 wide_scan 22% → 20%)
  → sector-neutral z-score 산식 정착

api/filters/medium_filter.py (신규 분리)
  → Stage 3 decile of remaining (현 300→100 → 300→30)
  → Brain v5 quick + Altman Z + commodity bucket

api/analyzers/brain_v5_score.py
  → 세후 환산 layer (KR/US 동일 hurdle 가능하도록)

api/portfolio/conviction_selector.py
  → Tier-aware K (6 KR + 2 US for Tier 1)
  → 베타 구역 분리 추적 (성과 별도 jsonl)
  → 세후 hurdle 적용

api/scheduling/rebalance_router.py (신규)
  → KR Momentum: 월 1회 cron
  → KR Value/Quality: 분기 cron
  → US 모든 factor: 분기 cron

docs/COST_MODEL_SPEC.md (확장)
  → 세후 alpha 정밀 산식
```

## 11. 검증 트랙 (65 거래일 PRODUCTION 게이트, 8/17 ~ 11/15)

- Stage 별 IC + ICIR 측정
- KR vs US 베타 구역 independent Sharpe
- 신규상장 0.5x position 군 hit rate
- 리밸런싱 주기별 거래비용 drag 실측
- 세후 환산 hurdle 의 KR/US 진입 분포 균형

## 12. 메모리 정합

- `project_stock_filter_v0_enhancement` — 9원칙 + 5단계 funnel 재정의
- `project_phase_2b_wide_scan` — Stage 2 quintile 정합 (현 22% → 20%)
- `project_funnel_5stage_sprint` — 5/17 sprint 시작점 = 이 doc
- `project_capital_evolution_path` — Tier 1 = 8 종목 (6+2), Tier 2+ 매트릭스
- `project_capital_3tier_mode` — 자본 3-Tier 모드 (60%/30%/10%) 와 ortho
- `feedback_source_attribution_discipline` — 모든 cut/임계값 학계 출처 (이 doc 표 형식)
- `reference_learning_materials_folder` — 학습 자료 3.pdf + 채팅 Perplexity Q1-Q4

## 13. v0.2 후속 박힘 사항 (2026-05-12 동일 세션 통합)

`feedback_spec_iteration_retract_rule` 정합: 운영 데이터 0건 상태에서 v0.1 → v0.2 → v0.3 트리플 iteration 회피. 추가 학습 자료 (5번) 의 *additive* 발견은 **별 spec 파일로 흡수**, v0.2 본문은 cross-ref 만 갱신:

| 분리 spec | 내용 | 박힌 일자 |
|---|---|---|
| `COST_MODEL_SPEC.md` Part II | 세후 alpha 정밀 산식 (Natixis/AQR/CFA L3/Greenblatt tax-aware) | 2026-05-12 |
| `SLEEVE_TRACKING_SPEC.md` | KR/US sleeve 독립 추적 + Brinson-Fachler attribution + Singer-Karnosky 환 분해 + 잔차 상관 0.4 임계 | 2026-05-12 |

이 두 spec + v0.2 = 5/17 sprint 진입 시 *함께* 적용. v0.3 박는 시점은 **운영 데이터 누적 후 (8/17~11/15 PRODUCTION 게이트 통과 후)** 또는 *근본 funnel 설계 변경* 발생 시.

## 14. v0.3 가능성 (지금 박지 않음)

- Brain v5 score 의 학계 calibration (5/17 sprint 후 데이터 누적 시)
- Factor crowding monitoring (한국 시장 alpha decay real-time)
- Sector classification 표준 (KRX vs GICS vs 자체)
- Tax-Aware Long/Short Beta-One (AQR/Quantinno 2026 트렌드, Tier 3+ 검토)
