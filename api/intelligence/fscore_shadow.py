# -*- coding: utf-8 -*-
"""B3 F-Score/Accrual shadow IC trail — 관측 전용 검증 축 (brain-input 0).

사전등록 = docs/PREREG_FSCORE_ACCRUAL_B3_2026_07_12.md
  PM 부분 승인 2026-07-12 ("굿임 고고") — §2·§3·§5·§6 동결, shadow IC trail 착수 승인.
  본 모듈은 **그 등록의 집행**이다 (신규 산식·신규 승인 0).

왜 별도 축인가 (§3): F-Score 는 이미 Brain quality 35점을 구동한다. 그 소비 축에서
예측력을 재면 "쓰고 있으니 좋다"는 순환이 된다. 검증은 소비와 분리된 독립 trail 에서만
성립한다. 이 trail 은 어떤 점수에도 입력되지 않는다.

산출:
  data/fscore_ic_shadow.jsonl   — 관측 entry (ticker × signal × horizon), forward-only
  data/fscore_ic_history.jsonl  — (signal, horizon) 집계 append

동결 계약 (§1·§2 — 튜닝 금지):
  · 신호 2종 = F-Score(0~9, wide_scan._piotroski_f_score SoT) · accrual(Sloan)
  · accrual = (NI − CFO) / 평균총자산. 低 = 양호 → 순위 방향 −1 로 정렬(H1 이 양쪽 IC>0)
  · horizon 3종 = 21 / 63 / 252 거래일 — 전부 paired 병기(cherry-pick 금지)
  · 결측 철학 = available_n < 9 → score None → 관측 제외 (부분 점수 금지)
  · 임계 스윕·그리드서치 금지. 현행 정의 1개의 성적만 낸다.

게이트 (§3): N ≥ 252 ∧ IC > 0.03 ∧ ICIR > 0.3 → N ≥ 684 시 DSR/PBO 2차.
  N = **일별 단면 개수**(거래일 ≈ 1년). N<30 "통계 무의미" / N<100 "예비 결과" 라벨 의무.
  실패 조항 = 게이트 시점 CI95 가 0 을 포함하면 재보정 금지(폐기 또는 현행 유지).

look-ahead 차단 (§6): Δ 는 fscore_delta 의 분기 공시 lag 적용분만 사용(기존 계약 승계).
base 가격은 관측 당일 이전 스냅샷만 참조(prediction_scoring._realized_stock_return 승계).
"""
from __future__ import annotations

import json
import math
import os
import statistics
from typing import Any, Dict, List, Optional, Tuple

from api.config import DATA_DIR, now_kst

SPEC_VERSION = "b3_fscore_accrual_v0"
TRAIL_PATH = os.path.join(DATA_DIR, "fscore_ic_shadow.jsonl")
HISTORY_PATH = os.path.join(DATA_DIR, "fscore_ic_history.jsonl")

# ── 등록 상수 (LOCKED — 조정 = 재등록) ──────────────────────────────────────
HORIZONS = {"21d": 21, "63d": 63, "252d": 252}   # §2 거래일
SIGNALS = ("fscore", "accrual")
SIGNAL_DIRECTION = {"fscore": 1, "accrual": -1}   # accrual 低=양호 → 부호 반전 후 IC>0 검정
MIN_CROSS_SECTION = 5      # 단면 rank-IC 최소 종목 수 (미만 = 그날 단면 폐기)
GATE_N = 252
GATE_IC = 0.03
GATE_ICIR = 0.3
GRACE_DAYS = 14            # eval 후 가격 결손 재시도 유예 (prediction trail 선례)

_LABEL_MEANINGLESS = "통계 무의미 (N<30)"
_LABEL_PRELIM = "예비 결과, 검증 진행 중 (N<100)"
_LABEL_ACCUMULATING = "누적 중 — 게이트 N=252 미도달"
_LABEL_GATED = "게이트 판정 가능"


def _load_jsonl(path: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _rewrite_jsonl(path: str, rows: List[Dict[str, Any]]) -> None:
    tmp = path + ".tmp"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def _append_jsonl(path: str, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _add_trading_days(date_str: str, n: int) -> str:
    """거래일 n 일 후의 달력일 근사 — 주말만 건너뛴다(공휴일 미반영).

    eval_date 는 채점 '자격 시점'일 뿐이고 실제 수익률은 최근접 스냅샷으로 계산하므로
    (prediction_scoring 계약 승계) 근사로 충분하다. 공휴일은 채점을 늦출 뿐 왜곡하지 않는다.
    """
    from datetime import datetime, timedelta
    d = datetime.strptime(date_str, "%Y-%m-%d")
    added = 0
    while added < n:
        d += timedelta(days=1)
        if d.weekday() < 5:
            added += 1
    return d.strftime("%Y-%m-%d")


# ── 신호 산출 ────────────────────────────────────────────────────────────

def compute_accrual(stock: Dict[str, Any]) -> Optional[float]:
    """Sloan(1996) accrual = (NI − CFO) / 평균총자산. 총자산 1기만 있으면 그 값으로 대체.

    반환 None = 계산 불가(결측). 부분 추정 금지 — 등록 §1 결측 철학 정합.
    """
    try:
        eps = stock.get("eps")
        shares = stock.get("shares_outstanding")
        cfo = stock.get("operating_cashflow")
        if eps is None or shares is None or cfo is None:
            return None
        ni = float(eps) * float(shares)
        fin = ((stock.get("dart_financials") or {}).get("financials") or {})
        ta = fin.get("total_assets") or stock.get("total_assets")
        if not ta:
            sec = stock.get("sec_financials") or {}
            ta = sec.get("total_assets")
        ta = float(ta or 0)
        if ta <= 0:
            return None
        return round((ni - float(cfo)) / ta, 6)
    except (TypeError, ValueError):
        return None


def observe(analyzed: List[Dict[str, Any]], base_date: Optional[str] = None) -> Dict[str, Any]:
    """당일 단면 관측 기록 (forward-only). 반환 = 요약 dict.

    같은 base_date 재실행 시 중복 append 하지 않는다(멱등).
    """
    base_date = base_date or now_kst().strftime("%Y-%m-%d")
    existing = _load_jsonl(TRAIL_PATH)
    if any(e.get("base_date") == base_date for e in existing):
        return {"base_date": base_date, "skipped": "already_observed",
                "trail_rows": len(existing)}

    from api.analyzers.wide_scan import _piotroski_f_score

    rows: List[Dict[str, Any]] = []
    n_f = n_a = 0
    for st in analyzed:
        ticker = str(st.get("ticker") or "").strip()
        if not ticker:
            continue
        vals: Dict[str, Any] = {}
        try:
            fs = _piotroski_f_score(st) or {}
        except Exception:  # noqa: BLE001 — 관측이 파이프를 죽이지 않는다
            fs = {}
        # §1 결측 철학: available_n < 9 = 전체 무효 (부분 점수 금지)
        if isinstance(fs.get("score"), (int, float)) and int(fs.get("available_n") or 0) >= 9:
            vals["fscore"] = float(fs["score"])
            n_f += 1
        acc = compute_accrual(st)
        if acc is not None:
            vals["accrual"] = acc
            n_a += 1
        for sig, val in vals.items():
            for hz, days in HORIZONS.items():
                rows.append({
                    "obs_id": f"{sig}_{ticker}_{base_date}_{hz}",
                    "spec_version": SPEC_VERSION,
                    "created_at": now_kst().isoformat(timespec="seconds"),
                    "base_date": base_date,
                    "ticker": ticker,
                    "market": "US" if st.get("currency") == "USD" else "KR",
                    "signal": sig,
                    "value": val,
                    "horizon": hz,
                    "eval_date": _add_trading_days(base_date, days),
                    "scored": False,
                    "realized_return": None,
                })
    _append_jsonl(TRAIL_PATH, rows)
    return {"base_date": base_date, "appended": len(rows),
            "fscore_n": n_f, "accrual_n": n_a, "trail_rows": len(existing) + len(rows)}


# ── 채점 ────────────────────────────────────────────────────────────────

def score(today: Optional[str] = None) -> Dict[str, Any]:
    """eval_date 도달분 채점 — 실현 수익률 부착 후 scored=True rewrite."""
    today = today or now_kst().strftime("%Y-%m-%d")
    rows = _load_jsonl(TRAIL_PATH)
    if not rows:
        return {"scored": 0, "pending": 0, "expired": 0}

    from api.intelligence.prediction_scoring import _realized_stock_return
    from api.workflows.archiver import list_available_dates
    available = list_available_dates()

    scored = pending = expired = 0
    for r in rows:
        if r.get("scored") or r.get("expired"):
            continue
        if str(r.get("eval_date") or "") > today:
            continue
        ret = _realized_stock_return(str(r.get("ticker")), str(r.get("base_date")),
                                     str(r.get("eval_date")), available)
        if ret is None:
            # grace 초과 = 영구 결손(상폐·데이터 부재) → 만료 처리, 무한 재시도 방지
            from datetime import datetime, timedelta
            try:
                over = (datetime.strptime(today, "%Y-%m-%d")
                        - datetime.strptime(str(r["eval_date"]), "%Y-%m-%d")).days
            except ValueError:
                over = 0
            if over > GRACE_DAYS:
                r["expired"] = True
                expired += 1
            else:
                pending += 1
            continue
        r["realized_return"] = ret
        r["scored"] = True
        r["scored_at"] = now_kst().isoformat(timespec="seconds")
        scored += 1
    _rewrite_jsonl(TRAIL_PATH, rows)
    return {"scored": scored, "pending": pending, "expired": expired, "trail_rows": len(rows)}


def _label(n: int) -> str:
    if n < 30:
        return _LABEL_MEANINGLESS
    if n < 100:
        return _LABEL_PRELIM
    if n < GATE_N:
        return _LABEL_ACCUMULATING
    return _LABEL_GATED


def _bootstrap_ci95(values: List[float], iters: int = 2000) -> Optional[List[float]]:
    """평균의 95% CI (편향 없는 재표본). N<3 = None."""
    n = len(values)
    if n < 3:
        return None
    import random
    rnd = random.Random(20260712)  # 결정론 — 같은 입력 = 같은 CI (재현성)
    means = []
    for _ in range(iters):
        means.append(sum(rnd.choice(values) for _ in range(n)) / n)
    means.sort()
    lo = means[int(0.025 * iters)]
    hi = means[int(0.975 * iters) - 1]
    return [round(lo, 4), round(hi, 4)]


def _cross_section_ic(pairs: List[Tuple[float, float]], direction: int) -> Optional[float]:
    """단면 rank-IC (Spearman). direction 으로 신호 방향 정렬 후 계산."""
    if len(pairs) < MIN_CROSS_SECTION:
        return None
    from api.intelligence.prediction_scoring import _spearman_ic
    sig = [direction * p[0] for p in pairs]
    ret = [p[1] for p in pairs]
    return _spearman_ic(sig, ret)


def _tercile_spread(pairs: List[Tuple[float, float]], direction: int) -> Optional[float]:
    """상위 1/3 − 하위 1/3 평균 수익률(%p) — expectancy 축(롱숏 스프레드)."""
    if len(pairs) < 6:
        return None
    srt = sorted(pairs, key=lambda p: direction * p[0])
    k = max(1, len(srt) // 3)
    lo = [p[1] for p in srt[:k]]
    hi = [p[1] for p in srt[-k:]]
    return round(sum(hi) / len(hi) - sum(lo) / len(lo), 4)


def aggregate() -> List[Dict[str, Any]]:
    """(signal, horizon) 별 집계 → history append. RULE 7: 모든 지표 paired 병기."""
    rows = [r for r in _load_jsonl(TRAIL_PATH) if r.get("scored")]
    out: List[Dict[str, Any]] = []
    stamp = now_kst().isoformat(timespec="seconds")

    for sig in SIGNALS:
        direction = SIGNAL_DIRECTION[sig]
        for hz in HORIZONS:
            by_date: Dict[str, List[Tuple[float, float]]] = {}
            for r in rows:
                if r.get("signal") != sig or r.get("horizon") != hz:
                    continue
                v, ret = r.get("value"), r.get("realized_return")
                if isinstance(v, (int, float)) and isinstance(ret, (int, float)):
                    by_date.setdefault(str(r.get("base_date")), []).append((float(v), float(ret)))

            ics: List[float] = []
            spreads: List[float] = []
            for d in sorted(by_date):
                ic = _cross_section_ic(by_date[d], direction)
                if ic is None:
                    continue
                ics.append(ic)
                sp = _tercile_spread(by_date[d], direction)
                if sp is not None:
                    spreads.append(sp)

            n = len(ics)
            ic_mean = round(statistics.mean(ics), 4) if n else None
            ic_std = round(statistics.stdev(ics), 4) if n >= 2 else None
            icir = round(ic_mean / ic_std, 4) if (ic_mean is not None and ic_std) else None
            hit = round(sum(1 for x in ics if x > 0) / n, 4) if n else None
            ci95 = _bootstrap_ci95(ics)
            expectancy = round(statistics.mean(spreads), 4) if spreads else None
            gate_pass = bool(n >= GATE_N and (ic_mean or 0) > GATE_IC and (icir or 0) > GATE_ICIR)

            out.append({
                "scored_at": stamp,
                "spec_version": SPEC_VERSION,
                "signal": sig,
                "signal_direction": direction,
                "horizon": hz,
                # RULE 7 — hit 단독/expectancy 단독 게재 금지. 전 지표 동시 노출.
                "n_cross_sections": n,
                "ic_mean": ic_mean,
                "ic_std": ic_std,
                "icir": icir,
                "ic_hit_rate": hit,
                "expectancy_spread_pp": expectancy,
                "ci95_ic": ci95,
                "ci95_includes_zero": (None if not ci95 else bool(ci95[0] <= 0 <= ci95[1])),
                "gate": {"n_min": GATE_N, "ic_min": GATE_IC, "icir_min": GATE_ICIR,
                         "pass": gate_pass},
                "label": _label(n),
                "brain_input": False,
                "note": ("관측 전용 — 어떤 점수에도 입력되지 않는다. "
                         "PREREG_FSCORE_ACCRUAL_B3_2026_07_12 §3. "
                         "CI95 가 0 을 포함한 채 게이트 도달 시 재보정 금지(폐기 또는 현행 유지)."),
            })
    _append_jsonl(HISTORY_PATH, out)
    return out
