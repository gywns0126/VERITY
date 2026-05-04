# [VERITY-CRON-BACKTEST-HISTORY-20260504] backtest_stats_history.jsonl 신설 cron

**상위 spec**: VERITY-CROSSLINK-THRESHOLDS-V1.4-20260504 §6 / §16 / §17
**유형**: cron sprint (신규 영속화 + cron job)
**예상 소요**: 2~3시간
**병행 sprint**: Sprint 1.5 (병행 가능, 의존 X)

---

## §1. 작업 배경

### 1-1. KI-9 사실

VERITY-CROSSLINK 운영 결함 메모리:
- `data/metadata/backtest_stats_history.jsonl` 미존재
- v1.4 §6-1 baseline 90일+ HISTORICAL phase의 historical mean source = 본 파일
- v1.4 §17 운영 단계 4 phase 중 HISTORICAL phase (90일+) 진입 prereq

### 1-2. 본 sprint 범위

| 항목 | 결과물 |
|---|---|
| 영속화 path 신설 | data/metadata/backtest_stats_history.jsonl |
| cron job 신설 | Railway tranquil-healing project 내 신규 cron |
| append 로직 | 매일 1회 backtest_stats.periods.14d snapshot append |
| idempotent 보장 | 같은 날 중복 append 무시 (KI-12 패턴) |
| retention 정책 | 90일 LRU (또는 mtime 기준) |

### 1-3. v1.4 정합

- §6-1: baseline 90일+ phase source
- §16-1: 영속화 path 일람 (history 필드)
- §17-1: HISTORICAL phase 진입 조건 (90 entry 누적)

---

## §2. P0 작업 — 영속화 + append 로직

### 2-1. 영속화 schema

`data/metadata/backtest_stats_history.jsonl` — JSONL 형식, 1일 1 entry.

```json
{
  "date": "2026-05-04",
  "timestamp": "2026-05-04T00:05:00Z",
  "snapshot": {
    "periods": {
      "14d": {
        "hit_rate": 0.55,
        "total_recs": 142,
        "total_trades": 142,
        ...
      }
    }
  }
}
```

**필드 설명**:
- `date`: YYYY-MM-DD (idempotent key)
- `timestamp`: append 시각 (UTC ISO8601)
- `snapshot.periods.14d`: backtest_stats.json의 periods.14d 그대로 복사

### 2-2. Append 로직

```python
# api/cron/backtest_history_append.py (신규 파일)

import json
from datetime import datetime, timezone
from pathlib import Path

BACKTEST_STATS_PATH = Path("data/metadata/backtest_stats.json")
HISTORY_PATH = Path("data/metadata/backtest_stats_history.jsonl")
RETENTION_DAYS = 90


def append_backtest_history():
    """v1.4 §6-1 / §16 — 매일 1회 backtest_stats.periods.14d snapshot append.
    
    Idempotent: 같은 날 중복 호출 시 append X (KI-12 패턴).
    Retention: 90일 LRU (2-3 함수 처리).
    """
    if not BACKTEST_STATS_PATH.exists():
        return {"status": "skipped", "reason": "backtest_stats.json missing"}
    
    today = datetime.now(timezone.utc).date().isoformat()
    
    # Idempotent check
    if _entry_exists_for_date(today):
        return {"status": "skipped", "reason": "already_appended_today", "date": today}
    
    # Snapshot 산출
    backtest_stats = json.loads(BACKTEST_STATS_PATH.read_text())
    periods_14d = backtest_stats.get("periods", {}).get("14d")
    if periods_14d is None:
        return {"status": "skipped", "reason": "periods.14d missing"}
    
    entry = {
        "date": today,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "snapshot": {"periods": {"14d": periods_14d}},
    }
    
    # Append
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY_PATH.open("a") as f:
        f.write(json.dumps(entry) + "\n")
    
    # Retention LRU
    _enforce_retention(retention_days=RETENTION_DAYS)
    
    return {"status": "appended", "date": today, "entry": entry}


def _entry_exists_for_date(date: str) -> bool:
    """idempotent check — 해당 날짜 entry 존재 시 True."""
    if not HISTORY_PATH.exists():
        return False
    with HISTORY_PATH.open("r") as f:
        for line in f:
            try:
                entry = json.loads(line)
                if entry.get("date") == date:
                    return True
            except json.JSONDecodeError:
                continue
    return False


def _enforce_retention(retention_days: int):
    """90일 retention LRU. RETENTION_DAYS 초과 entry 삭제."""
    if not HISTORY_PATH.exists():
        return
    
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc).date() - timedelta(days=retention_days)).isoformat()
    
    kept = []
    with HISTORY_PATH.open("r") as f:
        for line in f:
            try:
                entry = json.loads(line)
                if entry.get("date", "0000-00-00") >= cutoff:
                    kept.append(line)
            except json.JSONDecodeError:
                continue
    
    HISTORY_PATH.write_text("".join(kept))


if __name__ == "__main__":
    result = append_backtest_history()
    print(json.dumps(result, indent=2))
```

### 2-3. Cron Job 등록

**Railway tranquil-healing project 내 VERITY service**:

- 메모리 운영 사실: 신규 service 생성 X (룰 10 cohabitation)
- 기존 VERITY service 내 cron 추가 (railway.json 또는 cron config 활용)

**cron schedule**: 매일 00:05 UTC (= 09:05 KST). backtest_stats가 자정 산출되는 패턴 가정 시 5분 여유.

**Railway cron config 예시** (실제 형식은 Railway 문서 확인 의무):

```json
{
  "cron": [
    {
      "schedule": "5 0 * * *",
      "command": "python -m api.cron.backtest_history_append"
    }
  ]
}
```

또는 Railway 외부 cron (GitHub Actions, etc.) 활용. **Claude Code가 Railway 인프라 형식 실측 후 결정 의무**.

### 2-4. 시작 시 backfill (선택)

**옵션 A — backfill 없음**:
- cron job 시작 후 매일 1 entry 누적
- HISTORICAL phase (90 entry) 도달까지 90일 소요

**옵션 B — backfill 1회**:
- backtest_stats.json의 history 또는 git history 등에서 최근 30~90일 backtest_stats 산출
- 시작 시 1회 backfill로 30~90 entry 즉시 누적
- HISTORICAL phase 진입 가속

**v1.4 정합 결정**: **옵션 A 채택**. 이유:
- backfill source가 불명 (backtest_stats.json은 매 cycle 덮어쓰므로 과거 snapshot 없음)
- git history에서 backtest_stats.json 과거 commit 추출은 별도 sprint 범위
- v1.4 §17 4 phase 자연 진화 (cold-start → effective_n → historical) 정합

옵션 B 진입 시 별도 명령서 (out-of-scope).

---

## §3. P1 작업 — 검증 + 운영 통합

### 3-1. Mock 시나리오

`tests/mock/backtest_history/`:

| 시나리오 | 기대 동작 |
|---|---|
| `scenario_first_append.json` (history 미존재) | append 1건, retention 무영향 |
| `scenario_idempotent.json` (today entry 존재) | skipped, append 무시 |
| `scenario_retention_lru.json` (95 entry 누적, 5 entry retention 외) | 90 entry 유지, 5 entry 삭제 |
| `scenario_periods_14d_missing.json` | skipped, periods.14d missing |
| `scenario_backtest_stats_missing.json` | skipped, backtest_stats.json missing |

### 3-2. pytest

`tests/test_backtest_history_append.py` — parametrize 5건 + summary.

### 3-3. brain_distribution_evaluator 통합

v1.4 §6-1: HISTORICAL phase에서 historical mean baseline 산출 source = 본 jsonl.

`brain_distribution_evaluator.py`에 `history_fetcher` 인자 추가 (이미 P0/P1 코드에 있을 수 있음, 확인 의무):

```python
def evaluate(
    ...,
    history_fetcher=None,  # backtest_stats_history.jsonl loader
):
    if history_fetcher is not None:
        history = history_fetcher()  # mock or 운영
        if len(history) >= 90:
            baseline = _compute_historical_mean(history[-90:])
            sigma = _compute_historical_sigma(history[-90:])
            phase = "HISTORICAL"
        else:
            # cold-start or accumulating
            ...
```

### 3-4. cron 작동 verification

배포 후 1일 후 검증:
- backtest_stats_history.jsonl에 1 entry 누적 확인
- entry schema 정합
- idempotent 검증 (같은 날 수동 호출 시 skipped)

---

## §4. 절대 하지 말 것

1. **backtest_stats.json 수정 X** — read-only 참조만.
2. **trust_score.py 수정 X** — 방식 B 정신.
3. **신규 service / 신규 Railway project 생성 X** — 룰 10 cohabitation. 기존 VERITY service 내 cron 추가만.
4. **retention 90일 변경 X** — v1.4 §6-1 정합.
5. **schema 변경 X** — date / timestamp / snapshot.periods.14d 그대로.
6. **idempotent 보장 누락 X** — 같은 날 중복 append 시 데이터 중복 = baseline 산출 오류.
7. **ESTATE 트랙 자산 0**.
8. **backfill 1회 시도 X** — 옵션 A 채택. 별도 sprint.

---

## §5. 보고 양식

### 결정사항 표

| # | 항목 | 산출물 |
|---|---|---|
| 1 | api/cron/backtest_history_append.py 신규 | line 수 + 함수 list |
| 2 | data/metadata/backtest_stats_history.jsonl 신설 | path 확인 (mkdir 처리) |
| 3 | Railway cron 등록 | (Railway 인프라 형식 실측 + 등록 결과) |
| 4 | mock 시나리오 5건 | tests/mock/backtest_history/ |
| 5 | pytest 5/5 PASSED | tests/test_backtest_history_append.py |
| 6 | brain_distribution_evaluator 통합 | history_fetcher 추가 (또는 기존 인자 활용) |
| 7 | 배포 후 1일 검증 | (1일 후 cron 작동 보고) |

### 컴플라이언스 체크

- 절대 하지 말 것 8건 위반 0건
- 메모리 룰 자체 점검 (특히 룰 10 cohabitation, 룰 1 schema 실측 — Railway cron 형식)
- v1.4 §6 / §16 / §17 직접 인용

### 다음 step 진입 OK 요청

cron 등록 + 1일 검증 보고 후 STOP. P2 wire 명령서 진입은 Sprint 1.5 종료 + 본 sprint 종료 둘 다 만족 후.

---

STOP — 보고 후 사용자 다음 지시 대기.
