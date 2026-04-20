# KIS 토큰 중복 발급 방지 — GitHub Secret 경유 설정

## 배경
KIS OpenAPI 는 하루 1회 토큰 발급이 원칙이지만 GitHub Actions 의 cache 동기화
지연 + cron 분산 실행으로 실제로는 하루 2~3회 발급되는 경우 발생.

**해결**: `kis_token_refresh.yml` 이 자정 1회 발급 → GitHub Secret 으로 업데이트 →
다른 workflow 는 env 경유로 즉시 사용 (API 호출 0회).

## 설정 단계 (사용자 수동 작업)

### 1. Personal Access Token (PAT) 발급
1. GitHub → Settings → Developer settings → Personal access tokens →
   **Tokens (classic)** → Generate new token (classic)
2. 권한 설정:
   - `repo` (full) — private repo 면 필수
   - 또는 `public_repo` — public repo 면 충분
3. Expiration: 90 days 이상 권장 (만료 시 재발급)
4. 발급된 토큰 문자열 복사 (한 번만 표시됨)

### 2. Repo Secret 에 PAT 등록
1. repo → Settings → Secrets and variables → Actions → **New repository secret**
2. Name: `REPO_SECRET_PAT`
3. Value: 1단계에서 발급받은 PAT 문자열
4. Add secret

### 3. 첫 자동 갱신 대기 (또는 수동 trigger)
- 자동: 매일 KST 00:05 `kis_token_refresh` workflow 실행 시 Secret 업데이트
- 수동: Actions 탭 → KIS Token Refresh → Run workflow

### 4. 확인
Actions 탭에서 `kis_token_refresh` 최근 실행 → "GitHub Secret 업데이트" step
로그에 "✓ KIS_ACCESS_TOKEN / KIS_ACCESS_TOKEN_EXPIRES Secret 갱신 완료"
메시지 출력되면 성공.

Repo Settings → Secrets 에 `KIS_ACCESS_TOKEN`, `KIS_ACCESS_TOKEN_EXPIRES`
두 항목이 보이면 정상.

## 작동 원리
```
[매일 KST 00:05]
  kis_token_refresh workflow 실행
    ├─ KIS OpenAPI 로 토큰 발급 (1회)
    ├─ ~/.cache/verity_kis_token.json 저장 (cache 용)
    └─ gh secret set KIS_ACCESS_TOKEN / EXPIRES  ← 여기서 갱신

[이후 모든 workflow 실행]
  daily_analysis / daily_analysis_full
    └─ env: KIS_ACCESS_TOKEN, KIS_ACCESS_TOKEN_EXPIRES 주입됨
    └─ KISBroker.__init__() → _load_env_token() 먼저 시도
       └─ env 값 있고 미만료면 그대로 사용 (API 호출 0회)
```

## PAT 미설정 시
- `kis_token_refresh` 의 "GitHub Secret 업데이트" step 이 skip
- 기존 방식 (disk cache) 로 폴백 — 중복 발급 가능성 남음
- 기능상 동작에는 문제 없음

## 보안
- PAT 는 Secret 에만 저장, 코드/로그에 노출 안 됨
- KIS_ACCESS_TOKEN 도 Secret (암호화 보관)
- 토큰 만료 시 자동 재발급 + Secret 재갱신 → 유출 영향 최대 24h
