# Vercel 재배포 전 환경변수 체크리스트

2026-04-23 Railway + Vercel 양쪽 fail-closed 전환 이후 반드시 설정해야 할 Vercel
환경변수 목록. 누락 시 `/api/order` 는 503 반환 (정상 동작 — fail-safe 목적).

> **2026-05-04 갱신**: 옛 후보 도메인(`verity.ai`, `kim-hyojun.github.io`) 폐기.
> 운영 도메인은 `https://verity-terminal.framer.website` 단일.
> Railway 측 CORS env 이름은 `ALLOWED_ORIGINS` (Vercel `ORDER_ALLOWED_ORIGINS`
> 와 다름 — `server/config.py:32` 참조). 같은 이름 가정해서 Railway 에 잘못
> 등록하면 죽은 env 가 됨.

## 🔴 필수 (Production)

| Key | Value | 설명 |
|---|---|---|
| `RAILWAY_SHARED_SECRET` | (Railway와 동일한 임의 secret) | Vercel → Railway 서버 간 공유 비밀. 미설정 시 Vercel order.py 가 503 반환. Railway 측 동일 변수 일치 필요 |
| `ORDER_ALLOWED_ORIGINS` | `https://verity-terminal.framer.website` | (Vercel 측만) CORS 허용 origin. wildcard (`*`) 는 값으로 넣어도 자동 제거됨. 커스텀 도메인 추가 시 콤마 구분 |

## 🟡 Chat Hybrid 활성화 (원할 때)

| Key | Value | 설명 |
|---|---|---|
| `CHAT_HYBRID_ENABLED` | `true` | false 유지 시 기존 Gemini 단일 경로 |
| `CHAT_HYBRID_SYNTH_MODEL` | `claude-sonnet-4-6` | 합성 모델 (선택, 기본값 동일) |
| `CHAT_HYBRID_CLASSIFIER_MODEL` | `gemini-2.5-flash-lite` | 분류기 모델 (선택) |
| `CHAT_HYBRID_GROUNDING_MODEL` | `gemini-2.5-flash-lite` | Grounding (선택) |
| `CHAT_HYBRID_DAILY_CAP` | `500` | 일일 요청 상한 (비용 보호, 선택) |

## 🟢 선택 (한도·검증용 — 이미 기본값 있음)

| Key | Default | 설명 |
|---|---|---|
| `ORDER_MAX_QTY` | 10000 | 단일 주문 최대 수량 |
| `ORDER_MAX_PRICE_KRW` | 100_000_000 | 단일 주문 최대 가격 |
| `ORDER_MAX_VALUE_KRW` | 10_000_000 | 단일 주문 최대 금액 |
| `ORDER_DAILY_COUNT_LIMIT` | 50 | 사용자별 일일 주문 횟수 |
| `RAILWAY_URL` | `https://verity-production-1e44.up.railway.app` | Railway 엔드포인트 |

## 재배포 순서

1. Vercel Dashboard → Project Settings → Environment Variables
2. 위 **🔴 필수 2개** 먼저 추가 (Production + Preview)
3. (선택) **🟡 Chat Hybrid** 묶음 추가
4. Save → 자동 재배포 트리거 또는 `npx vercel deploy --prod --yes` 수동

## 설정 검증

재배포 후 즉시 확인:

```bash
# 1. 인증 없는 요청 → 503 (secret 없음) 또는 401 (secret 있음)
curl -i -X GET "https://<vercel-domain>/api/order?market=kr"
# 기대: 503 Service Unavailable 또는 401 Unauthorized

# 2. CORS preflight — 허용 origin
curl -i -X OPTIONS "https://<vercel-domain>/api/order" \
  -H "Origin: https://verity-terminal.framer.website"
# 기대: Access-Control-Allow-Origin: https://verity-terminal.framer.website

# 3. CORS preflight — 거부 origin
curl -i -X OPTIONS "https://<vercel-domain>/api/order" \
  -H "Origin: https://evil.example.com"
# 기대: Access-Control-Allow-Origin 헤더 없음 → 브라우저 차단
```

## 문제 발생 시

**모든 주문 요청이 503 을 반환하는 경우**:
- Vercel env 에 `RAILWAY_SHARED_SECRET` 누락. 대시보드에서 설정 후 재배포.

**CORS 차단으로 Framer 에서 주문 안 되는 경우**:
- `ORDER_ALLOWED_ORIGINS` 에 Framer 게시 도메인 누락. 추가 후 재배포.

**Railway 쪽도 503 을 반환하는 경우**:
- Railway 대시보드에도 `RAILWAY_SHARED_SECRET` 동일 값 설정 필요. 두 서비스의 값이 반드시 일치.

---

## 보안 원칙

- Secret 값은 **Railway ↔ Vercel 양쪽에 동일 값** 으로 설정. 값 자체는 무작위 32바이트 권장.
- Secret 은 GitHub·Notion·Slack 에 절대 복붙 금지. 1Password 등 시크릿 매니저 사용.
- rotation 필요 시 Vercel 먼저 → Railway 순으로 (역순은 일시 403 유발 가능). rotation 중에는 킬스위치 고려.
