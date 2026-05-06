# P3-4 korea.kr Railway 우회 Contract — P0

**생성일**: 2026-05-06 (4 결함 결정 반영 후 P0 정정 commit)
**위치**: `estate/docs/contract_p3_4_korea_kr_proxy.md` (SystemPulse · LandexPulse 컨벤션 정합)
**다음 단계**: P1 Mock — Railway worker 응답 mock + GH Actions wiring (사용자 OK 후 진입)
**선행 완료**: Prereq 측정 4건 모두 PASS (memory: `project_estate_p3_4_pending`)

---

## 0. 배경 — Prereq 측정 4건 결과

| # | 측정 항목 | 결과 |
|---|---|---|
| 1 | 차단 원인 | **IP 차단 확정**. Vercel egress (US-East AWS, x-vercel-id `iad1`) + GH Actions runner (Azure US) 양쪽 동일 `ConnectionResetError(104)`. UA 무관. [C]2 예외 closure 완료 |
| 2 | Railway capacity | dashboard 캡처 5장 회수 완료 — 가용 |
| 3 | RSS schema | RSS 2.0 + xmlns:dc, 50 items, UTF-8, drift 없음 |
| 4 | cache 헤더 | ETag + Last-Modified 304 검증 통과 |

→ **결론**: Railway (KR/SG/EU 등 non-US egress) 가 korea.kr 차단 우회 유일 경로.

---

## 1. 아키텍처

```
┌─────────────────────────┐    ┌──────────────────────────┐    ┌──────────┐
│ VERITY GH Actions cron  │───▶│ Railway verity_proxy_    │───▶│ korea.kr │
│ KST 09:00 1x/day        │    │ worker (KR/SG egress)    │    │ RSS      │
│                         │◀───│                          │◀───│          │
│ policy_collector.py     │    │ ETag/Last-Modified cache │    └──────────┘
└─────────────────────────┘    └──────────────────────────┘
        │                                  │
        │ verify VERITY alive              │
        ▼                                  ▼
   /api/system/health         RAILWAY_PROXY_KEY (auth)
   (vercel-api)               KOREA_KR_PROXY_KEY (worker→target token)
```

---

## 2. 4 결함 결정 — 본 contract 베이킹

| # | 결정 | 근거 |
|---|---|---|
| 1 | **wrapper 위치 = `api/collectors/policy_collector.py` 수정** (api/estate/ 신설 X) | 기존 collector 패턴 정합 + density-first (memory `feedback_estate_density_first`). policy_collector 는 ESTATE 전용 아닌 generic RSS 수집 — 신설 namespace 불필요 |
| 2 | **cron = GitHub Actions 유지** (Vercel cron 마이그레이션 X) | IP 차단은 cron 위치와 무관 (둘 다 US egress). Railway proxy 가 핵심. 마이그레이션 = 추가 리스크. memory `project_vercel_infra` 의 "vercel-api 통합" 은 API layer 한정 — cron 위치는 직교 차원 |
| 3 | **빈도 = 평일 KST 09:00 1x/day** (1h X) | 24h 정책 평균 0~1건 (기존 측정). 24x 빈도 = 비용·proxy 부하 24배 + 0 증분 가치. P0 의 1h 근거 미명시 = `feedback_source_attribution_discipline` 위반. 검증 후 재조정 |
| 4 | **VERITY health endpoint = `/api/system/health`** (`/health` X) | 직접 ping 검증 완료 (HTTP 200, 0.92s). vercel.json rewrite 룰: `/api/system/health` → `api/system_health.py`. 단순 `/health` 는 실재하지 않음 |

---

## 3. 컴포넌트 명세

### 3.1 Railway `verity_proxy_worker` (신설)

**역할**: korea.kr RSS fetch + ETag cache + 인증 게이트

**입력 (HTTP)**:
```
GET /proxy/korea_kr/policy_rss?since=<iso>
Headers:
  Authorization: Bearer <RAILWAY_PROXY_KEY>
```

**처리**:
1. Auth check — `RAILWAY_PROXY_KEY` 일치 → 401 시 즉시 reject
2. ETag/Last-Modified 캐시 hit → 304 즉시 반환 (cost 절감)
3. korea.kr fetch (UA: Railway 기본 + `KOREA_KR_PROXY_KEY` 헤더 — target 측 식별용)
4. RSS 50 items 파싱 → JSON 변환
5. since 필터 적용 → 신규 items 배열만 반환

**출력**:
```json
{
  "fetched_at": "2026-05-06T09:00:12+09:00",
  "egress_region": "kr-1",
  "etag": "...",
  "items": [
    {
      "guid": "...",
      "pub_date": "2026-05-06T...",
      "title": "...",
      "category": "...",
      "summary": "..."
    }
  ]
}
```

**Health endpoint** (운영자용):
```
GET /health
→ { "status": "ok", "egress_region": "kr-1", "last_fetch_at": "..." }
```

### 3.2 VERITY 측 `api/collectors/policy_collector.py` 수정

**현 상태**: korea.kr 직접 호출 (line 84) — IP 차단으로 항상 실패.

**수정**: env `KOREA_KR_VIA_RAILWAY=true` 시 Railway worker 호출 path 로 분기.

```python
if os.environ.get("KOREA_KR_VIA_RAILWAY") == "true":
    return _fetch_via_railway()
else:
    return _fetch_direct()  # 기존 — 로컬 dev 시
```

`_fetch_via_railway()`:
- env `RAILWAY_PROXY_URL` + `RAILWAY_PROXY_KEY` 사용
- timeout 30s
- 응답 파싱 → 기존 RSS items schema 정합 (downstream 변경 0)
- 실패 시 stderr `logged=True` 명시 + raise (memory `feedback_data_collection_verification_mandatory`)

### 3.3 GitHub Actions cron

**현 위치**: 기존 policy collect workflow (이름 확인 후 명시 — `.github/workflows/policy_*.yml`)

**수정 (decision 2 정합)**:
```yaml
schedule:
  - cron: '0 0 * * 1-5'  # KST 09:00 평일 1x/day (UTC 00:00)
env:
  KOREA_KR_VIA_RAILWAY: "true"
  RAILWAY_PROXY_URL: ${{ secrets.RAILWAY_PROXY_URL }}
  RAILWAY_PROXY_KEY: ${{ secrets.RAILWAY_PROXY_KEY }}
  KOREA_KR_PROXY_KEY: ${{ secrets.KOREA_KR_PROXY_KEY }}
```

### 3.4 SystemPulse `korea_kr_worker` 카드 정합

`estate_health.py:31` — 현재 `status="blocked"` 영구 박힘. P3-4 완료 후 해제:
- worker `/health` ping → `last_fetch_at < 24h` AND `egress_region != null` → `status="healthy"`
- 실패 → `status="degraded"` (blocked 해제, 일반 톤)

memory `project_estate_p3_4_pending` 의 `degraded` trigger 사전 승인 적용.

---

## 4. P1 Mock 범위 (다음 단계)

| 항목 | 내용 |
|---|---|
| Railway worker | 빈 Railway 프로젝트 + `/proxy/korea_kr/policy_rss` mock 응답 (3 items 고정) + `/health` |
| GH Actions | `KOREA_KR_VIA_RAILWAY=true` 분기 wiring + dry-run cron 1회 |
| policy_collector | `_fetch_via_railway()` 추가 + downstream schema 정합 검증 |
| SystemPulse | `korea_kr_worker` mock 응답 healthy/degraded 시나리오 추가 |

**P1 통과 조건**: GH Actions cron 1회 실행 → Railway mock 응답 수령 → policy_collector downstream 무변경 → SystemPulse 셀 healthy 표시.

P1 통과 후 P2 (실제 Railway worker 코드 + korea.kr 실호출) 진입.

---

## 5. 사전 승인 사항 (memory 기존 — 유효)

- ✅ SystemPulse `degraded` trigger.type 추가
- ✅ `RAILWAY_PROXY_KEY` / `KOREA_KR_PROXY_KEY` 32-byte hex 양쪽 env 등록
- ✅ VERITY `/api/system/health` 존재 검증 (path 정정 후 PASS)

추가 사전 승인 필요 항목 — **없음**. P1 Mock 즉시 진입 가능.

---

## 6. References

- memory `project_estate_p3_4_pending` (중단점 + 4 결함)
- memory `feedback_estate_density_first` (네임스페이스 결정 1)
- memory `feedback_source_attribution_discipline` (빈도 결정 3)
- memory `feedback_data_collection_verification_mandatory` (실패 시 logged=True)
- `estate/docs/contract_system_pulse.md` (네임스페이스 표준 v1.1)
- 측정 closure commits: `b923801`, `249886d`, `225428c`, `ef1dc64` ([temp-probe] prefix)
