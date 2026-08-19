#!/usr/bin/env python3
"""\"확실하면 비중을 높인다\" 에 근거가 있나 — 확신도의 수익 예측력 측정.

## 질문

PM 지시(2026-08-19) 후반부: *"확실하면 비중을 높이도록."*
현행 사이징 승수 3종(Kelly · ATR · macro)은 **전부 상한 1.0** 이라 축소만 한다.
상한을 1.0 위로 푸는 변경은 산식 변경(RULE 7, 1회 권한)이므로 근거가 먼저다.

**근거 조건은 하나다 — 확신도가 높을수록 실제 수익이 높아야 한다.**
그게 아니면 비중 확대는 수익이 아니라 분산만 키운다.

## 데이터 (RULE 13 — 열거 먼저)

`data/metadata/prediction_trail.jsonl` = **실제 운영 예측의 사후 채점 원장**.
백테스트가 아니라 그날 실제로 낸 예측이 만기 도달 후 채점된 것 = 진짜 out-of-sample.
전체/채점완료/타입별 분모를 출력한다.

## 측정 설계

- `pred_score`(= brain_score) 와 `confidence` 를 **각각** 축으로 삼는다. 둘은 다른 값이다.
- 종목·섹터를 **분리**한다(섞으면 분모가 다른 두 모집단이 합쳐진다).
- 🚨 **같은 날 예측은 서로 독립이 아니다**(시장 공통요인). 단순 SE 는 과소추정된다.
  → 날짜 클러스터 SE 를 함께 낸다. 판정은 **클러스터 SE 기준**으로만 한다.
- 판정 기준: 최상위 구간이 중간 구간을 **클러스터 SE 2배 이상** 앞서야 "확대 근거 있음".

🚨 **단위·오염 가드** — `realized_return` 은 **퍼센트 단위**다(P50 0.0 · P75 +3.27).
분수로 읽으면 전부 100배 틀린다. 그리고 |rr|>300% 행은 **가격맵 통화오염**이다
(2026-07-20 감사에서 특정: EQT 20건·EXE 15건 = 35건, 배수 1,456~1,589x).
생산 집계기 `prediction_scoring.py:362` 가 이미 같은 임계로 거른다 —
**여기서도 같은 상수를 쓴다.** 검정마다 다른 임계를 쓰면 발행 IC 와 대조가 안 된다.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict

import numpy as np

TRAIL = "data/metadata/prediction_trail.jsonl"
CONTAM_ABS_PCT = 300.0   # prediction_scoring.py:362 와 동일 상수 (통화오염 컷)


def load():
    rows = []
    for line in open(TRAIL, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows


def cluster_se(vals, keys):
    """날짜 클러스터 SE — 같은 날 예측의 상관을 무시하지 않는다."""
    g = defaultdict(list)
    for v, k in zip(vals, keys):
        g[k].append(v)
    means = np.array([np.mean(v) for v in g.values()])
    n = np.array([len(v) for v in g.values()], dtype=float)
    if len(means) < 2:
        return float("nan"), len(means)
    w = n / n.sum()
    # 클러스터 평균의 가중분산 → 전체 평균의 SE
    mu = (w * means).sum()
    var = (w ** 2 * ((means - mu) ** 2)).sum() * len(means) / max(len(means) - 1, 1)
    return float(np.sqrt(var)), len(means)


def spearman(a, b):
    ra = np.argsort(np.argsort(a)).astype(float)
    rb = np.argsort(np.argsort(b)).astype(float)
    ra -= ra.mean(); rb -= rb.mean()
    d = np.sqrt((ra ** 2).sum() * (rb ** 2).sum())
    return float((ra * rb).sum() / d) if d else float("nan")


def report(name, score, ret, dates, nbin=5):
    print(f"\n### {name} — N={len(score):,} · 날짜 {len(set(dates))}개")
    if len(score) < 50:
        print("  n<50 — 측정 보류")
        return
    ic = spearman(score, ret)
    # 날짜별 IC 의 평균과 SE (IC 자체도 날짜 클러스터로 본다)
    per = []
    g = defaultdict(list)
    for s, r, d in zip(score, ret, dates):
        g[d].append((s, r))
    for d, v in g.items():
        if len(v) >= 10:
            a = np.array(v)
            per.append(spearman(a[:, 0], a[:, 1]))
    per = np.array([p for p in per if np.isfinite(p)])
    if len(per) >= 2:
        icse = per.std(ddof=1) / np.sqrt(len(per))
        print(f"  풀드 IC {ic:+.4f} · 날짜별 IC 평균 {per.mean():+.4f} ± {icse:.4f}"
              f" (날짜 {len(per)}개, |t|={abs(per.mean()/icse):.2f})")
    else:
        print(f"  풀드 IC {ic:+.4f} · 날짜별 IC 산출 불가(날짜 표본 부족)")

    edges = np.percentile(score, np.linspace(0, 100, nbin + 1))
    edges[-1] += 1e-9
    print(f"  {'구간':>6}{'표본':>8}{'점수범위':>16}{'평균수익':>11}{'단순SE':>9}{'클러스터SE':>12}")
    stats = []
    for k in range(nbin):
        m = (score >= edges[k]) & (score < edges[k + 1])
        if m.sum() < 20:
            continue
        r = ret[m]
        se = r.std(ddof=1) / np.sqrt(len(r))
        cse, nc = cluster_se(r.tolist(), [d for d, keep in zip(dates, m) if keep])
        stats.append((k, r.mean(), cse, len(r)))
        print(f"  Q{k+1:<5}{m.sum():>8,}{edges[k]:>7.1f}~{edges[k+1]:>6.1f}"
              f"{r.mean():>10.3f}%{se:>8.3f}%{cse:>11.3f}%")
    if len(stats) >= 3:
        top, mid = stats[-1], stats[len(stats) // 2]
        d = top[1] - mid[1]
        pooled = np.sqrt(top[2] ** 2 + mid[2] ** 2)
        verdict = ("✅ 확대 근거 있음" if np.isfinite(pooled) and d > 2 * pooled
                   else "❌ 근거 없음 (최상위가 중간을 유의하게 못 이김)")
        print(f"  최상위−중간 = {d:+.3f}%p · 결합 클러스터SE {pooled:.3f}%p"
              f" → {verdict}")


def main() -> None:
    rows = load()
    raw = [r for r in rows
           if r.get("scored") and isinstance(r.get("realized_return"), (int, float))]
    scored = [r for r in raw if abs(float(r["realized_return"])) <= CONTAM_ABS_PCT]
    dropped = [r for r in raw if r not in scored]
    print("확신도의 수익 예측력 — \"확실하면 비중 확대\" 근거 검정")
    print(f"  원장 전체 {len(rows):,} · 채점완료 {len(raw):,}"
          f" ({len(raw)/len(rows)*100:.1f}%) · 미채점 {len(rows)-len(raw):,}")
    import collections as _c
    print(f"  🚨 통화오염 제외 {len(dropped)} 건 (|rr|>{CONTAM_ABS_PCT:.0f}%) — "
          f"{dict(_c.Counter(r['target'] for r in dropped))} · 유효 {len(scored):,}")
    print("  단위 = 퍼센트 (분수 아님). 아래 표의 평균수익은 원값 그대로 %.")
    by_t = defaultdict(list)
    for r in scored:
        by_t[r.get("target_type")].append(r)
    print("  타입별: " + " · ".join(f"{k} {len(v):,}" for k, v in sorted(by_t.items())))
    hz = defaultdict(int)
    for r in scored:
        hz[r.get("horizon")] += 1
    print("  지평별: " + " · ".join(f"{k} {v:,}" for k, v in sorted(hz.items())))
    ds = sorted({r.get("created_at", "")[:10] for r in scored if r.get("created_at")})
    print(f"  생성일 {ds[0]} ~ {ds[-1]} ({len(ds)}일)")

    for ttype in sorted(by_t):
        sub = by_t[ttype]
        for field, label in (("pred_score", "brain_score"), ("confidence", "confidence")):
            v = [(r[field], r["realized_return"], r.get("created_at", "")[:10])
                 for r in sub if isinstance(r.get(field), (int, float))]
            if not v:
                continue
            a = np.array([[x[0], x[1]] for x in v], dtype=float)
            uniq = len(set(a[:, 0].tolist()))
            if uniq < 5:
                print(f"\n### {ttype} × {label} — 🚨 고유값 {uniq}개뿐, 분위 불가")
                for u in sorted(set(a[:, 0].tolist())):
                    m = a[:, 0] == u
                    print(f"     값 {u:>6.2f}  N={int(m.sum()):>5,}  평균수익 {a[m,1].mean():+.3f}%")
                continue
            report(f"{ttype} × {label}", a[:, 0], a[:, 1], [x[2] for x in v])


if __name__ == "__main__":
    main()
