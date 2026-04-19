# VERITY 검수 리포트 — SESSION 4 (VAMS + Telegram Bot)

**대상:** `api/vams/engine.py`, `api/notifications/telegram_bot.py`
**연관 파일:** `api/intelligence/strategy_evolver.py`, `api/intelligence/periodic_report.py`, `api/predictors/backtester.py`, `api/config.py`, `api/main.py`, `.github/workflows/daily_analysis.yml`
**검수 범위:** VAMS 매매 로직 정확성 · 통계 무결성 · 동시성 / Telegram 권한 검증 · 전략 승인 플로우

---

## 🔴 CRITICAL

### CRIT-9. `rollback_strategy()`가 실제로 constitution을 되돌리지 않음
**api/intelligence/strategy_evolver.py > Line 470~494 + api/notifications/telegram_bot.py > Line 532~544 > [롤백 명령이 기능 미구현]**

**현상:**
```python
470:  def rollback_strategy() -> Optional[int]:
471:      """직전 버전의 constitution으로 롤백."""
472:      registry = _load_registry()
473:      versions = registry.get("versions", [])
474:      if len(versions) < 2:
475:          return None
476:
477:      constitution = _load_constitution()     # ← 로드하지만
478:      prev = versions[-2]                      # ← 이전 버전 메타만 읽음
479:      current_ver = registry["current_version"]
480:
481:      registry["current_version"] = current_ver + 1
482:      registry["versions"].append({...})       # ← registry에 "rollback" 엔트리만 추가
483:      _save_registry(registry)
484:                                                # ← _save_constitution 호출 없음!
485:      return current_ver + 1
```

`constitution`을 로드만 하고 한 글자도 수정·저장하지 않는다. `versions[-2]`에는 이전 **메타데이터**(version 번호, timestamp, reason)만 있고 **실제 가중치 스냅샷이 없다**. 즉 사령관이 텔레그램에서 `/rollback_strategy`를 보내면:
- 봇은 "✅ 전략 롤백 완료 (v7)" 응답
- 실제 `verity_constitution.json`은 **바뀌지 않음**
- 손실 유발한 가중치가 다음 full 분석에도 그대로 적용됨

**수정:** `apply_proposal` 시점에 이전 constitution 스냅샷을 registry에 저장하고, `rollback_strategy`에서 그 스냅샷으로 복원.

```python
# strategy_evolver.py
import shutil

_CONSTITUTION_BACKUP_DIR = os.path.join(
    os.path.dirname(_CONSTITUTION_PATH), "constitution_backups"
)


def _save_constitution(const: Dict[str, Any]):
    """원자적 쓰기 + 이전 버전 .bak 보존."""
    os.makedirs(os.path.dirname(_CONSTITUTION_PATH) or ".", exist_ok=True)
    tmp = _CONSTITUTION_PATH + ".tmp"
    bak = _CONSTITUTION_PATH + ".bak"
    if os.path.exists(_CONSTITUTION_PATH):
        shutil.copy2(_CONSTITUTION_PATH, bak)
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(const, f, ensure_ascii=False, indent=2, allow_nan=False)
        os.replace(tmp, _CONSTITUTION_PATH)
    except Exception:
        if os.path.exists(bak):
            shutil.copy2(bak, _CONSTITUTION_PATH)
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
    # 버전별 아카이브 — rollback이 사용할 소스
    os.makedirs(_CONSTITUTION_BACKUP_DIR, exist_ok=True)
    stamp = now_kst().strftime("%Y%m%dT%H%M%S")
    shutil.copy2(_CONSTITUTION_PATH, os.path.join(_CONSTITUTION_BACKUP_DIR, f"constitution_{stamp}.json"))


def apply_proposal(proposal: Dict[str, Any], backtest_result: Dict[str, Any]):
    constitution = _load_constitution()
    registry = _load_registry()
    changes = proposal.get("changes", {})

    # 롤백을 위해 변경 전 관련 섹션 스냅샷을 저장
    snapshot = {
        "fact_score_weights": dict((constitution.get("fact_score", {}) or {}).get("weights", {})),
        "sentiment_score_weights": dict((constitution.get("sentiment_score", {}) or {}).get("weights", {})),
        "grade_thresholds": {
            g: info.get("min_brain_score")
            for g, info in (constitution.get("decision_tree", {}) or {}).get("grades", {}).items()
        },
    }

    if changes.get("fact_score_weights"):
        constitution.setdefault("fact_score", {}).setdefault("weights", {})
        constitution["fact_score"]["weights"].update(changes["fact_score_weights"])
    if changes.get("sentiment_score_weights"):
        constitution.setdefault("sentiment_score", {}).setdefault("weights", {})
        constitution["sentiment_score"]["weights"].update(changes["sentiment_score_weights"])
    if changes.get("grade_thresholds"):
        grades = constitution.setdefault("decision_tree", {}).setdefault("grades", {})
        for grade, score in changes["grade_thresholds"].items():
            if grade in grades:
                grades[grade]["min_brain_score"] = score

    _save_constitution(constitution)

    new_version = registry.get("current_version", 1) + 1
    registry["current_version"] = new_version
    registry["versions"].append({
        "version": new_version,
        "applied_at": now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "proposed_by": proposal.get("_model", CLAUDE_MODEL_DEFAULT),
        "change_summary": proposal.get("reason", ""),
        "reason": proposal.get("expected_improvement", ""),
        "backtest_before": None,
        "backtest_after": backtest_result,
        "actual_performance": None,
        "pre_change_snapshot": snapshot,   # ← 추가: 롤백에 사용
    })
    stats = registry.setdefault("cumulative_stats", {})
    stats["accepted"] = stats.get("accepted", 0) + 1
    _check_auto_approve_transition(registry)
    _save_registry(registry)
    return new_version


def rollback_strategy() -> Optional[int]:
    """직전 apply_proposal 직전 스냅샷으로 constitution을 실제 복원."""
    registry = _load_registry()
    versions = registry.get("versions", [])
    if not versions:
        return None

    # 가장 최근 적용된 버전에 pre_change_snapshot이 있으면 그대로 되돌림
    target = None
    for v in reversed(versions):
        if v.get("pre_change_snapshot"):
            target = v
            break
    if not target:
        return None

    snap = target["pre_change_snapshot"]
    constitution = _load_constitution()
    if "fact_score_weights" in snap:
        constitution.setdefault("fact_score", {})["weights"] = dict(snap["fact_score_weights"])
    if "sentiment_score_weights" in snap:
        constitution.setdefault("sentiment_score", {})["weights"] = dict(snap["sentiment_score_weights"])
    if "grade_thresholds" in snap:
        grades = constitution.setdefault("decision_tree", {}).setdefault("grades", {})
        for g, score in snap["grade_thresholds"].items():
            if g in grades and score is not None:
                grades[g]["min_brain_score"] = score
    _save_constitution(constitution)

    current_ver = registry["current_version"]
    new_ver = current_ver + 1
    registry["current_version"] = new_ver
    registry["versions"].append({
        "version": new_ver,
        "applied_at": now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "proposed_by": "rollback",
        "change_summary": f"v{current_ver} 롤백 → v{target['version']} 기반 복원",
        "reason": "사령관 롤백 명령",
        "backtest_before": None,
        "backtest_after": None,
        "actual_performance": None,
        "rolled_back_from": current_ver,
        "rolled_back_to_snapshot_of": target["version"],
    })
    _save_registry(registry)
    return new_ver
```

---

### CRIT-10. 치명적 텔레그램 명령이 화이트리스트 미설정 시 누구나 실행
**api/notifications/telegram_bot.py > Line 778~836 + Line 119~128 > [기본값이 `open-to-all`]**

**현상:** `run_poll_once` Line 815의 게이트:
```python
815:  if TELEGRAM_ALLOWED_CHAT_IDS and chat_id not in TELEGRAM_ALLOWED_CHAT_IDS:
816:      print(f"[TelegramBot] 허용 목록에 없는 chat_id 무시: {chat_id}")
817:  else:
818:      print(f"[TelegramBot] 질의: {text}")
819:      answer = handle_query(text)
```
`TELEGRAM_ALLOWED_CHAT_IDS`가 **비어 있으면 `and` 쇼트서킷**으로 체크 자체가 건너뛰어져 **모든 chat_id에 응답**. 이 상태에서 누군가 bot_token을 탈취하거나 우연히 동일 봇에 메시지를 보내면 다음 명령을 모두 실행할 수 있다:
- `/approve_strategy` → Claude가 제안한 가중치가 본인 권한 없이 바로 반영
- `/rollback_strategy` → 프로덕션 전략 임의 롤백
- `/set_regime overheat` → 경제 분면 수동 오버라이드
- `/approve_strategy quarterly` → 분기 Constitution 패치 승인

심지어 이 명령 개별에 대한 **관리자 역할 분리가 없다** — 읽기 전용 쿼리(/포트폴리오, /브리핑)와 상태 변경(승인/롤백)이 동일 권한 티어.

**수정:** 상태 변경 명령에 대한 명시적 admin 체크를 추가하고, 화이트리스트 미설정 시 기본적으로 거부(fail-closed).

```python
# config.py에 관리자 전용 화이트리스트 추가 (telegram 일반 허용과 별도)
TELEGRAM_ADMIN_CHAT_IDS: Optional[FrozenSet[int]] = None  # 아래 parser 정의

def _parse_telegram_admin_chat_ids() -> Optional[FrozenSet[int]]:
    raw = os.environ.get("TELEGRAM_ADMIN_CHAT_IDS", "").strip()
    if not raw:
        return None
    ids = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.append(int(part))
        except ValueError:
            pass
    return frozenset(ids) if ids else None

TELEGRAM_ADMIN_CHAT_IDS = _parse_telegram_admin_chat_ids()
```

```python
# telegram_bot.py — 상태변경 명령 세트와 admin 가드
from api.config import TELEGRAM_ADMIN_CHAT_IDS

_ADMIN_COMMANDS = (
    "/approve_strategy",
    "/reject_strategy",
    "/rollback_strategy",
    "/set_regime",
    "/run_research",
)


def _is_admin_command(text: str) -> bool:
    t = text.strip().lower()
    return any(t.startswith(c) for c in _ADMIN_COMMANDS)


def _is_admin(chat_id: int) -> bool:
    # 명시적 admin 화이트리스트 미설정 시 fail-closed: 아무도 admin이 아님
    if TELEGRAM_ADMIN_CHAT_IDS is None:
        return False
    return chat_id in TELEGRAM_ADMIN_CHAT_IDS


# run_poll_once 내부
for update in data.get("result", []):
    update_id = update["update_id"]
    message = update.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    text = message.get("text", "")

    if text and chat_id:
        # 1차: 일반 허용 목록 (응답 자체를 가를지)
        if TELEGRAM_ALLOWED_CHAT_IDS and chat_id not in TELEGRAM_ALLOWED_CHAT_IDS:
            print(f"[TelegramBot] 허용 목록에 없는 chat_id 무시: {chat_id}")
            offset = update_id + 1
            continue
        # 2차: 상태변경 명령은 admin만
        if _is_admin_command(text) and not _is_admin(chat_id):
            send_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": "⛔ 권한 없음: 이 명령은 관리자 전용입니다.",
                "parse_mode": "HTML",
            }
            try:
                req.post(send_url, json=payload, timeout=10)
            except Exception:
                pass
            offset = update_id + 1
            continue
        print(f"[TelegramBot] 질의: {text}")
        answer = handle_query(text)
        # ...기존 송신 로직 그대로
    offset = update_id + 1
```

환경변수 운영 지침:
- `TELEGRAM_ALLOWED_CHAT_IDS`: 응답 수신 허용 목록 (읽기 권한)
- `TELEGRAM_ADMIN_CHAT_IDS`: 상태변경 명령 허용 목록 (쓰기 권한, 반드시 명시 설정)

---

### CRIT-11. portfolio.json 동시 수정 race condition (15분 크론 겹침)
**api/vams/engine.py > save_portfolio / run_vams_cycle + `.github/workflows/daily_analysis.yml` > [lost-update]**

**현상:** `save_portfolio`는 tmp+replace로 **단일 쓰기**는 원자적이지만, **read-modify-write 사이클 전체는 보호되지 않는다**.

시나리오:
- T=0s: cron A (realtime) 시작, `load_portfolio()` → state₀
- T=3s: cron B (realtime_us, 15분 오프셋인데 네트워크 지연 등으로 겹침) 시작, `load_portfolio()` → state₀ (동일)
- T=10s: A가 state₀ + 매수 1건 + 매도 2건 반영 → save (state_A)
- T=11s: B가 state₀ + 다른 매수 1건 반영 → save (state_B)
- → A의 매수/매도가 **통째로 사라짐**. 동일 종목이 두 크론에 의해 **중복 매수 가능** (각자 held_tickers 체크 시점에 반대쪽 매수가 미반영).

또한 `history.json`도 같은 패턴(Line 171~175 `save_history`)인데 이쪽은 아예 backup조차 없다.

**수정:** `fcntl` 기반 advisory lock으로 read-modify-write 전 사이클을 보호.

```python
# api/vams/engine.py 상단
import errno
import fcntl
from contextlib import contextmanager

_LOCK_PATH = os.path.join(DATA_DIR, ".portfolio.lock")


@contextmanager
def _portfolio_lock(timeout_sec: int = 60):
    """파일 기반 advisory lock. timeout 초과 시 RuntimeError."""
    os.makedirs(DATA_DIR, exist_ok=True)
    start = time.time()
    fd = os.open(_LOCK_PATH, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as e:
                if e.errno not in (errno.EAGAIN, errno.EACCES):
                    raise
                if time.time() - start > timeout_sec:
                    raise RuntimeError(f"portfolio lock timeout after {timeout_sec}s")
                time.sleep(0.5)
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)
```

호출부(`api/main.py`의 run_vams_cycle 부근, VAMS 사이클 실행 블록)를 락으로 감싼다:

```python
# api/main.py (VAMS 사이클 실행 부근)
from api.vams.engine import _portfolio_lock

with _portfolio_lock(timeout_sec=60):
    portfolio = load_portfolio()
    # ... (VAMS 사이클, 기타 수정) ...
    save_portfolio(portfolio)
```

GitHub Actions 레벨 보호로는 워크플로우 동시성 제어:
```yaml
# .github/workflows/daily_analysis.yml 상단
concurrency:
  group: verity-portfolio-write
  cancel-in-progress: false
```
(cancel-in-progress: false로 큐잉 — 실행 중 잡이 끝날 때까지 대기). 이 2중 방어가 권고.

---

## 🟡 WARNING

### WARN-14. `_save_constitution` / `_save_registry` 원자적 쓰기·백업 부재
**api/intelligence/strategy_evolver.py > Line 62~64, 109~111 > [부분 쓰기 시 JSON 손상]**

**현상:**
```python
62:  def _save_constitution(const: Dict[str, Any]):
63:      with open(_CONSTITUTION_PATH, "w", encoding="utf-8") as f:
64:          json.dump(const, f, ensure_ascii=False, indent=2)
```
`open(..., "w")`는 즉시 파일을 truncate한다. `json.dump` 도중 예외(디스크 풀, 권한, kill)가 발생하면 constitution.json이 잘린 채 남는다. 다음 실행에서 `_load_constitution`이 `JSONDecodeError`를 먹고 빈 dict 반환 → 전체 VCI 임계값·Cohen 보너스 등이 기본값으로 강등.

**수정코드:** (CRIT-9의 `_save_constitution` 수정코드에 이미 포함). `_save_registry`도 동일 패턴 적용:

```python
def _save_registry(reg: Dict[str, Any]):
    os.makedirs(os.path.dirname(STRATEGY_REGISTRY_PATH) or ".", exist_ok=True)
    tmp = STRATEGY_REGISTRY_PATH + ".tmp"
    bak = STRATEGY_REGISTRY_PATH + ".bak"
    if os.path.exists(STRATEGY_REGISTRY_PATH):
        try:
            shutil.copy2(STRATEGY_REGISTRY_PATH, bak)
        except Exception:
            pass
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(reg, f, ensure_ascii=False, indent=2, default=str, allow_nan=False)
        os.replace(tmp, STRATEGY_REGISTRY_PATH)
    except Exception:
        if os.path.exists(bak):
            shutil.copy2(bak, STRATEGY_REGISTRY_PATH)
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
```

`telegram_bot.py`의 `_handle_set_regime` Line 666~675도 동일 문제 — 직접 `open(const_path, "w")`로 constitution 덮어쓰기. `_save_constitution`을 import해서 쓰도록 변경:

```python
# telegram_bot.py _handle_set_regime 내부
from api.intelligence.strategy_evolver import _load_constitution, _save_constitution
const = _load_constitution()
const.setdefault("decision_tree", {})["quadrant_override"] = quadrant
_save_constitution(const)  # 원자적 쓰기 + 백업
```

---

### WARN-15. `recalculate_total`이 `VAMS_INITIAL_CASH=0` 일 때 ZeroDivisionError
**api/vams/engine.py > Line 456~458 > [환경변수 잘못 설정 시 크래시]**

**현상:**
```python
456:  portfolio["vams"]["total_return_pct"] = round(
457:      ((total - VAMS_INITIAL_CASH) / VAMS_INITIAL_CASH) * 100, 2
458:  )
```
`VAMS_INITIAL_CASH = _env_int("VAMS_INITIAL_CASH", 10_000_000)` — `0`이나 음수 입력 시 ZeroDivisionError 또는 허위 `total_return_pct` 산출.

**수정코드:**
```python
def recalculate_total(portfolio: dict):
    """총 자산 및 수익률 재계산"""
    holdings_value = sum(
        h["current_price"] * h["quantity"] for h in portfolio["vams"]["holdings"]
    )
    total = portfolio["vams"]["cash"] + holdings_value
    portfolio["vams"]["total_asset"] = total
    initial = VAMS_INITIAL_CASH if VAMS_INITIAL_CASH > 0 else 1  # 0/음수 방어
    portfolio["vams"]["total_return_pct"] = round(
        ((total - initial) / initial) * 100, 2
    )
```

또는 config.py 쪽에서 강제:
```python
VAMS_INITIAL_CASH = max(1, _env_int("VAMS_INITIAL_CASH", 10_000_000))
```

---

### WARN-16. `periodic_report.py` max_drawdown 정의 오류 — global min/max 사용
**api/intelligence/periodic_report.py > Line 397~399 > [drawdown 과대 보고]**

**현상:**
```python
397:  peak = max((a["total_asset"] for a in asset_history), default=0)
398:  trough = min((a["total_asset"] for a in asset_history), default=0)
399:  drawdown = round((trough - peak) / peak * 100, 2) if peak else 0
```
**Max Drawdown의 표준 정의**는 "각 시점까지의 running max로부터의 최대 하락". 위 식은 시퀀스와 무관한 global min/max를 사용한다.

예: 자산 추이 [50, 100, 200, 150] →
- 표준 max DD: 200 → 150 = **-25%**
- 위 식: (50-200)/200 = **-75%** ❌

운영 초기 자산 증가 국면에서 drawdown을 과대 보고 → 의사결정 왜곡.

**수정코드:**
```python
def _compute_max_drawdown(asset_history: list) -> float:
    """표준 정의의 max drawdown (%): running peak 대비 최대 하락률. 0 이하."""
    if not asset_history:
        return 0.0
    running_peak = None
    max_dd = 0.0
    for a in asset_history:
        v = a.get("total_asset", 0)
        if not v or v <= 0:
            continue
        if running_peak is None or v > running_peak:
            running_peak = v
        else:
            dd = (v - running_peak) / running_peak * 100
            if dd < max_dd:
                max_dd = dd
    return round(max_dd, 2)


# Line 397~399 교체
peak = max((a["total_asset"] for a in asset_history), default=0)
trough = min((a["total_asset"] for a in asset_history), default=0)
drawdown = _compute_max_drawdown(asset_history)
```

---

## 🟢 INFO

### INFO-8. VAMS 매도→매수 순서 올바름
**api/vams/engine.py > Line 482~529 > [확인됨]**

Line 482-489에서 손절/익절 루프 → Line 510-529에서 신규 매수. 매도로 확보된 현금이 같은 사이클의 `portfolio["vams"]["cash"]`에 반영된 후 `execute_buy` Line 312 `cash = portfolio["vams"]["cash"]`로 읽히므로 **매도 대금을 즉시 매수에 사용 가능**. ✅

### INFO-9. 손절 공식 및 트레일링 로직 정확성
**api/vams/engine.py > Line 194, 199~206 > [확인됨]**

`return_pct = ((current_price - buy_price) / buy_price) * 100` — 수학적으로 올바름. `buy_price` 는 `execute_buy` Line 317에서 0 이하 거부하므로 ZeroDivisionError 경로 없음.

트레일링 스톱: `update_holdings_price` Line 442-443에서 `highest_price`를 지속적으로 갱신하고, `check_stop_loss`는 이 값을 그대로 사용. Line 199-201의 로컬 업데이트는 **비지속적이지만 update_holdings_price가 선행(run_vams_cycle Line 479)되므로 실효성에 영향 없음**. ✅

### INFO-10. win_rate / avg_return ZeroDivisionError 방어
**api/predictors/backtester.py > Line 85~86, 110 + api/main.py > Line 850 > [확인됨]**

`backtester.py` 85~86: `if not trades: return _empty_result()` 가 선행되어 Line 110의 `wins / len(trades)`는 안전.
`main.py` 850: `win_rate = round(wins / total_trades * 100, 1) if total_trades else 0` — 명시적 가드.

### INFO-11. 보유 기간 비교 timezone 처리
**api/vams/engine.py > Line 208~211 > [확인됨]**

`buy_date` 는 `now_kst().strftime("%Y-%m-%d")`로 기록되므로 KST 날짜. `datetime.strptime(..., "%Y-%m-%d")`는 naive. `now_kst().replace(tzinfo=None)`도 naive(값은 KST 기준 시각). 둘 다 동일 naive-KST 컨벤션이므로 `.days` 계산 정확. ✅

### INFO-12. 복리/단리 사용 구분
**api/predictors/backtester.py > Line 91~100 > [확인됨 — 단리]**

`cum += r` 누적은 **단리 합산**. 짧은 보유 기간(수일~수주)의 연속 트레이드에서는 근사값으로 충분하지만 장기 백테스트에서는 복리가 정확. 현행 구현은 단리 전제이며 코드 주석에 명시만 되면 OK.

---

## 요약 (심각도순)

| # | 파일 | Line | 유형 | 영향 |
|---|---|---|---|---|
| 🔴 CRIT-9 | strategy_evolver.py | 470~494 | 기능 버그 | /rollback_strategy 가 constitution을 되돌리지 않음 |
| 🔴 CRIT-10 | telegram_bot.py | 778~836, 119~128 | 권한 부재 | 화이트리스트 미설정 시 누구나 상태변경 명령 실행 |
| 🔴 CRIT-11 | vams/engine.py + workflows | 전역 | 동시성 | 크론 겹침 시 portfolio lost-update / 종목 중복 매수 |
| 🟡 WARN-14 | strategy_evolver.py | 62~64, 109~111 | 원자성 | 쓰기 중 실패 시 JSON 손상, 백업 부재 |
| 🟡 WARN-15 | vams/engine.py | 456~458 | 엣지케이스 | VAMS_INITIAL_CASH=0 시 ZeroDivisionError |
| 🟡 WARN-16 | periodic_report.py | 397~399 | 정의 오류 | max_drawdown 과대 보고(글로벌 min/max) |
| 🟢 INFO-8 | vams/engine.py | 482~529 | 확인 | 매도→매수 순서 정상 |
| 🟢 INFO-9 | vams/engine.py | 194, 199~206 | 확인 | 손절/트레일링 공식 정확 |
| 🟢 INFO-10 | backtester.py, main.py | 85, 110, 850 | 확인 | win_rate zero-div 방어 존재 |
| 🟢 INFO-11 | vams/engine.py | 208~211 | 확인 | 보유기간 timezone 처리 정상 |
| 🟢 INFO-12 | backtester.py | 91~100 | 확인 | 단리 누적(문서화 권고) |

---

## 검수 원칙 기준 제외 항목
- **VAMS TASK 2 avg_return 빈 리스트**: 이미 total>0 체크 선행. 이슈 없음.
- **VAMS TASK 2 max_drawdown 부호**: backtester.py는 표준(peak-cum으로 양수 보고), periodic_report는 부호 포함(음수) — 두 컨벤션이 섞였지만 각 호출부에서 표기가 일관되면 버그 아님. periodic_report 자체 정의 오류는 WARN-16에서 다룸.
- **TELEGRAM TASK 1 개별 핸들러 화이트리스트 재검증**: `handle_query`는 유일 엔트리이므로 엔트리 한 곳 가드로 충분. 단 "미설정 시 전원 허용" 기본값이 문제의 핵심 — CRIT-10에서 다룸.
- **TELEGRAM TASK 2 constitution 트랜잭션**: apply_proposal 후 `_save_constitution` + `_save_registry`가 2-phase가 아니다 (첫 성공, 둘째 실패 시 부분 상태). 현실적으로 파일 2개를 원자적으로 묶을 방법은 journaling DB 도입뿐. 백업 + order(`constitution먼저` → 성공 시 registry)로 완화는 가능하나 별도 설계 이슈로 본 세션 범위에서 제외.
