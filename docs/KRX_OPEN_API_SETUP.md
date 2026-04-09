# KRX Open API — 인증키·이용신청 가이드 (VERITY)

한국거래소 Data Marketplace Open API는 **“인증키 1개”와 “쓰려는 데이터(API)마다의 이용 권한”이 분리**되어 있습니다. 키만 넣고 호출했을 때 `403 Forbidden`, `You don't have permission`, 빈 응답이 나오는 경우 대부분 **해당 API에 대한 이용 신청·승인이 안 된 상태**입니다.

공식 안내: [서비스 이용방법](https://openapi.krx.co.kr/contents/OPP/INFO/OPPINFO003.jsp)  
단계별 스크린샷 예시(커뮤니티): [KRX OpenAPI 따라하기](https://github.com/raccoonyy/pykrx-openapi/blob/main/docs/krx-openapi.md)

---

## 1. 전체 흐름 (꼭 둘 다 필요)

| 단계 | 내용 | 비고 |
|------|------|------|
| A | 포털 회원가입·로그인 | [openapi.krx.co.kr](https://openapi.krx.co.kr/) |
| B | **API 인증키 신청** → 관리자 승인 | 마이페이지 → API 인증키 신청 / 발급내역 |
| C | 쓸 **데이터 상품(API)마다** **API 이용신청** → 승인 | 서비스 이용 → 지수·주식 등에서 항목 선택 후 하단 **API 이용신청** |
| D | 개발 명세서의 URL·파라미터로 호출 | 샘플 테스트 탭에서 동일 조건으로 먼저 검증 |

**B만 되어 있고 C가 없으면** 키는 유효해도 특정 URL 호출은 거절되거나 데이터가 비는 경우가 많습니다.

---

## 2. 사장님이 포털에서 할 일 (체크리스트)

1. 로그인 후 **마이페이지 → API 인증키 발급내역**에서 키가 **승인 완료**인지 확인합니다.
2. **마이페이지 → API 이용현황**(또는 신청 내역)에서, 우리가 쓰려는 항목이 **승인됨**으로 보이는지 봅니다.
3. **서비스 이용 → 주식**(및 필요 시 다른 카테고리)에서 아래에 가까운 이름의 API를 검색합니다.
   - **공매도·잔고**류: 포털 표기명은 시기에 따라 다를 수 있으나, 통상 “공매도”, “순보유”, “잔고” 등 키워드로 검색합니다.
   - **투자주의·경고·위험·시장조치**류: “시장조치”, “투자주의”, “투자경고”, “관리종목” 등으로 검색합니다.
4. 각 API 상세 페이지에서 **개발명세서**·**샘플 테스트**를 열어, 표기된 **요청 URL**, **쿼리 파라미터 이름**(예: 기준일 `basDd`), 응답 필드명을 확인합니다.
5. 샘플 테스트가 성공한 뒤에만 앱/CI에 동일 방식으로 붙입니다.

---

## 3. 추천 이용신청 API (로드맵·터미널 확장 대비)

**전제:** KRX Open API는 **한국 거래소 상장·상품** 위주입니다.  
**나스닥·미국 지수·해외 주가**는 KRX가 아니라 기존처럼 `yfinance` / FMP / Alpha Vantage / 증권사 API 등 **별도 소스**가 필요합니다.  
**코인(가상자산)**도 KRX 포털에 없습니다. 거래소 API(업비트·빗썸 등) 또는 글로벌 시세 API를 따로 쓰면 됩니다.

그래도 **국내 “시장 지도 + ETF + 지수 + 원자재(장내)”**까지 한 번에 열어두려면, 아래 순서로 **API 이용신청**을 해 두는 것을 권합니다. (포털 **서비스 이용** 메뉴의 API ID와 동일합니다.)

### 3-1. 1순위 — 거의 필수에 가깝게 쓸 것

| 구분 | API ID | 화면상 이름(요지) | 용도 |
|------|--------|-------------------|------|
| 지수 | `kospi_dd_trd` | KOSPI 시리즈 일별시세 | 국내 대표 지수·날씨 |
| 지수 | `kosdaq_dd_trd` | KOSDAQ 시리즈 일별시세 | 코스닥 흐름 |
| 지수 | `krx_dd_trd` | KRX 시리즈 일별시세 | KRX 지수군(예: KRX300 등) |
| 증권상품 | `etf_bydd_trd` | ETF 일별매매정보 | ETF 확장·구성 추적 |
| 주식 | `stk_bydd_trd` | 유가증권 일별매매정보 | 코스피 종목 일별(헬스체크·스캐너와도 맞음) |
| 주식 | `ksq_bydd_trd` | 코스닥 일별매매정보 | 코스닥 종목 일별 |
| 주식 | `stk_isu_base_info` | 유가증권 종목기본정보 | 티커·상장 메타 정합성 |
| 주식 | `ksq_isu_base_info` | 코스닥 종목기본정보 | 위와 동일(코스닥) |

### 3-2. 2순위 — 매크로·상품 다각화

| 구분 | API ID | 용도 |
|------|--------|------|
| 증권상품 | `etn_bydd_trd` | ETN 일별 (ETF 다음 단계) |
| 일반상품 | `gold_bydd_trd` | 장내 금 시장 일별 — 안전자산·원자재 내러티브 보조 |
| 일반상품 | `oil_bydd_trd` | 석유시장 일별 — 에너지·인플레 맥락 |
| 지수 | `bon_dd_trd` | 채권지수 시세 — 금리·채권 분위기 |
| ESG | `esg_index_info` | ESG 지수 (ESG 화면 붙일 때) |
| ESG | `esg_etp_info` | ESG 증권상품 |

### 3-3. 3순위 — 심화(옵션)

| 구분 | API ID | 용도 |
|------|--------|------|
| 주식 | `knx_bydd_trd`, `knx_isu_base_info` | 코넥스 |
| 주식 | `sw_bydd_trd`, `sr_bydd_trd` | 신주인수권증권·증서 (니치) |
| 증권상품 | `elw_bydd_trd` | ELW |
| 채권 | `kts_bydd_trd`, `bnd_bydd_trd`, `smb_bydd_trd` | 국채·일반·소액 채권 시장 |
| 파생 | `fut_bydd_trd`, `opt_bydd_trd`, `eqsfu_stk_bydd_trd`, `eqkfu_ksq_bydd_trd`, `eqsop_bydd_trd`, `eqkop_bydd_trd` | 선물·옵션·주식선물/옵션 |
| 지수 | `drvprod_dd_trd` | 파생상품지수 시세 |
| 일반상품 | `ets_bydd_trd` | 배출권 |
| ESG | `sri_bond_info` | SRI 채권 정보 |

### 3-4. 공매도·투자경고·시장조치

스크린에 보이는 **주식 8종 API 목록만으로는** 공매도 잔고·투자경고 전용 ID가 항상 드러나지 않습니다. 포털 검색으로 **“공매도”, “잔고”, “시장조치”, “투자주의”, “투자경고”** 등으로 나오는 **별도 API**가 있으면, 그 항목마다 동일하게 **이용신청**하면 됩니다.

---

## 4. 이 레포에서 쓰는 환경변수

| 변수 | 설명 |
|------|------|
| `KRX_API_KEY` | VERITY 백엔드·GitHub Actions에서 읽는 이름 (`.env` / Secrets) |
| `KRX_OPENAPI_KEY` | (선택) `pykrx-openapi` 패키지는 기본으로 이 이름을 봅니다. 값은 `KRX_API_KEY`와 **동일**하게 두면 됩니다. |

로컬 `.env` 예시 (값은 복사한 인증키로 교체):

```bash
KRX_API_KEY=여기에_마이페이지에서_복사한_인증키
# pykrx-openapi 쓸 때만 중복 지정해도 됨
# KRX_OPENAPI_KEY=동일키
```

GitHub: **Settings → Secrets and variables → Actions → New repository secret**  
이름: `KRX_API_KEY`  
값: 포털에서 발급받은 인증키 문자열

워크플로 `Run analysis` 단계에서 위 시크릿이 `KRX_API_KEY` 환경변수로 주입됩니다.

---

## 5. HTTP 호출 방식 (일반 패턴)

Open API 문서·샘플에 따르되, 커뮤니티·래퍼에서 많이 쓰는 패턴은 다음과 같습니다.

- **메서드**: `GET`
- **인증**: 쿼리 파라미터 **`AUTH_KEY`** = 인증키 문자열  
  (일부 예제 문서에는 HTTP 헤더 `AUTH_KEY`로 안내하는 경우도 있으나, **해당 API 개발명세서·샘플 테스트에 맞출 것**이 우선입니다.)
- **기준일**: 흔히 `basDd=YYYYMMDD` (영업일 기준 — 주말·휴일은 에러이거나 전일 데이터만 가능할 수 있음)
- **응답**: JSON에 `OutBlock_1` 배열 형태가 많음 (API마다 상이 — 명세서 확인)

호스트·경로는 **반드시 해당 API 상세의 개발명세서**를 따릅니다. 서드파티 라이브러리 예시로는 베이스가 `https://data-dbg.krx.co.kr/svc/apis` 형태로 안내된 경우가 있습니다. **운영 URL이 바뀌면 명세서가 최우선**입니다.

간단 검증용 `curl` 예시(유가증권 일별매매정보 — **이용 신청·승인된 경우에만** 동작):

```bash
# basDd 는 최근 영업일 YYYYMMDD 로 바꿀 것
curl -sS "https://data-dbg.krx.co.kr/svc/apis/sto/stk_bydd_trd?AUTH_KEY=인증키&basDd=20250404"
```

---

## 6. 공매도·투자경고를 코드에 붙일 때 우리가 추가로 필요한 정보

포털에 올라온 **API마다 URL·파라미터가 다릅니다.** 아래 중 하나만 보내주시면 엔드포인트 연동을 정확히 할 수 있습니다.

1. 해당 API 상세 페이지의 **개발명세서**에 나온 **전체 요청 URL**(또는 path + 필수 파라미터 목록), 또는  
2. **샘플 테스트**에서 성공한 요청을 복사한 **전체 URL**(인증키는 가려서),

그리고 **마이페이지 → API 이용현황**에서 그 API가 **승인** 상태인지 확인해 주세요.

---

## 7. 자주 나는 오류

| 증상 | 가능 원인 |
|------|-----------|
| 401 / 인증 실패 | 키 오타, 키 미승인, 만료 |
| 403 / permission | 그 API에 대한 **이용 신청 미승인** |
| 빈 `OutBlock_1` | `basDd`가 비거래일, 또는 해당 일자 미제공 |
| 로컬만 되고 CI만 실패 | GitHub Secrets에 `KRX_API_KEY` 미등록·오타 |

---

## 8. 보안

- 인증키는 **Git에 커밋하지 말 것** (`.env`는 `.gitignore` 처리됨).
- 키가 로그·이슈·채팅에 노출되었다면 포털에서 **재발급·폐기** 절차를 확인하세요.

---

## 9. 참고 링크

- [KRX Data Marketplace OPEN API](https://openapi.krx.co.kr/)
- [서비스 이용방법](https://openapi.krx.co.kr/contents/OPP/INFO/OPPINFO003.jsp)
- 문의: 포털 하단 안내 `krxdata@krx.co.kr` (공지 기준, 변경 시 포털 확인)

---

## 10. VERITY 연동 상태 (2026-04)

현재 코드에는 아래가 반영되어 있습니다.

- `api/collectors/krx_openapi.py`
  - KRX OpenAPI 18개 엔드포인트 매핑
  - 공통 호출 패턴(`AUTH_KEY`, `basDd`) + 상태 분류(`ok` / `empty` / `forbidden` / `error`)
- `api/main.py`
  - `quick`/`full` 모드에서 KRX 스냅샷 수집 후 `portfolio["krx_openapi"]` 저장
  - `realtime` 모드는 호출량 제어를 위해 스킵(기존 스냅샷 유지)
- `api/health.py`
  - KRX 단일 API 확인이 아닌 18개 요약 헬스체크로 개선

참고: 수집 요약에서 `empty`가 많아도 오류는 아닐 수 있습니다(비거래일/상품별 데이터 미제공).

## 11. 원격(GitHub Actions)에서 꼭 해야 할 것

아래는 코드로 자동화할 수 없어서 **직접 UI에서 1회 설정**이 필요합니다.

1. 저장소 GitHub 페이지 → `Settings` → `Secrets and variables` → `Actions`
2. `New repository secret`
   - Name: `KRX_API_KEY`
   - Value: KRX 포털에서 발급받은 인증키
3. (선택) 동일 값으로 `KRX_OPENAPI_KEY`도 등록 가능  
   - 현재 워크플로는 `KRX_API_KEY` 값을 `KRX_OPENAPI_KEY`로도 주입하도록 되어 있어 필수는 아님
4. `Actions` 탭에서 `Stock Analysis Pipeline` 수동 실행(`workflow_dispatch`) 또는 다음 스케줄 대기
5. 로그에서 아래 문자열 확인
   - `KRX OpenAPI 스냅샷 수집 (18개)`
   - `KRX 요약: 정상 X | 빈데이터 Y | 권한없음 Z | 오류 W`

권한 이슈가 남아 있으면 KRX 포털의 API 이용신청 상태를 다시 확인하세요.
