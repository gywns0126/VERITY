# RealEstateTaxSimulator Plan v0.1

ESTATE Tier 2 / F — 한국 부동산 세제 시뮬레이터 (2026-05-12 박음).

## 1. 범위 (v0 — 단순화)

[[feedback_estate_density_first]] 정합 — 가장 흔한 케이스만:

- **1세대 1주택 트랙만** (다주택 중과는 v1 후순위)
- **3종 세금**: 취득세 (1회) / 보유세 (연간 = 재산세 + 종부세) / 양도세 (매도 시)
- **input**: 매수가, 공시가격, 보유기간, 거주기간, 매도가
- **output**: 각 세금 금액 + 총 부담 + 실효세율
- **외부 API 없음** — 자체 룰 표

## 2. 룰 표 (2026 기준 가정, 출처 명시 + 사용자 검증 의무)

### 2.1 취득세 (매수 시 1회)

| 매수가 구간 | 세율 |
|---|---|
| 6억 이하 | 1.1% (지방교육세 0.1% 포함) |
| 6~9억 | 1.0% + 누진 (= 2.0% 평균) |
| 9억 초과 | 3.3% (지방교육세 0.3% 포함) |

### 2.2 재산세 (매년)

```
과세표준 = 공시가격 × 공정시장가액비율(60%)
```

| 과세표준 구간 | 세율 | 누진공제 |
|---|---|---|
| ≤ 6,000만원 | 0.10% | 0 |
| ≤ 1.5억 | 0.15% | 3만원 |
| ≤ 3억 | 0.25% | 18만원 |
| > 3억 | 0.40% | 63만원 |

### 2.3 종합부동산세 (1세대 1주택, 매년)

```
공제 = 공시가격 12억 (1세대 1주택 특례)
과세표준 = max(0, 공시가격 - 12억) × 공정시장가액비율(60%)
```

| 과세표준 (대상금액) | 세율 |
|---|---|
| ≤ 3억 | 0.5% |
| ≤ 6억 | 0.7% |
| ≤ 12억 | 1.0% |
| ≤ 25억 | 1.3% |
| ≤ 50억 | 1.5% |
| ≤ 94억 | 2.0% |
| > 94억 | 2.7% |

### 2.4 양도세 (1세대 1주택, 매도 시)

```
1단계 비과세: 실거래가 12억 이하 + 보유 2년 + 거주 2년 → 양도세 0
2단계 (12억 초과 1주택): 12억 초과분에만 양도세 부과
3단계 (보유 < 2년 단기 양도): 1년 미만 70% / 1~2년 60%
4단계 (2년 이상 누진세율 + 장기보유특별공제):
```

기본세율 (2026):
| 과세표준 | 세율 | 누진공제 |
|---|---|---|
| ≤ 1,400만원 | 6% | 0 |
| ≤ 5,000만원 | 15% | 126만원 |
| ≤ 8,800만원 | 24% | 576만원 |
| ≤ 1.5억 | 35% | 1,544만원 |
| ≤ 3억 | 38% | 1,994만원 |
| ≤ 5억 | 40% | 2,594만원 |
| ≤ 10억 | 42% | 3,594만원 |
| > 10억 | 45% | 6,594만원 |

장기보유특별공제 (1세대 1주택 + 보유 + 거주):
- 3년: 24% (보유 12% + 거주 12%)
- 4년: 32%
- ... +8%p / 년
- 10년 이상: 80% (최대)

## 3. 출처 + 검증 의무 ([[feedback_master_rule_drift_audit]])

**룰 출처 (claude knowledge 2026 기준)**:
- 국세청 부동산 세제 매뉴얼 (2025-2026 변경 사항 반영)
- 1세대 1주택 12억 비과세 한도 (2025-12-31 시행)
- 종부세 1주택 12억 공제 (2025-01 시행)

**자체 신호 명시** (LLM 기반 — 운영 전 사용자 검증 필수):
- 실제 적용 시 국세청 홈페이지 또는 세무사 확인 의무
- 본 시뮬레이터 = **개인 시스템 트랙 추정용** ([[feedback_no_personal_use_regulation_warnings]] 정합 — 면책 경고 자동 첨부 X). 의사결정 = 사용자 책임.
- 룰 변경 잦음 — v1 sprint 에서 출처 link + 마지막 갱신일 박음

## 4. 데이터 흐름 (외부 API 없음)

```
사용자 input (Framer 컴포넌트)
    ↓
POST /api/estate/tax-simulator
    {매수가, 공시가격, 보유기간, 거주기간, 매도가}
    ↓
vercel-api/api/estate_tax_simulator.py
    rules dict (코드 내장 — vercel-api 단독 build artifact)
    ↓ 산식
output:
    {acquisition_tax, annual_property_tax, annual_compr_tax,
     capital_gains_tax, total_burden, effective_rate}
```

[[feedback_simple_front_monster_back]] 정합 — frontend input form 단순 / backend 산식 정밀.

## 5. 변경 파일

- `vercel-api/api/estate_tax_simulator.py` (new) — 룰 dict + 산식 + POST handler
- `vercel-api/vercel.json` (rewrite + maxDuration)
- `estate/components/pages/_shared/RealEstateTaxSimulator.tsx` (new) — input form + output 카드
- `tests/test_estate_tax_simulator.py` (new) — 산식 단위 테스트
- `docs/REAL_ESTATE_TAX_SIMULATOR_PLAN_v0.1.md` (this)

builder/cron/publish-data **변경 없음** — 정적 룰 표는 endpoint 내장.

## 6. v1 큐잉 (후순위)

- 다주택 중과 (조정대상지역 2주택 +20%p / 3주택 +30%p)
- 법인 보유 (취득세 12%)
- 임대사업자 등록 (조세 특례)
- 룰 출처 link + 마지막 갱신일 자동 검증
- 사용자 시나리오 (5년 후 매도 vs 보유) 비교 카드
