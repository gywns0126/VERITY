# Lynch 분포 진단 — 71% Slow Grower 원인 + 6월 백테스트 단계 적용 권고

**상태**: 분석 완료 / 수정 보류 (백테스트 데이터 부족)
**적용 시점**: 2026-06 백테스트 단계
**작성**: 2026-04-29 (다른 Claude 세션 답변 보존)

> **Errata 2026-04-29 #1 — Q1 cross-check (Perplexity·Gemini·다른 Claude):**
> 본 문서 §1 의 "Lynch 원전 Fast Grower 임계 = 15%" 는 부정확. **Lynch 원전 = 20~25% 절대값** (One Up On Wall Street p.99 직접 인용). 1989 미국 명목 GNP ≈ 7~8% → 약 3× GNP. 한국 명목 GDP × 3 ≈ 10~11% 가 원전 충실 환산. §수정 1 의 12% 권고는 *더욱* 정합. 현 코드 15% 는 "엄격 Fast Grower" 운영 선택으로 lynch_classifier.py 주석 정정. 6월 백테스트에서 12% vs 15% 분포 비교 그대로 진행.
>
> **Errata 2026-04-29 #2 — Q2 cross-check (5소스 합의 + 코드 audit):**
> §2 의 "표본 편향만으로 71%" 는 부분만 정확. 다른 Claude 세션 시뮬레이션 결과 **샘플 효과만으론 ~44% 한계**. 71% 도달은 코드 결함 4건 합산. 코드 audit 으로 확정:
> - **결함 1**: `CYCLICAL_KEYWORDS` 에 "반도체장비/자동차부품" 만 있어 삼성전자·SK하이닉스·현대차·기아 누락 → §수정 2 의 첫 단계로 **2026-04-29 즉시 적용** ("반도체", "자동차" 추가).
> - **결함 2**: `STALWART_REV_MIN=5%` cliff effect — 매출 성장 2~5% 대형주 (삼성전자·KEPCO·통신사) 가 STALWART 미달 → SLOW fallback. **§수정 6 신규**.
> - **결함 3**: Asset Play 단일 PBR 조건 — 한국 KIS PBR 누락률 시 거의 검출 안 됨. **§수정 7 신규**.
> - **결함 4**: 데이터 누락 시 SLOW default — `data_quality=low` 마킹만 하고 분류 자체는 SLOW 로 통계 왜곡. **§수정 8 신규**.

## 핵심 발견 — 두 가지 동시 문제

### 1. Lynch 원전 임계는 *상대값* (GDP 대비)

| 분류 | Lynch 원전 |
|---|---|
| Slow Grower | GDP × 1.0~1.5 |
| Stalwart | GDP × 2 (10~12%) |
| Fast Grower | **15% 이상** (절대값 명시) |

현 시스템: GDP 1.9% × 8 = **15.2%** → Lynch 원전 15% 와 거의 일치, **임계 자체는 거의 정확**.

### 2. 71% Slow Grower 의 진짜 원인: 표본 편향

KOSPI 50종목 풀 = 시가총액 상위 = **성숙 대기업 중심**:
- 삼성전자 매출 2~5%
- 현대차 매출 5~8%
- 금융주 매출 3~7%
- 통신주 매출 1~3%
- 전기/가스 매출 1~3%

한국 KOSPI 평균 매출 성장 +5.4% (2024 KRX) → 50종목 중 70% 가 Slow~Stalwart 사이에 자연스럽게 위치.

### 3. Magellan 비교 부적절

검색 확인:
- Magellan 종목 풀 = **1,400개 + 동적 배분**
- 1980년대 미국 시장 = 강세장 + 신규 IPO 활발
- 본 시스템 KOSPI 50 ≠ Magellan 1,400 → 직접 비교 X

## 권장 수정 (3건 동시)

### 수정 1 — Fast Grower 임계 미세 조정

```python
# 현재: 15% (Lynch 원전, GDP 1.9% × 8)
# 권장: 12% (한국 GDP 보정, GDP × 6.5)

FAST_GROWER_REV_MIN = 12.0  # 15.0 → 12.0
```

### 수정 2 — Cyclical 우선 분류 강화

한국 대표 Cyclical 업종 화이트리스트 추가:

```python
# 현재 CYCLICAL_KEYWORDS:
# ("철강", "화학", "조선", "건설", "해운", "항공",
#  "반도체장비", "정유", "비철금속", "시멘트", "자동차부품")

# 추가 권장 (한국 대형주 Cyclical 명시):
KR_CYCLICAL_INDUSTRIES_PROMINENT = [
    "반도체",          # 삼성전자, SK하이닉스 — 사이클성 강함
    "자동차",          # 현대차, 기아
    "조선업",
    "정유업",
    "화학",
    "건설",
    "철강",
    "해운",
]
```

또는 매출 변동계수 (5년 std/mean) > 0.15 면 Cyclical 자동 분류.

### 수정 3 — 표본 확장

KOSPI 50 → KOSPI 200 + KOSDAQ 150 (350종목)

```python
# 50종목 표본 → 350종목 → 분포 안정화
# 예상 분포 (조정 후):
#   Slow Grower:   30~40%  (현재 71% → 대폭 감소)
#   Stalwart:      25~30%
#   Fast Grower:   8~12%   (KOSPI 한정 시 적음)
#   Cyclical:      15~20%  (반도체/자동차 화이트리스트)
#   Turnaround:    3~5%
#   Asset Play:    3~5%
```

### 수정 4 — Magellan Slow Grower 0% 배분 정책 반영 (Q2 cross-check 후 신규)

Magellan 펀드 실제 배분 (Lynch 본인 Playbook 인터뷰):
- Fast Growers: 30~40%, Turnarounds: 20%, Stalwarts: 10~20%, Cyclicals: 10~20%
- **Slow Growers: 0%** (분류만 하고 매수 안 함)

→ VERITY brain_score 의 6분류별 가중치 점검 필요. 현 시스템에서 71% 가 Slow Grower 라면 *원전상 매수 대상이 아닌* 종목들임. brain_score 가 Slow 에 어떤 가중치를 주는지, 그게 Lynch 정책과 정합한지 6월 백테스트 단계에서 측정.

### 수정 5 — 검증 풀 자체 KOSPI 200 + KOSDAQ 150 으로 교체 (Q2 cross-check 후 신규)

KOSPI 50 = "Lynch 가 절대 투자하지 않았을 종목군" (Perplexity). 이 풀로 분류 알고리즘을 검증하면 **VAMS·brain_accuracy 등 모든 분류 의존 메트릭이 잘못된 풀에서 계산**됨. 분포 검증뿐 아니라 검증 정의 자체에 영향. `project_validation_plan` 메모리 갱신 영역.

### 수정 6 — Stalwart 임계 cliff effect 완화 (Q2 코드 audit 후 신규)

```python
# 현재: STALWART_REV_MIN = 5.0 (한국 GDP × 1.5 = 5.25 cliff)
# 권장: STALWART_REV_MIN = 3.0 (Lynch 원전 GNP × 1.0~1.5 동조 + 명목 GDP 3.5%)
```

매출 성장 2~5% 대형주 (삼성전자·KEPCO·SKT·KT·금융지주) 가 5% cliff 에 걸려 SLOW fallback. 3% 로 낮추면 STALWART 정상 검출.

### 수정 7 — Asset Play 다중 조건 (Q2 코드 audit 후 신규)

```python
# 현재: 0 < pbr < 0.8 단일 조건
# 권장: PBR < 0.8 OR (순현금/시총 > 30% AND 부동산자산/시총 > 50%)
```

Lynch 원전 Asset Play = 자산 할인 종목. PBR 만으로는 한국 KIS PBR 누락률 + 부동산 보유 법인 누락. DART 확장으로 순현금/부동산 데이터 수집 후 적용.

### 수정 8 — UNCLASSIFIED 카테고리 도입 (Q2 코드 audit 후 신규)

```python
# 현재: 데이터 누락 → cls = "SLOW_GROWER" default. data_quality="low" 마킹.
# 권장: cls = "UNCLASSIFIED". 분류 통계에서 분리.
```

핵심 데이터 누락 종목이 SLOW 로 흘러가 통계 왜곡. UNCLASSIFIED 분리 시 6월 백테스트 분포 측정 정확도 향상.

### 수정 9 — KOSPI 50 골든 데이터셋 + confusion matrix (Q2 cross-check 후 신규)

수동 라벨링 (월스트리트 한국 커버 베테랑 관점) 50종목 + 분류기 결과 비교 → confusion matrix → 어느 카테고리에서 누락이 가장 많이 발생하는지 정량 식별. 골든셋 없이 임계 조정하면 또 임의값. **다른 §수정의 측정 도구**.

## 적용 시점 — 단계별 분리

| 카테고리 | 즉시 적용 (백테스트 불필요) | 6월 백테스트 |
|---|---|---|
| §수정 2 첫 단계 (반도체·자동차 키워드) | ✓ 2026-04-29 적용 완료 | — |
| §수정 1 (Fast 12% vs 15%) | — | ✓ 분포 효과 측정 |
| §수정 2 변동계수 자동 식별 (Q3) | — | ✓ 방법론 비교 |
| §수정 3 (350 표본) | — | ✓ 분포 효과 |
| §수정 4 (Magellan Slow 0%) | — | ✓ brain_score 가중치 측정 |
| §수정 5 (검증 풀 교체) | — | ✓ 검증 정의 영역 |
| §수정 6 (Stalwart 5%→3%) | — | ✓ 임계 효과 |
| §수정 7 (Asset Play 다중) | — | ⚠ DART 확장 후 |
| §수정 8 (UNCLASSIFIED) | 선택 (1~2주 내 가능) | 또는 6월 |
| §수정 9 (골든 데이터셋) | ✓ 측정 도구 — 작성 가능 | 6월 측정에 사용 |

**원칙:** 사실 분류 (반도체=Cyclical 같은 5소스 합의 사항) 는 백테스트 불필요 — 즉시 적용. 임계 조정·임의값은 6월 백테스트.

## 한 줄 결론

71% Slow Grower 원인:
- 샘플 편향 (KOSPI 50 대형주 편중) — ~44% 기여
- 코드 결함 4건 (Cyclical 키워드 누락 / Stalwart cliff / Asset Play 단일 조건 / SLOW default) — 27% 기여

§수정 2 첫 단계 (반도체·자동차) 즉시 적용 → 71% → ~63% 예상. 나머지 §수정 1·3·6·7·8 + 골든셋(§9) 측정 + brain_score 가중치 점검(§4·5) 은 **6월 백테스트 단계**.

---

**원본 답변자**: 다른 Claude 세션 (2026-04-29)
**Q1·Q2 cross-check 완료** (Perplexity·Gemini·다른 Claude 5소스 합의 + 코드 audit). Q3 (Cyclical 키워드 vs 변동계수 자동 식별 방법론) 은 6월 백테스트 단계 디테일.
