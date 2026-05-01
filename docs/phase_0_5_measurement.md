# Phase 0.5 — Universe Load Measurement Report

- 측정일: 2026-05-01 (KST 18:33–18:46)
- 측정자 환경: macOS Darwin 25.2.0 / Python 3.9 / yfinance 1.2.0 / pykrx 1.0.51
- 측정 시간대: 18:30~18:50 KST (≈ 05:30 ET, US 시장 개장 4시간 전 — yfinance 응답 빠름 시간대)
- Raw 데이터: `data/metadata/universe_load_measurement.jsonl` (47 lines, 누적)
- 운영 코드 미터치: `api/analyzers/stock_filter.py`, `api/main.py` 등 변경 없음 (관측 전용)

⚠️ **선결조건 준수**
- 100 → 200 단계까지만 실측. 500/1,000 은 IP 차단 위험 + 로컬 측정 시간 보호 위해 **선형 외삽**.
- 첫 실패 시 즉시 중단 정책 발동: pykrx bulk 엔드포인트 (KR-B/C 초기 정의) 환경 부적합 → KRX OpenAPI + pykrx single 으로 우회.

---

## 1. yfinance 측정 결과 (US 시장)

| 케이스 | 30 종목 | 100 종목 | 200 종목 | 1,000 추정 (선형) | 3,500 추정 (선형) | 비고 |
|---|---|---|---|---|---|---|
| **U1** `yf.Ticker(t).info` 단건 순차 | 12.3s | 42.0s | (미측정) | **~7.0min** | **~24.5min** | 0.42s/ticker. 운영 stock_data.py 와 동일 패턴. |
| **U2** `yf.download(batch all)` | (미측정) | 5.4s (98 ok) | (미측정) | **~54s** | **~190s (3.2min)** | 가격 OHLCV. 실패 2건 = FI/MMC 상장폐지 |
| **U3** `yf.Ticker(t).history` 단건 | 6.2s | (미측정) | (미측정) | **~3.5min** | **~12min** | 0.21s/ticker. U2 batch 가 압도적 우월. |
| **P4** `yf.download(chunk=100)` | — | 6.7s (98 ok) | — | ~67s | ~235s | U2 single batch (5.4s) 보다 느림 — chunking 오버헤드. |
| **B1** Finnhub `/stock/metric` | 14.3s | (미측정, 60req/min cap) | — | **~16.7min** (rate cap 적용) | — | 60req/min 한계로 1,000 = 16.7min 불가피 |
| **B3** SEC EDGAR companyfacts | 23.4s | — | — | ~13min | — | 0.78s/ticker (0.11s sleep 포함) |

**핵심 관찰**:
- U1 (info 순차) = fundamentals 병목. 1,000 = 7분, 3,500 = 25분 — 매일 single thread 로는 GitHub Actions 90분 timeout 견딜 수 있으나 다른 작업과 충돌
- U2 batch 는 가격에 한해 압도적: 100=5.4s, 1,000 ≈ 54s, 3,500 ≈ 190s
- U3 history 단건은 U2 대비 3~10배 느림 → **가격은 무조건 U2/P4 batch 사용**

⚠️ U1 1,000 직접 실측 안 함 — IP 차단 위험. P2/P3 측정으로 대체 (아래 §3).

---

## 2. pykrx 측정 결과 (KR 시장) — bulk 엔드포인트 환경 부적합 회피

| 케이스 | 30 종목 | 100 종목 | 1,500 추정 (선형) | 비고 |
|---|---|---|---|---|
| **K1** KRX OpenAPI 일괄 (1콜) | — | — | **3.0s** (n 무관, 1콜) | KOSPI+KOSDAQ 전체 + 거래대금 정렬. **유니버스 추출 최적** |
| **K2** `pykrx.get_market_ohlcv` 단건 | 1.0s | 4.5s | **~67.5s** | 0.045s/ticker. 가격 데이터. 단건 매우 빠름 |
| **K3** `pykrx.get_market_fundamental_by_date` 단건 | 6.3s (**0 ok / 30 fail**) | — | — | ❌ **환경 부적합**. KR 펀더멘털 다른 경로 필요 (DART/yfinance .KS/KIS) |
| **(deprecated)** `pykrx.get_market_cap_by_ticker(ALL)` | — | — | — | ❌ KRX 백엔드 변경으로 깨짐. 운영 `trading_value_scanner.py` 도 이미 우회 |

**KR 측 결론**:
- **유니버스 추출**: K1 (KRX OpenAPI 1콜 = 3초) — 최적. 운영 `api/collectors/krx_openapi.py:155` 그대로 재활용
- **가격 데이터**: K2 (pykrx single OHLCV) — 1,500 종목 = ~68초, 매우 빠름. 병렬화 불필요.
- **펀더멘털**: pykrx 부적합. 대안 = (a) DART API (이미 운영) (b) yfinance ".KS" suffix 단건 = U1 동일 패턴 (c) KIS API (운영 사용 중). **Phase 2-A 진입 전 추가 합의 필요**.

---

## 3. 병렬화 효과 측정 (핵심)

| 케이스 | 100 종목 | 200 종목 | 1,000 추정 | 3,500 추정 | 순차 대비 배수 | rate limit 관찰 |
|---|---|---|---|---|---|---|
| **P1** 순차 (= U1) | **42.0s** | 84s* | 420s (7.0min) | 1,470s (24.5min) | **1.0x (baseline)** | 없음 |
| **P2** ThreadPool 20w | **3.2s** | **5.8s** | ~29s | ~100s | **13.1x** (100), 14.5x (200) | 0건 |
| **P3** ThreadPool 50w | **2.0s** | **2.7s** | ~13s | ~45s | **21.0x** (100), 31.1x (200) | 0건 |
| **P4** download chunk=100 | 6.7s | — | ~67s | ~235s | (가격만 적용) | 없음 |

*P1 200 은 미측정, 100 측정값으로 선형 추정.

**관찰**:
- 50w 가 20w 대비 +60~80% 추가 속도. 200 종목 측정에서 sub-linear 스케일링 (50w 가 거의 saturate)
- **rate limit 위반 0건** (yfinance 측정 시간 18:30 KST, US 장 마감 13시간 후 — 트래픽 한산)
- 50w 에서도 IP 차단 신호 미관찰 → US 새벽/장후 시간대 적용 가능

**경고**:
- 측정 100~200 종목 단계까지만. 1,000 종목 50w 는 미실측. **동시 50 connection x 1,000 ticker fan-out** 은 yfinance 비공식 limit (~2,000 req/hour) 인접 가능성 있음
- 운영 환경에서 50w 처음 사용 시 **5분 간격 로그 모니터링 + 즉시 fallback (= 20w 또는 P4 batch)** 가드 필수

**병렬화 권고**:
- **fundamentals (info)**: P3 (50w) 우선, 첫 7일 운영 모니터 후 안정 시 유지. 실패 시 P2 (20w)
- **가격 데이터**: U2/P4 batch — 병렬화 불요 (이미 5초)
- **KR**: 1,500 단건 OHLCV 67초 — 병렬화 불요. KRX OpenAPI 일괄 + pykrx single 조합

---

## 4. 차등 갱신 권고 (FUND-CHANGE 측정 결과)

`data/history/2026-04-23 ~ 2026-05-01` 8일치 53종목 분포:

| 필드 | n | 평균 변화율 % | 중앙값 % | 최대 % | 최소 % | 해석 |
|---|---|---|---|---|---|---|
| `per` | 53 | 5.39 | **3.22** | 29.76 | 0.09 | 가격 변동 직접 반영 — daily 갱신 가치 있음 |
| `pbr` | 53 | 2.49 | **0.00** | 39.53 | 0.00 | 절반 이상 동일 → weekly 충분 |
| `roe` | 51 | 9.37 | **0.00** | 100.0 | 0.00 | 분기 보고서 의존 → weekly/quarterly |
| `debt_ratio` | 46 | 4.36 | **0.00** | 100.0 | 0.00 | 분기 보고서 → weekly/quarterly |
| `operating_margin` | 53 | 139.85 | **0.00** | 4511.11 | 0.00 | 이상치 (TTM 분모 작은 종목) → weekly/quarterly |

**해석**:
- PER 만 일 단위 의미 있는 변화 (가격이 분자로 들어감). PBR/ROE/debt/op_margin 은 분기 보고서 시점에만 변화 → 일 갱신은 동일 데이터 반복 호출
- median 0% 인 필드 4개 = 펀더멘털 자체가 stable

**권고**:
| 데이터 | 갱신 주기 | 사용 패턴 | 부하 (3,500 기준) |
|---|---|---|---|
| **가격 1Y OHLCV** | **매일** | U2/P4 batch | 3.2~3.9분 |
| **PER (가격 의존)** | **매일** | U1 P3 50w | ~45초 |
| **PBR/ROE/debt/op_margin** | **주 1회 (월 또는 화)** | U1 P3 50w | ~45초 (주 1회) |
| **시총·거래대금 (랭킹)** | **매일** | K1 (KR) + U2 col 추출 (US) | KR 3초 + US (cached) |

**산출 효과**:
- 매일 부하 = 가격 batch + PER → ~4분
- 주 1회 부하 = 펀더멘털 풀 갱신 → +~45초 (주 1회만)
- vs 매일 풀 갱신 = ~4분 + 45초 = 매일 ~5분
- **차등 갱신 절감 = ~6분/주 (38주분 GH Actions 분 절감)** — 절감 자체보다 IP 부하 감소가 핵심

---

## 5. GitHub Actions 부하 추정

⚠️ **2차 측정 (workflow_dispatch) 미실행**. 사유: 본 Phase 의 신규 파일 허용 위치(`scripts/`, `docs/`, `data/metadata/`)에 `.github/workflows/` 미포함. 워크플로 추가는 별도 합의 필요.

**문서 측정 + 일반 보정계수**:
- `daily_analysis_full.yml` `timeout-minutes: 90`, `runs-on: ubuntu-latest`
- 현재 full 모드 평균 실행: 측정 인프라 부재 (워크플로 로그 비추적). gh API `gh run list -w daily_analysis_full.yml` 로 별도 조회 권장
- 일반적 보정계수 = **1.3~1.5x** (Actions ubuntu-latest 가 로컬 macOS arm64 대비 네트워크 latency + CPU 차이)

**Phase 2-A 추가 시 추정 (3,500 기준, P3 50w + 차등 갱신)**:
| 운영 작업 | 로컬 추정 | × 1.4 | 비고 |
|---|---|---|---|
| 매일: 가격 U2 batch (3,500) | 3.2min | 4.5min | |
| 매일: PER U1 P3 50w (3,500) | 0.75min | 1.05min | |
| 주 1회: 펀더멘털 풀 P3 50w (3,500) | 0.75min | 1.05min | 매일 비용 0 |
| 매일: KR K1 1콜 + K2 (1,500) | 1.15min | 1.6min | |
| **매일 추가 부하 합계** | **5.1min** | **7.2min** | wide_scan 자체 처리 시간 별도 |
| 90분 timeout 여유 | ≥ 80min | ≥ 80min | 충분 |

**결론**: 90분 timeout 안전. 단 운영 코드 추가/cron 충돌 시 재측정 필요.

---

## 6. 시총 상위 종목 리스트 확보 방법

### KR
- **1순위**: `api/collectors/krx_openapi.py:krx_stk_ksq_rows_sorted_by_trading_value()` — 1콜 = 전체 KOSPI+KOSDAQ + 거래대금 정렬. **3초**, IP 부하 0
- 갱신: 매일. 내장 영업일 retry (12일치) 있음
- 데이터: 종목코드 + ACC_TRDVAL (거래대금) — wide_scan Coarse Filter 의 거래대금 필터 즉시 적용 가능
- 시총 순위가 필요하면 KRX OpenAPI 다른 엔드포인트 또는 pykrx single 호출 보조 (`get_market_cap` 단건은 환경 부적합 — DART/KIS 우회 필요)

### US
- **yfinance 에 전체 종목 시총 API 부재** — 확인됨
- **권고**: 정적 리스트 (S&P 1500 + Russell 1000 일부 = ~2,000) **주 1회 갱신**
- 정적 리스트 출처:
  - 1순위: SEC EDGAR `company_tickers.json` (전 종목, **무료**, 시총 미포함이라 별도 결합 필요)
  - 2순위: Polygon `/v3/reference/tickers` (free 5req/min — 갱신 자체에는 충분)
  - 3순위: Finnhub `/stock/symbol` (60req/min) — universe list 만 받아오기
  - 4순위: GitHub의 무료 큐레이션 리스트 (S&P 1500 etc.) — 정적, 검증 필요

**부하**: 주 1회 캐시 갱신이라 daily 부하 0. 캐시 위치: `data/metadata/us_universe_cache.json` (Phase 2-A 진입 시 신설)

---

## 7. 백업 소스 평가 (선택)

| 소스 | 30종목 | 1,000 추정 | rate limit | 데이터 깊이 | 추천 우선순위 |
|---|---|---|---|---|---|
| **yfinance Ticker.info** | 12.3s (U1) | ~7min seq / **~30s P3** | 비공식 (~2k/hr) | per/pbr/roe/debt/op_margin 모두 | **1** (현재 기본) |
| **Finnhub /stock/metric** | 14.3s (B1) | ~16.7min (60/min cap) | 60/min | per/pbr/roe + 100+ 메트릭 | 2 (백업) |
| **SEC EDGAR companyfacts** | 23.4s (B3) | ~13min | 10/sec | XBRL fundamental raw | 3 (감사용) |
| **Polygon free tier** | 미실측 (5/min cap) | ~3.3시간 | 5/min | OHLCV + reference | 4 (free 비현실) |

**결론**: yfinance + ThreadPool (P3) 가 압도적 1순위. Finnhub 는 yfinance 장애 시 fallback 으로 Phase 2-A 코드에 미리 포함 권고 (이미 `api/collectors/finnhub_client.py` 존재).

---

## 8. 권고 — 확장 유니버스 크기

### 옵션 A — 3,500 직진 ✅ **권고**

**근거**:
1. P3 (50w) 측정값 100=2.0s, 200=2.7s — 1,000 종목 ~13s, 3,500 ~45s 추정. **13~45초 로 fundamentals 수집 가능**
2. KR 측 K1 (KRX OpenAPI) 1콜 3초 + K2 single 1,500 종목 67초 → KR 측은 **70초 이내 완전 처리**
3. 차등 갱신 적용 시 매일 부하 = 가격(U2/P4 batch 3.2분) + PER(45초) + KR(70초) = **~5분/일**
4. GH Actions 보정계수 1.4x 적용해도 ~7분 → 90분 timeout 여유 충분
5. rate limit 위반 0건 (P3 50w, 18:30 KST 측정)

**전제 조건 / 리스크**:
- yfinance rate limit 비공식 ~2,000 req/hour. P3 50w 1,000 동시 = 분당 2,000+ 가능. 운영 시 **반드시 5분 간격 모니터링 + 자동 fallback (P2 20w 또는 P4 batch)**
- US 시장 개장 시간대 (KST 22:30~05:00) 에는 yfinance 트래픽 폭증 → **wide_scan cron 은 KST 06:00~22:00 사이로 제약**
- 측정은 100~200 까지. 1,000 / 3,500 실측 미실시. **운영 1주차에 조심스러운 ramp-up 필수** (500 → 1,500 → 3,500 단계)
- KR 펀더멘털 (PER/PBR/ROE) 수집 경로 미확정. yfinance .KS suffix 사용 시 1,500 종목 P3 50w = ~13초 추정이지만 .KS 가 KRX 일부 종목에서만 fundamentals 반환할 가능성 있음 → **Phase 2-A 진입 전 KR fundamentals 소스 합의 필수**

### 옵션 B — 2,500 (KR 1,000 + US 1,500) — 차순위

**근거**: 옵션 A 의 모든 가드를 즉시 적용하지 않고 점진 도입 시. 측정값으로는 옵션 A 가능하지만 운영 무경험 (단독 25일차) 안전마진 확보.

**리스크**: 락인 해소 효과 부분적 (현 85 → 2,500 도 30배 확장이라 충분).

### 옵션 C — 1,500 (KR 500 + US 1,000) — 비추

**근거 (반대)**: 측정값이 3,500 가능을 강하게 시사. 1,500 으로 시작은 측정 가치 미반영.

---

## 권고 종합

| 항목 | 권고 |
|---|---|
| **확장 유니버스 크기** | **옵션 A: 3,500** (KR 1,500 + US 2,000) |
| **병렬화 방법** | **P3 (ThreadPool 50w)** 우선, 첫 7일 모니터 후 유지. 실패 신호 시 자동 fallback **P2 (20w)** → **P4 (batch chunked)** |
| **갱신 주기** | 가격 = **매일**, PER = **매일**, PBR/ROE/debt/op_margin = **주 1회 (월요일)**, 시총 랭킹 = 매일 (KR=K1 자동, US=주 1회 캐시) |
| **KR 펀더멘털 소스** | **합의 필요** (DART API / yfinance .KS / KIS API 중 1) — Phase 2-A 차단 요소 |
| **GH Actions 워크플로 측정** | 본 Phase 미실행. 워크플로 파일 추가 합의 후 별도 진행 권장 |
| **운영 가드** | (a) cron 시간 KST 06:00~22:00 (US 장 회피) (b) 50w 첫 7일 모니터 + 자동 fallback (c) 500→1,500→3,500 ramp-up (d) IP 차단 알림 (e) 백업 = Finnhub `api/collectors/finnhub_client.py` |

---

## 본인 결정 대기 사항

1. **확장 유니버스 크기**: 옵션 A (3,500) / B (2,500) / C (1,500) 중 1 — **결정됨: 5,000 (메모리 결정 1)**
2. **KR 펀더멘털 소스**: DART / yfinance .KS / KIS API 중 1 — **결정됨: DART 1순위 / .KS 2순위 (메모리 결정 2)**
3. **워크플로 보정 측정 시점**: Phase 2-A 시작 전 / 시작 후 / 생략 — **결정됨: 시작 전 (메모리 결정 3)**
4. **ramp-up 정책**: 즉시 풀스케일 / 7일 모니터 ramp-up / 격주 ramp-up — **결정됨: 14일 ramp-up (메모리 결정 4)**
5. 위 5번 운영 가드 (a)~(e) 모두 적용 / 일부 생략 — **결정됨: 가드 1~4 즉시 / 가드 5 후행 (메모리 결정 5)**

본 Phase 0.5 는 측정·문서·jsonl 3개 파일 외 변경 0건. Phase 2-A 자동 진입 금지.

---

## 9. GitHub Actions 보정 계수 (실측 — 2026-05-01 19:07~19:16 KST)

**실행 환경**: workflow_dispatch / ubuntu-latest / Python 3.11 / 총 10m47s / run id `25210604760`
**실행 트랙**: `u2,p3,k1,k2`, tier `1000` (US pool 캐시 한도로 실제 298 처리, KR 1,000 처리)

### 9.1 케이스별 비교

| 케이스 | 로컬 측정 | Actions 측정 | 비율 (Actions / Local) | 해석 |
|---|---|---|---|---|
| **U2** `yf.download` batch (n=298) | 19.3s | **16.8s** | **0.87x** | Actions 가 미세하게 빠름 |
| **P3** ThreadPool 50w (n=298) | 2.7s (200) → 외삽 4.0s (298) | **1.8s** | **~0.45x** | **Actions 가 2배 이상 빠름** (US-기반 runner ↔ Yahoo US 서버 근접) |
| **K1** KRX OpenAPI 1콜 | 3.0s (n=100) / 2.95s (n=30) | **5.8s** | **~1.93x** | Actions 가 약 2배 느림 (US-기반 runner ↔ Korea KRX 원거리) |
| **K2** pykrx single OHLCV (per-ticker) | 0.045s/ticker (n=100) | **0.547s/ticker** (n=1000) | **12.16x** | 🔴 **Actions 가 12배 느림** — pykrx 가 KRX 백엔드에 종목당 ~3-5콜 → 한국 RTT 누적 |
| **KR universe load** (K1 + ticker 추출) | 3.42s (n=100) | 7.32s (n=1000) | ~2.1x | 단일 호출 + 행 슬라이스 |

### 9.2 핵심 비대칭 발견

- **US 트랙 (yfinance)**: Actions 가 **로컬보다 빠르거나 동등** (0.45~0.87x). 보정 불필요.
- **KR 트랙 (pykrx single, KRX OpenAPI)**: Actions 가 **2~12배 느림**. **지리적 RTT 누적이 결정적**.
- 사전 추정 1.3~1.5x 보정계수는 **US 측에는 과대, KR 측에는 과소**.

### 9.3 5,000 tier 일일 부하 재추정 (Actions 실측 반영)

**전제**: Hard Floor (메모리 결정 6) + Coarse Filter cascade 적용. K1 결과의 거래대금으로 KR 2,000 → ~500 좁힌 후 K2 호출.

| 단계 | Actions 추정 |
|---|---|
| KR universe load (K1 1콜) | 7.3s |
| US P3 50w (3,000 fundamentals) | 18.1s |
| US U2 batch 가격 (3,000) | 169.1s (2.82min) |
| KR K2 sequential (cascade 후 500) | 273.5s (4.56min) |
| **일일 총합 (cascade 적용)** | **468.1s = 7.80min — 90min timeout 91% 여유** ✅ |
| (cascade 없이 K2 풀 2,000) | 1,288.6s = 21.5min — 안전 마진 부족 ❌ |

### 9.4 Phase 2-A 적용 권고

**확정 사항**:
- **max_workers (US fundamentals)**: **50 유지** ✅. Actions 298 종목 1.8s, rate limit 0건. 3,000 종목 = ~18s.
- **U2 batch (US 가격)**: 단일 batch (chunk 미적용) 권고. 298 = 16.8s, 3,000 외삽 ~169s.
- **K1 (KR universe)**: 매일 1콜로 충분. 5.8~7.3s.

**필수 아키텍처 변경 — Coarse Filter cascade 의무**:
- K1 응답에 포함된 ACC_TRDVAL (거래대금) 로 **K2 호출 전 Hard Floor + Coarse Filter** 적용
- KR 2,000 → 200~500 narrowed pool 만 K2 진입
- **K2 sequential 대안 검토**: ThreadPoolExecutor 20w on K2 측정 미실시. Phase 2-A 첫 단계로 측정 권고
- 만약 K2 ThreadPool 20w 도 Actions 8분 초과 시 **KR 가격 데이터를 KRX OpenAPI 일괄 (K1) 의 OHLCV 필드만 사용** 으로 전환 검토 (1Y 시계열 깊이는 잃음 — 일별 스냅샷만 매일 누적)

**timeout 권고**:
- 측정 워크플로 30min → Phase 2-A 운영 워크플로도 **30min 분리 timeout** 권고 (`daily_analysis_full.yml` 90min 과 별도 concurrency group)
- 또는 기존 90min 안에 통합 시 wide_scan 단계만 timeout 모니터링 추가

**Phase 2-A 진입 권고**: ✅ **Yes**

**선결 조건**:
1. K2 ThreadPoolExecutor 측정 1회 추가 (workflow_dispatch 동일 워크플로 재사용 가능 — `tracks=k2_pool` 신규 케이스 추가 필요)
2. Coarse Filter cascade 의무 — 코드 설계에 반영
3. KR fallback 정책: K2 timeout 시 K1 OHLCV 일별 누적 모드로 전환

### 9.5 데이터 소스 신뢰성 (Actions 실측)

- **U2 fail rate**: 19/298 = 6.4% (FI/MMC/MRO/PARA 등 상장폐지 + 최근 합병). **Hard Floor 룰로 사전 제거 가능**
- **K2 fail rate**: 4/1,000 = 0.4% (정지/관리종목 추정)
- **P3 fail rate**: 0/298 (rate limit 0건, IP 차단 0건)

원시 데이터: `/tmp/phase_0_5_artifact/phase-0-5-measurement-25210604760/data/metadata/universe_load_measurement.jsonl` (53 lines, run_id `25210604760` artifact retention 30 days)

---

## 10. K2 pykrx ThreadPool 측정 (Phase 2-A 진입 전 추가)

**실행 환경**: workflow_dispatch / ubuntu-latest / Python 3.11 / run id `25211054902`
**실행 트랙**: `k2_p10,k2_p20,k2_p30,k2_p50`, tier `500` (KOSPI+KOSDAQ 시총 상위 500)
**총 wall clock**: **30분 timeout 발동, conclusion=cancelled** — `if: always()` 덕분에 K2-P10/P20/P30 결과는 artifact 보존

### 10.1 측정 결과

| 케이스 | workers | n | elapsed | per-ticker | speedup vs seq | fail |
|---|---|---|---|---|---|---|
| K2-S (참고) | 1 | 1,000 | 547.0s | 0.547s | 1.0x | 0.4% |
| **K2-P10** | 10 | 500 | **32.21s** | 0.064s | **8.5x** | 0.4% |
| **K2-P20** | 20 | 500 | **14.81s** | 0.030s | **18.5x** | 0.4% |
| **K2-P30** | 30 | 500 | **10.12s** | 0.020s | **27.0x** | 0.4% |
| K2-P50 | 50 | 500 | **timeout (>30min)** 🔴 | — | — | hung |

### 10.2 핵심 발견 — KRX 방어 임계 = 30~50 사이

- **P10/P20/P30 모두 문제 없음**: 0.4% fail rate (관리/정지종목 추정), 모든 sub-linear scaling 명확
- **P50 hung**: 30분 timeout 안에 첫 batch (500종목) 도 완료 못 함. 평균 1초당 16+ 종목 처리 가능했어야 하지만 실제로는 응답 정지.
- **해석**: pykrx 가 종목당 KRX 백엔드에 ~3-5 호출 → P50 = 동시 150-250 호출 → KRX 가 IP/세션별 throttle 또는 connection drop. pykrx 는 timeout 처리 없이 무한 대기.
- **결론**: **P30 = 안전 상한**. P50 운영 절대 금지.

### 10.3 5,000 tier 일일 부하 재추정 (K2-P30 적용, Actions)

| 단계 | 시간 | 개선 vs §9 |
|---|---|---|
| KR universe load (K1) | 7.3s | 동일 |
| US P3 50w (3,000) | 18.1s | 동일 |
| US U2 batch 가격 (3,000) | 169.1s | 동일 |
| **KR K2-P30 (cascade 500)** | **10.1s** | -263s ✅ |
| **일일 총합 (cascade + P30)** | **204.6s = 3.41min** | -4.4min vs §9.3 (7.80→3.41) |
| (cascade 없이 K2-P30 풀 2,000) | 234.9s = 3.92min | Cascade 필요성 약화 |

**90min timeout 여유**: 96.2% (3.41 / 90)

### 10.4 Cascade 필요성 재평가

- §9 시점: K2 sequential 273s (cascade 후 500) vs 1,094s (전 2,000) → **cascade 필수**
- §10 시점: K2-P30 10.1s (cascade 후 500) vs 40.4s (전 2,000) → **cascade 시간 측면 비필수** (40s 차이만)
- 그러나 **Hard Floor (메모리 결정 6) 노이즈 통제 측면에서는 여전히 의무** — 페니/관리종목 사전 제외해야 wide_scan 알파 시그널 보호
- **권고**: cascade 유지 (시간 절감 < 노이즈 통제 가치). 단 cascade 깊이는 완화 가능 — 2,000 → 1,000 (Hard Floor 만 적용) → 1,000 그대로 K2-P30 수집 = 20.2s

### 10.5 Phase 2-A 적용 권고 (확정)

**KR 가격 데이터 수집 정책**:
- **`max_workers = 30`** (확정). 운영에서도 P30 절대 상한.
- 첫 7일 운영 모니터: fail_rate > 1% 또는 평균 elapsed_s 대비 +50% 시 즉시 P20 으로 하향
- **P50 시도 절대 금지** — 실측 hung. KRX 가 자동 차단.

**Cascade 설계**:
- **K1 universe 추출 → Hard Floor (페니/관리/거래정지/저거래대금 자동 cut) → 1,000~1,500 narrowed → K2-P30**
- 시간 절감보다 노이즈 통제 목적
- Hard Floor 룰은 wide_scan.py 진입 단계에 (Phase 2-A 첫 단계) 코드화

**timeout 권고 (재확인)**:
- Phase 2-A 운영 워크플로 timeout = **30min 분리** (`daily_analysis_full.yml` 90min 과 별도 concurrency group)
- wide_scan 자체 단계 timeout = 10min (cascade 적용 시 3.4min 완료 → 7분 안전 마진)

**측정 가치**:
- K2-S 273s → K2-P30 10.1s = **96% 시간 절감**
- 일일 부하 7.8min → 3.4min (90min timeout 대비 4% → 4%) — timeout 자체는 충분히 여유롭지만 **다른 cron 작업과의 자원 경합 감소** 효과 큼

### 10.6 운영 가드 (KRX rate limit 대비)

1. **K2-P30 워커 수 코드 상수화**: `WIDE_SCAN_KR_K2_WORKERS = 30` 하드코드, env 변수로 변경 가능 (긴급 하향 시)
2. **fail_rate 모니터**: 매일 `data/metadata/runtime_load_log.jsonl` 에 K2 단계 fail_rate 기록. 1% 초과 시 Telegram 알림
3. **첫 호출 elapsed 가드**: K2 첫 batch 가 30s 초과하면 즉시 abort + P20 fallback
4. **중복 호출 캐시**: 같은 영업일 OHLCV 는 1회만 호출 (`data/cache/k2_ohlcv/{date}/{ticker}.parquet`) — 재실행 시 0초

### 10.7 다음 측정 후보 (Phase 2-A 첫 주)

본 §10 까지로 Phase 2-A 진입 가능. 단 운영 첫 주에 다음 추가 측정 권고:
- K2-P25 (P30 보수 fallback 후보)
- K2-P30 시간대별 (KST 06:00 / 09:00 / 12:00 / 18:00 / 22:00) — KRX 트래픽 패턴
- K2-P30 1,000/1,500/2,000 점진 ramp-up (현재는 500까지만 검증)

원시 데이터: `data/metadata/universe_load_measurement.jsonl` (104 lines, run_ids `25210604760` + `25211054902`)
