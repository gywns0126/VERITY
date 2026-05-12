# VERITY 풀 audit sprint 2026-05-12 종합 요약

**시점**: 5/17 ATR verdict + VAMS reset 직전 baseline 확립
**범위**: 6갈래 경량 sweep (단일 세션 압축, 원래 plan 5일 → 1일 압축)
**Detailed docs**:
- `AUDIT_2026_05_12_axis2_operations.md` (운영 결함)
- `AUDIT_2026_05_12_axis5_data_integrity.md` (데이터 무결성)
- `AUDIT_2026_05_12_axis1_system_consistency.md` (메모리 룰 drift)
- `AUDIT_2026_05_12_axis3_code_quality.md` (코드 품질)
- `AUDIT_2026_05_12_axis4_6_architecture_ux.md` (아키텍처+UX)

---

## 총 결함 21건

| 갈래 | HIGH | MED | LOW | 합계 |
|---|---|---|---|---|
| #2 운영 결함 | 1 | 3 | 1 | 5 |
| #5 데이터 무결성 | 5 | 2 | 1 | 8 |
| #1 시스템 정합성 | 2 | 2 | 1 | 5 |
| #3 코드 품질 | 0 | 1 | 1 | 2 |
| #4+#6 아키텍처/UX | 1 | 2 | 0 | 3 |
| **계** | **9** | **10** | **4** | **21** |

---

## HIGH 9건 모음 (5/17 sprint 핵심 큐)

### 운영 (#2)
1. `daily_realtime.yml:8~45` — GH schedule 16+ 라인 + dispatch 동시 활성. 자정 race 재발 위험. `project_dispatch_chain` 폐기 결정 미이행

### 데이터 (#5)
2. `data/macro_snapshot.json::macro` — 15+ 매크로 필드 source/as_of 메타 누락
3. `data/portfolio.json::macro` — 동일 매크로 메타 누락
4. `data/daily_content/*/macro/meta.json` — collected_at 누락 (3일치)
5. `api/collectors/macro_data.py:69,133,147,163,190,204,628` — 7개 bare `except: pass`, logged 표식 부재
6. `api/collectors/RSSScout.py` — feedparser 예외 logged 누락

### 시스템 정합성 (#1)
7. `api/intelligence/verity_brain.py:1631` — `kis_debt > 300` 단일 floor, 금융주 면제 미적용 → 금융주 자동 AVOID 회귀 위험
8. `api/analyzers/safe_picks.py:30,46,48` — `debt_ratio > 100/60/50` 단순 분기, `sector_thresholds` helper 미호출

### Frontend (#6)
9. `estate/components/pages/residential/EstateBrainPanel.tsx:700,704,730` — scenario props 전용 (GuSelector 패턴 미적용). 사이트 내 셀렉터 부재

---

## 즉시 fix 권장 (5/17 전)
- **#1**: daily_realtime schedule 폐기 (단순 yml 수정, 자정 race 차단)
- **#7+#8**: sector_aware 회귀 정정 (verdict 신뢰도 영향 낮으나 금융주 데이터 회귀 가능)

## 5/17 sprint queue (나머지 HIGH 6 + MED 10 + LOW 4)
대부분 메모리 룰 정합화 + logged 적재 추가. 단일 변수 통제 일괄 패치 패턴.

## 영속 관찰
- `publish-data` staged 파일 list (자동화 불가, 메모리 룰 영속)
- USD/KRW cross-source 시간차 (정기 cron 동기화로 자연 해결)

---

## 메타 관찰

### 시스템 건강 신호
- 컴포넌트 overlap 0
- Builder/endpoint overlap 0
- Import cycle 0
- Workflow race 0
- Dead code 0
- Dangling reference 0
- Security 0 (false positive 정정 후)
- 메모리 룰 8/10 정합

42일치고는 매우 깨끗. 메모리 시스템 + commit prefix 룰 + audit 메모리들이 코드 작성 단계에 효과 발휘.

### 결함 분포 패턴
- HIGH 9건 중 **5건이 데이터 메타/로깅** 누락 (`feedback_macro_timestamp_policy` + `feedback_data_collection_verification_mandatory`) → 메모리 룰 박힌 후 신규 코드 추가 시 일관 미적용
- HIGH 2건 (sector_aware)도 동일 패턴 — helper 만들어놓고 caller 일괄 패치 미완
- **Root cause 공통**: 룰 박힌 후 일괄 audit 부재. 본 sprint가 그 기능 (5/17 전 정합화 기회)

### 5/17 진입 의사결정
- 즉시 fix 2건 처리 후 ATR verdict 진입 권장
- 나머지 18건은 evolution sprint queue
- 8월 말 65 거래일 종합 verdict 시 본 sprint 결과 재방문

---

## 다음 단계 후보

1. **즉시 fix 2건** (daily_realtime schedule + sector_aware) — 5/13~5/15
2. **5/17 sprint queue 정리** (별도 작업) — HIGH 6 + MED 10 + LOW 4
3. **22:30 hourly_pulse 첫 통 발송 모니터링** (오늘 밤)
4. **5/13 통수 재측정** (`project_telegram_quiet_hours_v0` 후속)
