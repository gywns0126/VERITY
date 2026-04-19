# VERITY 검수 리포트 — SESSION 7 (수정 후 통합 검증)

**범위:** SESSION 1~6에서 수정된 모든 파일의 사이드이펙트·dry run·최종 정리
**검증 항목:** 의존성 체인 추적 / brain_score 계산 dry run / git push 로직 재확인 / 전체 이슈 정리 / 적용 vs 미적용 체크리스트

---

## 1. 의존성 체인 추적

수정된 모듈의 시그니처 변경이 호출부에 사이드이펙트를 일으키는지 검증.

### 1-1. `supabase_client.py` 시그니처 변경 (`user_id=` → `user_jwt=`)

| 호출부 | 라인 | 사용 형태 | 정합성 |
|---|---|---|---|
| `vercel-api/api/order.py` | 100~108 | `sb.select("profiles", {...}, user_jwt=jwt)` | ✅ |
| `vercel-api/api/watchgroups.py` | 138, 145, 187, 194, 204, 242, 275, 282, 289, 295 | `sb.select/insert/update/delete(..., user_jwt=jwt)` | ✅ |

→ **모든 호출부가 새 키워드(`user_jwt=`)로 일관 사용**. 구 `user_id=` 호출 0건.

### 1-2. `_env_int` / `_env_float` 헬퍼 (config.py 신규)

- `api/config.py` 내부 34개 라인이 헬퍼로 일괄 교체 (WARN-7)
- 외부 모듈은 `from api.config import VAMS_INITIAL_CASH` 등 결과 상수만 import → **시그니처 변경 영향 없음**
- `api/trading/auto_trader.py:72`에 별도 로컬 `_env_int` 정의 존재 — 이름 충돌 없음 (서로 다른 모듈 스코프)

### 1-3. `portfolio_lock` (vams/engine.py 신규)

| 호출부 | 위치 | 사용 형태 |
|---|---|---|
| `api/main.py:86` | import | `from api.vams.engine import (..., portfolio_lock)` |
| `api/main.py:939~947` | `main()` 진입부 | `portfolio_lock.__enter__()` + `atexit.register(release)` |

→ 단일 호출부, fcntl 미지원 환경(Windows)은 no-op 폴백. ✅

### 1-4. `TELEGRAM_ADMIN_CHAT_IDS` (config.py 신규)

| 호출부 | 위치 |
|---|---|
| `api/config.py:88, 103` | 정의 |
| `api/notifications/telegram_bot.py:27` | import |
| `api/notifications/telegram_bot.py:49~51` | `_is_admin()` 체크 |

→ fail-closed: 미설정 시 None → admin 명령 전체 차단. ✅

### 1-5. `TELEGRAM_CRITICAL_DEDUPE_MINUTES` (config.py 신규)

| 호출부 | 위치 |
|---|---|
| `api/config.py:360` | 정의 |
| `api/notifications/telegram_dedupe.py:12` | import |
| `api/notifications/telegram_dedupe.py:22` | `_ttl_for_alert()`에서 60 곱해 초 단위 변환 |

→ ✅

### 1-6. `apply_proposal` 신규 필드 `pre_change_snapshot`

- `strategy_evolver.py:518`에 추가 — 기존 `versions[]` 구조와 호환 (필수 필드 아님)
- `rollback_strategy()` Line 543~594가 이 필드를 역순 검색해 사용
- 구 레지스트리(필드 없음)에 대한 처리: 명시적 `if not target: return None` (Line 558) → 사용자에게 "롤백 불가" 알림
- **이전 세션에서 v1 entry에 수동 시드 주입 완료** (data/strategy_registry.json)

### 1-7. Framer 컴포넌트 외부 의존성

- 9개 인라인 `fetchPortfolioJson` 모두 동일 패턴 (15s timeout + AbortController) → 일관성 확보
- `WatchGroupsCard.tsx`, `StockDashboard.tsx` 의 JWT 헬퍼는 동일 시그니처 (`getAccessToken`/`authHeaders`) 로 패턴 매칭

**의존성 체인 결론**: 모든 시그니처 변경이 호출부에 정상 반영됨. 깨진 import / undefined 변수 / signature mismatch 없음.

---

## 2. `verity_brain.py` brain_score 계산 dry run

### Case A — fact_score 입력 데이터 부재 (multi_factor·DART 등 None)

| 단계 | 값 | 근거 |
|---|---|---|
| `_compute_fact_score` 모든 components → None/0 | total=0 | NaN 가드 (Line 580~581) |
| → fact["score"] | `round(_clip(0)) = 0` | Line 584 |
| `fs = float(fact["score"] or 0)` | 0.0 | Line 1663 |
| sentiment 기본 50 (입력 없음 시) | ss = 50.0 | |
| vci_val = 0 - 50 | -50 → STRONG_CONTRARIAN_SELL | |
| vci_bonus | -10 (vci_val<-25 AND fs<50) | Line 1670~1671 |
| candle_bonus, gs_bonus, inst_bonus | 0, 0, 0 | |
| red_flag_penalty | 0 | downgrade_count=0 |
| raw = 0×0.7 + 50×0.3 + (-10) + 0 + 0 + 0 - 0 | **5.0** | |
| brain_score = round(_clip(5)) | **5** | |
| grade = _score_to_grade(5) | **AVOID** | constitution: 30 미만 |

### Case B — sentiment_score=0 입력

| 단계 | 값 |
|---|---|
| fact 기본 50 → fs = 50.0 | |
| sentiment["score"] = 0 → ss = 0.0 | |
| vci_val = 50 - 0 = +50 → STRONG_CONTRARIAN_BUY | |
| vci_bonus: `vci_val>25 AND fs>=60`? **fs=50 < 60 → vci_bonus=0** | |
| raw = 50×0.7 + 0×0.3 + 0 + 0 + 0 + 0 - 0 = **35.0** | |
| brain_score = **35**, grade = **CAUTION** (≥30) | |

### Case C — 모든 보너스=0, red_flag_penalty=100 (이론적 입력)

| 단계 | 값 |
|---|---|
| 실제 코드: `red_flag_penalty = min(downgrade_count × 5, 20)` → **상한 20** | |
| 가설로 100 강제 시: raw = 50×0.7+50×0.3+0+0+0+0-100 = **-50** | |
| `_clip(-50, 0, 100)` = **0** | Line 53~54 |
| brain_score = **0**, grade = **AVOID** | |
| **+ red_flags.has_critical=True 시 (CRIT-1 fix 적용)**: contrarian_upgrade도 차단 → grade=AVOID 보존 | Line 1740 |

**검증 결과**: 3개 케이스 모두 NaN/undefined 노출 없이 안전한 정수 결과 산출. CRIT-1 fix로 `has_critical` 종목은 패닉 모드에서도 AVOID 유지.

### NaN/inf 방어선 3중 구조 확인

1. `_compute_fact_score` Line 580: `if not isinstance(total, (int, float)) or math.isnan(total) or math.isinf(total): total = 0.0`
2. `_compute_sentiment_score` Line 788: 동일 패턴
3. `analyze_stock` Line 1722: `raw` 최종 sum에 동일 패턴

→ 어느 컴포넌트가 NaN을 만들어도 brain_score 출력은 정수 0~100 보장.

---

## 3. `daily_analysis.yml` git push 로직 재확인

### 검증 코드 (Line 187~217)

```yaml
- name: Commit & push results
  run: |
    git config user.name "AI Stock Bot"
    git config user.email "bot@ansim.ai"
    git add data/
    HOUR_KST=$(TZ=Asia/Seoul date +%H:%M)
    MODE="${{ steps.detect_mode.outputs.mode }}"
    if [[ "$MODE" == periodic_* ]]; then
      LABEL=$(echo "$MODE" | sed 's/periodic_//')
      git diff --staged --quiet || git commit -m "📋 ${LABEL} 리포트 $(TZ=Asia/Seoul date +%Y-%m-%d)"
    else
      git diff --staged --quiet || git commit -m "📊 분석 업데이트 $(TZ=Asia/Seoul date +%Y-%m-%d) ${HOUR_KST}"
    fi
    BRANCH="${{ github.ref_name }}"
    PUSHED=false
    for i in 1 2 3 4 5; do
      git rebase --abort 2>/dev/null || true        # ← WARN-5
      git merge --abort 2>/dev/null || true         # ← WARN-5
      if git pull --rebase -X theirs origin "$BRANCH" && git push origin "$BRANCH"; then
        PUSHED=true
        break
      fi
      echo "Push attempt $i failed, retrying in $((i * 10))s..."
      sleep $((i * 10))
    done
    if [ "$PUSHED" != "true" ]; then
      echo "::error::All 5 push attempts failed"
      exit 1
    fi
```

### concurrency 블록 (Line 50~54)

```yaml
concurrency:
  # WARN-17: data/* 쓰기 워크플로 단일 그룹 직렬화
  group: verity-data-write
  cancel-in-progress: false
```

### 검증 항목 체크

| 항목 | 상태 |
|---|---|
| concurrency group `verity-data-write` (4개 워크플로 공유) | ✅ WARN-17 |
| `cancel-in-progress: false` (저장 도중 cancel 방지) | ✅ CRIT-11 |
| retry 매 반복마다 `git rebase --abort` + `git merge --abort` 정리 | ✅ WARN-5 |
| `pull --rebase -X theirs` 로 data/*.json 충돌 시 원격 우선 | ✅ WARN-5 |
| 5회 실패 시 `exit 1` | ✅ |
| 명시적 `git push origin "$BRANCH"` (upstream 의존 제거) | ✅ |

→ **git push 로직 정상**. 동시 실행 시 큐잉되며 충돌 발생 시 자동 복구.

### 동일 패턴 적용 워크플로 (5개 일괄)

| 파일 | 적용 |
|---|---|
| `daily_analysis.yml` | ✅ |
| `daily_analysis_full.yml` | ✅ |
| `bond_etf_analysis.yml` | ✅ |
| `export_trade_daily.yml` | ✅ |
| `rss_scout.yml` | ✅ |

---

## 4. 전체 이슈 목록 (심각도순)

| # | 식별 | 파일 | 유형 | 적용 |
|---|---|---|---|---|
| 🔴 | CRIT-1 | verity_brain.py | auto_avoid가 contrarian_upgrade로 무력화 | ✅ |
| 🔴 | CRIT-2 | verity_brain.py | bond_regime이 red_flags/macro cap 소급 무효화 | ✅ |
| 🔴 | CRIT-3 | api/main.py | 캔디데이트 loop 외부 try/except 부재 | ✅ |
| 🔴 | CRIT-4 | api/main.py | briefing 실패 시 save_portfolio 미실행 | ✅ |
| 🔴 | CRIT-5 | order.py + StockDetailPanel.tsx | ORDER_SECRET 브라우저 노출 | ✅ |
| 🔴 | CRIT-6 | order.py | 주문 수량/금액/중복 검증 부재 | ✅ |
| 🔴 | CRIT-7 | watchgroups.py + supabase_client.py | IDOR / RLS 우회 | ✅ |
| 🔴 | CRIT-8 | chart.py | ticker path traversal | ✅ |
| 🔴 | CRIT-9 | strategy_evolver.py | rollback이 constitution을 되돌리지 않음 | ✅ |
| 🔴 | CRIT-10 | telegram_bot.py | admin 명령 화이트리스트 부재 | ✅ |
| 🔴 | CRIT-11 | vams/engine.py + workflows | portfolio.json 동시 수정 race | ✅ |
| 🔴 | CRIT-12 | daily_analysis.yml | cron 동일 분 중복 매치 | ✅ |
| 🔴 | CRIT-13 | health.py | Finnhub/Polygon/SEC/Perplexity 감시 누락 | ✅ |
| 🔴 | CRIT-14 | telegram_dedupe.py | CRITICAL 4시간 억제 | ✅ |
| 🔴 | CRIT-15 | WatchGroupsCard.tsx + StockDashboard.tsx | JWT 미전송 → 401 | ✅ |
| 🔴 | CRIT-16 | WatchGroupsCard.tsx | CRUD 빠른 클릭 중복 요청 | ✅ |
| 🔴 | CRIT-17 | StockDashboard.tsx | fetch 실패 무한 로딩 | ✅ |
| 🟡 | WARN-1 | verity_brain.py | None 비교 TypeError | ✅ |
| 🟡 | WARN-2 | verity_brain.py | STRONG_BUY 강등 누락 | ✅ |
| 🟡 | WARN-3 | api/config.py | env 빈문자열 → import 크래시 | ✅ |
| 🟡 | WARN-4 | verity_brain.py | candle ValueError 미방어 | ✅ |
| 🟡 | WARN-5 | workflows (5개) | git rebase 충돌 복구 부재 | ✅ |
| 🟡 | WARN-6 | vams/engine.py | json.dump allow_nan=False 누락 | ✅ |
| 🟡 | WARN-7 | api/config.py | env 파싱 패턴 확산 | ✅ |
| 🟡 | WARN-8 | api/main.py | 모드 전환 시 stale 데이터 잔류 | ✅ |
| 🟡 | WARN-9 | chat.py + watchgroups.py | rate limit 서버리스에서 무효 | ✅ (전역 budget 가드) |
| 🟡 | WARN-10 | 다수 vercel-api | str(e) 원문 노출 | ✅ |
| 🟡 | WARN-11 | search.py | limit ValueError | ✅ |
| 🟡 | WARN-12 | chat.py | 프롬프트 인젝션 방어 부재 | ✅ |
| 🟡 | WARN-13 | order.py | CORS wildcard | ✅ |
| 🟡 | WARN-14 | strategy_evolver.py | 원자적 쓰기·백업 부재 | ✅ |
| 🟡 | WARN-15 | vams/engine.py | VAMS_INITIAL_CASH=0 ZeroDiv | ✅ |
| 🟡 | WARN-16 | periodic_report.py | max_drawdown 정의 오류 | ✅ |
| 🟡 | WARN-17 | workflows | concurrency group 분리로 git race | ✅ |
| 🟡 | WARN-18 | export_trade_daily.yml | trade_analysis race | ✅ |
| 🟡 | WARN-19 | pdf_generator.py | 폰트 download timeout 부재 | ✅ |
| 🟡 | WARN-20 | health.py | 8초 일률 timeout, 재시도 부재 | ✅ |
| 🟡 | WARN-21 | StockDashboard.tsx + StockDetailPanel.tsx | NaN/undefined 렌더 | ✅ |
| 🟡 | WARN-22 | StockDetailPanel.tsx | SSE 영구 끊김 | ✅ |
| 🟡 | WARN-23 | 4개 패널 | stale 경고 부재 | ✅ |
| 🟡 | WARN-24 | fetchPortfolioJson + 인라인 8개 | timeout 부재 | ✅ |
| 🟢 | INFO-1~21 | 다수 | 확인 항목 (수정 불필요) | — |

---

## 5. 적용 vs 미적용 체크리스트

### ✅ 코드 적용 완료 (41건 — CRITICAL 17 + WARNING 24)
모든 CRITICAL 17건, 모든 WARNING 24건이 코드에 반영됨.

### ⚠️ 코드 외 후속 조치 필요 (운영자 수동)
| 항목 | 위치 | 내용 |
|---|---|---|
| 🔴 환경변수 설정 | Vercel/Railway/Actions Secrets | `TELEGRAM_ADMIN_CHAT_IDS` (CRIT-10 fail-closed) — **명시 설정 안 하면 모든 admin 명령 차단됨** |
| 🔴 환경변수 설정 | Vercel | `RAILWAY_SHARED_SECRET`, `ORDER_ALLOWED_ORIGINS` (CRIT-5/WARN-13 운영 모드) |
| 🔴 Supabase SQL | DB 콘솔 | `profiles.order_enabled / max_order_krw / daily_order_count_limit` 컬럼 추가 (CRIT-5/6) |
| 🔴 Supabase SQL | DB 콘솔 | `watch_groups`/`watch_group_items` RLS 정책 활성화 (CRIT-7) |
| 🟡 Railway 서버 | 별도 리포 | `X-Service-Auth` 헤더 검증 + `X-Verity-User-Id` 로깅 (CRIT-5) |
| 🟡 환경변수 | Actions Secrets | `FINNHUB_API_KEY`, `POLYGON_API_KEY`, `SEC_EDGAR_USER_AGENT`, `PERPLEXITY_API_KEY` 정상 주입 확인 (CRIT-13 — 미설정 시 deadman 감시 제외) |
| 🟡 분산 rate limiter | 신규 인프라 | Upstash Redis 도입 권고 (WARN-9 근본 해결, 현재는 인스턴스 로컬 가드) |
| 🟢 Framer 컴포넌트 확장 | 추가 컴포넌트 | `MacroSentimentPanel`, `USEconCalendar` 등 다른 인라인 fetchPortfolioJson 사본도 동일 timeout 적용 권고 (현재 9개만 적용) |
| 🟢 strategy_registry.json | 데이터 | v1 버전에 `pre_change_snapshot` 시드 주입 완료 (이전 세션) |

### 🚫 의도적으로 미적용 (보고만)
| 항목 | 사유 |
|---|---|
| INFO-1~21 (21건) | 확인 항목 — 코드 수정 불필요 |
| TASK 4 fpdf2 데이터 없는 섹션 | None-safe 이미 구현됨 |
| TASK 4 음수 수익률 색상 | 정상 동작 확인 |
| TASK 5 optimistic update 도입 | 현재 server-first 패턴이 정확 (개선 여지는 있으나 버그 아님) |
| 트랜잭션 보장 (constitution+registry 2-phase) | journaling DB 도입 필요, 별도 설계 이슈 |

---

## 종합 검증 결과

- **총 발견 이슈**: 62건 (CRIT 17 / WARN 24 / INFO 21)
- **코드 적용**: 41건 (CRIT 17건 100% + WARN 24건 100%)
- **AST/YAML 파싱**: 모든 수정 파일 clean
- **외부 API 호출**: 0건
- **의존성 체인 정합성**: 검증 완료 (signature 변경된 supabase_client·vams.engine·config 호출부 전부 새 시그니처 사용)

**런칭 전 운영자 수동 조치 필수** (위 후속 조치 표 참조). 특히 `TELEGRAM_ADMIN_CHAT_IDS` 미설정 시 fail-closed 동작으로 `/approve_strategy` 등 전체 차단됨에 유의.

---

## 검수 세션 이력

| 세션 | 대상 | CRIT | WARN | INFO | 적용 |
|---|---|---|---|---|---|
| 1 | verity_brain.py | 2 | 4 | 2 | ✅ 코드 |
| 2 | api/main.py | 2 | 4 | 2 | ✅ 코드 |
| 3 | vercel-api/ | 4 | 5 | 3 | ✅ 코드 |
| 4 | vams + telegram_bot | 3 | 3 | 5 | ✅ 코드 |
| 5 | CI/CD + safety | 3 | 4 | 4 | ✅ 코드 |
| 6 | Framer 컴포넌트 | 3 | 4 | 5 | ✅ 코드 |
| **합계** | | **17** | **24** | **21** | **41/41** |

세션 7은 통합 검증으로 신규 이슈 추가 없음. 모든 발견 사항이 SESSION 1~6에서 처리됨.
