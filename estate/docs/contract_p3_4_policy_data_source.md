# P3-4 정책 데이터 출처 Contract — P0 (v2)

**생성일**: 2026-05-06 (v1 = Railway proxy 가정, v2 정정)
**v1 폐기 사유**: EU West Railway 도 korea.kr 차단 측정 결과 (HTTP 502 ConnectionReset, 2026-05-06 13:18 UTC)
**v2 출처**: data.go.kr **정책브리핑 정책뉴스/보도자료 OpenAPI** — 정공법
**위치**: `estate/docs/contract_p3_4_policy_data_source.md`
**다음 단계**: API propagation 후 P1 — `policy_collector.py` 단일 모듈 swap

---

## 0. 측정 결과 — 직접 RSS 차단 확정

| egress | 결과 |
|---|---|
| Vercel iad1 (US-East AWS) | ConnectionResetError(104) |
| GitHub Actions runner (Azure US) | ConnectionResetError(104) |
| Railway EU West (Amsterdam) | **ConnectionResetError(104)** ← 신규 측정 |

→ korea.kr 가 **datacenter ASN 기반 차단** (geography 무관, 클라우드 IP 자체 차단). Railway 다른 region 시도 자체가 도박. **정공법 = 정식 OpenAPI 채널.**

---

## 1. 채택 출처 — data.go.kr 1371000 (문화체육관광부)

문화체육관광부가 정책브리핑(korea.kr) 운영주체. 동일 데이터 정식 API 노출.

| API | data.go.kr ID | endpoint | 용도 |
|---|---|---|---|
| **정책뉴스** | 15095335 | `http://apis.data.go.kr/1371000/policyNewsService/policyNewsList` | 전부처 정책뉴스 통합 (부처 필드로 filter) |
| **보도자료** | 15095295 | `http://apis.data.go.kr/1371000/pressReleaseService/pressReleaseList` | 부처별 보도자료 (`dept_molit.xml` 1:1 정합) |

**핵심 결정**: 보도자료 API 가 기존 `dept_molit.xml` (국토교통부 RSS) 와 데이터 정합도 높음 — 1순위. 정책뉴스는 fallback / 통합 검색 용도.

---

## 2. 기존 4 결함 결정 갱신

| # | v1 결정 | v2 갱신 |
|---|---|---|
| 1 wrapper 위치 | api/collectors/policy_collector.py 수정 (Railway 분기) | **api/collectors/policy_collector.py 수정** (출처만 swap, 분기 X) |
| 2 cron 위치 | GitHub Actions 유지 | **유지** (변경 없음) |
| 3 cron 빈도 | 1x/day | **유지** (변경 없음) |
| 4 health endpoint | /api/system/health (Railway worker 검증용) | **N/A** — Railway worker 폐기, 대신 `data_go_kr_policy` 자원으로 SystemPulse 갱신 |

**시너지**: 결함 1 의 "wrapper" 자체가 사라짐 (분기 불필요). 그냥 `policy_collector.py` 의 fetch 부분 출처를 바꾸면 끝.

---

## 3. 컴포넌트 명세 (단순화)

### 3.1 `api/collectors/policy_collector.py` 수정 (단일 모듈)

**현 상태**: korea.kr/rss/dept_molit.xml 직접 GET → ConnectionReset.

**v2**: data.go.kr `pressReleaseService/pressReleaseList` 호출 + 부처 필드 filter.

```python
# 환경변수 PUBLIC_DATA_API_KEY 필수 (vercel-api/.env 이미 박힘)
API_BASE = "http://apis.data.go.kr/1371000/pressReleaseService/pressReleaseList"
DEPT_FILTER = "국토교통부"  # 기존 dept_molit 정합

def collect_policies(...):
    params = {
        "serviceKey": PUBLIC_DATA_API_KEY,
        "startDate": (now - lookback).strftime("%Y%m%d"),
        "endDate":   now.strftime("%Y%m%d"),
        "numOfRows": 100,
        "pageNo":    1,
    }
    r = requests.get(API_BASE, params=params, timeout=15)
    # XML 파싱 + 부처 필드 == DEPT_FILTER 만 추출
    # 응답 → 기존 schema (id/title/source_url/source_name/published_at/raw_text) 정합
```

**변경 영향**:
- Downstream 0 변경 (응답 schema 동일 유지)
- `BeautifulSoup` 사용 부분만 data.go.kr XML schema 에 맞게 조정
- `T12 User-Agent 강제` 룰 → 불필요 (정식 API key 가 인증)
- error 처리 동일 (`logged=True` stderr + 빈 배열 반환)

### 3.2 SystemPulse 자원 정정

기존 `korea_kr_worker` 영구 blocked → **신규 `data_go_kr_policy`** 자원으로 교체:

| 자원 ID | 메트릭 | healthy 조건 |
|---|---|---|
| `data_go_kr_policy` | last_success_at + last_status_code | < 24h ago AND status 200 |

`estate/docs/contract_system_pulse.md` 의 endpoint 표 갱신 필요 (별도 PR).

### 3.3 Railway server 정정

`server/main.py` 의 `/proxy/korea_kr/probe` endpoint 는 **[temp-probe] revert 의무** (memory `project_estate_p3_4_pending` prereq pattern 정합):
- 측정 commit `37446ed` 의 추가 코드 제거
- `RAILWAY_PROXY_KEY` env 도 Railway dashboard 에서 삭제 권고 (사용자 액션)

### 3.4 GitHub Actions cron

기존 cron 그대로 사용. 변경 사항: env 에 `PUBLIC_DATA_API_KEY` 가 이미 있는지 확인 (없으면 GH Secret 등록 — `feedback_github_secret_autonomy` 정합 자율 실행).

---

## 4. P1 진입 절차 (단순화)

| 단계 | 내용 | 상태 |
|---|---|---|
| 1 | data.go.kr 활용신청 (정책뉴스 + 보도자료 둘 다) | ✅ 사용자 완료 (2026-05-06) |
| 2 | API propagation | ⏳ 대기 (활용 중 표시 후 5~30분~1h) |
| 3 | API 동작 확인 — `pressReleaseList` 200 + XML | 대기 |
| 4 | `policy_collector.py` data.go.kr 호출로 swap | 코드 준비 가능 |
| 5 | 단위 테스트 + 응답 schema 검증 (downstream 무변경) | 코드 준비 가능 |
| 6 | GH Actions cron 1회 발화 — 실데이터 수집 | propagation 후 |
| 7 | SystemPulse 자원 정정 + [temp-probe] revert | 6 완료 후 |
| 8 | P3-4 closure → ChangeFeed (4/5 페이지) 진입 | 7 완료 후 |

---

## 5. 폐기/유지 결정

| 항목 | 결정 |
|---|---|
| Railway proxy worker | **폐기** — v2 에서 불필요 |
| `RAILWAY_PROXY_KEY` 32-byte hex | **폐기** — Railway env + 메모리 사전 승인에서 제거 |
| `KOREA_KR_PROXY_KEY` | **폐기** — 동일 |
| 기존 server/main.py 의 KIS WebSocket relay | **유지 변경 없음** — 별개 책임 |
| [temp-probe] `/proxy/korea_kr/probe` endpoint | **revert 의무** (commit `37446ed`) |

---

## 6. References

- v1 commit: `cb7c2b6` (이번 commit 으로 대체 — file rename + content rewrite)
- 측정 closure: `37446ed` ([temp-probe] korea.kr egress)
- 데이터 출처 검색: WebSearch 2026-05-06 결과 (data.go.kr 15095335, 15095295)
- memory `project_estate_p3_4_pending` (재개점 — v2 진입으로 갱신 의무)
- memory `feedback_real_call_over_llm_consensus` (R-ONE 사례 정합 — 실호출 1회로 결론)
- `api/collectors/policy_collector.py` (수정 대상)
- `estate/docs/contract_system_pulse.md` (자원 정정 의존)
