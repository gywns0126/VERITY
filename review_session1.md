# VERITY 검수 리포트 — SESSION 1

**대상:** `api/intelligence/verity_brain.py` (+ 연관 파일)
**연관 파일:** `api/intelligence/strategy_evolver.py`, `api/analyzers/claude_analyst.py`, `api/config.py`, `api/main.py`
**검수 범위:** NaN/None 전파, 등급 판정 로직, 매크로 오버라이드 체인, Strategy Evolver 자동승인, Brain Drift Detection

---

## 🔴 CRITICAL

### CRIT-1. auto_avoid 레드플래그가 contrarian_upgrade로 무력화
**verity_brain.py > Line 1709~1733 > [로직 오류 — 등급 판정 우선순위 붕괴]**

**현상:**
```python
1709:  if red_flags["has_critical"]:
1710:      grade = "AVOID"    # 즉시회피 강제
...
1721:  if macro_override.get("contrarian_upgrade"):
...
1731:      g_idx = GRADE_ORDER.index(grade) if grade in GRADE_ORDER else 2
1732:      if g_idx > 0:
1733:          grade = GRADE_ORDER[g_idx - 1]   # ← AVOID(4) → CAUTION(3) 상향
```

FCF<0 + 부채>80%, 위험 키워드 감지 등 `auto_avoid`로 강제 AVOID된 종목이 패닉 Stage 3/4 + Cohen 체크 3개 통과 조건에서 한 단계 상향된다. 즉시회피 계약이 깨진다.

**수정코드:**
```python
if macro_override:
    max_g = macro_override.get("max_grade", "WATCH")
    grade = _cap_grade(grade, max_g)

    # auto_avoid된 종목은 contrarian upgrade 금지 — 펀더멘털 사망 신호 우선
    if macro_override.get("contrarian_upgrade") and not red_flags.get("has_critical"):
        vci_signal = vci.get("signal", "")
        stage = macro_override.get("stage", 0)
        contrarian_ok = (
            vci_signal == "STRONG_CONTRARIAN_BUY"
            or (stage == 4 and vci_signal in ("STRONG_CONTRARIAN_BUY", "CONTRARIAN_BUY"))
        )
        if contrarian_ok:
            cohen = vci.get("cohen_checklist")
            if cohen and cohen["passed"] >= 3:
                g_idx = GRADE_ORDER.index(grade) if grade in GRADE_ORDER else 2
                if g_idx > 0:
                    grade = GRADE_ORDER[g_idx - 1]
```

---

### CRIT-2. bond_regime이 red_flags / macro_override를 소급 무효화
**verity_brain.py > Line 1318~1336 > [오버라이드 체인 순서 결함]**

**현상:** `_apply_bond_regime`이 `brain_score`를 -10/-5 조정 후 `_score_to_grade(score)`만으로 `grade`를 **재계산**한다. analyze_stock에서 설정된 `has_critical → AVOID`, `macro_override max_grade cap`이 모두 사라진다.

예: auto_avoid 때문에 AVOID로 확정된 종목이 brain_score=65 → 55로 깎였을 때, `_score_to_grade(55)` = WATCH로 복구된다. CBOE panic cap(WATCH)도 동일하게 무효화된다.

**수정코드 (Line 1318~1336 전체 교체):**
```python
    if recession:
        # ... (macro_override 부분 그대로) ...
        for s in brain_result.get("stocks", []):
            orig = s.get("brain_score", 0)
            new_score = max(0, orig - 10)
            s["brain_score"] = new_score
            s["bond_penalty"] = -10
            # 기존 grade보다 완화되지 않도록: 재계산 결과와 기존 grade 중 더 나쁜 쪽
            recomputed = _score_to_grade(new_score)
            prev_grade = s.get("grade", "AVOID")
            s["grade"] = _cap_grade(recomputed, prev_grade)
            s["grade_confidence"] = _grade_confidence(new_score, s["grade"])

    if curve_shape == "inverted":
        penalty_cats = {"sector_financial", "alternative_reit", "sector_finance"}
        bonus_cats = {"bond_us_long", "bond_us_mid", "alternative_gold",
                      "commodity_gold", "bond_kr", "bond_us_agg"}
        for s in brain_result.get("stocks", []):
            cat = s.get("category", "")
            sector = (s.get("sector") or "").lower()
            if cat in penalty_cats or "금융" in sector or "부동산" in sector:
                new_score = max(0, s.get("brain_score", 0) - 5)
                s["brain_score"] = new_score
                s["bond_curve_adj"] = -5
                recomputed = _score_to_grade(new_score)
                prev_grade = s.get("grade", "AVOID")
                s["grade"] = _cap_grade(recomputed, prev_grade)
                s["grade_confidence"] = _grade_confidence(new_score, s["grade"])
```

---

## 🟡 WARNING

### WARN-1. None 비교 TypeError → analyze_stock 전체 폴백
**verity_brain.py > Line 1534, Line 1696~1700 > [런타임 예외로 종목 전체 0점 폴백]**

**현상:**
- Line 1534: `top_pct = shareholders[0].get("ownership_pct", 0)` — JSON에 `"ownership_pct": null`이 오면 `.get(k, default)`는 None을 반환. 다음 줄 `if top_pct >= 30`에서 `TypeError: '>=' not supported between NoneType and int`.
- Line 1696: `iscore = matched.get("score", 50)` — 동일 패턴, `iscore >= 70`에서 TypeError.

analyze_stock 레벨 try/except(line 2063)에서 잡히긴 하지만 **종목 전체 결과가 brain_score=0, WATCH로 날아간다**.

**수정코드:**
```python
# Line 1534 부근 (_compute_group_structure_bonus)
    shareholders = gs.get("major_shareholders", [])
    if shareholders:
        top_pct = shareholders[0].get("ownership_pct") or 0
        try:
            top_pct = float(top_pct)
        except (TypeError, ValueError):
            top_pct = 0
        if top_pct >= 30:
            bonus += 2
        elif top_pct >= 20:
            bonus += 1

# Line 1696 부근 (analyze_stock - inst_13f)
            if matched:
                iscore = matched.get("score")
                try:
                    iscore = float(iscore) if iscore is not None else 50
                except (TypeError, ValueError):
                    iscore = 50
                if iscore >= 70:
                    inst_bonus = 3
                elif iscore >= 60:
                    inst_bonus = 1
```

---

### WARN-2. market_structure_override가 STRONG_BUY 강등 누락
**verity_brain.py > Line 1958~1961 > [강등 로직 불완전]**

**현상:**
```python
1958:  for stock in result.get("stocks", []):
1959:      if stock.get("grade") == "BUY":
1960:          stock["grade"] = "WATCH"
```
만기 FULL_WATCH + 프로그램 sell_bomb 시 `BUY`만 강등되고 `STRONG_BUY`는 그대로 유지된다. `chase_buy_allowed=False`의 취지(추격매수 금지)에 반한다.

**수정코드:**
```python
        for stock in result.get("stocks", []):
            if stock.get("grade") in ("STRONG_BUY", "BUY"):
                stock["grade"] = "WATCH"
                stock["grade_label"] = "관망"
                stock["grade_confidence"] = _grade_confidence(stock.get("brain_score", 0), "WATCH")
                stock["reasoning"] = (
                    f"[만기/프로그램 강등] {downgrade_reason} | "
                    + stock.get("reasoning", "")
                )
```

---

### WARN-3. STRATEGY_MIN_SNAPSHOT_DAYS 환경변수 빈 문자열이면 import 크래시
**api/config.py > Line 249, 251 > [환경변수 파싱 방어 누락]**

**현상:**
```python
249:  STRATEGY_MIN_SNAPSHOT_DAYS = int(os.environ.get("STRATEGY_MIN_SNAPSHOT_DAYS", "14"))
251:  STRATEGY_MIN_OOS_DAYS = int(os.environ.get("STRATEGY_MIN_OOS_DAYS", "30"))
```
GitHub Actions에서 secrets에 빈 값으로 주입되거나 `""`로 설정되면 `int("")` → `ValueError`. 모듈 import 자체가 실패하여 전체 파이프라인이 다운된다.

**수정코드:**
```python
def _env_int(key: str, default: int) -> int:
    raw = os.environ.get(key, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default

STRATEGY_MIN_SNAPSHOT_DAYS = _env_int("STRATEGY_MIN_SNAPSHOT_DAYS", 14)
STRATEGY_MIN_OOS_DAYS = _env_int("STRATEGY_MIN_OOS_DAYS", 30)
```

---

### WARN-4. candle_psychology의 float 캐스팅 실패 미처리
**verity_brain.py > Line 308, 353, 363 > [ValueError 미방어]**

**현상:**
```python
308:  vol_ratio = float(tech.get("vol_ratio", 1.0) or 1.0)
353:  rsi = float(rsi)
363:  macd_hist = float(macd_hist)
```
`tech["rsi"]`가 `"N/A"` 같은 비숫자 문자열이면 `ValueError` → analyze_stock 전체 폴백.

**수정코드:**
```python
def _safe_float(v, default=None):
    if v is None:
        return default
    try:
        x = float(v)
        if math.isnan(x) or math.isinf(x):
            return default
        return x
    except (TypeError, ValueError):
        return default

# Line 308
vol_ratio = _safe_float(tech.get("vol_ratio"), 1.0)

# Line 350-354
rsi = _safe_float(tech.get("rsi"))
if rsi is not None:
    if candle_base > 0 and rsi < 40:
        rsi_bonus = 1.5
    elif candle_base < 0 and rsi > 60:
        rsi_bonus = -1.5

# Line 360-367
macd_hist = _safe_float(tech.get("macd_hist"))
if macd_hist is not None:
    if candle_base > 0 and macd_hist > 0:
        macd_bonus = 1.0
    elif candle_base < 0 and macd_hist < 0:
        macd_bonus = -1.0
```

---

## 🟢 INFO

### INFO-1. Brain Drift 임계값 하드코딩
**api/main.py > Line 2897 > [설정 외부화 부재]**

**현상:** `if abs(cur_bs - prev_bs) >= 10 and prev_bs > 0:` — 임계값 10이 하드코딩. `prev_bs > 0` 가드 때문에 직전 분석이 오류로 0점 폴백된 종목(WARN-1/4 경로)은 모든 드리프트 탐지에서 영구적으로 제외된다. 오탐 아닌 **누락** 리스크가 크다.

**수정코드:**
```python
# api/config.py
BRAIN_DRIFT_THRESHOLD = _env_int("BRAIN_DRIFT_THRESHOLD", 10)

# api/main.py Line 2897
from api.config import BRAIN_DRIFT_THRESHOLD
if prev_bs > 0 and abs(cur_bs - prev_bs) >= BRAIN_DRIFT_THRESHOLD:
    drift = check_brain_drift(stock, prev_bs, cur_bs)
```

### INFO-2. Fact/Sentiment 합산의 NaN 방어는 이미 견고
**verity_brain.py > Line 580, 788, 1704 > [확인됨]**

`_compute_fact_score` Line 580, `_compute_sentiment_score` Line 788, `analyze_stock` Line 1704 세 지점에서 `isinstance + isnan + isinf` 체크가 일관되게 적용되어 있다. **TASK 1의 NaN 직접 전파 경로는 없음.** 실제 리스크는 WARN-1/4의 None/문자열로 인한 TypeError/ValueError이며 NaN 자체는 아니다.

---

## 요약 (심각도순)

| # | 파일 | Line | 유형 | 영향 |
|---|---|---|---|---|
| 🔴 CRIT-1 | verity_brain.py | 1721~1733 | 로직 | auto_avoid 무력화 |
| 🔴 CRIT-2 | verity_brain.py | 1318~1336 | 오버라이드 체인 | red_flags/macro cap 소급 무효화 |
| 🟡 WARN-1 | verity_brain.py | 1534, 1696 | None 비교 | 종목 전체 0점 폴백 |
| 🟡 WARN-2 | verity_brain.py | 1958~1961 | 강등 누락 | STRONG_BUY 미강등 |
| 🟡 WARN-3 | config.py | 249, 251 | env 파싱 | 모듈 import 크래시 |
| 🟡 WARN-4 | verity_brain.py | 308, 353, 363 | ValueError | 종목 폴백 |
| 🟢 INFO-1 | main.py | 2897 | 하드코딩 | 드리프트 탐지 누락 |

---

## 검수 원칙 기준 제외 항목
- **TASK 1 NaN 전파**: 방어 코드 이미 존재 (INFO-2 참조). 실제 리스크는 None/문자열 → TypeError로 분류됨.
- **TASK 2 float 경계값**: `round(_clip(raw))`로 int 변환되어 `75.0000001` / `74.9999999` 엣지케이스 무해. 이슈 없음.
- **TASK 4 AND/OR 로직**: Line 681-692 `all([...]) and rolling_ok` 정상. 스냅샷 일수 체크도 Line 783 early return으로 선행됨. 이슈 없음.
