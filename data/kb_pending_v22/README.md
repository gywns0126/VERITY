# KB v2.2 Staged Materials — DO NOT INTEGRATE BEFORE 2026-07-24

이 디렉토리는 VAMS 검증 잠금 기간 (2026-04-25 ~ 2026-07-24) 동안
**보관만** 되는 KB v2.2 후보 자료입니다.

## 잠금 해제 절차 (2026-07-24)

1. AdminDashboard 일정/TODO 카드의 `kb-v22-merge-2026-07-24` 항목 done:false 확인
2. brain_quality 90일 합격 기준 충족 여부 검증 (사후 기준 조정 금지)
3. 합격 시 → Draft PR 머지 → `python3 scripts/build_brain_kb_v2.py` 실행 → 자동 활성화
4. 불합격 시 → 잠금 연장 또는 v2.2 재설계

## 신규 등록 3권 (build_brain_kb_v2.py BOOK_ENRICH_VOL4)

| book_id | 저자 | 카테고리 | PDF |
|---------|-----|----------|-----|
| `ackman_concentrated_activist` | Bill Ackman | value_investing | Bill_Ackman_on_What_Makes_a_Great_Investment.pdf |
| `hohn_tci_activist_quality` | Chris Hohn | value_investing | Chris Hohn — TCI Fund Management.pdf |
| `druckenmiller_macro_liquidity` | Stanley Druckenmiller | **macro_liquidity (신규)** | 2020DruckenmillerTranscript.pdf |

## 보조 자료 (재료로만 보유, 별도 등록 X)

| PDF | 용도 |
|-----|------|
| Beating-the-Street-by-Peter-Lunch.pdf | `lynch_one_up` 항목 강화 case study |
| the-peter-lynch-playbook.pdf | `lynch_one_up` 6 카테고리 룰 추출 재료 |
| One Up On Wall Street ...pdf | 이미 등록된 `lynch_one_up` full text 백업 |
| 9781118505212.excerpt.pdf (The Most Dangerous Trade) | short-selling 재평가 자료 (lewis_big_short 와 비교) |
| 2026-Annual-Investor-Presentation.pdf (Pershing 2026) | Ackman 활동주의 적용 사례 |
| RCM_TCFD Entity-Level Report.pdf | KB 부적합 (회사 자체 climate 공시) — 보관만 |

## 신규 카테고리 — `macro_liquidity`

기존 KB 의 `cape_macro_strategy` (Shiller CAPE 기반) 를 보완하는
*Fed/Treasury 자금 흐름 기반* 매크로 분야. Druckenmiller 가 시작점.
추후 Soros / Dalio / Howard Marks 추가 시 카테고리 확장.

## 신규 트리거 (TRIGGER_INDEX 추가)

- `concentrated_activist_target` (Ackman)
- `depressed_earnings_with_moat` (Ackman + Buffett)
- `headcount_growth_gt_revenue_growth_3y` (Hohn)
- `comp_per_employee_gt_peer_median_50pct` (Hohn)
- `excess_cash_gt_5pct_market_cap` (Hohn + Buffett)
- `non_core_segment_loss_5yr` (Hohn)
- `fed_balance_sheet_yoy_gt_20pct` (Druckenmiller)
- `treasury_net_issuance_minus_fed_purchases_negative` (Druckenmiller)
- `qe_qt_regime_change` (Druckenmiller)
- `fed_funds_path_change` (Druckenmiller)

## 신규 frameworks

- `ackman_concentrated_8_12` — 8~12 포지션 / 55-15-30 split / 회피 섹터 / 숏 기준
- `tci_activist_letter_template` — 6요소 정량 활동주의 letter 구조
- `druckenmiller_liquidity_regime` — 4단계 매크로 유동성 regime + 자산 stance

## 잠금 위반 시 위험

이 변경을 7/24 전에 머지하면:
- 새 트리거가 활성화되어 기존 종목의 등급/점수 분포 이동
- `brain_quality` 25일+ 누적 데이터의 비교 기준 깨짐
- 90일 검증 시계 사실상 리셋
