# Audit Sprint #2 — 운영 결함 sweep

**일자**: 2026-05-12
**범위**: 운영 결함 (silent skip / race / cron 누락 / dedupe / dispatch chain / token / commit-push)
**산출**: 결함 list + fix 분류 (즉시 / 5/17 sprint queue)
**컨텍스트**: 5/17 ATR verdict + VAMS reset = evolution sprint 시작점. 그 전 fresh baseline 확립.

---

## 결함 요약

| # | Risk | Axis | File:Line | 결함 | Fix 분류 |
|---|---|---|---|---|---|
| 1 | **HIGH** | 1 (workflow) | `.github/workflows/daily_realtime.yml:8~45` | GH schedule 16+ 라인 + repository_dispatch 동시 활성. `project_dispatch_chain.md` 폐기 결정 미이행 | **즉시** |
| 2 | MED | 3 (token) | `.github/workflows/kis_token_refresh.yml:7~11` | schedule 주석화 → 자정 자동 갱신 불가, 만료 시 수동 trigger 필요 | 5/17 queue |
| 3 | MED | 4 (silent skip) | `api/collectors/eps_estimate_snapshot.py:61~63, 113~114, 129` | `except Exception` 후 None/{} return — 로깅 누락 | 5/17 queue |
| 4 | MED | 4 (silent skip) | `api/collectors/market_flow.py` | `except → 0 반환` — 실패/제로 데이터 구분 불가 | 5/17 queue |
| 5 | LOW | 6 (publish-data) | `.github/actions/publish-data/action.yml:12` | staged 파일 11개 하드코드, 신규 파일 추가 시 수정 의무 | 영속 룰 (관찰) |

**총 결함**: 5건 (HIGH 1, MED 3, LOW 1)

---

## 검사 축별 상세

### Axis 1 — GH Actions workflow 정합성 (HIGH 1건)

**[HIGH] `.github/workflows/daily_realtime.yml:8~45`**

GH `schedule:` 라인 16+ + `repository_dispatch: types: [daily_realtime]` 동시 활성. dispatch_pulse는 `minute % 30 == 0` 으로 30분당 1회 발화하지만 GH schedule 라인이 다른 시각들에 추가 발화:

- KR 개장 러시: `0,5,10,15,20,25 0 * * 1-5` → 5분 간격 6회
- KR 장중: `*/15 1-5 * * 1-5` → 15분 간격
- KR 종가 러시: `0,5,10,15,20,25,30,35,40 6 * * 1-5` → 5분 간격 9회
- 미장: 다수 5분/30분 간격

결과: 의도(`30분당 1회`) vs 실제(`5~30분 다양`). 5/12 새벽 KIS 4 토큰 race 재발 위험 잔존.

**Fix**: `schedule:` 블록 전체 제거. `repository_dispatch` + `workflow_dispatch` 만 유지. `project_dispatch_chain.md` 결정 이행 + `project_dispatch_chain_hotfix_2026_05_12` 30분 룰 정합.

**검사 완료, 결함 0인 항목**:
- price_pulse.yml: schedule 폐기 완료, dispatch only ✓
- hourly_pulse.yml: 신규, schedule 없음 ✓
- 다른 workflow의 concurrency group 충돌: 없음
- timeout 누락: 없음 (모두 5~30분 명시)

---

### Axis 2 — dispatch_chain 정합성 (결함 0)

dispatch_pulse.py 발화 events vs workflow `repository_dispatch types` 매칭:

| event | dispatcher | receiver | 정합 |
|---|---|---|---|
| price_pulse | 매분 | price_pulse.yml | ✓ |
| daily_realtime | minute % 30 == 0 | daily_realtime.yml | ✓ (단 Axis 1 결함) |
| daily_analysis_quick | minute == 7 | daily_analysis.yml | ✓ |
| reports_v2 | UTC 13:07 | reports_v2.yml | ✓ |
| hourly_pulse | slot 매처 | hourly_pulse.yml (신규) | ✓ |

dispatch chain logic 자체는 정상.

---

### Axis 3 — Token 인증 정책 (MED 1건)

**[MED] `.github/workflows/kis_token_refresh.yml:7~11`**

schedule 라인 주석 처리됨 (폐기 상태) → workflow_dispatch only. 자정 자동 토큰 갱신 불가. 만료 시 수동 trigger 필요. `project_kis_token_policy` (6h 갱신 / 24h 만료) 준수 위태.

영향:
- price_pulse 매분 호출 시 자정 직후 token expired (cache miss) 가능
- 5/12 dispatch_chain hotfix 후 daily_realtime 30분 분리로 완화되었으나 token refresh 자체 자동화 미복구

**Fix**: schedule 복구 (KST 06:00 / 12:00 / 18:00 / 00:00 4회 또는 12h 1회). 5/17 VAMS reset 전 검증 의무.

**다른 토큰 정책 검사**:
- `broker.authenticate(force_refresh=False)` 일관 사용 ✓
- 토큰 캐시 `~/.cache/verity_kis_token.json` 일관 ✓
- KIS_APP_KEY/SECRET secrets 매핑 ✓

---

### Axis 4 — silent skip / try-except 결함 (MED 2건)

**[MED] `api/collectors/eps_estimate_snapshot.py:61~63, 113~114, 129`**

3개 `except Exception` + `return {} / return None / pass`. `feedback_data_collection_verification_mandatory` 정합 위반 (try/finally + logged=True stderr 누락).

**[MED] `api/collectors/market_flow.py`**

`except Exception: return {"foreign_net": 0, ...}` 패턴. 실패 / 진짜 0 구분 불가 → 시장 신호 일부 손실.

**Fix**: 둘 다 outcome field 추가 (`status: "ok"|"fail"`) + stderr 명시 + logged=True. 다만 5/17 sprint 부담 큼 → queue.

**검사 완료, 결함 없는 영역**:
- `api/cron/price_pulse.py`: try/except OK (실패 시 None 반환 + stderr)
- `api/notifications/telegram.py`: 5/12 영속 dedupe 신규 코드 logged=True 정합 ✓
- `api/collectors/` 다른 모듈 (대부분): logged 정합

---

### Axis 5 — race / dedupe 결함 (결함 0)

- concurrency group `verity-data-write` 11 워크플로 공유 직렬화 정상
- `verity-price-pulse` / `verity-realtime` / `verity-hourly-pulse` 분리 ✓
- 5/12 신규 `data/telegram_dedupe_global.json` 영속 dedupe 정상 동작
- publish-data action `force_orphan` 가드 (5/7 fix `4a8111e`) 정상

---

### Axis 6 — commit / push (LOW 1건)

**[LOW] `.github/actions/publish-data/action.yml:12`**

staged 파일 11개 하드코드. 신규 builder snapshot 추가 시 action 수정 의무. `feedback_publish_data_file_list_audit` 영속 룰 잔존.

**Fix**: 영속적 — 신규 파일 추가 때마다 audit. 자동화 불가능 (의도된 명시).

---

## Fix 분류

### 즉시 (5/12~5/13)
- **HIGH 1**: daily_realtime.yml schedule 폐기 — 자정 race 재발 차단

### 5/17 sprint queue
- **MED 2**: kis_token_refresh.yml schedule 복구 (VAMS reset 전 검증)
- **MED 3**: eps_estimate_snapshot.py silent skip 정리
- **MED 4**: market_flow.py outcome field 추가

### 영속 관찰
- **LOW 5**: publish-data staged list 영속 룰 (자동화 불가, 메모리 룰 준수만)

---

## 다음 갈래 (5/13)

Axis #5 데이터 무결성 — 수집 silent skip 깊이 검사 (Axis 4와 일부 중첩 — 깊이 다름 / 본 audit은 try-except 패턴, 5/13은 수집기 산출 데이터 staleness/schema).
