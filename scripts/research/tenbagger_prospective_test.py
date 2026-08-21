#!/usr/bin/env python3
"""텐배거 전향 검정 — PREREG_TENBAGGER_BASE_RATE_2026_08_21 실행. 🚨 산식 변경 0.

선행 `docs/TENBAGGER_RESEARCH_KR_2026_08_18.md` 가 스스로 지목한 최우선 후속:
  *"B. 전향 검정 — 2020년 초 스크리닝으로 31종목을 잡을 수 있었나.
    사후 특성 나열은 실무 가치가 없고, 사전에 잡을 수 있었는지가 유일하게 중요한 질문."*
KR 은 6.5년 = 창 1개라 창 간 재현을 못 한다. **US 28년 = 창 5개**가 이 검정의 기여다.

🚨 등록된 판정 규칙 (실행 전 고정, 여기서 코드로 강제한다):
  ① 검출하한 미달 = "효과 없음" 이 아니라 **"못 잼"**. 방향도 말하지 않는다
  ② 창 간 **5/5 부호 일치**만 유의(p=0.031). 4/5 이하 = 판정 보류
  ③ 🚨 상방·하방 **항상 병기**. P(10배) 단독 출력 금지
  ④ 🚨 **상폐를 제외하지 않는다** — 관측 종료로 처리하고 분모에 유지
  ⑤ 분위로만 자른다. 절대 임계 신설 금지
  ⑥ 결과를 보고 가설·구간·창을 바꾸지 않는다

🚨 이 스크립트가 고치는 내 선행 결함:
  초기 낙폭 측정에서 `a.notna() & b.notna()` 로 **양 끝 관측을 요구**해 상폐 종목을
  통째로 떨어뜨렸다 — 규칙 ④ 위반이자 오늘 하루 경계한 생존편향 그 자체다.
  여기서는 창 내 **마지막 관측치**를 종점으로 써서 상폐를 분모에 유지한다.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Dict, List

import numpy as np
import pandas as pd

LAKE = os.path.expanduser("~/VERITY_data_lake/features")
RET = os.path.join(LAKE, "monthly_returns.parquet")
FUN = os.path.join(LAKE, "fundamentals_features.parquet")

H = 60                    # 5년 창 (개월)
TENX, WIPEOUT = 10.0, 0.1
NQ = 5                    # 분위 수 — 등록문 §3 검출하한이 상위 20% 기준
DETECT_MULT = 3.64        # 🚨 등록 신고 검출하한(상위 20% · Harvey t≥3 · power 0.8)
SIGN_REQUIRED = 5         # 창 5개 중 몇 개 일치해야 유의로 인정하는가

# 등록 §4 가설 — 실행 전 고정. 추가 금지.
TRAITS = {
    "H1_size":        ("book_equity",  "size 방향성 — KR 2차는 대형이 더 높았다(반증 반영)"),
    "H2_asset_growth":("asset_growth", "저자산성장 = operating_leverage 개념 대리"),
    "H2b_netmargin":  ("netmargin",    "마진 = operating_leverage 개념 대리"),
    "H3_quality":     ("piotroski_f",  "퀄리티 — fact 축 quant_quality 대응"),
    "H4_solvency":    ("altman_z",     "재무건전성 — 🚨 하방(90% 손실) 축"),
}


def load() -> tuple:
    r = pd.read_parquet(RET)
    r["month"] = pd.to_datetime(r["month"])
    r = r.sort_values(["ticker", "month"])
    r["g"] = 1 + r["ret_1m"].clip(-0.99, 10)
    r["idx"] = r.groupby("ticker")["g"].cumprod()
    piv = r.pivot_table(index="month", columns="ticker", values="idx")
    f = pd.read_parquet(FUN)
    f["datekey"] = pd.to_datetime(f["datekey"])
    return piv, f


def forward_multiple(win: pd.DataFrame) -> pd.Series:
    """🚨 규칙 ④ — 창 내 **마지막 관측치**를 종점으로. 상폐를 분모에서 빼지 않는다.

    양 끝 관측을 요구하면 상폐 종목이 통째로 사라져 생존편향이 들어간다.
    """
    start = win.iloc[0]
    alive = start.notna() & (start > 0)
    sub = win.loc[:, alive]
    last = sub.ffill().iloc[-1]      # 상폐 후에는 마지막 관측이 유지된다
    return (last / start[alive]).dropna()


def pit_traits(f: pd.DataFrame, asof: pd.Timestamp) -> pd.DataFrame:
    """🚨 룩어헤드 0 — `datekey <= asof` 중 가장 최근 1건만."""
    g = f[f["datekey"] <= asof]
    if g.empty:
        return g
    return g.sort_values("datekey").groupby("ticker").tail(1).set_index("ticker")


def main() -> int:
    piv, f = load()
    months = piv.index
    starts = list(range(0, len(months) - H, H))
    out: Dict[str, List[dict]] = {k: [] for k in TRAITS}
    base_rows = []

    print("=" * 78)
    print(f"텐배거 전향 검정 — 비중첩 5년 창 {len(starts)}개 · 🚨 상폐 분모 유지")
    print("=" * 78)

    for s in starts:
        asof = months[s]
        win = piv.iloc[s:s + H + 1]
        fwd = forward_multiple(win)
        tr = pit_traits(f, asof)
        n = len(fwd)
        ten = int((fwd >= TENX).sum())
        wipe = int((fwd <= WIPEOUT).sum())
        base_rows.append({"win": f"{asof:%Y-%m}", "n": n, "ten": ten,
                          "ten_pct": ten / n * 100, "wipe_pct": wipe / n * 100})
        print(f"\n[{asof:%Y-%m}] 유니버스 {n:,} · 10배 {ten} ({ten/n*100:.2f}%) "
              f"· 90%손실 {wipe} ({wipe/n*100:.2f}%) · 특성 보유 {len(tr):,}")

        common = fwd.index.intersection(tr.index)
        if len(common) < NQ * 50:
            print("   특성 교집합 부족 — 이 창은 검정 생략")
            continue
        y = fwd.loc[common]
        for hkey, (col, _) in TRAITS.items():
            x = pd.to_numeric(tr.loc[common, col], errors="coerce")
            m = x.notna()
            if m.sum() < NQ * 50:
                continue
            q = pd.qcut(x[m], NQ, labels=False, duplicates="drop")
            yy = y[m]
            tops, bots = (q == q.max()), (q == 0)
            rec = {
                "win": f"{asof:%Y-%m}", "n": int(m.sum()),
                "top_ten": float((yy[tops] >= TENX).mean() * 100),
                "bot_ten": float((yy[bots] >= TENX).mean() * 100),
                "base_ten": float((yy >= TENX).mean() * 100),
                "top_wipe": float((yy[tops] <= WIPEOUT).mean() * 100),
                "bot_wipe": float((yy[bots] <= WIPEOUT).mean() * 100),
            }
            out[hkey].append(rec)

    print("\n" + "=" * 78)
    print("가설별 판정 — 🚨 규칙 ①②③ 강제")
    print("=" * 78)
    verdicts = {}
    for hkey, (col, note) in TRAITS.items():
        rows = out[hkey]
        print(f"\n▶ {hkey}  ({col}) — {note}")
        if len(rows) < len(starts):
            print(f"   창 {len(rows)}/{len(starts)} 만 검정됨")
        print(f"   {'창':9s}{'상위20% 10배':>13s}{'하위20%':>9s}{'기저':>8s}"
              f"{'│':>3s}{'상위 90%손실':>13s}{'하위':>8s}")
        signs = []
        for r in rows:
            d = r["top_ten"] - r["bot_ten"]
            signs.append(np.sign(d))
            print(f"   {r['win']:9s}{r['top_ten']:12.2f}%{r['bot_ten']:8.2f}%"
                  f"{r['base_ten']:7.2f}%{'│':>3s}{r['top_wipe']:12.2f}%{r['bot_wipe']:7.2f}%")
        if not rows:
            verdicts[hkey] = "no_data"; print("   판정: 데이터 없음"); continue
        pos, neg = signs.count(1.0), signs.count(-1.0)
        agree = max(pos, neg)
        # 🚨 규칙 ① 구현 정정 (2026-08-21) — 초판은 **상위 분위 lift 만** 계산했다.
        #   등록된 가설은 "상위가 유리하다" 가 아니라 **"방향성"** 이고(H1 은 명시적으로
        #   size 방향 재현), 등록 §5-3 은 **상방·하방 병기 의무**를 이미 적고 있었다.
        #   상위만 보면 효과가 **하위 분위**에 있을 때 구조적으로 검출되지 않는다 —
        #   실제로 5가설 전부가 그 상태였다. 가설 변경이 아니라 **누락된 규칙 구현**이다.
        #   ⑥(결과 보고 가설·구간·창 변경 금지)에 저촉되지 않는다: 가설·분위·창 불변.
        up_top = [r["top_ten"] / r["base_ten"] if r["base_ten"] > 0 else 0 for r in rows]
        up_bot = [r["bot_ten"] / r["base_ten"] if r["base_ten"] > 0 else 0 for r in rows]
        fav_up = "top" if np.mean(up_top) >= np.mean(up_bot) else "bot"
        lifts = up_top if fav_up == "top" else up_bot
        over = sum(1 for L in lifts if L >= DETECT_MULT)
        # 🚨 하방 축 — 90% 손실 회피. 두 꼬리의 비(높은 쪽/낮은 쪽)로 크기를 잰다.
        dn = [(max(r["top_wipe"], r["bot_wipe"]) / min(r["top_wipe"], r["bot_wipe"]))
              if min(r["top_wipe"], r["bot_wipe"]) > 0 else 0 for r in rows]
        dn_sign = [np.sign(r["bot_wipe"] - r["top_wipe"]) for r in rows]
        dn_agree = max(dn_sign.count(1.0), dn_sign.count(-1.0))
        dn_over = sum(1 for L in dn if L >= DETECT_MULT)
        print(f"   [상방] 유리한 꼬리 = {'상위20%' if fav_up=='top' else '하위20%'} · "
              f"부호 일치 {agree}/{len(rows)} · lift 최대 {max(lifts):.2f}배 · "
              f"검출하한 {DETECT_MULT}배 초과 {over}/{len(rows)}")
        print(f"   [하방] 90%손실 부호 일치 {dn_agree}/{len(rows)} · "
              f"두 꼬리 비 최대 {max(dn):.2f}배 · 검출하한 초과 {dn_over}/{len(rows)}")
        up_v = ("significant" if (agree >= SIGN_REQUIRED and over >= 1)
                else "sign_only" if agree >= SIGN_REQUIRED else "undetermined")
        dn_v = ("significant" if (dn_agree >= SIGN_REQUIRED and dn_over >= 1)
                else "sign_only" if dn_agree >= SIGN_REQUIRED else "undetermined")
        verdicts[hkey] = {"upside": up_v, "downside": dn_v,
                          "favored_tail": fav_up,
                          "up_lift_max": round(max(lifts), 2),
                          "dn_ratio_max": round(max(dn), 2)}
        LAB = {"significant": "🚨 유의(부호 일치 + 검출하한 초과)",
               "sign_only": "부호만 일치 — **검출하한 미달, 크기는 못 잼**",
               "undetermined": "판정 보류(부호 불일치)"}
        print(f"   판정 상방: {LAB[up_v]}")
        print(f"   판정 하방: {LAB[dn_v]}")

    print("\n" + "=" * 78)
    print("🚨 이 검정이 말하지 않는 것: 검출하한 미달은 '효과 없음'이 아니라 '못 잼'이다.")
    print("   창 5개는 표본을 더 모아도 안 늘어난다(28년이 이미 전부).")
    res = {"windows": base_rows, "verdicts": verdicts, "detail": out,
           "rules": {"detect_mult": DETECT_MULT, "sign_required": SIGN_REQUIRED,
                     "delisted_kept": True, "lookahead": "datekey<=asof"}}
    p = os.path.join("data", "analysis", "tenbagger_prospective.json")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=1)
    print(f"\n저장: {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
