"""미장(US) ETF 빌더 — 주요 US 상장 ETF(VOO/SPY/QQQ 등) 사실(카테고리·AUM·운용사·보유종목·보수).

배경(2026-07-11): KR ETF(ACE 미국S&P500 등 KRX 상장)는 검색되나 US 상장 ETF(VOO)는 유니버스 부재
→ 검색·리포트 0. KR ETF flow(설정/환매)의 US 대응 = US ETF는 KRX 미상장이라 yfinance 소스.

🚨 RULE 7 — 사실만: 카테고리·순자산(AUM)·운용사·보수율·보유종목 top(비중). 자체 점수·판단 0.
🚨 가격/NAV 재배포 회피 = 실시간 시세 미노출(증권사 link-out). 여긴 구성·비용 사실 렌즈.

소스 = yfinance (Ticker.info + funds_data.top_holdings). 큐레이션 ~70종(AUM 상위 광범/섹터/해외/채권/원자재).
출력 = data/us_etf.json {_meta, etfs:[{ticker, name, category, aum_usd, family, expense, top_holdings}]}.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CACHE_PATH = os.path.join(_ROOT, "data", "us_etf_cache.json")
OUTPUT_PATH = os.path.join(_ROOT, "data", "us_etf.json")
KST = timezone(timedelta(hours=9))
FRESH_DAYS = 5          # ETF 구성/AUM 저빈도 변동 → 5일 재수집
# 스키마를 넓힌 날은 캐시가 신선해도 옛 필드만 들고 있다 → 전량 재수집이 필요.
# US_ETF_FORCE=1 (신선도 무시) · US_ETF_MAX_PER_RUN=N (1회 상한) 로 일회성 전량 갱신.
MAX_PER_RUN = int(os.environ.get("US_ETF_MAX_PER_RUN") or 40)  # yfinance 레이트리밋 안전
FORCE_REFETCH = os.environ.get("US_ETF_FORCE") == "1"
THROTTLE_SEC = 0.3
STALE_EMIT_DAYS = 30

# 큐레이션 = AUM/인지도 상위 US 상장 ETF (광범·섹터·해외·채권·원자재·테마)
CURATED: List[str] = [
    # 광범 시장
    "VOO", "SPY", "IVV", "VTI", "QQQ", "QQQM", "SPLG", "DIA", "IWM", "IJH", "IJR", "RSP", "MDY", "VO", "VB",
    # 스타일
    "VUG", "VTV", "IWF", "IWD", "SCHG", "SCHD", "VIG", "VYM", "DVY", "HDV", "QUAL", "MTUM", "USMV",
    # 섹터 (SPDR Select)
    "XLK", "XLF", "XLE", "XLV", "XLY", "XLP", "XLI", "XLU", "XLB", "XLC", "XLRE",
    "SMH", "SOXX", "IBB", "XBI", "KRE", "ITB", "JETS",
    # 해외
    "VEA", "VWO", "IEFA", "IEMG", "EFA", "EEM", "VXUS", "SCHF", "INDA", "MCHI", "FXI", "EWJ", "EWZ", "EWY",
    # 채권
    "BND", "AGG", "TLT", "IEF", "SHY", "LQD", "HYG", "TIP", "VCIT", "MUB", "BIL", "SGOV",
    # 원자재·기타
    "GLD", "IAU", "SLV", "USO", "DBC", "URA",
    # 테마·인컴·레버리지
    "ARKK", "JEPI", "JEPQ", "SCHY", "TQQQ", "SQQQ",
]


def _now_kst() -> datetime:
    return datetime.now(KST)


def _age_days(as_of: str, now: datetime) -> float:
    try:
        return (now - datetime.fromisoformat(as_of)).days
    except (ValueError, TypeError):
        return 1e9


def _expense(info: Dict[str, Any]) -> Optional[float]:
    # yfinance annualReportExpenseRatio = 이미 % 표기 값(VOO=0.03 → 0.03%). ×100 금지.
    for k in ("annualReportExpenseRatio", "netExpenseRatio", "expenseRatio"):
        v = info.get(k)
        if isinstance(v, (int, float)) and v > 0:
            return round(v, 3)
    return None


def _num(v: Any) -> Optional[float]:
    """NaN/None/pandas NA 를 걸러 float 로. json.dump 의 NaN 리터럴 = JS JSON.parse 파손."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None  # NaN != NaN


def _pct(v: Any, digits: int = 2) -> Optional[float]:
    """분수(0.3861) → 퍼센트(38.61)."""
    f = _num(v)
    return round(f * 100, digits) if f is not None else None


def _fund_ops(fd: Any, tk: str) -> Dict[str, Any]:
    """운용 지표 — 보수·회전율을 카테고리 평균과 나란히.

    🚨 스케일 함정: fund_operations 의 보수는 **분수**(VOO 0.0003 = 0.03%) 인데
    info["annualReportExpenseRatio"] 는 **이미 %**(0.03). 둘을 같은 자로 재면 100배 어긋난다.
    여기(카테고리 평균)만 ×100 하고, 펀드 자신의 보수는 기존 _expense(info) 를 그대로 쓴다.
    Total Net Assets 는 VOO=486,952(단위 불명, info.totalAssets=$1.67T 와 불일치) → 미채택.
    """
    out: Dict[str, Any] = {}
    try:
        df = fd.fund_operations
        col = df.columns[0] if len(df.columns) else None
        cat = "Category Average" if "Category Average" in df.columns else None
        rows = {
            "expense_cat_pct": "Annual Report Expense Ratio",
            "turnover_pct": "Annual Holdings Turnover",
        }
        if cat is not None:
            out["expense_cat_pct"] = _pct(df.loc[rows["expense_cat_pct"], cat], 3)
            out["turnover_cat_pct"] = _pct(df.loc[rows["turnover_pct"], cat], 1)
        if col is not None:
            out["turnover_pct"] = _pct(df.loc[rows["turnover_pct"], col], 1)
    except Exception:  # noqa: BLE001 — 지표 없는 ETF graceful
        pass
    return {k: v for k, v in out.items() if v is not None}


def _equity_stats(fd: Any) -> Dict[str, Any]:
    """구성종목 가중 밸류에이션.

    🚨 yfinance 는 Price/Earnings 를 **역수(이익수익률)** 로 준다 — VOO 0.03716.
    그대로 실으면 "PER 0.04" 라는 거짓이 사이트에 뜬다. 1/x 환산 실측 검증:
    VOO 26.91 / 5.39 / 3.72 / 19.89, SCHD 18.29 / 3.49 (배당 ETF = 저평가 특성 일치),
    TLT 0(=채권) → None. 2026-07-28 확인.
    """
    out: Dict[str, Any] = {}
    keys = {
        "per": "Price/Earnings", "pbr": "Price/Book",
        "psr": "Price/Sales", "pcf": "Price/Cashflow",
    }
    try:
        df = fd.equity_holdings
        col = df.columns[0]
        for k, row in keys.items():
            v = _num(df.loc[row, col])
            if v and v > 0:
                out[k] = round(1.0 / v, 2)
    except Exception:  # noqa: BLE001
        pass
    return out


def _fetch_one(ticker: str) -> Dict[str, Any]:
    """yfinance ETF 사실 (info + top_holdings). 실패 시 {}."""
    import yfinance as yf
    t = yf.Ticker(ticker)
    info = t.info or {}
    if not info or str(info.get("quoteType") or "").upper() not in ("ETF", "MUTUALFUND"):
        return {}
    out: Dict[str, Any] = {
        "name": info.get("shortName") or info.get("longName") or ticker,
        "category": info.get("category"),
        "aum_usd": info.get("totalAssets"),
        "family": info.get("fundFamily"),
        "expense": _expense(info),
        "legal_type": info.get("legalType"),
    }
    inc = _num(info.get("fundInceptionDate"))
    if inc and inc > 0:
        out["inception"] = datetime.fromtimestamp(inc, timezone.utc).strftime("%Y-%m-%d")

    # 수익률 — 🚨 스케일이 필드마다 다르다(실측 2026-07-28):
    #   ytdReturn = 이미 %(VOO 10.19), threeYear/fiveYearAverageReturn = 분수(0.19176 = 연 19.18%).
    #   같은 자로 재면 3Y 가 0.19% 로 찍힌다. 각각 다르게 환산.
    rets: Dict[str, Any] = {}
    ytd = _num(info.get("ytdReturn"))
    if ytd is not None:
        rets["ytd"] = round(ytd, 2)
    for key, src in (("y3", "threeYearAverageReturn"), ("y5", "fiveYearAverageReturn")):
        v = _pct(info.get(src))
        if v is not None:
            rets[key] = v
    if rets:
        out["returns"] = rets
    for key, src, conv in (
        ("yield_pct", "yield", _pct),
        ("beta3y", "beta3Year", _num),
    ):
        v = conv(info.get(src))
        if v is not None:
            out[key] = round(v, 2)

    fd = None
    try:
        fd = t.funds_data
    except Exception:  # noqa: BLE001
        fd = None
    if fd is None:
        return out

    try:
        ov = fd.fund_overview or {}
        if ov.get("categoryName"):
            out["category_name"] = ov.get("categoryName")
    except Exception:  # noqa: BLE001
        pass
    out.update(_fund_ops(fd, ticker))
    eq = _equity_stats(fd)
    if eq:
        out["equity_stats"] = eq
    # 자산군 구성 — 주식/채권/현금/기타 (분수 → %)
    try:
        ac = fd.asset_classes or {}
        assets = {
            k2: _pct(ac.get(k1))
            for k1, k2 in (
                ("stockPosition", "stock"), ("bondPosition", "bond"),
                ("cashPosition", "cash"), ("preferredPosition", "preferred"),
                ("convertiblePosition", "convertible"), ("otherPosition", "other"),
            )
        }
        assets = {k: v for k, v in assets.items() if v}
        if assets:
            out["assets"] = assets
    except Exception:  # noqa: BLE001
        pass
    # 섹터 비중 — 주식형만 채워짐(채권·원자재는 {} → 생략)
    try:
        sw = fd.sector_weightings or {}
        sect = {k: _pct(v) for k, v in sw.items()}
        sect = {k: v for k, v in sect.items() if v}
        if sect:
            out["sectors"] = sect
    except Exception:  # noqa: BLE001
        pass
    # 🚫 bond_holdings(듀레이션/만기) 미채택 — 실측 TLT duration 3.55·maturity 7.98 로 나오는데
    #    iShares 공시 실값은 각각 ~15.6년·~25년. Yahoo 값이 틀렸다. 틀린 사실 게재 금지(RULE 7).
    #    bond_ratings 도 TLT 에서 aa 1.0 + us_government 0.9963 로 합이 199% → 정의 불명, 미채택.
    try:
        th = fd.top_holdings  # DataFrame index=심볼, cols=[Name, Holding Percent]
        holdings = []
        wsum = 0.0
        for sym, row in th.head(10).iterrows():
            fp = _num(row.get("Holding Percent"))
            w = None
            if fp is not None:
                w = round(fp * 100, 2) if fp < 1 else round(fp, 2)  # funds_data=분수(0.075=7.5%)
                wsum += w
            holdings.append({"t": str(sym), "n": str(row.get("Name") or ""), "w": w})
        if holdings:
            out["top_holdings"] = holdings
            # 상위 10 이 전체의 몇 %인지 — Yahoo 는 10종까지만 준다. "나머지" 를 정직하게 표기.
            out["top_w_sum"] = round(wsum, 1)
    except Exception:  # noqa: BLE001 — funds_data 없는 ETF (채권/원자재 등) graceful
        pass
    return out


def main() -> int:
    cache: Dict[str, Any] = {"updated_at": None, "by_ticker": {}}
    if os.path.exists(CACHE_PATH):
        try:
            cache = json.load(open(CACHE_PATH, encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    by_ticker: Dict[str, Any] = cache.get("by_ticker") or {}

    now = _now_kst()
    todo = [
        t for t in CURATED
        if FORCE_REFETCH or _age_days((by_ticker.get(t) or {}).get("as_of", ""), now) >= FRESH_DAYS
    ]
    todo.sort(key=lambda t: (by_ticker.get(t) or {}).get("as_of", ""))
    todo = todo[:MAX_PER_RUN]

    fetched = 0
    for t in todo:
        try:
            rec = _fetch_one(t)
        except Exception as e:  # noqa: BLE001 — 개별 실패 격리
            print(f"[us_etf] {t} 실패: {type(e).__name__}", file=sys.stderr)
            rec = {}
        if rec:
            rec["as_of"] = now.isoformat()
            by_ticker[t] = rec
            fetched += 1
        time.sleep(THROTTLE_SEC)

    cache["by_ticker"] = by_ticker
    cache["updated_at"] = now.isoformat()
    tmp = CACHE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)
    os.replace(tmp, CACHE_PATH)

    etfs = []
    for t in CURATED:
        rec = by_ticker.get(t)
        if not rec or not rec.get("name") or _age_days(rec.get("as_of", ""), now) > STALE_EMIT_DAYS:
            continue
        # as_of(내부 신선도 키) 만 빼고 수집한 사실 전부 발행 — 신 필드 추가 시 emit 누락 방지
        entry = {"ticker": t}
        entry.update({k: v for k, v in rec.items() if k != "as_of" and v not in (None, {}, [])})
        etfs.append(entry)
    etfs.sort(key=lambda e: (e.get("aum_usd") or 0), reverse=True)

    out = {
        "_meta": {
            "generated_at": now.isoformat(),
            "source": "yfinance (US 상장 ETF info + funds_data: 개요/운용/자산군/섹터/밸류에이션/보유종목)",
            "curated_n": len(CURATED),
            "covered_n": len(etfs),
            "fetched_this_run": fetched,
            "disclaimer": "US ETF 사실(카테고리·AUM·운용사·보수·보유종목 top) — 점수/추천 아님(RULE 7). "
                          "실시간 시세·NAV 미노출(증권사 앱). yfinance 무료 소스.",
        },
        "etfs": etfs,
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    print(f"[us_etf] curated {len(CURATED)} | fetched {fetched} | covered {len(etfs)} | out={OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
