# KIS 단일 발급원 cutover 런북 (2026-05-31)

## 사고

KIS 사용자 알림 2건 = 실 발급 2회 (RULE 1 위반, 계좌 제재 위험).

**발급원이 둘, 서로 독립:**
- **GH Actions** — `api/trading/kis_broker.py`, file lock(`data/.kis_issued_date.txt`) 24h 가드. 정책 정합.
- **Railway 상주 서버** — `server/kis_rest_client.py`, `/tmp` cache + **6h** 가드. file lock 안 읽음.
  - `/tmp` 는 재배포/재시작마다 초기화 → stale cache 사라짐 → 6h 가드 무력 → **재시작마다 신규 발급**.

근본: 라이브 토큰이 필요한 subsystem 이 2개인데 토큰 **값** 공유 저장소가 없었음. lock 파일은 timestamp 만 — 토큰 값이 없어 타 subsystem 재사용 불가 → 각자 발급 → 하루 2토큰+.

## 결정 (PM 2026-05-31)

**GH Actions = 단일 발급원.** (1차로 Railway 후보였으나 PM 재질문 후 GH 로 변경.)

GH 채택 이유:
1. **가용성 결합 안전 방향** — ephemeral GH 스케줄 작업이 가변 uptime 의 Railway 에 의존하지 않음. always-on 소비자(Railway)가 store 를 아무 때나 read.
2. **관측성 + 기존 RULE 1 인프라 재사용** — file lock 트레일 + `cron_health_monitor` lock-commit proxy 그대로 유효 (GH 가 계속 발급+commit). proxy 재작성 불필요.
3. **보수성** — 6+ 사고로 단련된 file-lock 경로 최대 재사용 (1인/N<365).
4. server/main.py "Railway 상주 토큰 사용" 주석은 **보유 ≠ 발급** — store 에서 read 한 토큰을 보유해도 충족.

동작: GH 가 기존 file-lock 24h 가드로 1일 1발급 → 발급 직후 Supabase `kis_shared_token` 에 토큰 **값** publish → Railway/Vercel 은 service_role 읽기 소비 (자체 발급 금지).

## 구현 (이 커밋)

- `supabase/migrations/017_kis_shared_token.sql` — 단일행 테이블 + RLS service_role only (anon 접근 0).
- `api/trading/kis_broker.py` — 발급 직후 `_kis_publish_shared_token()` (KIS_SHARED_TOKEN=1 일 때). 발급 로직/file lock 무변경.
- `server/kis_rest_client.py` — KIS_SHARED_TOKEN=1 시 **순수 소비자** (Supabase read-only, 발급 금지, 없으면 RuntimeError → `_get/_post` graceful {}). flag off = legacy 자체 발급(6h→24h 정정).
- `tests/test_kis_token_one_per_day.py` — publish 호출 + flag-off 무변경 케이스 (5 passed).

모든 신규 동작은 `KIS_SHARED_TOKEN` 플래그 gate. **기본 off = 무변경 (안전 롤백).**

## 단계적 cutover (각 단계 RULE 8 N=2 audit)

### Step 0 — Supabase 마이그레이션
Supabase SQL Editor 에서 `017_kis_shared_token.sql` 실행. 확인:
```sql
select id, issued_at, expires_at, app_key_fp, updated_at from public.kis_shared_token;  -- 빈 테이블 OK
```

### Stage A — GH 발급 publish 활성 + store seed
✅ 워크플로 4개 (`kis_token_refresh` / `daily_analysis` / `daily_analysis_full` / `daily_realtime`) 에
`KIS_SHARED_TOKEN: "1"` (workflow-level env) + preflight/refresh step 에 `SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY`
**이미 이 커밋에 포함됨.** merge 후 다음 GH 발급부터 자동 publish (migration 적용 전엔 publish 가 404 → try/except 무해).
- seed: Step 0 적용 후 `kis_token_refresh.yml` 을 다음 발급일 또는 수동(`data/.kis_issued_date.txt` 삭제 후 dispatch)로 1회 발급 → Supabase row 1개 생성 확인.
- 이 단계는 Railway 무관 (additive). 아직 Railway 도 자체 발급 → 하루 2토큰 유지 (회귀 아님).

### Stage B — Railway 순수 소비자 활성 (← 여기서 2→1)
Railway env 추가: `KIS_SHARED_TOKEN=1`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`. 재배포.
- 검증 1 (N=1): Railway 첫 KIS 호출 로그 `KIS REST 공유 store 소비 (GH 발급분)`. 자체 발급 0.
- 검증 2 (N=2): **Railway 강제 재시작** → 발급 0 (store read 만). KIS 사용자 알림 0. → **하루 1토큰 확정.**
- store 가 비어있는 순간(GH 미발급) Railway 호출 = 토큰 없음 → 차트/실시간 빈 응답. Stage A seed 후 진입하면 회피.

### 롤백
어느 단계든 해당 subsystem 의 `KIS_SHARED_TOKEN` env 제거 → 즉시 기존 동작 복귀 (코드 그대로).

## 미완 (cutover 실행 — 사용자 수동, 코드/yml 는 커밋 완료)
- [x] 코드 + yml + env(`KIS_SHARED_TOKEN`/SUPABASE) — 이 커밋
- [ ] Step 0: Supabase SQL Editor 에서 migration 017 적용
- [ ] Stage A: (yml 이미 반영) Step 0 후 `kis_token_refresh` 1회 발급 → Supabase row seed 확인
- [ ] Stage B: Railway 대시보드 env 3종(`KIS_SHARED_TOKEN=1`/`SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY`) + 재배포 + N=2 (재시작 후 발급 0)

## 변경 없음 (GH 발급 유지 효과)
- `cron_health_monitor` lock-commit proxy — GH 가 계속 발급+commit → 그대로 유효. 재작성 불필요.
- `kis_token_refresh.yml` 발급 로직 — 그대로 (publish 만 broker 내부에서 추가됨).
