# VERITY Brain Monitor — 구현 명세서

**대상 독자**: Claude Code (또는 다른 AI 코딩 에이전트)
**선행 문서**: `docs/BRAIN_MONITOR_WIREFRAME.md` (시각 설계)
**선행 시스템**: `docs/VERITY_SYSTEM_SPEC_2026.md` (전체 시스템 spec)

---

## 0. 단계별 구현 순서 (강제)

이 명세서는 **4단계로 분리**되어야 한다. 한 번에 다 짜지 말 것.

| 단계 | 산출물 | 시간 | 선행 조건 |
|---|---|---|---|
| **Phase 1** | 측정 모듈 (드리프트/설명 가능성) | 1~2일 | 메타데이터 1주일 누적 |
| **Phase 2** | 2D 대시보드 (Overview + 4탭) | 1일 | Phase 1 완료 + 데이터 검증 |
| **Phase 3** | 3D Brain (Three.js, iframe 호스팅) | 2일 | Phase 2 검증 + Sandbox 한계 테스트 |
| **Phase 4** | Telegram 알림 통합 + Trust 자동 판정 | 0.5일 | Phase 1~3 안정 |

**가드 정책**:
- 각 Phase 종료 후 git commit + 회귀 테스트 통과 + 1~2일 운영 검증 후 다음 Phase
- Phase 3 (3D)는 별도 호스팅 (Vercel preview 또는 GitHub Pages) — Framer Sandbox 직접 ❌
- 모든 Phase 시작 전 git checkpoint 생성

---

## 1. Phase 1 — 측정 모듈

신규 파일: `api/observability/`

### 1.1 `api/observability/data_health.py`

**목적**: 데이터 소스별 신선도 / 성공률 / 결측률 측정

```python
def check_data_health(portfolio: dict) -> dict:
    """
    Returns:
      {
        "yfinance": {
          "last_update_ts": "2026-04-27T22:00:00+09:00",
          "freshness_minutes": 5,
          "success_count_7d": 2851,
          "failure_count_7d": 3,
          "missing_pct": 0.001,
          "status": "ok" | "warning" | "critical",
          "latency_ms_p50": 320,
        },
        "fred": {...},
        "ecos": {...},
        "dart": {...},
        "kis": {...},
        ...
      }
    """
```

**입력 소스 식별**: portfolio.json 의 각 섹션 메타 (collected_at, source, as_of) + system_health 섹션 + Deadman Switch 로그.

**status 룰**:
- `ok`: success_rate >= 95% AND freshness < 30min
- `warning`: success_rate 90~95% OR freshness 30~120min
- `critical`: success_rate < 90% OR freshness > 120min

**저장**: `data/metadata/data_health.jsonl` (일별 누적, JSON 한 줄)

### 1.2 `api/observability/feature_drift.py`

**목적**: 입력 feature 분포의 일별 변화 측정 (PSI / KL divergence)

```python
def compute_drift(yesterday: dict, today: dict, features: list[str]) -> dict:
    """
    PSI (Population Stability Index) 계산.
    PSI 0~0.1: 정상 / 0.1~0.2: 의심 / 0.2+: drift 발생

    Returns:
      {
        "feature_drifts": {
          "vix_avg": {"psi": 0.08, "level": "ok", "yesterday": 18.5, "today": 19.0},
          "news_sentiment": {"psi": 0.45, "level": "high", ...},
          ...
        },
        "overall_drift_score": 0.18,  # 모든 PSI 평균
        "drifted_features": ["news_sentiment", "sp500_change_pct"],
        "level": "warning",  # ok/warning/critical
      }
    """
```

**대상 feature** (portfolio + recommendations 에서 추출):
- 매크로: vix_avg, usd_krw, us_10y, sp500_change_pct, mood_score
- 종목 평균: avg_per, avg_pbr, avg_roe, avg_debt_ratio
- 시장: avg_brain_score, grade_distribution_buy_pct, vci_avg
- 수급: foreign_net_avg, institution_net_avg
- 뉴스: news_sentiment_avg

**저장**: `data/metadata/feature_drift.jsonl`

### 1.3 `api/observability/explainability.py`

**목적**: 오늘 Brain Score 의 기여도 분해 (positive / negative TOP 5)

```python
def explain_brain_score(portfolio: dict) -> dict:
    """
    포트폴리오의 평균 Brain Score 가 왜 그 값인지 설명.

    Returns:
      {
        "avg_brain_score": 65.2,
        "positive_contributors": [
          {"feature": "consensus_score", "avg_contribution": 12.4, "weight": 0.13},
          {"feature": "multi_factor", "avg_contribution": 9.2, "weight": 0.19},
          ...
        ],
        "negative_contributors": [
          {"feature": "macro_override_active", "avg_contribution": -8.1, "weight": 0.0},
          {"feature": "vci_extreme", "avg_contribution": -6.3, ...},
          ...
        ],
        "vs_yesterday": {
          "score_change": +3.2,
          "biggest_change_feature": "news_sentiment",
          "biggest_change_value": +5.1,
        },
      }
    """
```

**계산**: verity_constitution.json 의 `fact_score.weights` × 각 feature 평균값. 음수 기여는 macro_override 발동 / red_flags 발생 등으로 역산.

### 1.4 `api/observability/trust_score.py`

**목적**: "오늘 리포트 발행 가능?" 8개 조건 자동 판정

```python
def report_readiness(portfolio: dict) -> dict:
    """
    Returns:
      {
        "verdict": "ready" | "hold" | "manual_review",
        "conditions": {
          "data_freshness_ok": True,
          "core_sources_ok": True,
          "drift_below_threshold": True,
          "ai_models_ok": True,
          "brain_distribution_normal": True,
          "pipeline_cron_ok": True,
          "deadman_clear": True,
          "pdf_generator_ok": True,
        },
        "satisfied": 8,
        "total": 8,
        "blocking_reasons": [],  # 미충족 조건
        "recommendation": "발행 가능 — 자동 cron 진행",
      }
    """
```

### 1.5 신규 모듈 테스트

`tests/test_observability.py` — 각 함수 회귀 테스트 (mock 데이터 입력 → 예상 status 반환)

---

## 2. Phase 2 — 2D 대시보드

**플랫폼 결정**:
- 옵션 A: **Framer 코드 컴포넌트** (1개 파일, 단일 페이지) — Sandbox 한계 위험
- 옵션 B: **별도 Vercel 페이지** (`/admin/brain-monitor`) — 안전, 권장
- 옵션 C: **Next.js 앱** (별도 repo 또는 monorepo) — 가장 자유롭지만 인프라 작업 큼

**권장**: **옵션 B**. Vercel API와 같은 repo 안에 페이지로 추가.

### 2.1 라우트 구조

```
vercel-api/api/admin/
  brain_health.py        # GET /api/admin/brain_health
  data_health.py         # GET /api/admin/data_health
  drift.py               # GET /api/admin/drift
  trust.py               # GET /api/admin/trust
  explain.py             # GET /api/admin/explain
```

각 엔드포인트는 Phase 1 측정 모듈 호출 결과 JSON 반환. 인증: 쿠키 기반 (본인만).

### 2.2 프론트엔드

**스택**: React + TypeScript + Tailwind CSS (또는 styled-components)
**위치**: `vercel-api/admin/` (Vercel 정적 페이지) 또는 별도 폴더
**라우트**: `/admin/brain-monitor`

**컴포넌트**:
- `<BrainMonitor />` — 메인 페이지, 5탭 구조
- `<OverviewTab />` — 4 KPI + 알림 + Trust
- `<DataHealthTab />` — 소스별 표 + 7일 추이
- `<ModelHealthTab />` — Brain Score 분포 + 적중률 + AI 이견
- `<DriftTab />` — Feature drift bars + Prediction drift + 기여도 TOP 5
- `<ReportReadinessTab />` — Trust 8개 조건 + PDF 생성 버튼

**상태 관리**: SWR or React Query (5분 폴링)

### 2.3 인증 (관리자 전용)

기존 Supabase 인증 재사용. `profiles.is_admin = true` 사용자만 접근. 다른 사용자는 401.

---

## 3. Phase 3 — 3D Brain

**플랫폼**: 별도 페이지 (Vercel 정적 또는 GitHub Pages)
**스택**: React + Three.js (또는 react-three-fiber)
**Framer 통합**: iframe embed (`<iframe src="https://verity-3d.vercel.app/" />`)

### 3.1 노드 데이터 구조

```typescript
interface BrainNode {
  id: string                  // "input_price", "engine_fact", "output_grade" 등
  cluster: "input" | "engine" | "output"
  position: [number, number, number]  // 3D 좌표
  health: "ok" | "warning" | "critical"
  health_score: number        // 0~100
  metric: {
    primary_value: number
    primary_label: string     // "성공률 95%", "신선도 5분" 등
    yesterday_change: number
  }
  detail: {
    description: string
    related_data_health_keys: string[]  // 이 노드 클릭 시 표시할 데이터 소스
  }
}

interface BrainEdge {
  from: string
  to: string
  strength: number  // 0~1, 굵기
  health: "ok" | "warning" | "critical"
}
```

### 3.2 시각화 룰

- 노드: 구체 (sphere), 반경 = sqrt(health_score), 색 = status
- 에지: 곡선 (cubic bezier), 두께 = strength, 색 = health
- 카메라: 자유 회전, 자동 회전 옵션 (기본 OFF)
- 클릭: 노드 ID + 디테일을 부모 컴포넌트에 emit (postMessage)

### 3.3 데이터 페칭

5분 간격 fetch `/api/admin/brain_topology` — 노드/에지 모두 포함된 단일 응답.

### 3.4 폴백

WebGL 미지원 환경: 2D SVG 토폴로지로 폴백 (동일 노드/에지 표시).

---

## 4. Phase 4 — Telegram 알림 + Trust 자동

### 4.1 알림 룰

`api/observability/alert_dispatcher.py`:

```python
def dispatch_alerts(health: dict, drift: dict, trust: dict) -> list:
    """
    상태 변화 검출 + Telegram 푸시.

    Rules:
      - 데이터 소스 status: ok → critical 즉시 푸시
      - drift level: ok → critical 즉시 푸시
      - trust verdict: ready → hold/manual_review 즉시 푸시
      - warning 누적 1시간 후 푸시 (스팸 방지)
    """
```

### 4.2 Trust 자동 판정 + 발행 게이트

cron 에서 PDF 생성 전:
1. `report_readiness()` 호출
2. `verdict == "ready"` 면 PDF 생성 + git commit
3. `verdict == "hold"` 면 PDF 생성 X, 텔레그램 알림 + 사유 명시
4. `verdict == "manual_review"` 면 PDF 생성 + 워터마크 강조 + 알림

기존 `_run_long_horizon_v2` 등에 `report_readiness()` 호출 추가.

---

## 5. 데이터 스키마

### 5.1 `data/metadata/data_health.jsonl` (일별)

```json
{"date": "2026-04-27", "timestamp": "2026-04-27T22:00:00+09:00",
 "sources": {"yfinance": {...}, "fred": {...}, ...},
 "overall_status": "ok"}
```

### 5.2 `data/metadata/feature_drift.jsonl` (일별)

```json
{"date": "2026-04-27", "feature_drifts": {...},
 "overall_drift_score": 0.18, "level": "warning"}
```

### 5.3 `data/metadata/explainability.jsonl` (일별)

```json
{"date": "2026-04-27", "avg_brain_score": 65.2,
 "positive_contributors": [...], "negative_contributors": [...]}
```

### 5.4 `data/metadata/trust_log.jsonl` (cron 실행마다)

```json
{"timestamp": "2026-04-27T22:00:00+09:00", "verdict": "ready",
 "satisfied": 8, "total": 8, "blocking_reasons": []}
```

---

## 6. 가드 정책 (강제)

1. **각 Phase 종료 시 git commit + 회귀 테스트 통과 + 1~2일 운영 검증**
2. **Phase 3 (3D) 는 별도 호스팅** — Framer 코드 컴포넌트에 직접 ❌
3. **새 측정 모듈은 항상 try/except + logger.warning** — 실패 시 None 반환, 메인 흐름 영향 0
4. **메타데이터 jsonl 누적 — 운영 1주일 후가 의미 시작** — 그 전엔 차트가 빈 칸
5. **3D 노드 수 ≤ 12개** — 그 이상이면 시각화 가독성 저하
6. **인증 필수** — `profiles.is_admin = true` 만 접근. 일반 사용자 401

---

## 7. 메모리 정책 매핑

이 시스템은 다음 메모리 정책에 직결:
- `feedback_continuous_evolution`: 4개 가드 (commit / 시간대 / 모니터링 / 롤백) 적용
- `feedback_macro_timestamp_policy`: data_health 의 freshness 측정에 timestamp 메타 사용
- `feedback_ai_fallback_sanitization`: AI 모델 health 체크 시 fallback 메시지 raw 노출 금지
- `feedback_sector_aware_thresholds`: drift 측정 시 금융주 분기 (부채비율 등은 별도 임계)
- `project_validation_plan`: trust 의 "검증 미완료" 워터마크 적용

---

## 8. 의존성

신규 패키지:
- `scipy` (PSI 계산용 — 또는 직접 구현)
- `numpy` (기존)
- Phase 3: `three`, `@react-three/fiber`, `@react-three/drei` (별도 레포에서)

기존 재사용:
- `api.utils.dilution` (가드 + 변환 사전)
- `api.metadata` (4모듈 누적 데이터)
- `api.config.now_kst`
- `fpdf2` (PDF — 신규 필요 없음)

---

## 9. 미구현 영역 (이 spec 범위 밖)

- 모바일 레이아웃 (Phase 2 데스크탑만)
- 다중 사용자 권한 (본인 단독 — admin/non-admin 이분만)
- 알림 우선순위 큐 / 묶음 발송 (Phase 4 단순 룰만)
- 자동 인시던트 회복 (수동 트리거만)

---

## 10. 검수 체크리스트 (각 Phase 완료 시)

**Phase 1**:
- [ ] `data_health.py` / `feature_drift.py` / `explainability.py` / `trust_score.py` 4개 모듈 존재
- [ ] 각 함수 mock 데이터 회귀 테스트 통과
- [ ] `data/metadata/` 에 4개 jsonl 자동 누적
- [ ] `try/except` 모든 진입점에 적용

**Phase 2**:
- [ ] 5개 API 엔드포인트 작동 (curl 검증)
- [ ] `/admin/brain-monitor` 페이지 5탭 모두 표시
- [ ] 인증 미통과 시 401
- [ ] 5분 폴링 자동
- [ ] 모바일에서 깨지지 않음 (최소 표시)

**Phase 3**:
- [ ] 별도 호스팅 페이지 작동 (Vercel preview)
- [ ] 12개 노드 + 에지 렌더링
- [ ] 노드 클릭 → postMessage 작동
- [ ] WebGL 미지원 환경 폴백

**Phase 4**:
- [ ] Telegram 알림 룰 작동 (테스트 메시지)
- [ ] cron PDF 생성 전 `report_readiness()` 호출 통합
- [ ] `verdict == "hold"` 시 PDF 생성 차단 + 알림 검증

---

## 11. 작업 시작 시 첫 명령

```bash
cd "/Users/macbookpro/Desktop/배리티 터미널"
git checkout -b feature/brain-monitor
mkdir -p api/observability
touch api/observability/{__init__,data_health,feature_drift,explainability,trust_score,alert_dispatcher}.py
git add -A && git commit -m "scaffold: brain-monitor Phase 1 module skeleton"
```

각 모듈 한 함수씩 구현 + 테스트 + commit. Phase 끝마다 회귀 테스트 + main 머지.
