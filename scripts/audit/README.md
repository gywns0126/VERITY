# scripts/audit — 측정층 자체를 재는 감사

여기 있는 것은 **데이터를 만드는 코드가 아니라, 우리 측정이 유효한지 재는 코드**다.
산출물은 `data/analysis/*_audit.json` 으로 나가고, 각각 `_meta` 에 **못 잰 것**을 자기 신고한다
(CLAUDE.md RULE 12 — 산출물이 자기 입으로 말하게 한다).

---

## `ic_overlap_check.py` — 팩터 IC 의 t 값이 겹침으로 부풀려졌는지

### 왜 필요한가

`alpha_scanner.compute_factor_ic` 은 **일별 스냅샷마다** forward 창을 연다. 스냅샷 간격이
중앙 1일이므로 인접 관측은 `(fwd-1)/fwd` 만큼 **같은 미래 구간을 공유**한다. 그런데
시스템이 쓰는 t 는 관측 **일수** n 을 그대로 독립 표본으로 센다.

```
t_현행   = ICIR × √n        # n = 관측 일수
독립관측 k = n // fwd        # 겹치지 않는 블록 수
```

`factor_decay.compute_ic_weight_adjustments()` 는 2026-05-23 에 정확히 이 사유로 동결됐고
(*"유효-N ≈ 6 … overlap, autocorrelation 착시"*), 해제 조건을
**"non-overlapping 또는 Newey-West 보정 도달"** 로 적어 두었다.
**이 스크립트가 그 해제 조건이다.**

### 2026-08-15 판정 — 미달

스냅샷 115일(2026-04-05 ~ 08-15) 기준, 60개 (팩터 × 지평) 칸:

| 지평 | 관측일수 n | 독립관측 k | 겹침률 | 판정 |
|---|---|---|---|---|
| fwd7  | 48 | **6** | 86% | 2칸만 통과 |
| fwd14 | 49 | **3** | 93% | 0칸 |
| fwd30 | 54 | **1** | 97% | 🚨 표준오차 추정 불가 |
| fwd63 | 36 | **0** | 98% | 🚨 표준오차 추정 불가 |

살아남은 것 2 / 60, 둘 다 경계선:

```
mean_reversion  fwd7   IC +0.152   t 현행 +4.9 → 비겹침 +2.13  (부풀림 2.3배)
timing          fwd7   IC +0.094   t 현행 +4.9 → 비겹침 +1.98  (부풀림 2.5배)
```

🚨 **3개월 누적이 유효 N 을 전혀 못 올렸다** — 5/23 추정 6 → 8/15 실측 6.
병목이 달력이 아니라 **겹침**이라서다. fwd30 에서 독립 관측 30개를 모으려면
스냅샷 약 **900일 ≈ 2.5년**이 필요하다.
→ `docs/VALIDATION_METHODOLOGY.md` §7 원칙 0("틀은 '더 모아라' 를 기본 출력으로 가질 수 없다")이
정면으로 걸리는 지점.

### 이 판정이 바꾸는 것 / 바꾸지 않는 것

- ✅ **실운용 가중치는 무영향.** IC 기반 가중 변조 path 는 frozen static dict 반환.
  부풀려진 t 가 돈을 움직이지 **않는다.**
- 🚨 **남은 실물 결함** = `alpha_scanner.py:206`
  ```python
  "is_significant": abs(ic_mean) > 0.05 and abs(icir) > 0.4,   # 표본 수 항이 없다
  ```
  유의성 검정이 아니라 고정 임계 2개다. 그 결과가 `significant_factors` 로 나가
  `daily_admin_pdf.py:1307` · `monthly_admin_pdf.py:500` 에서 **"유의 팩터 (N): ..."** 로
  표시되고, 옆에 `n=48` 이 붙어 큰 표본처럼 읽힌다. → **PM 판단 입력의 오표기.**
  라벨 정정은 RULE 7(자기 산식 임계 조정 = 사전 PM 승인) 대상이라 승인 대기.

### 실행

```bash
python3 scripts/audit/ic_overlap_check.py            # 표 + 산출물 기록
python3 scripts/audit/ic_overlap_check.py --dry-run  # 출력만
```

**재실행 시점** — 분기 1회 또는 동결 해제를 검토할 때. 매일 돌릴 이유는 없다
(관측 인프라가 관측 대상보다 정교해지면 측정이 목적이 된 것 — kickoff "산으로 가는가" ②).

### 이 스크립트가 못 재는 것 (산출물 `_meta` 와 동일)

1. **표본 풀의 자기선택 편향** — 일별 `recommendations` 는 `stock_filter` 가 `safety_pct`
   정렬로 뽑은 상위 집합이다. `safety_score` 의 IC 는 이 때문에 부호·크기 모두 해석 불가
   (`alpha_scanner._SELECTION_KEY_FACTORS` 에 이미 명시).
2. **horizon truncation** — fwd7/14/30 의 비-exact 경로는 창 끝에서 실제 지평이 라벨보다
   짧아진다 (`alpha_scanner.py:130-136`, "기존 trail 의미 보존" 으로 의도적 잔존).
3. **일별 종목 수 변동** — 중앙 40, 범위 18~67. 각 IC 추정치의 분산이 날마다 다르다.

---

## 관련

- `docs/BRAIN_AUDIT_2026_08_15.md` §1-B — 이 판정의 전체 맥락
- `api/quant/alpha/factor_decay.py:276` — 동결 사유 + 해제 trigger 원문
- `docs/VALIDATION_METHODOLOGY.md` §7 — 검증 틀 v2
