"""dart_importance_observer — DART 공시 중요도 게이팅 관측 (C1, SHADOW only).

목적 (2026-06-15): "공시 중요도(severity)로 게이팅하면 forward return 예측력(IC)이 더해지는가"
가설을 관측-only 로 검증한다. dart_catalyst.py 가 이미 live 로 산출하는 5-tier severity
(=중요도 프록시) + dart_catalyst_alerts.jsonl 을 그대로 재사용하고, 가격레이크에서
price_at_event + forward return 만 조인한다.

🚨 적대적 검증 2026-06-14 핵심:
   · 카탈로그 통계(S&P 6.4%/51.5%)는 web 검증 0건 = **날조 의심** → 임계 prior 없음.
   · 동료심사급(arXiv 2510.03195)은 LLM 공시 long-short 에 **음(-)의 알파(t≈-2.5)** →
     **부호가 가설(+)과 반대일 수 있음.** 그래서 이 관측의 1차 목적 = "부호가 어느 쪽인가"
     를 N 으로 확인하는 것.
   · **N<50 = 임계 미설정, 관측-only 적재만**(임계 fit=곡선맞추기 금지). score-wire =
     N≥50 + walk-forward 1회 + H2(IC_gated > IC_all) 통과 + PM 승인.
   · **재구현 금지** — 기존 severity 재사용만. LLM importance 점수는 deferred 강화
     (이 rule-based 게이트가 IC 보이면 그때 비용 정당화. 지금=LLM 0, 비용 0).
   · mass-fire 가드: severity 가 전부 동일하면 변별력 0 → IC 의미 없음(분포 로깅으로 감시).

🚨 SHADOW ONLY — brain 점수/등급/추천 입력 0. data/observations/ 별 trail.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone, date, timedelta
from typing import Any, Dict, List, Optional

from api.config import DATA_DIR, now_kst

ALERTS_PATH = os.path.join(DATA_DIR, "dart_catalyst_alerts.jsonl")
OBS_DIR = os.path.join(DATA_DIR, "observations")
OBS_PATH = os.path.join(OBS_DIR, "dart_importance_gating.jsonl")
LAKE_PATH = os.path.expanduser("~/VERITY_data_lake/kr_prices.duckdb")

_FWD_HORIZONS = [1, 5, 20]   # d1/d5/d20 forward return


def _load_alerts() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not os.path.exists(ALERTS_PATH):
        return out
    with open(ALERTS_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out


def _existing_rcept_nos() -> set:
    seen = set()
    if not os.path.exists(OBS_PATH):
        return seen
    with open(OBS_PATH, "r", encoding="utf-8") as f:
        for line in f:
            try:
                seen.add(json.loads(line).get("rcept_no"))
            except Exception:
                continue
    return seen


def _lake_closes(ticker: str, start: str) -> List[tuple]:
    """price lake 에서 ticker 의 start 이후 (date, close) — 오름차순. 없으면 []."""
    try:
        import duckdb
        con = duckdb.connect(LAKE_PATH, read_only=True)
        rows = con.execute(
            "SELECT date, close FROM ohlcv WHERE ticker = ? AND date >= ? ORDER BY date",
            [ticker, start],
        ).fetchall()
        con.close()
        return [(r[0], float(r[1])) for r in rows]
    except Exception:
        return None


def _price_and_fwd(ticker: str, rcept_dt: str) -> Dict[str, Any]:
    """공시일(rcept_dt YYYYMMDD) 기준 price_at_event + d1/d5/d20 forward return.

    price_at_event = rcept_dt 당일 또는 그 이후 첫 거래일 종가. forward = 그로부터 N 거래일.
    가격레이크 미존재/부족 = None (PIT: 미래 데이터 없으면 null, 추후 레이크 갱신 시 재계산).
    """
    try:
        start = f"{rcept_dt[:4]}-{rcept_dt[4:6]}-{rcept_dt[6:8]}"
    except Exception:
        return {"price_at_event": None, "fwd": {}, "lake": "bad_date"}
    closes = _lake_closes(ticker, start)
    if closes is None:
        return {"price_at_event": None, "fwd": {}, "lake": "fetch_fail"}
    if not closes:
        return {"price_at_event": None, "fwd": {}, "lake": "no_data"}
    base_price = closes[0][1]
    fwd: Dict[str, Optional[float]] = {}
    for h in _FWD_HORIZONS:
        if len(closes) > h and base_price > 0:
            fwd[f"d{h}"] = round((closes[h][1] - base_price) / base_price, 5)
        else:
            fwd[f"d{h}"] = None
    return {"price_at_event": round(base_price, 2), "fwd": fwd,
            "lake": "ok", "available_days": len(closes) - 1}


def build_observations() -> List[Dict[str, Any]]:
    """기존 catalyst alert(severity 분류 완료) → price/forward 조인 관측 레코드."""
    alerts = _load_alerts()
    seen = _existing_rcept_nos()
    obs: List[Dict[str, Any]] = []
    for a in alerts:
        rcept_no = a.get("rcept_no")
        if not rcept_no or rcept_no in seen:
            continue
        ticker = a.get("ticker", "")
        pf = _price_and_fwd(ticker, str(a.get("rcept_dt", "")))
        fwd = pf["fwd"]
        scored = fwd.get("d20") is not None   # d20 채워지면 채점 가능
        obs.append({
            "logged_at": now_kst().isoformat(),
            "rcept_no": rcept_no,
            "ticker": ticker,
            "name": a.get("name"),
            "severity": a.get("severity"),          # 중요도 게이트 (기존 분류 재사용)
            "pblntf_label": a.get("pblntf_label"),
            "is_correction": a.get("is_correction"),
            "rcept_dt": a.get("rcept_dt"),
            "price_at_event": pf["price_at_event"],
            "fwd_ret": fwd,                          # d1/d5/d20 (가용분만, 나머지 null)
            "lake_status": pf["lake"],
            "scored": scored,
            "shadow": True,
            "brain_input": False,
        })
    return obs


def severity_distribution(obs: List[Dict[str, Any]]) -> Dict[str, int]:
    """mass-fire 가드 — severity 분포(전부 동일이면 변별력 0)."""
    dist: Dict[str, int] = {}
    for o in obs:
        s = str(o.get("severity"))
        dist[s] = dist.get(s, 0) + 1
    return dist


def score_observations() -> Dict[str, Any]:
    """관측 이벤트 로그 → 레이크에서 forward return **재계산**(authoritative, 결정론).

    이게 N≥50 IC 분석 진입점. 로깅된 fwd_ret(스냅샷)이 stale/null 이어도 여기서 항상
    최신 레이크로 다시 계산 → backfill 문제 원천 해소(append-only 로그는 이벤트만 보존,
    forward 는 분석 시점 재산출 = PIT 정합). **IC/부호 판정은 N≥50 도달 시에만**(여기선
    채점 가능 레코드 수 + severity별 평균 forward 만 노출, 임계 판정 금지).
    """
    if not os.path.exists(OBS_PATH):
        return {"status": "no_observations"}
    by_sev: Dict[str, List[float]] = {}
    total, scorable = 0, 0
    with open(OBS_PATH, "r", encoding="utf-8") as f:
        for line in f:
            try:
                o = json.loads(line)
            except Exception:
                continue
            total += 1
            pf = _price_and_fwd(o.get("ticker", ""), str(o.get("rcept_dt", "")))
            d5 = pf["fwd"].get("d5")
            if d5 is None:
                continue
            scorable += 1
            sev = str(o.get("severity"))
            by_sev.setdefault(sev, []).append(d5)
    # severity별 평균 forward (부호 관찰용 — 판정 아님, N<50 무의미 명시)
    sev_avg = {s: round(sum(v) / len(v), 5) for s, v in by_sev.items() if v}
    sev_n = {s: len(v) for s, v in by_sev.items()}
    return {
        "status": "ok",
        "total_observations": total,
        "scorable_d5": scorable,
        "severity_avg_fwd_d5": sev_avg,
        "severity_n": sev_n,
        "note": ("부호 관찰용. N<50=통계 무의미. IC/H2 판정은 N≥50 walk-forward 후. "
                 "severity별 평균이 0 근처거나 부호 역전(검증 경고) 여부만 N 누적 관찰."),
    }


def run_shadow() -> Dict[str, Any]:
    """신규 공시 관측 → dart_importance_gating.jsonl 적재(brain 무입력) → 요약."""
    obs = build_observations()
    if obs:
        try:
            os.makedirs(OBS_DIR, exist_ok=True)
            with open(OBS_PATH, "a", encoding="utf-8") as f:
                for o in obs:
                    f.write(json.dumps(o, ensure_ascii=False) + "\n")
        except Exception:
            pass
    return {
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "new_observations": len(obs),
        "scored_now": sum(1 for o in obs if o["scored"]),
        "severity_dist": severity_distribution(obs),
        "caveat": ("SHADOW DART 중요도 게이팅 관측. 임계 미설정(N<50). 부호 미확정(검증상 "
                   "역(-) 알파 가능). H2(IC_gated>IC_all) + N≥50 walk-forward + PM 승인 전 "
                   "wire 금지. 기존 severity 재사용(LLM 0). brain-input 0."),
    }


if __name__ == "__main__":
    r = run_shadow()
    print(f"[dart_importance] SHADOW — 신규 관측 {r['new_observations']} (채점가능 {r['scored_now']})")
    print(f"  severity 분포: {r['severity_dist']}")
    print(f"  ⚠ {r['caveat']}")
