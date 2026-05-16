# Phase Verdict 자동화 템플릿 (Phase 1/2/3...)

작성: 2026-05-16 (audit P0-5)
연관: `feedback_continuous_evolution` (잠금 폐기 + 4가드)
원본: `.github/workflows/atr_phase_0_verdict.yml` (Phase 0, 5/16 완료 1회성)

---

## 자동화 목적

Phase 0 (ATR Wilder vs SMA migration) 1회성 verdict 인프라를 후속 Phase 에 일반화.
**자가 성장 인프라 P2 완성도 58 → 80+ 달성 의무 항목**.

---

## Phase 별 verdict cron 매핑

| Phase | 의제 | verdict 기준 | 진입 게이트 | cron yml |
|---|---|---|---|---|
| **Phase 0** ✅ | ATR Wilder vs SMA | avg_diff_pct < 15% | Phase 1.5.1 unlock | `atr_phase_0_verdict.yml` (완료) |
| **Phase 1.1** | ATR×2.5 stop hit rate | stop_hit ≤ 30% / 정상 holding ≥ 70% | Phase 1.2 진입 | `atr_phase_1_1_stop_verdict.yml` |
| **Phase 1.2** | R-multiple 부분 익절 50/30/20 | +1R hit ≥ 40% / 잔여 trailing 정상 | Phase 1.3 진입 | `atr_phase_1_2_exit_verdict.yml` |
| **Phase 2-A** | universe ramp-up 5000 | cron 발화 ≥ 90% / 데이터 fresh | Phase 2-B 진입 | `phase_2a_ramp_verdict.yml` |
| **Phase 2-B** | wide_scan SHADOW (5000→1000) | IC ≥ 0.05 / ICIR ≥ 0.3 | Phase 2-C 진입 | `phase_2b_wide_scan_verdict.yml` |
| **Phase 2-C** | medium_filter (1000→300) | Brain v5 quick scoring 정합 | Phase 2-D 진입 | `phase_2c_medium_verdict.yml` |
| **Phase 2-D** | conviction_selector (300→100→25) | Sector diversified Top 10 | PRODUCTION 진입 | `phase_2d_conviction_verdict.yml` |
| **Phase 3** | PRODUCTION 65 거래일 (8/17~) | excess_accuracy > 0 + sharpe ≥ 1.0 | PROD 정식 | `phase_3_production_verdict.yml` |

---

## 표준 yml 템플릿 구조

```yaml
name: <Phase N> Verdict (cron 자동화)

on:
  schedule:
    - cron: '<UTC time>'   # 게이트 직전 자동 발화
  workflow_dispatch:        # 수동 트리거 보존

env:
  FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: "true"

concurrency:
  group: verity-data-write
  cancel-in-progress: false

permissions:
  contents: write

jobs:
  verdict:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - name: Run verdict analyzer
        env:
          # API keys / secrets
          KIS_APP_KEY: ${{ secrets.KIS_APP_KEY }}
        run: |
          python scripts/<phase_n>_verdict_analyzer.py \
            --window-start <start_date> \
            --window-end <end_date> \
            --persist <persist_path> | tee verdict.txt
      - name: Telegram push verdict
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
        run: |
          VERDICT=$(grep -oE "VERDICT: \w+" verdict.txt | head -1)
          MSG_MAP='{
            "ok": "✅ <b>OK</b> — 후속 Phase 진입 가능",
            "monitoring": "🟡 <b>MONITORING</b> — +7일 후 재산정",
            "fail": "🔴 <b>FAIL</b> — rollback 검토",
            "escape": "⚠️ <b>ESCAPE</b> — 매크로 이상 +7일 연장",
            "insufficient_data": "⚠️ <b>INSUFFICIENT_DATA</b> — 데이터 누적 필요"
          }'
          MSG=$(echo "$MSG_MAP" | python -c "import sys,json; d=json.load(sys.stdin); print(d.get('$VERDICT', 'unknown'))")
          curl -X POST https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/sendMessage \
            -d chat_id=$TELEGRAM_CHAT_ID \
            -d parse_mode=HTML \
            -d text="$MSG"
      - name: Commit + push verdict
        run: |
          git config user.name "AI Stock Bot"
          git config user.email "bot@ansim.ai"
          git add data/metadata/phase_<N>_results.json
          git commit -m "[brain] Phase <N> verdict 자동 산출" || echo "no changes"
          git push
```

---

## verdict_analyzer 스크립트 패턴

각 Phase 마다 `scripts/phase_<N>_verdict_analyzer.py`:

```python
"""Phase N verdict analyzer — <설명>.

Args:
    --window-start: ISO date
    --window-end: ISO date
    --persist: result 저장 경로 (data/metadata/phase_N_results.json)

Verdict 결정:
    ok: 임계 통과 → 후속 Phase 진입 가능
    monitoring: 부분 통과 → 7일 추가 검증
    fail: 미통과 → rollback
    escape: market_abnormal (KOSPI ±5%+) 발화 → 7일 연장
    insufficient_data: 표본 부족 → 데이터 누적 후 재실행
"""
```

핵심 룰:
1. **명시적 verdict + reason** (silent skip 절대 금지)
2. **persist json** = 결과 영속화 (gh-pages publish 통합)
3. **telegram push** = 사용자 즉시 통지
4. **market_abnormal escape** = KOSPI/외인 급변 시 verdict 보류

---

## 진행 순서 (P0-5 후속 박힘 액션)

1. **Phase 1.1 stop verdict** (2026-06 첫 평일 cron 누적 후)
2. **Phase 2-A ramp verdict** (이미 5/10 5000 ramp 완료 → 즉시 박힘 가능)
3. **Phase 2-B wide_scan verdict** (5/17 sprint 후 IC 측정 시작 → 6월 말)
4. **Phase 3 PRODUCTION verdict** (8/17 게이트, 가장 중요)

---

## 메모리 정합

- `feedback_continuous_evolution`: 4가드 (commit/시간대/모니터링/롤백) — 본 템플릿이 commit + 모니터링 가드 자동화
- `project_atr_phase0_migration`: Phase 0 5/16 완료 → 본 템플릿이 후속 일반화
- `project_phase_2b_wide_scan`: 65 거래일 게이트 → Phase 3 verdict 의 핵심 입력
- `feedback_workflow_yml_audit_mandatory`: 6축 audit 의무 (env/push/concurrency/timeout/secret/pip) — 본 템플릿 이미 정합
