# -*- coding: utf-8 -*-
"""Frozen OOS 개봉 — PREREG_FACTOR_OOS_2026_08_23. 설계 동결 후 실행."""
import json, glob, math, collections, sys
from statistics import mean, stdev

VAL="data/metadata/kr_valuation_panel.jsonl"; FUND="data/metadata/kr_fundamental_panel.jsonl"
OOS_LO, OOS_HI = 20240801, 20260731
MIN_N_T=100; FUND_LAG=45; HAIRCUT=0.70; CA_SCREEN=0.25
PRIMARY=["bp","roa","cfoa"]; UNDERPOWERED=["ep","dy","asset_turnover"]

def d2i(v): return int(str(v)[:8].replace("-",""))
def days(a,b):
    import datetime as dt
    f=lambda x: dt.date(int(str(x)[:4]),int(str(x)[4:6]),int(str(x)[6:8]))
    return (f(a)-f(b)).days

# ── 밸류 패널: 월말 횡단면 ──
by_m=collections.defaultdict(dict)
for l in open(VAL,encoding="utf-8"):
    if not l.strip(): continue
    r=json.loads(l); d=d2i(r["d"])
    by_m[d][r["t"]]=r
months=sorted(by_m)
oos=[m for m in months if OOS_LO<=m<=OOS_HI]

# ── 펀더 패널: PIT (quarter_end+45일 <= 월말) 최신 분기 ──
fund=collections.defaultdict(list)
for l in open(FUND,encoding="utf-8"):
    if not l.strip(): continue
    r=json.loads(l)
    qe=r["quarter_end"]
    if qe[5:] not in ("03-31","06-30","09-30","12-31"): continue
    fund[r["ticker"]].append((d2i(qe.replace("-","")), r))
for t in fund: fund[t].sort()
def pit(t,m):
    best=None
    for qi,r in fund.get(t,[]):
        if days(m,qi)>=FUND_LAG: best=r
        else: break
    return best

# ── 상폐 ──
dl=json.load(open("data/kr_delisting.json",encoding="utf-8"))
asof=str(dl["as_of"]); gone={t:str(v) for t,v in dl["last_seen"].items() if str(v)!=asof}
dpx={}
for f in sorted(glob.glob("data/kr_chart_delisted/chunk_*.json")):
    dpx.update(json.load(open(f,encoding="utf-8")).get("stocks",{}))
def last_close(t):
    s=dpx.get(t)
    if not s: return None
    for bar in reversed(s.get("c",[])):
        if bar and len(bar)>4 and bar[4]: return float(bar[4])
    return None

def fval(t,m,f):
    v=by_m[m].get(t)
    if f=="bp":  return (1.0/v["pbr"]) if v and v.get("pbr") else None
    if f=="ep":  return (1.0/v["per"]) if v and v.get("per") else None
    if f=="dy":  return v.get("div_yield") if v else None
    p=pit(t,m)
    if not p: return None
    if f=="roa": return p.get("roa_ttm")
    if f=="cfoa":
        o,a=p.get("operating_cashflow_ttm"),p.get("assets")
        return (o/a) if (o is not None and a) else None
    if f=="asset_turnover": return p.get("asset_turnover")
    return None

def spearman(xs,ys):
    def rank(v):
        idx=sorted(range(len(v)),key=lambda i:v[i]); r=[0.0]*len(v); i=0
        while i<len(idx):
            j=i
            while j+1<len(idx) and v[idx[j+1]]==v[idx[i]]: j+=1
            avg=(i+j)/2.0+1
            for k in range(i,j+1): r[idx[k]]=avg
            i=j+1
        return r
    rx,ry=rank(xs),rank(ys); n=len(xs)
    mx,my=mean(rx),mean(ry)
    num=sum((a-mx)*(b-my) for a,b in zip(rx,ry))
    den=math.sqrt(sum((a-mx)**2 for a in rx)*sum((b-my)**2 for b in ry))
    return num/den if den else None

def run(include_delisted):
    out={}
    for f in PRIMARY+UNDERPOWERED:
        ics=[]; nexc=0; nca=0
        for i,m in enumerate(oos[:-1]):
            nm=oos[i+1]
            xs,ys=[],[]
            for t,r in by_m[m].items():
                x=fval(t,m,f); c0=r.get("close")
                if x is None or not c0: continue
                nx=by_m[nm].get(t)
                if nx and nx.get("close"):
                    # 🚨 v1.1 기업행동 스크린 — 패널 close 는 무수정 종가다.
                    #    |Δln close − Δln mktcap| > 0.25 면 주당 수익률 신뢰 불가 → 제외.
                    #    시총 결측도 검증 불가라 제외(보수). factor.py:296-304 와 동일.
                    k0,k1=r.get("mktcap"),nx.get("mktcap")
                    if k0 and k1 and k0>0 and k1>0:
                        if abs(math.log(nx["close"]/c0)-math.log(k1/k0))>CA_SCREEN:
                            nca+=1; continue
                    else:
                        nca+=1; continue
                    ret=nx["close"]/c0-1.0
                elif include_delisted and t in gone and d2i(gone[t])<=nm:
                    lc=last_close(t)
                    if lc is None: nexc+=1; continue
                    ret=lc*HAIRCUT/c0-1.0
                else:
                    nexc+=1; continue
                xs.append(x); ys.append(ret)
            if len(xs)<MIN_N_T: continue
            ic=spearman(xs,ys)
            if ic is not None: ics.append(ic)
        if len(ics)<3: out[f]={"n":len(ics)}; continue
        mu=mean(ics); sd=stdev(ics); t=mu/(sd/math.sqrt(len(ics)))
        out[f]={"ic_mean":round(mu,4),"t":round(t,2),"n_months":len(ics),"dropped_obs":nexc,"excluded_ca":nca}
    return out

print(f"OOS 월 {len(oos)}개  {oos[0]} ~ {oos[-1]}")
res={"excl":run(False),"incl":run(True)}
IS={"bp":0.0861,"roa":0.0593,"cfoa":0.0439,"ep":0.0528,"dy":0.0617,"asset_turnover":0.0299}
FLOOR={"bp":0.0687,"roa":0.0405,"cfoa":0.0282,"ep":0.0540,"dy":0.0819,"asset_turnover":0.0357}
print(f"\n{'팩터':<16}{'IS IC':>8}{'excl IC':>9}{'excl t':>8}{'incl IC':>9}{'incl t':>8}{'하한':>8}  판정")
for f in PRIMARY+UNDERPOWERED:
    a,b=res["excl"].get(f,{}),res["incl"].get(f,{})
    if "ic_mean" not in b: print(f"  {f:<14} 산출 불가 (n={b.get('n')})"); continue
    prim = f in PRIMARY
    t=b["t"]; ic=b["ic_mean"]
    if not prim: v="판정 불가(검정력 부족)"
    elif abs(t)>=3 and ic*IS[f]>0: v="✅ 통과"
    elif abs(t)>=2: v="부분 — 연결 보류"
    else: v="❌ 탈락"
    print(f"  {f:<14}{IS[f]:>+8.4f}{a.get('ic_mean',float('nan')):>9.4f}{a.get('t',0):>8.2f}"
          f"{ic:>+9.4f}{t:>8.2f}{FLOOR[f]:>8.4f}  {v}")
json.dump({"oos_months":len(oos),"range":[oos[0],oos[-1]],"results":res},
          open("/tmp/oos_result.json","w"),ensure_ascii=False,indent=1)
