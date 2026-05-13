# EstateMacroBridge Plan v0.1

ESTATE Tier 3 / Macro 페이지 — 매크로 → 부동산 영향 다리 (2026-05-13 박음).

## 1. 책임

VERITY 의 `market_horizon` (주식 트랙) 과 직교 — **부동산 valuation 관점** 매크로 해설.

wireframe-macro.md 정합:
- 매크로 N지표 (공공 데이터)
- LANDEX 방향성 영향 해설 (내부 관점)
- "매크로 → 부동산" 다리 역할

## 2. 부동산 직결 4지표 (자체 선정, v0)

| 지표 | source | 부동산 의미 |
|---|---|---|
| 한국 기준금리 (`korea_policy_rate`) | ECOS | 주담대 비용 driver |
| 국고채 10년 (`korea_gov_10y`) | ECOS | 부동산 valuation discount rate |
| USD/KRW (`usd_krw`) | yfinance | 외국인 매수/매도 driver |
| VIX (`vix_close`) | FRED | 위험회피 → 부동산 안전자산 선호 |

선정 사유 ([[feedback_source_attribution_discipline]] 정합):
- ECOS 2지표 = 한국 부동산 직접 driver (금리 + 장기 discount rate)
- USD/KRW = 외국인 한국 자산 매수 압력
- VIX = 글로벌 위험선호 → 부동산 vs 주식 자금 흐름

**자체 신호 명시**: 운영 누적 후 (3개월) cross-correlation 정량 검증 후 4지표 retract 검토 ([[feedback_spec_iteration_retract_rule]]).

## 3. 룰 기반 narrative (v0)

LLM 호출 X — 정적 룰 dict ([[feedback_estate_density_first]] 정합, 단순 시작).

각 지표 → 부동산 영향 1줄. 산식 코드 주석 ([[feedback_master_rule_drift_audit]]):
- 기준금리: 3.5% 이상 = 고금리 압박 / 2.5% 이상 = 중립 / 그 이하 = 저금리 자극
- 국고채 10y: YoY +1.0pp 이상 = 급등 압박 / YoY -0.5pp 이하 = 하락 신호
- USD/KRW: change_pct ±1% 임계로 외국인 매수/매도 압력 분기
- VIX: 25 이상 안전자산 매수 / 15 이하 위험선호 → 주식 유입

종합 verdict: 4지표 narrative 의 압박/완화 카운트 → "압박 우세 / 완화 우세 / 혼조".

## 4. 데이터 흐름

```
api/builders/macro_collect_builder.py (30분 cron, project_macro_collect_split)
    → data/macro_snapshot.json (main commit + publish-data staging 추가됨, 본 sprint)
    → gh-pages /macro_snapshot.json
    → /api/estate/macro-bridge (read-through + 4지표 추출 + narrative)
    → EstateMacroBridge.tsx (_shared)
```

[[feedback_simple_front_monster_back]]: frontend = 4 카드 + verdict 단순 / backend = 룰 dict + ECOS·FRED·yfinance 통합 (다중 source).

## 5. 변경 파일

- `vercel-api/api/estate_macro_bridge.py` (new) — endpoint + 룰 narrative
- `vercel-api/vercel.json` (rewrite + maxDuration)
- `estate/components/pages/_shared/EstateMacroBridge.tsx` (new) — 4 카드 + verdict
- `.github/actions/publish-data/action.yml` (macro_snapshot.json staging 추가)
- `tests/test_estate_macro_bridge.py` (new, 8 tests)
- `docs/MACRO_BRIDGE_PLAN_v0.1.md` (this)

## 6. 사용자 액션 (Bell)

- Vercel env `ESTATE_MACRO_BRIDGE_SOURCE_URL` = `https://gywns0126.github.io/VERITY/macro_snapshot.json`
- Vercel 재배포
- Framer 페이지에서 `EstateMacroBridge.tsx` paste (macro 페이지)

## 7. v1 큐잉 (후순위)

- LLM narrative (claude-sonnet) — 4지표 종합 자연어 해설
- LANDEX 시계열 cross-correlation 정량 (3개월 누적 후)
- 추가 지표 후보 (가계대출 / 미분양 / 전세가율) — wireframe-macro § "남은 결정"
- 정책 타임라인 통합 (PolicyPulse 와 직교 — 매크로 정책 vs 부동산 정책)
