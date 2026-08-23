# -*- coding: utf-8 -*-
"""생존편향 진단 — 상폐 종목이 소멸 몇 달 전에 패널에서 빠지는가.

🚨 이 스크립트가 만들어진 이유: 2026-08-23 OOS 개봉 직후 나는 "밸류 패널이 월말 생존
종목만 담아 소멸 직전 구간이 이미 빠져 있다" 고 **검증 없이 단정**해 산출물·커밋·
kickoff 4곳에 내보냈다. 재보니 존재율 100% 로 반증됐다. 추측을 측정으로 대체한 기록.
"""
import json, collections

def d2i(v): return int(str(v)[:8].replace("-", ""))

def run(panel="data/metadata/kr_valuation_panel.jsonl",
        delist="data/kr_delisting.json", k=6):
    by_m = collections.defaultdict(set)
    for l in open(panel, encoding="utf-8"):
        if l.strip():
            r = json.loads(l); by_m[d2i(r["d"])].add(r["t"])
    months = sorted(by_m)
    dl = json.load(open(delist, encoding="utf-8"))
    asof = str(dl["as_of"])
    gone = {t: str(v) for t, v in dl["last_seen"].items() if str(v) != asof}
    dens = [0] * k; base = 0; never = 0
    for t, last in gone.items():
        prior = [m for m in months if m <= d2i(last)]
        if len(prior) < k: continue
        win = prior[-k:]
        if not any(t in by_m[m] for m in win): never += 1; continue
        base += 1
        for j, m in enumerate(win):
            if t in by_m[m]: dens[j] += 1
    return {"delisted_total": len(gone), "evaluated": base, "never_in_panel": never,
            "presence_by_month_before_delist": [round(x / base, 4) for x in dens] if base else [],
            "verdict": ("직전 구간 이탈 없음 — 생존편향 노출은 소멸 직전 1개월뿐"
                        if base and dens[-1] == base else "이탈 있음 — 편향 재평가 필요")}

if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=1))
