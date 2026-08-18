"""
3단계 깔때기 필터링 엔진 v2 (Sprint 3) + Phase 2-A 확장 유니버스 (2026-05-01)
Step 1: 거래대금 필터
Step 2: 펀더멘털 필터 (PER/PBR + 부채비율 + 영업이익률)
Step 3: 안심 점수 계산 (8개 팩터 기반)

Phase 2-A: run_extended_filter_pipeline — 정적 화이트리스트 85종목 → 동적 5,000.
  UNIVERSE_RAMP_UP_STAGE 환경변수로 Stage 1 (500) ~ Stage 4 (5000) 제어.
  Hard Floor → 코어 fallback → step1/step2 호환성 유지.
"""
import os
from typing import List, Optional
from api.config import (
    FILTER_MIN_TRADING_VALUE, FILTER_MIN_TRADING_VALUE_US, FILTER_MAX_DEBT_RATIO,
    FILTER_TOP_N, FILTER_KR_TOP_N, FILTER_US_TOP_N, UNIVERSE_RAMP_UP_STAGE,
)
from api.collectors.stock_data import get_all_stock_data


def step1_trading_filter(stocks: list) -> list:
    """Step 1: 거래대금 기준 필터 (KRW/USD 자동 분기)"""
    filtered = []
    for s in stocks:
        is_us = s.get("currency") == "USD"
        threshold = FILTER_MIN_TRADING_VALUE_US if is_us else FILTER_MIN_TRADING_VALUE
        if s["trading_value"] >= threshold:
            filtered.append(s)
    filtered.sort(key=lambda x: x["trading_value"], reverse=True)
    return filtered


def step2_fundamental_filter(stocks: list) -> list:
    """Step 2: 펀더멘털 필터 (PER/PBR + 부채비율 + 수익성)"""
    results = []
    for s in stocks:
        per = s.get("per", 0)
        pbr = s.get("pbr", 0)
        debt = s.get("debt_ratio", 0)
        op_margin = s.get("operating_margin", 0)

        if per < 0:
            if op_margin > 0:
                s["_turnaround"] = True
            else:
                continue
        if per > 100:
            continue
        if pbr > 10:
            continue
        if debt > FILTER_MAX_DEBT_RATIO and debt > 0:
            continue

        results.append(s)
    return results



# ── 심층분석 지명 로테이션 (2026-08-12, PREREG_ANALYSIS_ROTATION · PM 승인) ──────
_ROTATION_STATE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "metadata", "analysis_rotation_state.json")
_ROTATION_LOG_PATH = os.path.join(
    os.path.dirname(_ROTATION_STATE_PATH), "analysis_rotation_log.jsonl")
_ROTATION_DEAD_DAYS = 14      # §4 — 상태 파일 미갱신 ~10거래일(달력 14일) = 배선 사망 → 구 지명 복귀


def nominate_for_analysis(step2: list, market_scope: str = "all",
                          label: str = "Filter") -> list:
    """심층분석 지명 — **staleness 순환** (안심점수 상위 직선발 폐지).

    근거(측정): 상위 구간 승자보존 0.746~0.795 < 무작위 1.0 (PR #357 · 독립 재계산 검증).
    상위 선별에 엣지가 없으므로 지명은 고르는 것이 아니라 돌아가며 전부 보는 것이다.
    지명 = 게이트 통과 풀(safety_pct ≥ GATE_BOTTOM_PCT)에서 **최장 미분석 순**
    (미분석 우선 → last_nominated asc → 티커 asc — 완전 결정론 · 점수 순위 0).

    🚨 폴백(등록 §4): 상태 파일이 존재하는데 {_ROTATION_DEAD_DAYS}일 미갱신 = 기록 배선
    사망 → 구 지명(안심 상위)으로 자동 복귀 + 큰 소리로 신고. 파일 부재 = cold start
    (사망 아님 — 전 종목 미분석으로 시작). 섀도 = 구 지명 상위를 병행 로그.
    """
    import json as _json
    from datetime import datetime, timedelta, timezone

    from api.config import GATE_BOTTOM_PCT

    kst_now = datetime.now(timezone(timedelta(hours=9)))
    today = kst_now.strftime("%Y-%m-%d")

    state = {}
    dead = False
    try:
        if os.path.exists(_ROTATION_STATE_PATH):
            doc = _json.load(open(_ROTATION_STATE_PATH, encoding="utf-8")) or {}
            state = doc.get("tickers") or {}
            upd = str(doc.get("updated_at") or "")[:10]
            if upd:
                age = (kst_now.date()
                       - datetime.strptime(upd, "%Y-%m-%d").date()).days
                if age > _ROTATION_DEAD_DAYS:
                    dead = True
    except Exception as _e:  # noqa: BLE001 — 읽기 실패 = 배선 사망 취급
        print(f"[{label}] 🚨 로테이션 상태 읽기 실패({type(_e).__name__}) — 구 지명 폴백")
        dead = True

    def _legacy(pool, quota):
        return sorted(pool, key=lambda x: x.get("safety_score", 0), reverse=True)[:quota]

    def _rotate(pool, quota):
        gated = [x for x in pool if (x.get("safety_pct") or 0) >= GATE_BOTTOM_PCT]
        if not gated:
            # 게이트 판정 불가(표본 부족 등) — 지어내지 않고 구 지명 폴백 + 신고
            print(f"[{label}] 🚨 게이트 통과 0 (pct 부재/표본 부족) — 구 지명 폴백")
            return _legacy(pool, quota), None
        gated.sort(key=lambda x: (state.get(str(x.get("ticker"))) or "0000-00-00",
                                  str(x.get("ticker"))))
        return gated[:quota], len(gated)

    markets = ([("KR", [x for x in step2 if x.get("currency") != "USD"], FILTER_KR_TOP_N),
                ("US", [x for x in step2 if x.get("currency") == "USD"], FILTER_US_TOP_N)]
               if market_scope == "all" else [("ALL", list(step2), FILTER_TOP_N)])

    top: list = []
    pool_total = 0
    for mkt, pool, quota in markets:
        if dead:
            picked, gsize = _legacy(pool, quota), None
            print(f"[{label}] 🚨 로테이션 사망 폴백({mkt}) — 안심상위 {len(picked)}종")
        else:
            picked, gsize = _rotate(pool, quota)
        shadow = _legacy(pool, quota)
        overlap = len({x.get("ticker") for x in picked}
                      & {x.get("ticker") for x in shadow})
        cyc = (f" · 완주≈{(gsize + quota - 1) // quota}일" if gsize else "")
        print(f"[{label}] 지명({mkt}): {len(picked)}/{quota} · 게이트 풀 {gsize}{cyc} "
              f"· 구지명(안심상위) 겹침 {overlap}/{len(picked)}")
        top.extend(picked)

    if not dead:
        for x in top:
            state[str(x.get("ticker"))] = today
        try:
            os.makedirs(os.path.dirname(_ROTATION_STATE_PATH), exist_ok=True)
            tmp = _ROTATION_STATE_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                _json.dump({"updated_at": today, "tickers": state}, f, ensure_ascii=False)
            os.replace(tmp, _ROTATION_STATE_PATH)
            with open(_ROTATION_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(_json.dumps({"date": today, "nominated": len(top),
                                     "state_size": len(state)},
                                    ensure_ascii=False) + "\n")
        except Exception as _e:  # noqa: BLE001 — 기록 실패가 지명을 막지 않는다 (다음 run 사망 감지)
            print(f"[{label}] 🚨 로테이션 상태 기록 실패: {type(_e).__name__}: {_e}")
    return top


def attach_safety_percentile(scored: list) -> None:
    """단면 백분위(safety_pct) 부착 — 시장(KR/US)별 · 동점 평균.

    2026-08-12 게이트 컷오버 (PREREG_GATE_STRENGTH_REDESIGN §4, PR #357 채택 B).
    safety_score 의 검증된 역할 = **하위 배제** (하위 20% 컷 시 승자격납비 0.746→0.933,
    t 10.35). 소비처(_profile_picks · VAMS 매수)는 절대점수 55 대신 `safety_pct ≥
    GATE_BOTTOM_PCT` 를 쓴다. 🚨 백분위는 **이 단면(Step2 생존자)** 기준 — 소비처가
    좁은 풀(~40)에서 재계산하면 의미가 사라지므로 여기서 한 번만 계산해 부착한다.
    """
    from api.config import GATE_BOTTOM_PCT
    for is_us in (False, True):
        pool = [s for s in scored if (s.get("currency") == "USD") == is_us]
        n = len(pool)
        if n < 5:
            for s_ in pool:
                s_["safety_pct"] = None      # 표본 부족 — 게이트 판정 불가로 신고
            continue
        order = sorted(range(n), key=lambda i: pool[i].get("safety_score", 0))
        i = 0
        while i < n:
            j = i
            v = pool[order[i]].get("safety_score", 0)
            while j + 1 < n and pool[order[j + 1]].get("safety_score", 0) == v:
                j += 1
            avg = ((i + j) / 2 + 1) / n
            for k in range(i, j + 1):
                pool[order[k]]["safety_pct"] = round(avg, 4)
            i = j + 1
        passed = sum(1 for s_ in pool if (s_.get("safety_pct") or 0) >= GATE_BOTTOM_PCT)
        mkt = "US" if is_us else "KR"
        print(f"[Filter] 게이트(하위{GATE_BOTTOM_PCT:.0%} 컷) {mkt}: {passed}/{n} 통과 "
              f"(구 게이트 ≥55: {sum(1 for s_ in pool if s_.get('safety_score', 0) >= 55)} — 섀도)")


# ── 팩터 하위신호 단면 z-score (2026-08-17, PREREG_FACTOR_V2 §5-1) ──────────────
# 🚨 왜: 팩터 **내부** 하위신호를 임계 배점(+12/+5/−8)으로 합치고 있었다. 문헌 표준은
#   순위 → z-score → 단순평균이다 (Asness-Frazzini-Pedersen 2019 QMJ, RAS 24(1) 34–112,
#   DOI 10.1007/s11142-018-9470-2). 구간화는 표준이 아니며 **경계 선택 자체가 은닉 자유도**라
#   짧은 표본에서 연속 z 보다 위험하다. 우리 다단계 배점은 F-score 의 0/1 과 달라 배점 크기가
#   추정 파라미터이므로 Altman Z 회귀계수와 같은 과최적화 범주다.
#
# 🚨 기준 단면 = **스캔 생존자 전체**(PM 결정 2026-08-17). `universe_candidates.json` 의
#   `ramp_up_note` 가 "5000 = cap(상한), 목표 아님 — 실 유니버스 = 품질 floor 통과 전체" 라
#   명시하므로 고정 5,000 이 아니라 그날 생존자 전체다.
#
# 🚨 시장(KR/US)별 분리 — `attach_safety_percentile` 과 같은 규약. 섞으면 통화·시장 구조가
#   오염된다(실측: beta 를 KR 만 채우자 KR 평균 +16.8 · US +0.0 = 시장 단위 편향).
#
# 방향(+1/−1)은 **신호의 성질**이지 소비처의 선택이 아니므로 여기서 정규화한다 —
# 부착 후에는 **높을수록 좋음**으로 통일된다. 소비처는 방향을 다시 생각하지 않는다.
#
# 이 함수는 **부착만 한다.** 점수를 바꾸지 않는다 (전환은 팩터 함수 쪽, 별도 단계).
_ZSPEC = {
    # 필드                        방향   비고
    "per":                        -1,   # 낮을수록 저평가 (Graham)
    "pbr":                        -1,
    "debt_ratio":                 -1,
    "roe":                        +1,
    "div_yield":                  +1,
    "eps_quarterly_growth":       +1,   # CANSLIM C
    "drop_from_high_pct":         +1,   # 0 에 가까울수록 신고가 근처 = RS 프록시
    "roa":                        +1,
    "operating_margin":           +1,
    "current_ratio":              +1,
    "gross_margin":               +1,
    "asset_turnover":             +1,
    "volatility_20d":             -1,   # 저변동 = 고점수 (AHXZ 2006 · BBW 2011)
    "volatility_60d":             -1,
}
# 🚨 실측(2026-08-17 운영 풀 N=56) 보유 0 이라 제외한 것 — 넣어도 전 종목 결측이라
#   z 가 안 만들어지고, "있는 척" 만 하게 된다:
#     operating_profit_yoy_est_pct 0/56 · institutional_ownership 0/56 · beta 0/56
#   beta 는 PREREG_FACTOR_V2 §6(입력 완결)이 채운 뒤 여기에 추가한다.
_Z_MIN_SAMPLE = 5          # attach_safety_percentile 과 같은 하한


# 🚨 비율 지표에서 0·음수는 "가장 싸다" 가 아니라 **못 잰 것**이다 (실적 없음·적자).
#   실측 2026-08-17: KR 20종목 중 `per == 0` 이 3건인데, 방향(-1)을 그대로 적용하면
#   그 3건이 **최고 저평가(z +1.40)** 로 매겨졌다. 앞서 잡은 `or 50` falsy 결함과 같은 클래스다.
#   분모가 0 이하일 수 없는 지표는 여기서 걸러 **미측정으로 남긴다**(중립 대입 아님).
_Z_POSITIVE_ONLY = {"per", "pbr", "current_ratio", "asset_turnover"}


def _field_value(s: dict, f: str):
    v = s.get(f)
    if not isinstance(v, (int, float)):
        v = (s.get("technical") or {}).get(f)
    if not isinstance(v, (int, float)):
        return None
    if f in _Z_POSITIVE_ONLY and v <= 0:
        return None                       # 0·음수 = 못 쟀음. 순위에 넣지 않는다
    return v


def attach_factor_zscores(scored: list) -> None:
    """단면 z-score 부착 — `stock["factor_z"] = {필드: z}`.

    규약은 `attach_safety_percentile` 과 동일: 시장별 분리 · 동점 평균 순위 · 표본 부족 시
    None + 신고. 순위 → 정규분위 근사(Blom) → z 로 변환해 이상치 영향을 제한한다
    (AQR QMJ 가 "순위 변환 후 표준화" 를 쓰는 이유와 같다).

    🚨 결측은 **제외**한다 — 중립 0 을 넣으면 "못 잼" 이 "평균" 으로 둔갑한다.
       소비처는 `factor_z` 에 키가 없으면 미측정으로 다룬다.
    """
    from statistics import NormalDist
    _nd = NormalDist()
    for is_us in (False, True):
        pool = [s for s in scored if (s.get("currency") == "USD") == is_us]
        if not pool:
            continue
        for s_ in pool:
            s_.setdefault("factor_z", {})
        for f, direction in _ZSPEC.items():
            vals = [(i, _field_value(s_, f)) for i, s_ in enumerate(pool)]
            have = [(i, v) for i, v in vals if v is not None]
            if len(have) < _Z_MIN_SAMPLE:
                continue                      # 표본 부족 — 키를 만들지 않는다(=미측정)
            # 🚨 상수 축은 부착하지 않는다. 실측: KR 20종목의 `pbr` 이 **전부 1.0** 이었다
            #   (US 는 33/36 정상). 임계 배점에서는 전 종목이 같은 점수를 받아 안 보이던
            #   결함인데, z 로 바꾸면 σ=0 이라 드러난다. 값이 하나뿐이면 변별 정보가 0 이므로
            #   "있는 척" 하지 말고 미측정으로 남긴다 — 소비처가 unmeasured 로 다룬다.
            if len({v for _i, v in have}) < 2:
                continue
            n = len(have)
            order = sorted(range(n), key=lambda k: have[k][1])
            ranks = [0.0] * n
            i = 0
            while i < n:                      # 동점 평균
                j = i
                while j + 1 < n and have[order[j + 1]][1] == have[order[i]][1]:
                    j += 1
                avg = (i + j) / 2 + 1
                for k in range(i, j + 1):
                    ranks[order[k]] = avg
                i = j + 1
            for (idx, _v), r in zip(have, ranks):
                # Blom 근사 — 순위를 정규분위로. 극단값이 z 를 지배하지 않는다
                q = (r - 0.375) / (n + 0.25)
                pool[idx]["factor_z"][f] = round(direction * _nd.inv_cdf(q), 4)


def calculate_safety_score(stock: dict) -> int:
    """안심 점수 계산 v2 (0~100, 8개 팩터)"""
    score = 0

    per = stock.get("per", 0)
    if 5 <= per <= 15:
        score += 20
    elif 15 < per <= 25:
        score += 12
    elif 0 < per <= 50:
        score += 5

    pbr = stock.get("pbr", 0)
    if 0 < pbr <= 1.0:
        score += 15
    elif 1.0 < pbr <= 1.5:
        score += 10
    elif 1.5 < pbr <= 3.0:
        score += 5
    elif pbr == 0:
        score += 3

    div_yield = stock.get("div_yield", 0)
    if div_yield >= 3:
        score += 12
    elif div_yield >= 1:
        score += 7

    drop = stock.get("drop_from_high_pct", 0)
    if drop <= -30:
        score += 15
    elif drop <= -20:
        score += 10
    elif drop <= -10:
        score += 5

    trading_val = stock.get("trading_value", 0)
    is_us = stock.get("currency") == "USD"
    if is_us:
        if trading_val >= 500_000_000:
            score += 12
        elif trading_val >= 100_000_000:
            score += 8
        elif trading_val >= 50_000_000:
            score += 4
    else:
        if trading_val >= 50_000_000_000:
            score += 12
        elif trading_val >= 10_000_000_000:
            score += 8
        elif trading_val >= 1_000_000_000:
            score += 4

    debt = stock.get("debt_ratio", 0)
    if 0 < debt <= 30:
        score += 10
    elif 30 < debt <= 60:
        score += 6
    elif debt == 0:
        score += 3

    op_margin = stock.get("operating_margin", 0)
    if op_margin >= 15:
        score += 10
    elif op_margin >= 8:
        score += 6
    elif op_margin >= 3:
        score += 3

    roe = stock.get("roe", 0)
    if roe >= 15:
        score += 6
    elif roe >= 8:
        score += 4
    elif roe >= 3:
        score += 2

    if stock.get("_turnaround"):
        score = max(score - 10, 0)

    return min(score, 100)


# ───────────────────────────────────────────────────────────────────
# Stage 1.5 — 금융업(industry) 제외 (2026-06-07, funnel Phase A.2)
# ───────────────────────────────────────────────────────────────────
# 표준 펀더멘털 팩터(P/B·ROE·레버리지)가 은행/보험/여신에 구조적 왜곡 → 분석 풀 제외.
# sector(섹터) 통째가 아니라 industry(세부업종) 기준 (PM 결정 2026-06-07) — 자산경량
# 금융(데이터/거래소 'Financial Data & Stock Exchanges' = 에프앤가이드 류)은 왜곡 없어 유지.
# 제외 ≠ 영구 무시: 금융 전용 분석 sleeve(은행 NIM/CET1, 보험 combined ratio/float)는
# 별 모듈 큐잉 ([[project_funnel_5stage_sprint]] Phase A.2 trail). 증권(Capital Markets)/
# 자산운용(Asset Management)은 본 경계 밖 — 미래 확장.
_EXCLUDED_FINANCIAL_INDUSTRY_KW = ("Banks", "Insurance", "Credit Services")


def exclude_financial_sector(stocks: List[dict]) -> List[dict]:
    """금융업(은행/보험/여신) industry 제외. 코어 포함 (팩터 왜곡은 코어도 동일).

    industry 빈값(yfinance 미제공) = 통과 (보수 — 결손 데이터로 과제외 회피).
    제외 건수 로깅 (silent cap 금지).
    """
    kept: List[dict] = []
    excluded: List[str] = []
    for s in stocks:
        industry = str(s.get("industry") or "")
        if industry and any(kw in industry for kw in _EXCLUDED_FINANCIAL_INDUSTRY_KW):
            excluded.append(s.get("name") or s.get("ticker") or "?")
        else:
            kept.append(s)
    if excluded:
        print(f"[Stage 1.5 금융업 제외] {len(excluded)}종목: {excluded[:10]}")
    return kept


def run_filter_pipeline(market_scope: str = "all", _metrics: Optional[dict] = None) -> List[dict]:
    """필터링 파이프라인 실행. market_scope: 'kr' | 'us' | 'all'.

    _metrics: ramp_up_monitor 가 yf_failure_rate 받아갈 dict (silent skip 차단).
    """
    print(f"[Filter] 전 종목 데이터 수집 중... (scope={market_scope})")
    all_stocks = get_all_stock_data(market_scope=market_scope, _metrics=_metrics)
    print(f"[Filter] 수집 완료: {len(all_stocks)}개 종목")

    # Stage 1.5 — 금융업 제외 (sector 보유 후)
    all_stocks = exclude_financial_sector(all_stocks)

    # ── Phase 2-B wide_scan shadow (legacy core path 도 동일 hook) ──
    # WIDE_SCAN_MODE=DISABLED 면 즉시 skip. decision 영향 0.
    try:
        from api.analyzers.wide_scan import run_wide_scan_shadow
        ws_result = run_wide_scan_shadow(all_stocks)
        if not ws_result.get("skipped"):
            print(
                f"[Phase 2-B wide_scan {ws_result['mode']}] "
                f"input={ws_result['input_n']} target={ws_result['target_n']} "
                f"passed={ws_result['passed_n']} logged={ws_result['logged']}"
            )
    except Exception as _ws_err:
        print(f"[Phase 2-B wide_scan] 실패(무시): {_ws_err}")

    # ── Phase 2-B 분기 시계열 jsonl 누적 (legacy core path 도 동일 hook) ──
    try:
        from api.utils.quarterly_history import append_universe_snapshot
        qh_result = append_universe_snapshot(all_stocks)
        if qh_result.get("logged"):
            print(f"[quarterly_history] appended {qh_result['appended_n']}")
    except Exception as _qh_err:
        print(f"[quarterly_history] 실패(무시): {_qh_err}")

    print("[Filter] Step 1: 거래대금 필터")
    step1 = step1_trading_filter(all_stocks)
    print(f"[Filter] Step 1 결과: {len(step1)}개 종목")

    print("[Filter] Step 2: 펀더멘털 필터 (PER/PBR/부채비율)")
    step2 = step2_fundamental_filter(step1)
    print(f"[Filter] Step 2 결과: {len(step2)}개 종목")

    for s in step2:
        s["safety_score"] = calculate_safety_score(s)
    attach_safety_percentile(step2)
    # 🚨 2026-08-17 — 같은 단면에서 팩터 하위신호 z 도 부착 (PREREG_FACTOR_V2 §5-1).
    #   여기서 한 번만 계산한다 — 소비처가 좁은 풀(~40)에서 재계산하면 의미가 사라진다
    #   (바로 위 함수 docstring 이 같은 이유로 경고하는 함정).
    #   현재는 **부착만** 한다. 점수 전환은 팩터 함수 쪽 별도 단계다.
    attach_factor_zscores(step2)

    # 지명 = staleness 순환 (안심상위 직선발 폐지 — PREREG_ANALYSIS_ROTATION, 측정 근거 PR #357).
    # 쿼터 KR 10 + US 15 는 5/11 PM 결정 그대로.
    top = nominate_for_analysis(step2, market_scope=market_scope, label="Filter")

    for s in top:
        tag = " [턴어라운드]" if s.get("_turnaround") else ""
        mkt = "US" if s.get("currency") == "USD" else "KR"
        print(f"  [{mkt}] {s['name']} | 안심 {s['safety_score']}점 | PER {s['per']} | 부채 {s['debt_ratio']}% | 영업 {s['operating_margin']}%{tag}")

    return top


# ───────────────────────────────────────────────────────────────────
# Phase 2-A — 확장 유니버스 파이프라인 (UNIVERSE_RAMP_UP_STAGE 제어)
# ───────────────────────────────────────────────────────────────────

# 코어 화이트리스트 = 85종목. Stage > 85 일 때 확장 모드 진입.
_PHASE_2A_TRIGGER_THRESHOLD = 85


def _build_custom_universe_for_phase_2a(market_scope: str, target_size: int) -> Optional[dict]:
    """확장 유니버스 dict ({ticker_yf: name}) 생성. Hard Floor 통과 종목만.

    KR=KRX OpenAPI K1 + US=정적 캐시. 종목 0인 edge case 는 None 반환 → 호출자가 fallback.
    """
    from api.collectors.universe_builder import build_extended_universe

    # KR/US 비율 — 결정 1: KR 2,000 + US 3,000 = 5,000 (40:60)
    kr_target = max(int(target_size * 0.4), 1)
    us_target = max(int(target_size * 0.6), 1)

    custom: dict = {}
    if market_scope in ("kr", "all"):
        try:
            kr_entries = build_extended_universe("KR", target_size=kr_target, apply_hard_floor=True)
            for e in kr_entries:
                # ticker (6자리) → ticker_yf (.KS or .KQ)
                suffix = ".KS" if e.get("market", "").upper() == "KOSPI" else ".KQ"
                custom[f"{e['ticker']}{suffix}"] = e.get("name") or e["ticker"]
        except Exception as exc:
            print(f"[Phase 2-A] KR universe build 실패 → 코어 fallback: {exc}")
    if market_scope in ("us", "all"):
        try:
            us_entries = build_extended_universe("US", target_size=us_target, apply_hard_floor=True)
            for e in us_entries:
                custom[e["ticker"]] = e.get("name") or e["ticker"]
        except Exception as exc:
            print(f"[Phase 2-A] US universe build 실패 → 코어 fallback: {exc}")

    if not custom:
        return None
    return custom


def run_extended_filter_pipeline(
    market_scope: str = "all",
    target_size: int = 0,
    _metrics: Optional[dict] = None,
) -> List[dict]:
    """Phase 2-A 확장 유니버스 → 기존 step1/step2/score/topN 그대로 적용.

    target_size <= 85 → 기존 run_filter_pipeline 으로 위임 (backward compatible).
    target_size > 85 → universe_builder + hard_floor → custom_universe → 기존 파이프라인.
    종목 0 edge case → 코어 fallback (run_filter_pipeline 호출).

    _metrics: ramp_up_monitor 가 yf_failure_rate 받아갈 dict (silent skip 차단).
    """
    if target_size <= _PHASE_2A_TRIGGER_THRESHOLD:
        return run_filter_pipeline(market_scope=market_scope, _metrics=_metrics)

    print(f"[Phase 2-A] 확장 유니버스 모드 (target={target_size}, scope={market_scope})")

    custom = _build_custom_universe_for_phase_2a(market_scope, target_size)
    if not custom:
        print(f"[Phase 2-A] custom universe 비어 있음 → 코어 fallback")
        return run_filter_pipeline(market_scope=market_scope, _metrics=_metrics)

    print(f"[Phase 2-A] Hard Floor 통과 {len(custom)}개 종목 데이터 수집 시작")
    all_stocks = get_all_stock_data(market_scope=market_scope, custom_universe=custom, _metrics=_metrics)
    print(f"[Phase 2-A] 수집 완료: {len(all_stocks)}개 종목")

    if not all_stocks:
        print(f"[Phase 2-A] 데이터 수집 0건 → 코어 fallback")
        return run_filter_pipeline(market_scope=market_scope, _metrics=_metrics)

    # Stage 1.5 — 금융업 제외 (sector 보유 후, DART/shadow/snapshot 전)
    all_stocks = exclude_financial_sector(all_stocks)

    # ── DART pre-attach (KR universe 주 1회 batch snapshot 주입) ──
    # dart_batch cron (일요일 KST 22:00) 가 dart_fundamentals_kr.json 적재.
    # cache hit 시 stock dict per/pbr/roe/debt_ratio/op_margin 보강 (DART 1순위, 메모리 결정 2).
    try:
        from api.utils.dart_pre_attach import attach_dart_to_stocks
        dart_result = attach_dart_to_stocks(all_stocks, max_stale_days=8)
        if dart_result.get("cache_hit"):
            print(f"  [DART pre-attach] {dart_result['attached_n']}/{dart_result['kr_total_n']} KR 종목 보강")
    except Exception as _dart_err:
        print(f"  [DART pre-attach] 실패(무시): {_dart_err}")

    # ── Phase 2-B wide_scan shadow (5,000 raw 입력) ──
    # 메모리 원칙 9 funnel 정합: Coarse Filter 위치 = step1/step2 *전*, 5,000 raw.
    # WIDE_SCAN_MODE=DISABLED 면 즉시 skip (config.py default). decision 영향 0 보장.
    try:
        from api.analyzers.wide_scan import run_wide_scan_shadow
        ws_result = run_wide_scan_shadow(all_stocks)
        if not ws_result.get("skipped"):
            print(
                f"[Phase 2-B wide_scan {ws_result['mode']}] "
                f"input={ws_result['input_n']} target={ws_result['target_n']} "
                f"passed={ws_result['passed_n']} logged={ws_result['logged']}"
            )
    except Exception as _ws_err:
        print(f"[Phase 2-B wide_scan] 실패(무시): {_ws_err}")

    # ── Phase 2-B 분기 시계열 jsonl 누적 (5,000 raw snapshot) ──
    # WIDE_SCAN_MODE 무관 — 시계열 누적 자체가 텐버거 leading 정량 input (CANSLIM C / GP/A 가속 / FCF trend)
    # 13주 누적 후 F-Score Δ 항목 + Magic Formula 한국개선 정량 가능. decision 영향 0.
    try:
        from api.utils.quarterly_history import append_universe_snapshot
        qh_result = append_universe_snapshot(all_stocks)
        if qh_result.get("logged"):
            print(f"[quarterly_history] appended {qh_result['appended_n']}")
    except Exception as _qh_err:
        print(f"[quarterly_history] 실패(무시): {_qh_err}")

    print("[Phase 2-A] Step 1: 거래대금 필터")
    step1 = step1_trading_filter(all_stocks)
    print(f"[Phase 2-A] Step 1 결과: {len(step1)}개")

    print("[Phase 2-A] Step 2: 펀더멘털 필터")
    step2 = step2_fundamental_filter(step1)
    print(f"[Phase 2-A] Step 2 결과: {len(step2)}개")

    for s in step2:
        s["safety_score"] = calculate_safety_score(s)
    attach_safety_percentile(step2)
    # 🚨 2026-08-17 — 같은 단면에서 팩터 하위신호 z 도 부착 (PREREG_FACTOR_V2 §5-1).
    #   여기서 한 번만 계산한다 — 소비처가 좁은 풀(~40)에서 재계산하면 의미가 사라진다
    #   (바로 위 함수 docstring 이 같은 이유로 경고하는 함정).
    #   현재는 **부착만** 한다. 점수 전환은 팩터 함수 쪽 별도 단계다.
    attach_factor_zscores(step2)

    # 지명 = staleness 순환 (동일 규칙 — PREREG_ANALYSIS_ROTATION)
    top = nominate_for_analysis(step2, market_scope=market_scope, label="Phase 2-A")

    if not top:
        print(f"[Phase 2-A] step1/step2 통과 0건 → 코어 fallback")
        return run_filter_pipeline(market_scope=market_scope, _metrics=_metrics)

    return top


def _is_within_phase2a_window() -> bool:
    """결정 5 가드 1 — KST 06:00~22:00 만 wide_scan 허용.

    범위 밖이면 backward compatible: 기존 85종목 run_filter_pipeline 으로 fallback.
    (workflow cron 자체는 손대지 않음 — US realtime 지원 backward compat 보호.)
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo
    hour = datetime.now(ZoneInfo("Asia/Seoul")).hour
    return 6 <= hour < 22


def run_filter_pipeline_with_ramp_up(market_scope: str = "all") -> List[dict]:
    """Phase 2-A dispatch — UNIVERSE_RAMP_UP_STAGE + KST 시간대 기반 자동 분기.

    main.py 가 호출하는 진입점. backward compatible:
      - UNIVERSE_RAMP_UP_STAGE <= 85 → 기존 run_filter_pipeline
      - KST 시간 범위 밖 (가드 1) → 기존 run_filter_pipeline
      - 그 외 → run_extended_filter_pipeline
    """
    from time import perf_counter
    _t0 = perf_counter()
    stage = UNIVERSE_RAMP_UP_STAGE or 0
    # 2026-05-10 fix (silent skip 차단): get_all_stock_data → run_filter_pipeline →
    # 여기까지 yf_failure_rate 흘러오게 _metrics dict 전달.
    # ramp_up_monitor 가 항상 0 으로 보고 → trigger dead 였던 결함 (5000 stage 첫 run 노출).
    metrics: dict = {}
    # 2026-05-05: try/finally 보장. 5/1~5/4 mode=full 3건 schedule success 인데
    # jsonl entry 1건만 누적 — extended path 의 예외가 main.py tracer.step 에서
    # silently catch 되면 hook 도달 못 함. finally 로 어떤 경로에서도 측정 보장.
    try:
        if stage <= _PHASE_2A_TRIGGER_THRESHOLD:
            return run_filter_pipeline(market_scope=market_scope, _metrics=metrics)
        if not _is_within_phase2a_window():
            print(f"[Phase 2-A] KST window 06~22 밖 → 코어 fallback (가드 1)")
            return run_filter_pipeline(market_scope=market_scope, _metrics=metrics)
        return run_extended_filter_pipeline(market_scope=market_scope, target_size=stage, _metrics=metrics)
    finally:
        _log_w1_runtime(stage=stage, elapsed=perf_counter() - _t0, market_scope=market_scope, metrics=metrics)


def _log_w1_runtime(*, stage: int, elapsed: float, market_scope: str, metrics: Optional[dict] = None) -> None:
    """W1 production hook — runtime_load_log.jsonl 1줄 누적. silent 실패.

    2026-05-03 — 5건 cron 중 2건만 row 누적 (silent gap) 디버깅 위해
    실패 시 stderr 1줄 노출 (logger 환경 의존 없이). main 흐름 무중단.

    2026-05-10 — silent skip 차단 (memory feedback_data_collection_verification_mandatory):
      get_all_stock_data 가 _metrics dict 에 채운 yf_failure_rate 를 monitor 에 의무 전달.
      이전엔 default 0.0 으로 설정되어 yf rate-limit 65% 도 trigger=[] 로 보고된 결함 노출.
    """
    try:
        import os as _os
        import sys
        from api.observability.ramp_up_monitor import log_run_with_estimate
        from api.observability.dart_metrics import (
            compute_dart_failure_rate,
            get_dart_snapshot,
        )
        mode = _os.environ.get("ANALYSIS_MODE", "unknown")
        m = metrics or {}
        yf_fail = float(m.get("yf_failure_rate", 0.0))
        yf_attempted = int(m.get("yf_attempted", 0))
        yf_failed = int(m.get("yf_failed", 0))
        # W3 wiring (2026-05-21) — get_all_stock_data 가 _metrics 에 채운 라이브 인자 통합.
        #   rate_limit_violations ← yf_rate_limited (yfinance_safe wrapper 누적)
        #   kr_first_call_ms       ← 첫 KR fetch latency (get_all_stock_data 측정)
        # W3 4/4 (2026-05-23) — dart_metrics drain. DartScout._call + dart_fundamentals
        #   _fetch_fnltt_all_cached 가 process-level state 에 누적 → 여기서 snapshot.
        rate_limit_violations = int(m.get("yf_rate_limited", 0))
        kr_first_call_ms = int(m.get("kr_first_call_ms", 0))
        dart_fail = compute_dart_failure_rate()
        dart_snap = get_dart_snapshot()
        result = log_run_with_estimate(
            mode=mode,
            ramp_up_stage=stage,
            execution_time_seconds=elapsed,
            yfinance_failure_rate=yf_fail,
            dart_failure_rate=dart_fail,
            kr_max_workers_used=30,
            kr_first_call_ms=kr_first_call_ms,
            rate_limit_violations=rate_limit_violations,
            us_max_workers_used=50,
            extra={
                "market_scope": market_scope,
                "yf_attempted": yf_attempted,
                "yf_failed": yf_failed,
                "dart_attempted": dart_snap["dart_attempted"],
                "dart_failed": dart_snap["dart_failed"],
                "dart_rate_limited": dart_snap["dart_rate_limited"],
            },
        )
        # 2026-05-05: 5/1~5/4 mode=full 3건 success 인데 jsonl entry 1건만 누적.
        # logged=True 도 명시적 stderr 1줄 — 다음 run 부터 발동 여부 추적용.
        if result.get("logged"):
            triggers = result.get("fail_triggers") or []
            print(
                f"[runtime_load] OK: mode={mode} stage={stage} elapsed={elapsed:.2f}s "
                f"scope={market_scope} yf_fail={yf_fail:.2%} ({yf_failed}/{yf_attempted}) "
                f"dart_fail={dart_fail:.2%} ({dart_snap['dart_failed']}/{dart_snap['dart_attempted']}) "
                f"rate_limit={rate_limit_violations} kr_first_call_ms={kr_first_call_ms} triggers={triggers}",
                file=sys.stderr, flush=True,
            )
        else:
            print(
                f"[runtime_load] WARNING: stage={stage} elapsed={elapsed:.2f}s "
                f"scope={market_scope} → logged=False err={result.get('error')}",
                file=sys.stderr, flush=True,
            )
    except Exception as e:
        import sys, traceback
        print(
            f"[runtime_load] WARNING outer except: stage={stage} elapsed={elapsed:.2f}s "
            f"scope={market_scope} err={e}",
            file=sys.stderr, flush=True,
        )
        traceback.print_exc(file=sys.stderr)
