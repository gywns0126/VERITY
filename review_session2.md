# VERITY 검수 리포트 — SESSION 2

**대상:** `api/main.py` (3348줄)
**연관 파일:** `api/health.py`, `api/config.py`, `api/vams/engine.py`, `.github/workflows/*.yml` (5개)
**검수 범위:** Deadman Switch, 모드 분기, Git Conflict, NaN/Infinity sanitize, 예외 처리 누락

---

## 🔴 CRITICAL

### CRIT-3. 캔디데이트 분석 루프 외부 try/except 부재 → 종목 1개 실패 시 전체 루프 사망
**api/main.py > Line 1838~1958, Line 427~475 > [예외 전파로 분석 파이프라인 전체 중단]**

**현상:** `for i, stock in enumerate(candidates)` 루프 내부에서 외부 API를 **try 없이 직접 호출**:
```python
1844:  tech = analyze_technical(ticker_yf)                 # NO try/except
1883:  flow = compute_us_flow(stock)                       # NO try/except
1885:  flow = get_investor_flow(ticker)                    # NO try/except
1889:  sentiment = get_stock_sentiment(...)                # NO try/except
1919:  raw_c = scout_consensus(ticker)                     # NO try/except
1922:  cblock = build_consensus_block(...)                 # NO try/except
1931:  mf = compute_multi_factor_score(...)                # NO try/except
1986:  stock["timing"] = compute_timing_signal(stock)      # NO try/except (별도 for문)
```
동일 패턴이 Line 438, 444, 453, 457, 467에도 재현. 한 종목 분석 중 yfinance timeout, DART 장애, 네트워크 reset 발생 시 **loop 전체가 ExceptionBailout → 후속 모든 STEP 건너뜀**. `analyze_batch`, `verity_brain_analyze`, `save_portfolio` 모두 실행되지 않는다.

**수정코드 (Line 1838 loop 예시):**
```python
for i, stock in enumerate(candidates, 1):
    name = stock["name"]
    ticker = stock["ticker"]
    ticker_yf = stock.get("ticker_yf", f"{ticker}.KS")
    print(f"  [{i}/{len(candidates)}] {name}...", end="")
    try:
        tech = analyze_technical(ticker_yf)
        stock["technical"] = tech
        # ... (이하 현재 로직 전부 try 블록으로 감싸기) ...
    except Exception as _loop_err:
        print(f" ❌ 분석 실패: {_loop_err}")
        stock.setdefault("technical", {"rsi": None, "signals": []})
        stock.setdefault("flow", {"flow_score": 50, "flow_signals": []})
        stock.setdefault("sentiment", {"score": 50, "headline_count": 0, "top_headlines": [], "detail": []})
        stock.setdefault("consensus", {})
        stock.setdefault("multi_factor", {"multi_score": 50, "grade": "N/A"})
        continue
```
Line 1986의 timing loop도 동일 처리:
```python
for stock in candidates:
    try:
        stock["timing"] = compute_timing_signal(stock)
    except Exception:
        stock["timing"] = {"timing_score": 50}
```

---

### CRIT-4. briefing 실패 시 save_portfolio 미실행 → 전체 분석 결과 소실
**api/main.py > Line 1767, Line 3015~3018 > [최종 저장 블로킹]**

**현상:**
```python
3015:  briefing = generate_briefing(portfolio)
3016:  portfolio["briefing"] = briefing
3017:  portfolio["alerts"] = briefing.get("alerts", [])
3018:  print(f"  비서: {briefing['headline']}")       # KeyError 가능
```
`generate_briefing`이 예외 던지면 Line 3015에서 크래시 → Line 3029의 `[9] 저장 + 알림` 섹션(`save_portfolio`) 실행 안 됨. **7분짜리 full 분석 결과가 디스크에 한 글자도 쓰이지 않는다.** 동일 패턴이 realtime 경로(Line 1767)에도 존재.

**수정코드:**
```python
# Line 3015 부근
try:
    briefing = generate_briefing(portfolio)
except Exception as _e:
    print(f"  비서 생성 실패(무시): {_e}")
    briefing = {
        "headline": "브리핑 생성 실패",
        "alerts": [],
        "alert_counts": {"critical": 0, "warning": 0, "info": 0},
        "action_items": [],
    }
portfolio["briefing"] = briefing
portfolio["alerts"] = briefing.get("alerts", [])
print(f"  비서: {briefing.get('headline', '?')}")
counts = briefing.get("alert_counts", {})
print(f"  알림: CRITICAL {counts.get('critical', 0)} | WARNING {counts.get('warning', 0)} | INFO {counts.get('info', 0)}")

# Line 1767 realtime 블록도 동일하게 try/except 추가
```

---

## 🟡 WARNING

### WARN-5. git pull --rebase 충돌 시 복구 누락 → 5회 재시도 무한 실패
**.github/workflows/daily_analysis.yml > Line 202~206 (daily_analysis_full.yml:191, bond_etf_analysis.yml:81, export_trade_daily.yml:56, rss_scout.yml:57 동일) > [rebase 충돌 잔존]**

**현상:**
```bash
202:          for i in 1 2 3 4 5; do
203:            git pull --rebase origin "$BRANCH" && git push && PUSHED=true && break
204:            echo "Push attempt $i failed, retrying in $((i * 10))s..."
205:            sleep $((i * 10))
206:          done
```
`git pull --rebase` 중 data/portfolio.json에 **rebase 충돌**이 발생하면 로컬 저장소는 rebase-in-progress 상태로 남는다. 다음 반복에서 `git pull --rebase`는 "You have unmerged paths" 에러로 즉시 실패 → 5회 내내 같은 상태에서 실패 → `exit 1`. 동시에 돌던 다른 워크플로우 하나가 먼저 푸시하면 이 잡은 영영 반영 불가.

**수정코드 (5개 workflow 모두 동일 패턴 적용):**
```yaml
          BRANCH="${{ github.ref_name }}"
          PUSHED=false
          for i in 1 2 3 4 5; do
            # 이전 시도에서 미해결 rebase 상태 정리
            git rebase --abort 2>/dev/null || true
            git merge --abort 2>/dev/null || true
            # pull 전략: theirs 선호 (data/*.json은 항상 최신 원격본 승계)
            if git pull --rebase -X theirs origin "$BRANCH" && git push origin "$BRANCH"; then
              PUSHED=true
              break
            fi
            echo "Push attempt $i failed, retrying in $((i * 10))s..."
            sleep $((i * 10))
          done
          if [ "$PUSHED" != "true" ]; then
            echo "::error::All 5 push attempts failed"
            exit 1
          fi
```

---

### WARN-6. save_portfolio json.dump에 allow_nan=False 누락
**api/vams/engine.py > Line 130, 144, 158 > [JSON 스펙 위반 데이터 방출]**

**현상:**
```python
144:  json.dump(clean, f, ensure_ascii=False, indent=2, default=str)
```
`allow_nan=True`(Python 기본값)이므로 `_sanitize_nan`이 놓친 NaN/Infinity가 있으면 **문자열 "NaN" / "Infinity"를 파일에 직접 기록**한다. 이는 표준 JSON이 아니므로 브라우저 `JSON.parse()`가 터진다. 증거: `api/main.py:781`에 읽기 시점 `txt.replace("NaN", "null")` 워크어라운드가 이미 존재 — **NaN이 새는 경로가 있다는 실증**.

누락 가능 타입: pandas Timestamp/NaT, decimal.Decimal, np.datetime64, __float__를 가진 커스텀 객체, set, pandas Series.

**수정코드:**
```python
# vams/engine.py 세 군데 json.dump 호출에 allow_nan=False 추가
# Line 130
with open(rec_tmp, "w", encoding="utf-8") as f:
    json.dump(clean_full, f, ensure_ascii=False, indent=2, default=str, allow_nan=False)
os.replace(rec_tmp, rec_dest)

# Line 144
with open(tmp_path, "w", encoding="utf-8") as f:
    json.dump(clean, f, ensure_ascii=False, indent=2, default=str, allow_nan=False)
os.replace(tmp_path, dest_path)

# Line 158 (save_history)
with open(HISTORY_PATH, "w", encoding="utf-8") as f:
    json.dump(clean, f, ensure_ascii=False, indent=2, allow_nan=False)
```
`_sanitize_nan`이 2차 방어선 역할을 하도록 타입 확장:
```python
# api/vams/engine.py Line 73 _sanitize_nan 확장
def _sanitize_nan(obj):
    import numpy as np
    try:
        import pandas as pd
        _pd_na_types = (pd.Timestamp, type(pd.NaT))
    except ImportError:
        _pd_na_types = ()

    if obj is None:
        return None
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        v = float(obj)
        return None if math.isnan(v) or math.isinf(v) else v
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if _pd_na_types and isinstance(obj, _pd_na_types):
        # NaT는 falsy, 비교 시 NaN 유사 처리
        try:
            if obj != obj:  # NaT != NaT → True
                return None
        except Exception:
            pass
        return str(obj)
    if isinstance(obj, dict):
        return {k: _sanitize_nan(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set, frozenset)):
        return [_sanitize_nan(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return [_sanitize_nan(v) for v in obj.tolist()]
    return obj
```

---

### WARN-7. DEADMAN_FAIL_THRESHOLD env 파싱 방어 누락 (SESSION 1 WARN-3과 동일 패턴 확산)
**api/config.py > Line 241 > [환경변수 빈값 → import 크래시]**

**현상:**
```python
241:  DEADMAN_FAIL_THRESHOLD = int(os.environ.get("DEADMAN_FAIL_THRESHOLD", "3"))
```
SESSION 1에서 `STRATEGY_MIN_SNAPSHOT_DAYS`만 `_env_int` 헬퍼로 교체했으나 다른 `int(os.environ.get(...))` 패턴은 그대로 남아 있다. Actions secrets 빈 주입 시 모듈 import 실패 → 파이프라인 전체 다운.

**수정코드:**
```python
# config.py Line 241
DEADMAN_FAIL_THRESHOLD = _env_int("DEADMAN_FAIL_THRESHOLD", 3)
```
같은 위험이 있는 다른 `int(os.environ.get(...))` 호출도 전수 스캔:
```bash
grep -nE 'int\(os\.environ\.get\(' api/config.py
```
결과에 있는 모든 줄을 `_env_int` 또는 `_env_float(...)` 동등 헬퍼로 일괄 교체 권고.

---

### WARN-8. 모드 전환 시 이전 모드 전용 데이터 잔류 → 프론트에 스테일 표시
**api/main.py > Line 1055 load_portfolio + 전체 write 경로 > [상태 누적]**

**현상:** realtime/quick/full 공통으로 `portfolio = load_portfolio()`로 **기존 JSON 전체를 로드**하고 각 STEP이 자기 키만 덮어쓴다. full 전용 결과 키(`postmortem`, `quarterly_research`, `strategy_evolution`, `claude_morning`, `bubble_warning` 등)는 다음 full 실행까지 **최대 수시간~수일** 스테일 상태로 프론트에 노출된다.

특히 `macro_override`/`market_brain`이 quick 실행 시 `verity_brain_analyze`가 실제로 돌면 갱신되지만, quick 모드에서 이 함수가 건너뛰는 경로(realtime)에서는 **전날 패닉 오버라이드가 오늘 장중에도 살아있을 수 있다**.

**수정코드 (Line 1055 직후 모드 진입 시 강제 무효화):**
```python
portfolio = load_portfolio()
portfolio["updated_at"] = now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00")
portfolio["market_summary"] = market_summary
portfolio["macro"] = macro
portfolio["system_health"] = system_health

# 모드별 TTL이 지난 결과는 현재 실행에서 재계산하지 않을 거라면 비운다
_STALE_ON_MODE = {
    "realtime": ("postmortem", "quarterly_research", "strategy_evolution",
                 "claude_morning", "verity_brain"),
    "realtime_us": ("postmortem", "quarterly_research", "strategy_evolution",
                    "claude_morning", "verity_brain"),
}
for _k in _STALE_ON_MODE.get(mode, ()):
    v = portfolio.get(_k)
    # 타임스탬프 있으면 6시간 초과 시 파기
    try:
        ts = v.get("generated_at") or v.get("updated_at") if isinstance(v, dict) else None
        if ts:
            from datetime import datetime as _dt
            t = _dt.fromisoformat(ts.replace("+09:00", "+09:00"))
            if (now_kst() - t).total_seconds() > 6 * 3600:
                portfolio.pop(_k, None)
    except Exception:
        pass
```
간단 대안: full 모드 진입 시 해당 키들을 **무조건 `.pop`** 하고 이번 실행이 다시 채우게 한다.

---

## 🟢 INFO

### INFO-3. Deadman Switch 임계값-어노말리 조합 gap
**api/health.py > Line 546~549 > [애매한 조합 처리]**

**현상:**
```python
546:  anomaly_count = len(reasons)
547:  should_abort = anomaly_count >= 1 and len(failed_apis) >= DEADMAN_FAIL_THRESHOLD
548:  if not should_abort and anomaly_count >= 2:
549:      should_abort = True
```
- `failed_apis=3` + sanity=0 → reasons=["API 3개..."] → anomaly_count=1, failed=3 → abort. ✅
- `failed_apis=0` + sanity=2 → abort. ✅
- `failed_apis=2` + sanity=1 → anomaly_count=1 (사실상 2개 이상의 "이상 신호") → **abort 안 함**. 🟢

정상 범위 이탈 1건 + API 2개 다운은 실제로는 심각한 상태인데 스위치가 작동하지 않는다. 임계값 조정 또는 가중치 기반 판정이 바람직. 현재 로직의 원본 의도(3-API-down AND any-anomaly, OR 2-anomaly)는 유지되므로 버그는 아니지만 사각지대 존재.

**권고:**
```python
failed_api_count = len(failed_apis)
sanity_anomaly_count = anomaly_count - (1 if failed_api_count >= DEADMAN_FAIL_THRESHOLD else 0)
# API fail은 1당 1점, sanity anomaly는 1당 1.5점 가중
score = failed_api_count + sanity_anomaly_count * 1.5
should_abort = score >= 3.0 or failed_api_count >= DEADMAN_FAIL_THRESHOLD
```

---

### INFO-4. 모드 자동결정 경계는 정상
**api/main.py > Line 498~528 > [확인됨]**

`get_analysis_mode()`의 분기 순서:
- Line 517: `(hour==15 and minute>=30) or hour==16` → full (15:30–16:59)
- Line 520: `9<=hour<=15` → realtime (9:00–15:29, 왜냐하면 15:30부터는 517이 먼저 매칭)
- Line 523: `_is_us_market_close` → full_us
- Line 526: `_is_us_market_hours` → realtime_us
- else: quick

KST 15:29:59 → realtime, 15:30:00 → full, 16:00:00 → full, 17:00:00 → quick. 경계 전부 정상. 이슈 없음.

---

## 요약 (심각도순)

| # | 파일 | Line | 유형 | 영향 |
|---|---|---|---|---|
| 🔴 CRIT-3 | api/main.py | 1838~1958, 427~475, 1986 | 예외 전파 | 종목 1개 실패 → 전체 loop 사망 |
| 🔴 CRIT-4 | api/main.py | 1767, 3015 | 예외 전파 | briefing 실패 → save_portfolio 미실행 |
| 🟡 WARN-5 | .github/workflows/*.yml (5개) | retry loop | git rebase | 충돌 복구 불가 → 5회 재시도 무의미 |
| 🟡 WARN-6 | api/vams/engine.py | 130, 144, 158 | JSON 안전성 | NaN 유출 시 프론트 JSON.parse 실패 |
| 🟡 WARN-7 | api/config.py | 241 | env 파싱 | 빈값 주입 → import 크래시 (패턴 확산) |
| 🟡 WARN-8 | api/main.py | 1055 외 | 상태 잔류 | 이전 모드 데이터가 수시간 스테일 |
| 🟢 INFO-3 | api/health.py | 546~549 | 판정 gap | 2+1 조합이 abort 미발동 |
| 🟢 INFO-4 | api/main.py | 498~528 | 확인 | 모드 경계 정상 |

---

## 검수 원칙 기준 제외 항목
- **TASK 1 heartbeat 카운트 정확성**: `api_health` dict 구조상 API당 정확히 1회 +1. 이슈 없음.
- **TASK 1 sys.exit vs return**: Line 1053 `return`으로 `main()` 함수만 종료, 프로세스는 정상 종료. 이것이 의도된 동작이며 나머지 로직이 계속 실행되지 않음. 이슈 없음.
- **TASK 3 5회 재시도 각 pull 포함 여부**: `for i in 1..5` 루프 내부 `git pull --rebase && git push` — 매 반복마다 pull 수행. 패턴 자체는 올바름(복구 누락이 문제).
- **TASK 4 recommendations[] 중첩 객체**: `_sanitize_nan`이 재귀로 dict/list 모두 순회. 중첩 경로 누락 없음. 단 `allow_nan=False`는 별도 이슈(WARN-6).
