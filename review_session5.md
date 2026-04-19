# VERITY 검수 리포트 — SESSION 5 (CI/CD & Safety Layer)

**대상:** `.github/workflows/daily_analysis.yml`, `api/health.py`, `api/intelligence/alert_engine.py`
**연관 파일:** `.github/workflows/daily_analysis_full.yml`, `bond_etf_analysis.yml`, `export_trade_daily.yml`, `rss_scout.yml`, `api/notifications/telegram_dedupe.py`, `api/reports/pdf_generator.py`, `api/main.py`, `api/config.py`
**검수 범위:** GitHub Actions 크론 겹침 · 워크플로 의존성 · Health Check 완결성 · Alert 중복 발송 · PDF 생성 실패 처리

---

## 🔴 CRITICAL

### CRIT-12. `daily_analysis.yml` 자가 크론 중복 — 동일 UTC 분에 2~3개 엔트리 트리거
**.github/workflows/daily_analysis.yml > Line 18, 20, 24, 28 > [CI 자원 낭비 + 큐잉 지연]**

**현상:** 같은 UTC 시각에 복수 cron 라인이 동시에 매치:
```yaml
18:  - cron: '0,5,10,15,20,25,30,35,40 6 * * 1-5'   # 08~14:40
20:  - cron: '45,50,55 6 * * 1-5'                    # 06:45, 06:50, 06:55
24:  - cron: '10,20,30,40,50 8-15 * * 1-5'           # 08:10~15:50 :10,:20,:30,:40,:50
28:  - cron: '10,20,30,40,50 16-23 * * 0-4'          # 16:10~23:50
10:  - cron: '30,35,40,45,50,55 23 * * 0-4'          # 23:30, 23:35, ... 23:55
```

**실제 겹침 지점 (UTC 기준, dow 0-4 기준):**
- **23:30 / 23:40 / 23:50**: 10번 라인 + 28번 라인 **둘 다 매치** → `cancel-in-progress: false`이므로 두 job 큐잉. 한 사이클 10~15분이면 **30분 이상 밀림**.
- **16:30 / 16:40 / 16:50 (및 17:30/.../22:30 등)**: 28번 라인만 매치. 정상.
- **UTC 06:45 / 06:50 / 06:55**: 18번 + 20번 **둘 다 매치** → 중복 큐잉.

GitHub Actions는 cron이 정확한 UTC minute에 최대 "5분 오차" 허용하지만, **동시 매치 여부는 패턴 독립성**에 달려있다. 동일 minute 매치 시 두 개의 독립 트리거가 큐에 쌓인다.

또한 **`cancel-in-progress: false`는 graceful queue**이지만, 이전 job이 `git push` 도중이면 후속 job은 `git pull --rebase` 직후에도 또 다른 충돌 가능성. 동일 페이로드로 실행되는 두 job은 실질적 분석 결과가 동일하므로 **순수 CI 낭비**.

**수정코드 (라인 단위로 정리):**
```yaml
on:
  schedule:
    # ── KR Market ──
    - cron: '30,35,40,45,50,55 23 * * 0-4'   # KST 08:30~08:55 개장 전
    - cron: '0,5,10,15,20,25 0 * * 1-5'      # KST 09:00~09:25 개장 러시
    - cron: '30,45 0 * * 1-5'                # KST 09:30~09:45
    - cron: '*/15 1-5 * * 1-5'               # KST 10:00~14:45
    - cron: '0,5,10,15,20,25,30,35,40 6 * * 1-5'  # KST 15:00~15:40 종가 러시
    - cron: '45,50,55 6 * * 1-5'             # KST 15:45~15:55 마감 직후
    # ── 장외 (UTC 08~15) — 08시만 :00 정각 quick, 나머지는 realtime ──
    - cron: '0 8 * * 1-5'                    # UTC 08:00 quick (장외 시작)
    - cron: '20,40 8-15 * * 1-5'             # UTC 08:20~15:40 realtime (:10/:30/:50 제거 — 중복 줄이기)
    - cron: '0 9-15 * * 1-5'                 # UTC 09:00~15:00 quick (정시)
    # ── 저녁~새벽 (UTC 16~23, dow 0-4) ──
    - cron: '0 16-22 * * 0-4'                # UTC 16~22:00 quick
    - cron: '20,40 16-22 * * 0-4'            # UTC :20/:40 realtime
    # UTC 23시대는 '30,35,40,45,50,55' 라인이 담당하므로 :10/:20/... 중복 제거
    # ── US Market ──
    - cron: '0 13 * * 1-5'                   # KST 22:00 프리마켓
    - cron: '30 14 * * 1-5'                  # KST 23:30 미장 개장
    - cron: '0,30 15-20 * * 2-6'             # KST 00~05시
    - cron: '30,45 20 * * 2-6'               # KST 05:30~05:45 종가 러시
```
또는 운영 자동화 스크립트로 중복 탐지:
```python
# scripts/audit_crons.py (선택)
import re, yaml, pathlib
def audit(path):
    data = yaml.safe_load(open(path))
    crons = [s["cron"] for s in data["on"]["schedule"]]
    # (각 cron 패턴을 UTC minute set으로 expand, 교집합 탐지)
```

---

### CRIT-13. `validate_deadman_switch` 감시 대상에 핵심 수집기 다수 누락
**api/health.py > Line 220~232 > [데이터 블랙홀을 deadman이 감지 못함]**

**현상:** `check_api_health()`가 감시하는 API 집합:
```python
220:  checks = {
221:      "dart": ...,        # KR 재무
222:      "fred": ...,        # 미국 매크로
223:      "telegram": ...,    # 알림
224:      "gemini": ...,      # AI
225:      "anthropic": ...,   # AI
226:      "kipris": ...,      # 특허
227:      "public_data": ..., # 관세청
228:      "krx_open_api": ...,# KRX
229:  }
```

반면 코드가 의존하는 외부 데이터 소스:
- **Finnhub** (US 애널리스트 컨센서스, insider sentiment, 기관 보유, earnings surprises) — `api/collectors/finnhub_client.py`
- **Polygon** (US 프리마켓, 옵션 IV, 실시간 가격) — `api/clients/polygon_client.py`
- **SEC EDGAR** (10-K, 8-K, 재무 facts) — `api/collectors/sec_edgar`
- **Perplexity** (분기 리서치, 이벤트 인사이트) — `api/clients/perplexity_client.py`
- **yfinance** (기본 가격 소스 — API 키 불필요지만 rate limit 시 조용히 실패)
- **KIS Open API** (장중 실시간, 주문, 잔고 조회)
- **NewsAPI** (뉴스 헤드라인)

이 중 **Finnhub·SEC·Polygon** 3곳이 동시에 죽으면 **US 분석 파이프라인 전체가 더미 데이터로 채워지는데 deadman은 트리거되지 않는다** (dart/fred/telegram/gemini 4개는 정상이므로 threshold=3 미달).

**수정코드:**
```python
# api/config.py 에 키 추가
FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", "")
POLYGON_API_KEY = os.environ.get("POLYGON_API_KEY", "")
SEC_EDGAR_USER_AGENT = os.environ.get("SEC_EDGAR_USER_AGENT", "")
KIS_APP_KEY = os.environ.get("KIS_APP_KEY", "")
# (이미 있다면 재사용)
```

```python
# api/health.py — 새 프로브 추가
def _check_finnhub() -> tuple:
    from api.config import FINNHUB_API_KEY
    if not FINNHUB_API_KEY:
        return False, "키 미설정"
    r = requests.get(
        "https://finnhub.io/api/v1/quote",
        params={"symbol": "AAPL", "token": FINNHUB_API_KEY},
        timeout=_TIMEOUT,
    )
    if r.status_code == 200 and isinstance(r.json(), dict):
        return True, "정상"
    return False, f"HTTP {r.status_code}"


def _check_polygon() -> tuple:
    from api.config import POLYGON_API_KEY
    if not POLYGON_API_KEY:
        return False, "키 미설정"
    r = requests.get(
        "https://api.polygon.io/v2/aggs/ticker/AAPL/prev",
        params={"apiKey": POLYGON_API_KEY},
        timeout=_TIMEOUT,
    )
    if r.status_code == 200:
        return True, "정상"
    return False, f"HTTP {r.status_code}"


def _check_sec_edgar() -> tuple:
    from api.config import SEC_EDGAR_USER_AGENT
    if not SEC_EDGAR_USER_AGENT:
        return False, "User-Agent 미설정"
    r = requests.get(
        "https://data.sec.gov/submissions/CIK0000320193.json",  # Apple CIK
        headers={"User-Agent": SEC_EDGAR_USER_AGENT},
        timeout=_TIMEOUT,
    )
    if r.status_code == 200:
        return True, "정상"
    return False, f"HTTP {r.status_code}"


def _check_perplexity() -> tuple:
    from api.config import PERPLEXITY_API_KEY
    if not PERPLEXITY_API_KEY:
        return False, "키 미설정"
    # Perplexity는 호출당 과금 — 가벼운 models list 엔드포인트만
    r = requests.get(
        "https://api.perplexity.ai/models",
        headers={"Authorization": f"Bearer {PERPLEXITY_API_KEY}"},
        timeout=_TIMEOUT,
    )
    # 인증만 통과하면 정상. 200 또는 401 아닌 200계열 → 정상
    if 200 <= r.status_code < 300:
        return True, "정상"
    return False, f"HTTP {r.status_code}"


def check_api_health() -> dict:
    """모든 API 상태를 한 번에 점검"""
    checks = {
        "dart": _probe("DART", _check_dart),
        "fred": _probe("FRED", _check_fred),
        "telegram": _probe("Telegram", _check_telegram),
        "gemini": _probe("Gemini", _check_gemini),
        "anthropic": _probe("Anthropic", _check_anthropic),
        "kipris": _probe("KIPRIS", _check_kipris),
        "public_data": _probe("공공데이터", _check_public_data),
        "krx_open_api": _probe("KRX Open API", _check_krx_open_api),
        # 신규: US 분석 파이프라인 핵심
        "finnhub": _probe("Finnhub", _check_finnhub),
        "polygon": _probe("Polygon", _check_polygon),
        "sec_edgar": _probe("SEC EDGAR", _check_sec_edgar),
    }
    if ECOS_API_KEY:
        checks["ecos"] = _probe("ECOS", _check_ecos)
    from api.config import PERPLEXITY_API_KEY as _pk
    if _pk:
        checks["perplexity"] = _probe("Perplexity", _check_perplexity)
    return checks
```

`validate_deadman_switch`의 optional 리스트에 "이미 optional인 API"만 남기고, 새로 추가한 3개는 일반 필수 체크에 포함 권고.

---

### CRIT-14. CRITICAL 알림이 4시간 동안 억제되는 쿨다운 버그
**api/notifications/telegram_dedupe.py > Line 29~50 + api/main.py > Line 1829~1838 > [중요 이벤트 미전달]**

**현상:** realtime 알림 발송 로직:
```python
1829:  tg_alerts = [
1830:      a
1831:      for a in briefing.get("alerts", [])
1832:      if a.get("level") in ("CRITICAL", "WARNING")
1833:  ]
1834:  tg_alerts = filter_deduped_realtime_alerts(tg_alerts, portfolio)
```
`filter_deduped_realtime_alerts`는 **CRITICAL/WARNING을 동일하게 취급** — 동일 카테고리+메시지 fingerprint가 `TELEGRAM_ALERT_DEDUPE_HOURS` (기본 4시간) 내 이미 전송됐으면 suppress.

**시나리오:**
- 10:00 KOSPI -5% → CRITICAL 발송. dedupe에 기록.
- 10:15 여전히 -5% 지속 → 동일 메시지 suppress.
- 11:30 VIX > 40 신규 CRITICAL이지만 동일 category/message면 suppress.
- 14:00까지 CRITICAL 재발송 없음.

CRITICAL은 "**즉시 행동**"이 명시된 레벨(`alert_engine.py` Line 8 주석). 4시간 묵살은 설계 의도 위배.

**수정코드:**
```python
# api/config.py
TELEGRAM_CRITICAL_DEDUPE_MINUTES = _env_int("TELEGRAM_CRITICAL_DEDUPE_MINUTES", 30)
TELEGRAM_ALERT_DEDUPE_HOURS = _env_int("TELEGRAM_ALERT_DEDUPE_HOURS", 4)  # 기존
```

```python
# api/notifications/telegram_dedupe.py
from api.config import TELEGRAM_ALERT_DEDUPE_HOURS, TELEGRAM_CRITICAL_DEDUPE_MINUTES


def _ttl_for_alert(alert: Dict[str, Any]) -> float:
    """CRITICAL은 별도 짧은 쿨다운(기본 30분). 그 외는 기존 TELEGRAM_ALERT_DEDUPE_HOURS."""
    level = str(alert.get("level", "")).upper()
    if level == "CRITICAL":
        return max(1, TELEGRAM_CRITICAL_DEDUPE_MINUTES) * 60
    return max(1, TELEGRAM_ALERT_DEDUPE_HOURS) * 3600


def filter_deduped_realtime_alerts(
    alerts: List[Dict[str, Any]],
    portfolio: Dict[str, Any],
) -> List[Dict[str, Any]]:
    if not alerts:
        return []
    raw = portfolio.get(_META_KEY)
    bucket: Dict[str, float] = raw if isinstance(raw, dict) else {}
    portfolio[_META_KEY] = bucket

    now = time.time()
    # prune은 max TTL 기준으로
    max_ttl = max(1, TELEGRAM_ALERT_DEDUPE_HOURS) * 3600
    _prune_bucket(bucket, now, max_ttl)

    out: List[Dict[str, Any]] = []
    for a in alerts:
        fp = _fingerprint(a)
        last = bucket.get(fp)
        ttl = _ttl_for_alert(a)
        if last is not None and (now - float(last)) < ttl:
            continue
        out.append(a)
    return out


def mark_realtime_alerts_sent(
    portfolio: Dict[str, Any],
    alerts: List[Dict[str, Any]],
) -> None:
    if not alerts:
        return
    bucket = portfolio.setdefault(_META_KEY, {})
    if not isinstance(bucket, dict):
        bucket = {}
        portfolio[_META_KEY] = bucket
    now = time.time()
    max_ttl = max(1, TELEGRAM_ALERT_DEDUPE_HOURS) * 3600
    _prune_bucket(bucket, now, max_ttl)
    for a in alerts:
        bucket[_fingerprint(a)] = now
```

---

## 🟡 WARNING

### WARN-17. Cross-workflow 동시 실행 — bond_etf vs daily_analysis
**.github/workflows/bond_etf_analysis.yml + daily_analysis.yml > UTC 22:00 / 09:30 > [git push 충돌]**

**현상:**
- bond_etf: `'0 22 * * 0-4'` (UTC 22:00 Sun-Thu), `'30 9 * * 1-5'` (UTC 09:30 Mon-Fri)
- daily_analysis: 위 두 시각 모두 매치 (`0 16-23 * * 0-4` ∋ 22:00, `10,20,30,40,50 8-15 * * 1-5` ∋ 09:30)
- **다른 concurrency group** → 병렬 실행 → 동시에 `git add data/ && git commit && git push` → 한쪽 rebase 필요.

WARN-5(SESSION 2)의 rebase retry 로직으로 push 충돌 자체는 복구되지만, 두 잡이 동일 `data/portfolio.json` or `data/bonds.json`을 touch할 때 **rebase 머지 충돌**은 복구 안 됨. CRIT-11의 Python-level `portfolio_lock`은 같은 프로세스/인스턴스에서만 유효.

**수정코드 (workflow 레벨 단일 group):**
```yaml
# bond_etf_analysis.yml Line 20~23 교체
concurrency:
  # daily_analysis.* 와 동일 그룹으로 묶어 data/ 쓰기를 직렬화
  group: verity-data-write
  cancel-in-progress: false
```
```yaml
# daily_analysis.yml
concurrency:
  group: verity-data-write
  cancel-in-progress: false
```
```yaml
# daily_analysis_full.yml
concurrency:
  group: verity-data-write
  cancel-in-progress: false
```
```yaml
# export_trade_daily.yml
concurrency:
  group: verity-data-write
  cancel-in-progress: false
```
모든 `data/` 쓰기 워크플로우를 **하나의 group**에 통합하면 Actions 레벨에서 직렬화되어 git push 충돌 소거. 단점: 큐 지연 증가. daily 풀분석 7분 + bond 3분이 같은 시각에 매치되면 10분 큐잉.

`rss_scout`(news_flash.json만 씀)는 굳이 같은 group에 넣을 필요 없음.

---

### WARN-18. export_trade UTC 08:30 vs daily_analysis UTC 08:30 동시 실행
**.github/workflows/export_trade_daily.yml Line 7 + daily_analysis.yml Line 24 > [trade_analysis.json race]**

**현상:**
- export_trade: `'30 8 * * 1-5'` → UTC 08:30 Mon-Fri
- daily_analysis: `'10,20,30,40,50 8-15 * * 1-5'` → UTC 08:30 매치 → **동시 실행**
- export_trade는 `data/trade_analysis.json` 쓰고, daily_analysis `load_trade_export_by_ticker()`로 읽는다.
- tmp+replace 원자적 쓰기 덕에 **partial read는 없지만**, daily_analysis가 읽는 순간이 export_trade write **이전이면 전일 데이터로 분석됨** (무해하나 혼선).
- git push는 WARN-17 그룹 통합 해결에 포함됨.

**수정코드 (cron 시각 분리):**
```yaml
# export_trade_daily.yml Line 7
schedule:
  - cron: "15 8 * * 1-5"   # UTC 08:15 (기존 08:30 → 08:15로 15분 조기)
```
이렇게 하면 export_trade가 먼저 완료되고, UTC 08:30 daily_analysis realtime이 최신 trade_analysis.json을 읽는다. WARN-17의 group 통합과 병행 시 완전 직렬화.

---

### WARN-19. PDF 폰트 다운로드 timeout 부재 — 프로세스 행 가능
**api/reports/pdf_generator.py > Line 27~35 > [urllib.request.urlretrieve 무한 대기]**

**현상:**
```python
27:  def _ensure_fonts():
28:      os.makedirs(_FONT_DIR, exist_ok=True)
29:      for path, url in [(_FONT_PATH, _FONT_URL), (_FONT_BOLD_PATH, _FONT_BOLD_URL)]:
30:          if not os.path.exists(path):
31:              try:
32:                  urllib.request.urlretrieve(url, path)   # ← timeout 없음
33:              except Exception as e:
34:                  print(f"  폰트 다운로드 실패 ({url}): {e}")
```
`urlretrieve`는 기본 timeout이 **없음**(`socket._GLOBAL_DEFAULT_TIMEOUT`). GitHub 네트워크가 느리거나 DNS 실패 시 수분~무한 대기 → GitHub Actions 90분 timeout까지 점유 가능. 현재 `fonts/` 디렉터리에 TTF가 이미 존재하므로 로컬 개발 환경에서나 발생하지만 CI 재설치 상황에서 위험.

**수정코드:**
```python
import socket
import urllib.error

_FONT_DL_TIMEOUT = 10  # seconds


def _ensure_fonts():
    """한글 폰트 다운로드 (없으면). 실패 시 Helvetica로 폴백."""
    os.makedirs(_FONT_DIR, exist_ok=True)
    for path, url in [(_FONT_PATH, _FONT_URL), (_FONT_BOLD_PATH, _FONT_BOLD_URL)]:
        if os.path.exists(path):
            continue
        try:
            # urlretrieve는 timeout 인자가 없으므로 urlopen로 대체
            req = urllib.request.Request(url, headers={"User-Agent": "VERITY-PDF/1.0"})
            with urllib.request.urlopen(req, timeout=_FONT_DL_TIMEOUT) as resp:
                data = resp.read()
            # 10KB 미만 응답은 오류 페이지로 간주
            if len(data) < 10_000:
                raise RuntimeError(f"font file too small: {len(data)} bytes")
            tmp_path = path + ".tmp"
            with open(tmp_path, "wb") as f:
                f.write(data)
            os.replace(tmp_path, path)
        except (urllib.error.URLError, socket.timeout, OSError, RuntimeError) as e:
            print(f"  폰트 다운로드 실패 ({url}): {e} — Helvetica 폴백으로 진행")
```

---

### WARN-20. Health check timeout 8초 일률 — DART/SEC 응답 느릴 때 오탐
**api/health.py > Line 39 + 프로브 전체 > [false-positive error]**

**현상:** `_TIMEOUT = 8` 모든 프로브에 동일. DART(`opendart.fss.or.kr/api/corpCode.xml`)는 **대량 XML(수 MB)** 을 반환해 일반적으로 5~10초 소요. 네트워크 지연 시 timeout exception으로 `status=error` 기록 → deadman 카운트 증가 → 실제로는 API 정상인데 파이프라인 중단.

**수정코드:** API별 차등 timeout + 최소 2회 재시도.
```python
# api/health.py
_TIMEOUT_FAST = 5   # gemini, anthropic, polygon, telegram
_TIMEOUT_DEFAULT = 8
_TIMEOUT_SLOW = 20  # dart, sec_edgar, krx_open_api(batch)


def _probe(label: str, fn, retries: int = 1) -> dict:
    """공통 프로브: 1회 실패 시 짧게 재시도 후 실패 확정."""
    last_err = None
    t0 = time.time()
    for attempt in range(retries + 1):
        try:
            ok, detail = fn()
            elapsed = round((time.time() - t0) * 1000)
            return {
                "status": "ok" if ok else "error",
                "latency_ms": elapsed,
                "detail": detail,
                "attempts": attempt + 1,
            }
        except Exception as e:
            last_err = e
            if attempt < retries:
                time.sleep(0.5)
    elapsed = round((time.time() - t0) * 1000)
    return {
        "status": "error",
        "latency_ms": elapsed,
        "detail": str(last_err)[:120],
        "attempts": retries + 1,
    }


def _check_dart() -> tuple:
    if not DART_API_KEY:
        return False, "키 미설정"
    r = requests.get(
        "https://opendart.fss.or.kr/api/corpCode.xml",
        params={"crtfc_key": DART_API_KEY},
        timeout=_TIMEOUT_SLOW,   # 8 → 20
    )
    if r.status_code == 200:
        return True, "정상"
    return False, f"HTTP {r.status_code}"


# _check_sec_edgar, _check_krx_open_api 도 _TIMEOUT_SLOW 사용
# _check_gemini, _check_anthropic, _check_telegram 은 _TIMEOUT_FAST
```

---

## 🟢 INFO

### INFO-13. portfolio["alerts"] 무한 증가 없음
**api/main.py > Line 1826, 3116 > [확인됨]**

두 지점 모두 `portfolio["alerts"] = briefing.get("alerts", [])` — **덮어쓰기**이므로 누적되지 않는다. ✅

### INFO-14. telegram_dedupe 버킷 자연 정리
**api/notifications/telegram_dedupe.py > Line 22~26 > [확인됨]**

`_prune_bucket` 이 `ttl * 3` 이전 엔트리를 자동 삭제 (filter/mark 호출 시마다). 무한 증가 없음. ✅

### INFO-15. PDF 폰트 Helvetica 폴백
**api/reports/pdf_generator.py > Line 353 > [확인됨]**

`self._font_name = "Nanum" if os.path.exists(_FONT_PATH) else "Helvetica"` — 폰트 다운로드 실패해도 파이프라인 중단되지 않고 Helvetica(ASCII only)로 렌더. 한글은 깨지지만 실패는 아님. 🟢 (한글 섹션은 `?????`로 표시될 수 있음, 경고만).

### INFO-16. `cancel-in-progress: false` 실효성
**.github/workflows/daily_analysis.yml > Line 54 > [확인됨]**

CRIT-11에서 수정한 `cancel-in-progress: false` 는 GitHub Actions에서 graceful queue를 의미. 실행 중 job에 영향 없고 신규 트리거는 queue된다. 다만 워크플로우별 **separate group**인 경우(`daily-analysis` vs `daily-analysis-full` vs bond_etf 등)는 서로 cancel/queue하지 않으므로 WARN-17 group 통합 필요.

---

## 요약 (심각도순)

| # | 파일 | Line | 유형 | 영향 |
|---|---|---|---|---|
| 🔴 CRIT-12 | daily_analysis.yml | 18, 20, 24, 28 | cron 중복 | UTC 23:30/:40/:50 + 06:45/.../ 3개 라인 동시 매치 |
| 🔴 CRIT-13 | api/health.py | 218~232 | 감시 누락 | Finnhub/Polygon/SEC/Perplexity 장애를 deadman이 미탐 |
| 🔴 CRIT-14 | telegram_dedupe.py, main.py | 전역 | 알림 누락 | CRITICAL이 4시간 동안 억제됨 |
| 🟡 WARN-17 | workflows/*.yml | concurrency | 직렬화 | bond_etf/export/daily_analysis 병렬 git push |
| 🟡 WARN-18 | export_trade_daily.yml | Line 7 | 타이밍 race | trade_analysis.json 쓰기 전 daily_analysis 읽을 가능 |
| 🟡 WARN-19 | pdf_generator.py | 32 | 무한 대기 | urlretrieve timeout 없음 |
| 🟡 WARN-20 | api/health.py | 39 | false-positive | 8초 일률 timeout, 재시도 없음 |
| 🟢 INFO-13 | main.py | 1826, 3116 | 확인 | alerts 누적 없음 |
| 🟢 INFO-14 | telegram_dedupe.py | 22 | 확인 | 버킷 자연 정리 |
| 🟢 INFO-15 | pdf_generator.py | 353 | 확인 | Helvetica 폴백 |
| 🟢 INFO-16 | daily_analysis.yml | 54 | 확인 | cancel-in-progress:false 동작 정확 |

---

## 검수 원칙 기준 제외 항목
- **TASK 5 fpdf2 렌더링 중 데이터 없는 섹션**: pdf_generator 전반에서 `portfolio.get("key", {})` 패턴으로 None-safe 구성. 데이터 없는 섹션은 빈 페이지로 스킵되고 raise 없음. 버그 아님.
- **TASK 2 daily_analysis vs daily_analysis_full group 충돌**: `cancel-in-progress: false` + Python-level lock(CRIT-11)으로 1차 방어, git retry(WARN-5)가 2차. 3중 방어가 구현되어 있으며 WARN-17에서 추가 group 통합 권고로 마무리.
- **TASK 4 portfolio.json 저장 시 alert_history 무한 증가**: 코드상 누적 로직 없음. INFO-13 참조.
