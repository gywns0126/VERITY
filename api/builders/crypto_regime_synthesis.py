"""crypto_regime_synthesis — 크립토 레짐 종합 v0 (사전등록 self-formula).

🚨 사전등록 (feedback_methodology_pre_registration + RULE 7) — PM 승인 2026-06-24:
  · 역발상(극단=반대신호) 해석 + 유리박스 forward 채점 "지금 시작" 결정.
  · 임계 = 이론·관행 고정값(곡선맞추기 X, N<50 walk-forward 금지). 변경 = 1회만 + PM 승인.
  · 종합 = 투명 tally(가중치 없음): net = (#on − #off) over active dims. net≥+2 risk-on / ≤−2 risk-off / else neutral.
  · 전부 "가설 v0" 라벨. RULE6: 결정론(LLM 0). 매매 미연결(관측-only).

차원 6 (입력 = crypto_collect 10피드. point-in-time 4개 = day1 active, 이력/브릿지 의존 3개 = 누적 중):
  1. 심리(Sentiment)       [active]  FNG 역발상(극공포=on/극탐욕=off) + 검색관심 급등=caution
  2. 포지셔닝(Positioning)  [active]  펀딩 과열=off + 풋콜 과도=on(역발상) + 롱숏 쏠림=off
  3. 자금흐름(Flows)        [active]  ETF(BTC+ETH) 일일 순플로 부호
  4. 추세(Trend)           [active]  BTC 7d 변화(v0 proxy; 200d SMA = TIDE 브릿지 후 교체)
  5. 유동성(Liquidity)     [누적중]  스테이블 공급 추세(이력 누적) + SSR 정보
  6. 펀더멘털·온체인        [브릿지]  DeFiLlama 매출 추세(이력) + 활성주소/NVT(TIDE 브릿지 대기)

유리박스: 일별 종합 판독 로깅(crypto_regime_trail.jsonl, date dedup) + forward BTC 7/30d 수익률 자가채점.
  hit = (risk_on & ret>0) or (risk_off & ret<0). neutral 제외. N·평균수익률 병기. N<30 "통계 무의미".
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

KST = timezone(timedelta(hours=9))
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(_REPO_ROOT, "data")
REGIME_PATH = os.path.join(DATA_DIR, "crypto_regime.json")
TRAIL_PATH = os.path.join(DATA_DIR, "crypto_regime_trail.jsonl")

# ── 사전등록 임계 (가설 v0 · 이론·관행 고정 · 곡선맞추기 금지) ──
FNG_EXTREME_FEAR = 25      # FNG ≤ → 역발상 on (De Bondt-Thaler 극단 평균회귀)
FNG_EXTREME_GREED = 75     # FNG ≥ → off
TREND_SPIKE_PCT = 50.0     # 검색관심 trend_pct ≥ → 과열 caution(off 쪽)
PUTCALL_FEAR = 1.2         # 풋콜 OI ≥ → 역발상 on (과도한 풋 헤지=항복)
PUTCALL_COMPLACENT = 0.5   # 풋콜 OI ≤ → off (안일)
LS_CROWDED_LONG = 2.0      # 롱숏 ≥ → off (롱 쏠림)
LS_CROWDED_SHORT = 0.7     # 롱숏 ≤ → on (숏 쏠림=역발상)
BTC_TREND_UP = 3.0         # BTC 7d % ≥ → on
BTC_TREND_DOWN = -3.0      # BTC 7d % ≤ → off
NET_RISK_ON = 2            # net tally ≥ → risk_on
NET_RISK_OFF = -2          # net tally ≤ → risk_off
SCORE_HORIZONS = (7, 30)   # forward 채점 지평(일)
SCORE_GRACE_DAYS = 2       # 지평 ±grace 내 가장 가까운 trail 가격으로 채점


def _now_kst() -> datetime:
    return datetime.now(KST)


def _load(name: str) -> Dict[str, Any]:
    path = os.path.join(DATA_DIR, name)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except (OSError, json.JSONDecodeError):
        return {}


def _vote_label(v: int) -> str:
    return "on" if v > 0 else ("off" if v < 0 else "neutral")


# ── 차원 1: 심리 (active) ──
def dim_sentiment(macro: Dict[str, Any], trends: Dict[str, Any]) -> Dict[str, Any]:
    fng = macro.get("fear_and_greed") or {}
    drivers: Dict[str, Any] = {}
    active = bool(fng.get("ok")) and fng.get("value") is not None
    vote = 0
    if active:
        v = float(fng["value"])
        drivers["fng"] = v
        if v <= FNG_EXTREME_FEAR:
            vote = 1
        elif v >= FNG_EXTREME_GREED:
            vote = -1
    # 검색관심 급등 = 과열 caution (역발상: 리테일 몰리면 후기) — vote 0 인 경우만 살짝 off 쪽
    kws = trends.get("keywords") or [] if trends.get("ok") else []
    btc_kw = next((k for k in kws if str(k.get("term", "")).lower().startswith("bitcoin")), None)
    if btc_kw and btc_kw.get("trend_pct") is not None:
        drivers["search_trend_pct"] = btc_kw["trend_pct"]
        if vote == 0 and float(btc_kw["trend_pct"]) >= TREND_SPIKE_PCT:
            vote = -1
    return {"name": "심리", "vote": vote, "read": _vote_label(vote), "active": active,
            "drivers": drivers, "rule": "FNG≤25 역발상 on / ≥75 off · 검색 급등 caution"}


# ── 차원 2: 포지셔닝 (active) ──
def dim_positioning(macro: Dict[str, Any], options: Dict[str, Any], positioning: Dict[str, Any]) -> Dict[str, Any]:
    drivers: Dict[str, Any] = {}
    sub = 0
    any_active = False
    funding = macro.get("funding_rate") or {}
    if funding.get("ok"):
        any_active = True
        sig = funding.get("signal")
        drivers["funding_signal"] = sig
        if sig == "long_overheat":
            sub -= 1
        elif sig in ("short_overheat", "underheat"):
            sub += 1
    obtc = (options.get("btc") or {}) if isinstance(options.get("btc"), dict) else {}
    pc = obtc.get("put_call_ratio_oi")
    if options.get("ok") and pc is not None:
        any_active = True
        drivers["put_call_oi"] = pc
        if float(pc) >= PUTCALL_FEAR:
            sub += 1
        elif float(pc) <= PUTCALL_COMPLACENT:
            sub -= 1
    pbtc = (positioning.get("btc") or {}) if isinstance(positioning.get("btc"), dict) else {}
    ls = pbtc.get("long_short_ratio")
    if positioning.get("ok") and ls is not None:
        any_active = True
        drivers["long_short_ratio"] = ls
        if float(ls) >= LS_CROWDED_LONG:
            sub -= 1
        elif float(ls) <= LS_CROWDED_SHORT:
            sub += 1
    vote = 1 if sub > 0 else (-1 if sub < 0 else 0)
    return {"name": "포지셔닝", "vote": vote, "read": _vote_label(vote), "active": any_active,
            "drivers": drivers, "rule": "펀딩 과열 off · 풋콜≥1.2 역발상 on · 롱숏≥2 쏠림 off"}


# ── 차원 3: 자금흐름 (active) ──
def dim_flows(etf: Dict[str, Any]) -> Dict[str, Any]:
    drivers: Dict[str, Any] = {}
    active = bool(etf.get("ok"))
    vote = 0
    if active:
        total = 0.0
        for sym in ("btc", "eth"):
            s = etf.get(sym) or {}
            ni = s.get("daily_net_inflow_usd")
            if ni is not None:
                total += float(ni)
                drivers[f"{sym}_net_inflow_usd"] = ni
        if total > 0:
            vote = 1
        elif total < 0:
            vote = -1
        drivers["combined_net_inflow_usd"] = total
    return {"name": "자금흐름", "vote": vote, "read": _vote_label(vote), "active": active,
            "drivers": drivers, "rule": "ETF(BTC+ETH) 일일 순유입 on / 순유출 off"}


# ── 차원 4: 추세 (active) ──
def dim_trend(universe: Dict[str, Any]) -> Dict[str, Any]:
    drivers: Dict[str, Any] = {}
    coins = universe.get("coins") or []
    btc = next((c for c in coins if c.get("id") == "bitcoin" or str(c.get("symbol", "")).lower() == "btc"), None)
    active = False
    vote = 0
    if btc:
        chg7 = btc.get("change_pct_7d")
        if chg7 is None:
            sp = btc.get("sparkline") or []
            if len(sp) >= 8 and sp[0]:
                chg7 = (float(sp[-1]) - float(sp[0])) / float(sp[0]) * 100.0
        if chg7 is not None:
            active = True
            drivers["btc_change_pct_7d"] = round(float(chg7), 2)
            if float(chg7) >= BTC_TREND_UP:
                vote = 1
            elif float(chg7) <= BTC_TREND_DOWN:
                vote = -1
    return {"name": "추세", "vote": vote, "read": _vote_label(vote), "active": active,
            "drivers": drivers, "rule": "BTC 7d ≥+3% on / ≤−3% off (v0 proxy, 200d SMA=TIDE 브릿지 후)"}


# ── 차원 5: 유동성 (누적 중 — 이력 의존) ──
def dim_liquidity(universe: Dict[str, Any], stablecoins: Dict[str, Any], macro: Dict[str, Any]) -> Dict[str, Any]:
    drivers: Dict[str, Any] = {}
    # SSR = BTC 시총 / 스테이블 총공급 (정보용 — level 임계는 약해 tally 미반영, 추세 누적 후 활성)
    btc_mcap = None
    for c in (universe.get("coins") or []):
        if c.get("id") == "bitcoin" or str(c.get("symbol", "")).lower() == "btc":
            btc_mcap = c.get("market_cap")
            break
    stable_usd = stablecoins.get("total_supply_usd")
    if stable_usd is None:
        sm = macro.get("stablecoin_mcap") or {}
        stable_usd = sm.get("total_mcap_usd")
    if btc_mcap and stable_usd:
        drivers["ssr"] = round(float(btc_mcap) / float(stable_usd), 2)
    if stable_usd:
        drivers["stablecoin_supply_usd"] = stable_usd
    return {"name": "유동성", "vote": 0, "read": "누적 중", "active": False,
            "drivers": drivers, "rule": "스테이블 공급 추세 = 이력 누적 후 활성 · SSR 정보용"}


# ── 차원 6: 펀더멘털·온체인 (브릿지 대기) ──
def dim_fundamentals(defillama: Dict[str, Any]) -> Dict[str, Any]:
    drivers: Dict[str, Any] = {}
    protos = defillama.get("protocols") or []
    if protos:
        drivers["top_protocol_fees_24h"] = {"name": protos[0].get("name"), "fees_24h": protos[0].get("fees_24h")}
        drivers["protocol_count"] = len(protos)
    return {"name": "펀더멘털·온체인", "vote": 0, "read": "브릿지 대기", "active": False,
            "drivers": drivers, "rule": "DeFiLlama 매출 추세=이력 누적 · 활성주소/NVT=TIDE 브릿지 후"}


def compute_dimensions() -> List[Dict[str, Any]]:
    macro = _load("crypto_macro.json")
    trends = _load("crypto_trends.json")
    options = _load("crypto_options.json")
    positioning = _load("crypto_positioning.json")
    etf = _load("crypto_etf_flow.json")
    universe = _load("crypto_universe.json")
    stablecoins = _load("crypto_stablecoins.json")
    defillama = _load("crypto_defillama.json")
    return [
        dim_sentiment(macro, trends),
        dim_positioning(macro, options, positioning),
        dim_flows(etf),
        dim_trend(universe),
        dim_liquidity(universe, stablecoins, macro),
        dim_fundamentals(defillama),
    ]


def aggregate(dims: List[Dict[str, Any]]) -> Tuple[str, int, int]:
    active = [d for d in dims if d.get("active")]
    net = sum(int(d["vote"]) for d in active)
    if net >= NET_RISK_ON:
        call = "risk_on"
    elif net <= NET_RISK_OFF:
        call = "risk_off"
    else:
        call = "neutral"
    return call, net, len(active)


def _btc_price(universe: Dict[str, Any]) -> Optional[float]:
    for c in (universe.get("coins") or []):
        if c.get("id") == "bitcoin" or str(c.get("symbol", "")).lower() == "btc":
            p = c.get("current_price")
            return float(p) if p is not None else None
    return None


def _read_trail() -> List[Dict[str, Any]]:
    if not os.path.isfile(TRAIL_PATH):
        return []
    out: List[Dict[str, Any]] = []
    try:
        with open(TRAIL_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return out


def _write_trail(entries: List[Dict[str, Any]]) -> None:
    tmp = TRAIL_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    os.replace(tmp, TRAIL_PATH)


def _score_trail(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """forward BTC 수익률 자가채점 — date→price 맵 기준 horizon±grace 가장 가까운 가격으로."""
    dated = []
    for e in entries:
        try:
            d = datetime.strptime(e["date"], "%Y-%m-%d").date()
            if e.get("btc_price"):
                dated.append((d, e))
        except (KeyError, ValueError):
            continue
    dated.sort(key=lambda x: x[0])
    price_by_date = {d: float(e["btc_price"]) for d, e in dated}
    all_dates = [d for d, _ in dated]

    buckets = []
    for horizon in SCORE_HORIZONS:
        hits = 0
        eligible = 0
        rets: List[float] = []
        for d, e in dated:
            call = e.get("call")
            if call not in ("risk_on", "risk_off"):
                continue
            target = d + timedelta(days=horizon)
            best = None
            best_gap = SCORE_GRACE_DAYS + 1
            for ad in all_dates:
                gap = abs((ad - target).days)
                if gap < best_gap:
                    best_gap = gap
                    best = ad
            if best is None or best_gap > SCORE_GRACE_DAYS:
                continue
            p0 = float(e["btc_price"])
            p1 = price_by_date[best]
            if p0 <= 0:
                continue
            ret = (p1 - p0) / p0
            eligible += 1
            rets.append(ret)
            if (call == "risk_on" and ret > 0) or (call == "risk_off" and ret < 0):
                hits += 1
        n = eligible
        bucket = {
            "horizon_days": horizon,
            "n": n,
            "hit_rate": round(hits / n, 4) if n else None,
            "mean_realized_return": round(sum(rets) / len(rets), 6) if rets else None,
            "label": "통계 무의미 (N<30)" if n < 30 else "예비 결과",
        }
        buckets.append(bucket)
    return {"buckets": buckets,
            "_disclaimer": "가설 v0 · 관측-only · 매매 미연결 · hit rate는 N·평균수익률 병기 · N<30 통계 무의미"}


def build_regime() -> Tuple[Dict[str, Any], bool]:
    universe = _load("crypto_universe.json")
    dims = compute_dimensions()
    call, net, active_count = aggregate(dims)
    btc_price = _btc_price(universe)
    now = _now_kst()
    date_str = now.strftime("%Y-%m-%d")

    # 유리박스 trail — date dedup, 일별 1엔트리
    entries = _read_trail()
    entries = [e for e in entries if e.get("date") != date_str]
    if btc_price:
        entries.append({"date": date_str, "call": call, "net_score": net,
                        "btc_price": btc_price, "active_dims": active_count})
    entries.sort(key=lambda e: e.get("date", ""))
    _write_trail(entries)
    track_record = _score_trail(entries)

    payload = {
        "collected_at": now.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "schema_version": "v0",
        "spec": "crypto_regime_synthesis_v0 (사전등록 2026-06-24, PM 승인: 역발상+채점 지금)",
        "composite": {"call": call, "net_score": net, "active_dims": active_count,
                      "rule": "net≥+2 risk_on / ≤−2 risk_off / else neutral (투명 tally, 가중치 없음)"},
        "dimensions": dims,
        "btc_price_at_call": btc_price,
        "track_record": track_record,
        "_disclaimer": "가설 v0 · 자체 기준 · 관측-only · 매매 미연결 · 임계 변경 1회+PM 승인",
    }
    ok = active_count >= 1 and btc_price is not None
    return payload, ok


def _atomic_write(path: str, data: Dict[str, Any]) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def main() -> int:
    payload, ok = build_regime()
    _atomic_write(REGIME_PATH, payload)
    comp = payload["composite"]
    sys.stderr.write(f"[crypto_regime] call={comp['call']} net={comp['net_score']} "
                     f"active={comp['active_dims']} ok={ok}\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
