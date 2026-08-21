#!/usr/bin/env python3
"""희석 오버행 패널 — 사전등록 `PREREG_DILUTION_INSIDER_CROSS_2026_08_21.md` L1 집행.

🚨 **관측 전용.** 산식 변경 0 · `brain_input=False` · RULE 7 쿼터 미소모.
🚨 발행 화이트리스트에 넣지 않는다(Vercel 전송비 증가 0).

## 무엇을 재는가 (등록된 정의 §0′-1)

    시점 T 유효 오버행 = cvrqpd_bgd ≤ T ≤ cvrqpd_edd 인 CB/BW 의 cvisstk_cnt 합

🚨 **잔량이 아니라 잔량의 상한이다.** 전환 실행분은 모른다. 결과 문장에 항상 동반한다.

## 등록된 규칙 (결과 보기 전 고정 — 여기서 바꾸지 말 것)

- 결과변수 = forward 3개월 / 6개월 수익률 **연속값**
- 검출하한 **d ≥ 0.37** 미만이면 "검출 불가" 로 적는다. "효과 없음" 이라 쓰지 않는다
- 다중비교 8회 — 명목 유의로 승자를 고르지 않는다
- 🚨 상폐 미제외 — 가격이 끊기면 그 시점 관측 종료로 처리하고 분모에 유지한다
- 월 고정효과를 함께 본다(단일 국면 아님을 이용)
"""
from __future__ import annotations

import glob
import json
import os
import re
import statistics
import sys
from datetime import date

import numpy.core as _np_core

sys.modules.setdefault("numpy._core", _np_core)
for _sub in ("numeric", "multiarray", "umath", "numerictypes", "_multiarray_umath", "overrides"):
    try:
        sys.modules[f"numpy._core.{_sub}"] = __import__(f"numpy.core.{_sub}", fromlist=[_sub])
    except Exception:
        pass
import pickle  # noqa: E402  (별칭 뒤에 import)

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = os.path.join(_ROOT, "data")
OUT = os.path.join(DATA, "metadata", "dilution_overhang_panel.json")

_KDATE = re.compile(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일")


def kdate(v) -> date | None:
    m = _KDATE.match(str(v or ""))
    return date(int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def num(v) -> float | None:
    s = str(v or "").replace(",", "").strip()
    if s in ("", "-", "None"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def month_ends(y0: int, m0: int, y1: int, m1: int) -> list[date]:
    out, y, m = [], y0, m0
    while (y, m) <= (y1, m1):
        nm_y, nm_m = (y + 1, 1) if m == 12 else (y, m + 1)
        out.append(date(nm_y, nm_m, 1))          # 다음달 1일 = 이 달 경계
        y, m = nm_y, nm_m
    return out


def load_prices() -> dict[str, dict[date, float]]:
    """pkl(상장 장기) + delisted 청크(상폐) — 🚨 상폐를 반드시 포함한다(§5-4)."""
    px: dict[str, dict[date, float]] = {}
    for p in glob.glob(os.path.join(DATA, "cache", "5r_analysis_ohlcv", "*.pkl")):
        tk = os.path.basename(p).split("_")[0]
        try:
            df = pickle.load(open(p, "rb"))
            px[tk] = {d.date(): float(c) for d, c in zip(df.index, df["close"]) if c == c}
        except Exception:
            continue
    for f in glob.glob(os.path.join(DATA, "kr_chart_delisted", "chunk_*.json")):
        try:
            st = (json.load(open(f, encoding="utf-8")) or {}).get("stocks") or {}
        except Exception:
            continue
        for tk, v in st.items():
            ser = {}
            for r in (v.get("c") or []):
                try:
                    s = str(r[0])
                    ser[date(int(s[:4]), int(s[4:6]), int(s[6:8]))] = float(r[4])
                except Exception:
                    continue
            if ser:
                px.setdefault(tk, {}).update(ser)
    return px


def px_at(ser: dict[date, float], t: date, back: int = 10) -> float | None:
    """t 이하 최근 거래일 종가. back 일 안에 없으면 None(= 그 시점 관측 불가)."""
    ds = [d for d in ser if d <= t]
    if not ds:
        return None
    last = max(ds)
    return ser[last] if (t - last).days <= back else None


def cohen_d(a: list[float], b: list[float]) -> float | None:
    if len(a) < 2 or len(b) < 2:
        return None
    va, vb = statistics.pvariance(a), statistics.pvariance(b)
    n1, n2 = len(a), len(b)
    sp = ((n1 * va + n2 * vb) / (n1 + n2)) ** 0.5
    return None if sp == 0 else (statistics.mean(a) - statistics.mean(b)) / sp


def main() -> int:
    det = json.load(open(os.path.join(DATA, "dart_cb_bw_detail.json"), encoding="utf-8"))["by_ticker"]
    px = load_prices()
    print(f"[panel] CB/BW 종목 {len(det)} · 가격 보유 {len(px)}")

    # instrument 정규화 — 🚨 파싱 실패는 버리지 않고 센다
    inst: dict[str, list[dict]] = {}
    drop = 0
    for tk, v in det.items():
        rows = []
        for x in v["instruments"]:
            # 🚨 공통키 x_* — 수집기가 CB/BW 를 정규화한다. 종전엔 CB 이름만 읽어
            #   BW 187건이 100% 탈락했고 2015~16 은 99%/94% 탈락했다(실측).
            b, e = kdate(x.get("x_bgd")), kdate(x.get("x_edd"))
            cnt, pct = num(x.get("x_cnt")), num(x.get("x_pct"))
            d0 = kdate(x.get("bddd"))
            derived = bool(x.get("x_cnt_derived"))
            if not (b and e) or (cnt is None and pct is None):
                drop += 1
                continue
            rows.append({"b": b, "e": e, "cnt": cnt, "pct": pct, "bddd": d0,
                         "kind": x.get("kind"), "derived": derived})
        if rows:
            inst[tk] = rows
    tot_inst = sum(len(v["instruments"]) for v in det.values())
    print(f"[panel] instrument {tot_inst} · 사용 {tot_inst - drop} · 🚨 필수필드 결측으로 제외 {drop} "
          f"({drop/tot_inst*100:.1f}%)")

    HOR = {"m3": 3, "m6": 6}
    ends = month_ends(2015, 1, 2025, 9)
    panel = []
    for t in ends:
        for tk, ser in px.items():
            p0 = px_at(ser, t)
            if p0 is None or p0 <= 0:
                continue                      # 🚨 상폐 후 = 관측 종료(제외 아님, 종료)
            rows = inst.get(tk) or []
            live = [r for r in rows if r["b"] <= t <= r["e"]]
            # 🚨 pct(총수대비%)가 없는 건은 오버행 합에 못 넣는다 — 분모(발행주식수)가
            #   시점별로 없기 때문이다. 뺀 수를 함께 센다.
            ov_pct = sum(r["pct"] for r in live if r["pct"] is not None)
            n_nopct = sum(1 for r in live if r["pct"] is None)
            freq1y = sum(1 for r in rows if r["bddd"] and 0 <= (t - r["bddd"]).days <= 365)
            rec = {"t": t.isoformat(), "tk": tk, "ov": ov_pct, "n_live": len(live),
                   "n_nopct": n_nopct, "freq1y": freq1y}
            last_d = max(ser)
            for name, mth in HOR.items():
                y, m = t.year, t.month + mth
                y, m = (y + (m - 1) // 12, (m - 1) % 12 + 1)
                tgt = date(y, m, 1)
                p1 = px_at(ser, tgt)
                # 🚨 §5-4 이행 — 지평 안에서 시계열이 끝나면(= 상폐·거래정지) **마지막 거래가**를
                #   종말값으로 쓴다. 종전 코드는 관측을 그냥 버려서 "분모엔 유지" 만 지키고
                #   결과값을 빼먹었다 = 규칙을 절반만 지킨 것.
                #   🚨 일괄 −100% 는 쓰지 않는다 — 합병·자진상폐는 프리미엄에 사라지므로
                #   편향이 반대로 뒤집힌다. 데이터가 말하게 둔다.
                #   ⚠ 정리매매 마지막 가격도 0 이 아니므로 실손실을 **과소평가**한다(한계).
                terminal = False
                if p1 is None and last_d < tgt:
                    p1 = ser[last_d]
                    terminal = True
                rec[name] = (p1 / p0 - 1) if (p1 and p1 > 0) else None
                if terminal:
                    rec.setdefault("terminal", []).append(name)
            panel.append(rec)
    print(f"[panel] 관측 {len(panel):,} 종목-월 · 기간 {ends[0]} ~ {ends[-1]}")

    # 🚨 §5-5 이행 — 월 고정효과. 같은 달 횡단면 평균을 빼 시기 효과를 제거한다.
    #   129개월을 확보한 이유가 이것이다(텐배거 문서의 창별 24배 변동 통제).
    for name in HOR:
        by_t: dict[str, list[float]] = {}
        for r in panel:
            if r[name] is not None:
                by_t.setdefault(r["t"], []).append(r[name])
        mu = {k: statistics.mean(v) for k, v in by_t.items() if v}
        for r in panel:
            r[name + "_ex"] = (r[name] - mu[r["t"]]) if (r[name] is not None and r["t"] in mu) else None

    n_term = sum(1 for r in panel if r.get("terminal"))
    n_nopct = sum(r.get("n_nopct") or 0 for r in panel)
    print(f"[panel] 🚨 종말값 적용(상폐·거래정지) {n_term:,} 관측 · pct 결측 live {n_nopct:,}")

    res = {"_meta": {
        "prereg": "docs/PREREG_DILUTION_INSIDER_CROSS_2026_08_21.md (개정 4차)",
        "definition": "시점 T 유효 오버행 = cvrqpd_bgd<=T<=cvrqpd_edd 인 CB/BW 의 총수대비% 합",
        "caveat": "🚨 잔량이 아니라 잔량의 상한 — 전환 실행분 미반영",
        "detect_floor_d": 0.37,
        "brain_input": False,
        "publish": False,
        "n_obs": len(panel), "n_ticker": len(px),
        "inst_used": tot_inst - drop, "inst_dropped": drop,
        "n_terminal_obs": n_term,
        "month_fixed_effect": "각 지평의 *_ex = 같은 달 횡단면 평균 차감(§5-5)",
        "terminal_rule": "지평 내 시계열 종료 시 마지막 거래가 사용. 일괄 -100% 아님(합병·자진상폐 프리미엄 때문). 정리매매가도 0 이 아니라 실손실 과소평가",
    }, "H1": {}, "H3": {}, "H4": {}}

    for name in list(HOR) + [n + "_ex" for n in HOR]:
        obs = [r for r in panel if r.get(name) is not None]
        hi = [r[name] for r in obs if r["ov"] > 0]
        lo = [r[name] for r in obs if r["ov"] == 0]
        d = cohen_d(hi, lo)
        res["H1"][name] = {
            "n_overhang": len(hi), "n_none": len(lo),
            "mean_overhang": round(statistics.mean(hi), 5) if hi else None,
            "mean_none": round(statistics.mean(lo), 5) if lo else None,
            "cohen_d": round(d, 4) if d is not None else None,
            "detectable": (abs(d) >= 0.37) if d is not None else None,
        }
        pos = sorted((r["ov"], r[name]) for r in obs if r["ov"] > 0)
        if len(pos) >= 25:
            q = len(pos) // 5
            res["H3"][name] = [
                {"quintile": i + 1,
                 "ov_med": round(statistics.median([x[0] for x in pos[i*q:(i+1)*q]]), 3),
                 "ret_mean": round(statistics.mean([x[1] for x in pos[i*q:(i+1)*q]]), 5),
                 "n": len(pos[i*q:(i+1)*q])}
                for i in range(5)]
        f_hi = [r[name] for r in obs if r["freq1y"] >= 2]
        f_lo = [r[name] for r in obs if r["freq1y"] == 0]
        d4 = cohen_d(f_hi, f_lo)
        res["H4"][name] = {"n_freq2plus": len(f_hi), "n_freq0": len(f_lo),
                           "cohen_d": round(d4, 4) if d4 is not None else None,
                           "detectable": (abs(d4) >= 0.37) if d4 is not None else None}

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"[panel] 기록 → {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
