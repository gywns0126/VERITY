# 안심(安心) AI 주식 보안 비서

> 잃지 않는 투자를 위한 AI 기반 중장기 가상 투자 시스템

## 구조

```
├── api/
│   ├── main.py                  ← 메인 파이프라인 (매일 실행)
│   ├── config.py                ← 설정 (환경변수로 자본금 조절 가능)
│   ├── collectors/
│   │   └── stock_data.py        ← pykrx 주가/수급 데이터 수집
│   ├── analyzers/
│   │   ├── stock_filter.py      ← 3단계 깔때기 필터링
│   │   └── gemini_analyst.py    ← Gemini AI 종합 분석
│   ├── vams/
│   │   └── engine.py            ← 가상 투자 엔진 (VAMS)
│   └── notifications/
│       └── telegram.py          ← 텔레그램 알림
├── framer-components/           ← Framer 코드 컴포넌트 (복사해서 사용)
│   ├── MarketBar.tsx            ← 상단 시장 지수 바
│   ├── StockHero.tsx            ← 종목 분석 히어로 카드
│   ├── SafetyGauge.tsx          ← 안심 점수 게이지
│   ├── PortfolioCard.tsx        ← 가상 투자 현황
│   ├── ManualInput.tsx          ← 실계좌 수동 입력
│   ├── HistoryTable.tsx         ← 매매 이력
│   └── SignalBadge.tsx          ← 매수/매도/알림 신호
├── data/
│   ├── portfolio.json           ← 포트폴리오 현황 (자동 생성)
│   └── history.json             ← 매매 이력 누적 (자동 생성)
└── .github/workflows/
    └── daily_analysis.yml       ← 매일 16:00 KST 자동 실행
```

## 빠른 시작

### 1. 로컬 실행

```bash
pip install -r requirements.txt

# 기본 실행 (Gemini 없이도 작동)
python api/main.py

# Gemini AI 연동
export GEMINI_API_KEY="your-key-here"
python api/main.py

# 자본금 변경 (기본: 1,000만 원)
export VAMS_INITIAL_CASH=50000000
export VAMS_MAX_PER_STOCK=5000000
python api/main.py
```

### 2. GitHub Actions 자동화

1. GitHub에 이 저장소를 push
2. Settings → Secrets and variables → Actions에서 설정:
   - **Secrets** (필수):
     - `GEMINI_API_KEY`: [Google AI Studio](https://aistudio.google.com/)에서 발급
   - **Secrets** (선택 - 텔레그램 알림):
     - `TELEGRAM_BOT_TOKEN`: @BotFather에서 발급
     - `TELEGRAM_CHAT_ID`: @userinfobot에서 확인
   - **Variables** (선택 - 자본금 변경):
     - `VAMS_INITIAL_CASH`: 초기 자본금 (기본: 10000000)
     - `VAMS_MAX_PER_STOCK`: 종목당 최대 투자금 (기본: 2000000)
3. Actions 탭에서 수동 실행 (Run workflow) 또는 매일 16:00 KST 자동 실행

### 3. Framer 컴포넌트 연결

1. GitHub Pages 활성화 (Settings → Pages → Source: main, /data)
2. Framer에서 새 Code Component 생성
3. `framer-components/` 폴더의 `.tsx` 파일 내용을 복사 → 붙여넣기
4. Property Controls에서 JSON URL 입력:
   - portfolio.json: `https://<username>.github.io/<repo>/portfolio.json`
   - history.json: `https://<username>.github.io/<repo>/history.json`

## 설정 가능한 환경변수

| 변수 | 기본값 | 설명 |
|---|---|---|
| `GEMINI_API_KEY` | (없음) | Gemini API 키 |
| `TELEGRAM_BOT_TOKEN` | (없음) | 텔레그램 봇 토큰 |
| `TELEGRAM_CHAT_ID` | (없음) | 텔레그램 채팅 ID |
| `VAMS_INITIAL_CASH` | 10000000 | 가상 투자 초기 자본금 |
| `VAMS_MAX_PER_STOCK` | 2000000 | 종목당 최대 투자금 |

## VAMS 매매 규칙

- **매수 조건**: AI 추천 = BUY, 안심 점수 60점 이상, 리스크 키워드 미감지
- **고정 손절**: -5% 도달 시 즉시 매도
- **트레일링 스톱**: 수익 발생 후 고점 대비 3% 하락 시 익절
- **기간 손절**: 14일 보유 후 수익 없으면 매도
- **종목당 제한**: 최대 200만 원 (변경 가능)
- **수수료**: 0.015% 반영
