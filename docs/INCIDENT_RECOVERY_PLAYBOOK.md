# 장애 복구 플레이북

직업군인 본업으로 24/7 대응 불가. 당황할 상황을 미리 정리해둔 1페이지.
상황별 **1~2줄 복구 절차**만. 심화 원인 분석은 사후.

---

## 0. 판단 플로우 (30초)

```
장애 감지 → [자동매매 실행 중?]
             ├─ YES → ★ 즉시 킬스위치 ON (아래 §1)
             └─ NO  → §2 로 이동
```

**자동매매가 돌고 있는 상황에서 뭔가 이상하면, 원인 파악 전에 킬스위치부터.** 잘못 멈추는 비용 < 잘못 체결되는 비용.

---

## 1. 긴급 킬스위치 (실자금 관련)

### 즉시 중단
```bash
# 로컬에서 (SSH 접근 가능 시)
touch "/Users/macbookpro/Desktop/배리티 터미널/data/.auto_trade_paused"

# 또는 GitHub 웹에서 파일 직접 생성 (data/.auto_trade_paused 빈 파일)
# → 다음 파이프라인 사이클부터 모든 주문 차단
```
- 파일 **존재 자체**가 킬스위치. 내용 무관.
- `apply_safety_limits` 가 파일 감지 즉시 전 주문 blocks 처리.

### 재개
```bash
rm "/Users/macbookpro/Desktop/배리티 터미널/data/.auto_trade_paused"
```
- 다음 사이클부터 정상 복귀.

### 더 강한 차단 (마스터 스위치)
GitHub Actions Variables에서:
```
AUTO_TRADE_ENABLED=false
```
- 이건 `run_auto_trade_cycle` 자체가 no-op 반환. 코드 경로 진입 안 함.

---

## 2. portfolio.json 손상

### 증상
- `[load_portfolio] portfolio.json 파싱 실패`
- 또는 VAMS 수치 0/빈 배열로 급변

### 자동 복구
`api/vams/engine.py:load_portfolio` 가 자동으로 시도:
1. `portfolio.json` 파싱 → 실패
2. `portfolio.json.bak` 파싱 → 이게 살아있으면 복구 후 진행
3. 둘 다 깨지면 **RuntimeError 로 중단** (빈 dict 로 덮어쓰지 않음 — 실측 사고 방지)

### 수동 복구
```bash
# .bak 살아있는지 확인
ls -la "data/portfolio.json"*

# .bak 가 있으면 수동으로 복사
cp "data/portfolio.json.bak" "data/portfolio.json"

# 둘 다 깨졌으면 git 에서 복원
git log --oneline -5 data/portfolio.json
git checkout <commit> -- data/portfolio.json
```

⚠️ **절대 금지**: `rm data/portfolio.json` + 새 사이클 실행 — VAMS 누적 이력 증발.

---

## 3. history.json 손상

### 증상
- `load_history` 가 빈 리스트 반환 (auto_trader 는 이 경우 안전하게 계속 진행)
- 또는 `compute_adjusted_return` 이 실현 매도 0 으로 표시

### 복구
```bash
# 백업 확인
ls -la "data/history.json"*     # .bak 있으면 복원

# .bak 도 없으면 git 이력에서
git checkout HEAD~1 -- data/history.json
```

⚠️ `auto_trade_history.json` 과 `history.json` 은 **다른 파일** (전자: 실거래, 후자: VAMS 가상매매). 혼동 주의.

---

## 4. KIS API 오류

### 토큰 만료 / 403
- 증상: `auto_trader` FAILED 기록, 메시지에 "invalid_client" 또는 "401/403"
- 조치:
  1. 2026-04-21 rotate 이후 **3곳 모두** 키 동기화됐는지 확인 (GitHub Actions · Vercel · Railway)
  2. `.env.example` 주석의 rotate 가이드 참조
  3. KIS 개발자센터에서 토큰 상태 확인

### 네트워크 타임아웃
- 증상: `auto_trader_safety` 테스트 시나리오 #3 과 동일 — FAILED 기록 + 잔고 불변
- 조치: 로그만 확인. 다음 사이클 자동 재시도. **수동 개입 불필요**.

### 실거래 모드에서 의심스러운 체결
1. 킬스위치 ON (§1)
2. KIS HTS/MTS 직접 접속해서 실계좌 상태 확인
3. `data/auto_trade_history.json` 과 실계좌 체결 내역 대조
4. 불일치 발견 시 VERITY 측 history 를 실계좌 기준으로 수정 후 킬스위치 해제

---

## 5. pykrx / yfinance / 외부 데이터 장애

### 증상
- 수집 단계에서 빈 데이터 또는 stale 경고
- `main.py` 가 해당 스텝 스킵하고 진행

### 조치
대부분 자가 회복. 관망:
- pykrx: KRX 페이지 스키마 변경 시 주기적으로 발생. 1~2일 내 pypi 업데이트 대기.
- yfinance: Yahoo rate limit 걸릴 때 있음. quick/full 사이클 분리 실행.
- FRED / DART / SEC: 대체로 안정적. 키 만료만 주의.

**임시 우회**: 특정 수집기만 끄려면 `safe_collect` 래퍼가 이미 예외 캡슐화. 별도 조치 불필요.

---

## 6. Supabase Down

### 증상
- Framer 인증 실패 / 관심종목 그룹 로드 실패
- `watchgroups.py` API 500 반환

### 조치
- VAMS 본체는 **Supabase 독립**. 데이터 수집/판정/백엔드는 영향 없음.
- Framer UI 만 일부 기능 저하. 본인 외 접근자 없으니 대기가 답.
- 복구 후 자동 재연결.

---

## 7. LLM API 쿼터 초과

### Gemini / Claude / Perplexity
- 증상: `[gemini]` / `[claude]` 호출이 `ResourceExhausted` 또는 429 반환
- 조치:
  - 파이프라인은 **LLM 실패해도 정량 분석은 완료**. 수치 지표는 정상 발행.
  - 다음 리셋 주기(일별/월별)까지 LLM 서술만 공란. 판정·매매 로직 영향 없음.
  - VERITY_MODE=dev 로 임시 전환하면 mock 응답 (0원).

```bash
# GitHub Actions Variables
VERITY_MODE=dev              # LLM mock
VERITY_STAGING_REAL_KEYS=    # 전부 mock
```

---

## 8. Vercel 호출 한도 초과

### 증상
- Framer 실시간 차트·검색·chat 500/404
- `vercel-api/` 배포 불가

### 조치
- 이미 무료 한도 소진 상태 (현재 기본 상태).
- VAMS·검증·배당 수집은 **Vercel 독립**. 영향 없음.
- 다음 달 리셋까지 Framer 실시간 기능만 대기.
- 리셋 후 `vercel-api/api/*.py` 응답에 `Cache-Control: s-maxage=300` 추가 검토 (한도 절약).

---

## 9. GitHub Actions 실패 (파이프라인 전면 정지)

### 증상
- Actions 탭에서 매일 16:00 KST job 이 연속 실패
- `portfolio.json` 가 더 이상 업데이트 안 됨

### 조치
1. Actions 탭에서 실패 job 로그 확인
2. 가장 흔한 원인:
   - **Secrets 만료**: GEMINI_API_KEY, KIS_APP_KEY 등
   - **requirements.txt 버전 충돌**: Python 3.11 러너에서 패키지 설치 실패
   - **pykrx KRX 스키마 변경**: 재시도 또는 pypi 업데이트 대기
3. 수동 재실행: Actions 탭 → `Run workflow`

**임시 로컬 실행** (장기 장애 시):
```bash
cd "/Users/macbookpro/Desktop/배리티 터미널"
python3 api/main.py
```
- 로컬 환경변수에 필요한 키만 세팅.
- 결과 `data/portfolio.json` 수동 git push.

---

## 10. 배당 수집 오작동

### 증상
- `dividends_kr.json` 이 비어 있거나, 특정 보유 종목 누락
- VAMS DIVIDEND 이벤트가 예상 시점에 발생하지 않음

### 원인별 조치
| 원인 | 증상 | 조치 |
|---|---|---|
| DART_API_KEY 없음 | `tier1 dart 실패` 로그 | .env 또는 Actions secrets 에 키 확인 |
| sweep 미실행 | DB 비어있음 | 다음 월요일/1·7월 15일 기다리거나 수동 실행 |
| 추정 ex_date 오차 | 실제 배당락 ±며칠 | Phase 2 과제. 현재는 공식 ex_date 수집 미구현 |

### 수동 sweep
```bash
python3 -c "
from api.collectors.dividend_kr import sweep_annual_plans
tickers = ['005930', '000660', '035420']  # 본인 보유 종목
print(sweep_annual_plans(tickers))
"
```

---

## 11. 긴급 연락처 (참고용)

- **KIS 개발자센터**: https://apiportal.koreainvestment.com
- **KRX Data Marketplace**: https://openapi.krx.co.kr
- **DART Open API**: https://opendart.fss.or.kr
- **GitHub Status**: https://www.githubstatus.com

---

## 일일 체크 (여유 있을 때)

```bash
# 1분 안에 끝나는 헬스체크
cd "/Users/macbookpro/Desktop/배리티 터미널"
python3 api/health.py 2>&1 | tail -20

# portfolio 신선도
python3 -c "
import json, datetime as dt
p = json.load(open('data/portfolio.json'))
print('updated_at:', p.get('updated_at'))
print('holdings:', len(p.get('vams', {}).get('holdings', [])))
print('validation:', p.get('vams', {}).get('validation_report', {}).get('overall'))
"
```

---

**원칙**: 의심스러우면 **킬스위치 먼저**. 원인 파악은 그 다음.
