# 도메인 플러그인 추상화 — 설계 스케치

**지금 구현하지 말 것.** 이건 전역 이후 부동산·정치 도메인 확장 시점에 꺼내 쓸 청사진일 뿐.

## 배경

현재 VERITY 는 **주식** 도메인에 하드코딩:
- `api/collectors/` 48개 전부 주식 데이터
- `api/analyzers/` 16개 전부 종목/시장 분석
- `api/intelligence/verity_brain.py` 의 판단 스키마가 "종목 × 시그널" 전제
- VAMS 엔진의 portfolio 스키마도 holdings = 종목 리스트

전역 이후 부동산/정치 확장 시 **이대로는 collectors/analyzers/brain 을 통째로 복제**해야 함. 3배 유지보수.

## 원칙

재사용 가능한 건 재사용, 도메인 고유한 건 분리. **공유 = 플랫폼, 도메인 = 플러그인**.

### 공유 (재사용)
- LLM 클라이언트 (Gemini/Claude/Perplexity 래퍼)
- Supabase Auth / RLS
- 텔레그램·PDF 리포트 엔진
- tracing / mocks / safe_collect
- 스케줄러 (GitHub Actions · main.py 오케스트레이션)
- Framer 디자인 토큰 + 공통 컴포넌트 (AuthGate, MarketBar 등)
- 결제 레이어 (전역 후)

### 도메인별 (분리)
- 수집기 — 데이터 소스가 도메인마다 완전히 다름
- 분석기 — 지표 체계 다름 (종목 PER vs 부동산 PIR vs 정치 공약 점수)
- Constitution — 판단 규칙
- 프론트 컴포넌트 — 도메인 고유 시각화
- portfolio 스키마 — holdings/positions 의 개념 자체가 다름

## 제안 구조

```
api/
├── platform/                  ← 도메인 무관 공통 기반
│   ├── llm/                   ← gemini/claude/perplexity 래퍼
│   ├── auth/                  ← Supabase 연동
│   ├── notifications/         ← telegram / pdf
│   ├── tracing/
│   ├── scheduler/             ← main 오케스트레이션 인터페이스
│   └── utils/                 ← safe_collect, portfolio_writer 등
│
├── domains/
│   ├── stocks/                ← 현재 코드 전부 여기로
│   │   ├── collectors/
│   │   ├── analyzers/
│   │   ├── brain/             ← verity_brain 을 도메인 브레인으로
│   │   ├── engine/            ← VAMS
│   │   ├── trading/           ← auto_trader, kis_broker
│   │   └── manifest.py        ← 플러그인 등록 엔트리
│   │
│   ├── realestate/            ← 전역 후 신규
│   │   ├── collectors/        ← 국토부 실거래가, PIR, 청약경쟁률
│   │   ├── analyzers/         ← 레버리지율, 임대수익률
│   │   ├── brain/             ← realestate_brain
│   │   ├── engine/            ← VARS (Virtual Asset Realestate Sim)
│   │   └── manifest.py
│   │
│   └── politics/              ← 전역 후 신규
│       ├── collectors/        ← 선관위, 공약 DB, 여론조사
│       ├── analyzers/         ← 공약 이행률, 테마 연동성
│       ├── brain/
│       └── manifest.py
│
└── apps/                      ← 도메인 조합해서 서비스 하나 구성
    ├── verity_terminal/       ← stocks 주력
    ├── realestate_terminal/   ← realestate 주력 + stocks 참조
    └── politics_terminal/     ← politics 주력 + stocks·realestate 참조
```

## 도메인 매니페스트

```python
# api/domains/stocks/manifest.py
from api.platform.plugin import DomainPlugin

stocks_domain = DomainPlugin(
    name="stocks",
    version="9.0",
    collectors=[StockDataCollector, DartScout, MacroCollector, ...],
    analyzers=[StockFilter, MultiFactor, SectorRotation, ...],
    brain=VerityBrain,
    engine=VAMSEngine,
    trader=AutoTrader,
    portfolio_schema=STOCK_PORTFOLIO_SCHEMA,
    frontend_components=[
        "StockDashboard", "MarketBar", "SectorHeat", ...
    ],
)
```

## 플랫폼 인터페이스 (도메인이 구현)

```python
# api/platform/plugin.py (스케치)
class DomainPlugin(ABC):
    @abstractmethod
    def run_cycle(self, portfolio: dict) -> dict:
        """도메인 고유 수집-분석-판단 사이클."""

    @abstractmethod
    def validation_criteria(self) -> dict:
        """도메인별 검증 지표 정의 (주식은 샤프/MDD, 부동산은 임대수익률/레버리지...)."""

    @abstractmethod
    def portfolio_schema(self) -> dict:
        """portfolio.json 에 쓰는 이 도메인의 키 스키마."""
```

## 단일 `portfolio.json` 에 여러 도메인

```json
{
  "updated_at": "...",
  "domains": {
    "stocks": {
      "vams": {...},
      "recommendations": [...],
      "validation_report": {...}
    },
    "realestate": {
      "vars": {...},
      "listings": [...],
      "validation_report": {...}
    },
    "politics": {
      "theme_links": [...],
      "policy_tracker": [...]
    }
  },
  "cross_domain": {
    "policy_impact": {...}        ← 정치 → 부동산·주식 영향
  }
}
```

## 프론트 측 분리 전략

- Framer 워크스페이스: **3 개 별도 사이트** (verity.app / realestate / politics)
- 각 사이트는 자기 도메인의 portfolio 섹션만 읽음 (`portfolio.domains.stocks` 등)
- 공통 컴포넌트 (로그인, 경제캘린더 등) 는 shared library 한 곳에서 복붙 (Framer 제약)

## cross-domain 가치

**정치 도메인이 두 시장의 연결고리가 되는** 것이 차별점:
- 총선 공약 → 섹터별 매출 영향 → 주식 테마
- 부동산 규제 변화 → 건설주/리츠 영향
- 환경 정책 → 에너지 ETF 영향

이런 cross-domain 인사이트는 **domains/politics/analyzers/** 에서 stocks/realestate 의 recommendations 를 읽어 영향도 계산.

## 마이그레이션 전략 (전역 후 3개월 프로젝트)

### Phase 1 (1개월): 현재 코드를 stocks 도메인으로 이전
- `api/collectors/*` → `api/domains/stocks/collectors/*`
- import 경로만 변경, 로직 불변
- 기존 테스트 전부 통과하는지 확인
- main.py 를 오케스트레이터 → 플러그인 호출자로 재설계

### Phase 2 (1개월): 플랫폼 추출
- `api/platform/llm/` 등으로 공통 모듈 분리
- stocks 도메인이 platform 을 참조하게 재배선
- 기존 동작 100% 유지

### Phase 3 (1개월): 부동산 도메인 스켈레톤
- `api/domains/realestate/manifest.py` 만 먼저 등록
- 수집기 1~2 개만 (국토부 실거래가 / 청약경쟁률) 로 최소 MVP
- 그 다음 analyzers → brain → engine 순

### Phase 4 (무기한): 부동산 깊이 확장
- 본격 데이터 소스 추가, 판정 로직, 실매매 시뮬
- 정치는 부동산 안정화 후 검토

## 지금 당장 할 수 있는 것

Phase 1 에 들어가기 전 준비로 **지금 구현 0** 이지만:

1. **새 코드를 작성할 때 platform vs domain 구분 감각 유지**.
   예: LLM 호출 래퍼 새로 만든다면 `api/platform/llm/` 을 상상하고 짜기.
2. 새 수집기가 주식 외 도메인에서도 쓰일 가능성 있으면 **수집기 내부에서 주식 전용 필드 하드코딩 지양**.
3. portfolio.json 에 새 top-level 키 추가 시, `domains.stocks.xxx` 가 될 가능성을 고려해 네이밍.

## 하지 말 것

- 지금 실제로 폴더 옮기기 — 코드베이스 깨짐
- 부동산 수집기 미리 만들기 — stocks 주력이 트랙레코드 쌓이기 전엔 분산 투자 손실
- 플러그인 인터페이스 미리 정의 — 실제 두 번째 도메인 만들 때 필요한 모양을 알게 됨 (premature abstraction)

## 결정 원칙

> "두 번째 도메인을 시작할 때 **기존 주식 코드의 어느 비율** 이 재사용되는가" — 이게 설계 성공의 척도.
>
> 목표: 70% 이상 재사용. 30% 미만이면 추상화가 잘못된 것.

---

**한 줄**: 주식 시스템이 실자금 트랙레코드로 증명된 뒤, 전역 후 1 개월 안에 Phase 1 착수. 그 전엔 **이 문서 안 보는 게** 정답.
