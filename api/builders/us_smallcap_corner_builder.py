"""미장(US) 소형주 코너 유니버스 빌더 — 골든구스 미장 트랙.

KR smallcap_corner_builder 의 미장 대응. 방치된 미국 소형주 = sell-side 커버 얇은 구간
(Finviz/Fintel 이 넓게 커버하나 KR 사용자 접근성·우리 forensics 각이 차별). Russell 2000
"멤버십" 대신 Polygon CS active universe + 시총 컷으로 자체 정의(RULE 7, FTSE 라이선스 회피).

코너 정의 (투명·튜닝가능 상수):
  · 시총 CAP_MIN ~ SMALLCAP_CAP_MAX ($50M~$5B) — <$50M shell/dead 차단, >$5B 대형(타사 커버) 제외
  · 재무 보유 (debt_to_equity non-null) — Brain fact 입력 최소조건 (delisted/결측 자동 탈락)
입력(read-only):
  · data/us_market_caps.json        — ticker -> market_cap (USD, yfinance)
  · data/us_financials/*.json       — 종목별 재무 (SEC EDGAR XBRL derived)
  · data/us_universe_combined.json  — ticker -> name (Polygon CS ∪ sp1500)
  · data/us_disclosure_forensics.json — 8-K forensic 깊이 (Phase 4, 부재 시 빈 set)
출력: data/us_smallcap_corner.json — 트랙 funnel-top (KR 스키마 미러, market=US).

LLM 0(RULE 6). 점수/랭킹 0(RULE 7) — 유니버스 정의일 뿐. 시총/재무 부재 = 제외(사실 없으면 비노출).
"""
import json
import os
from datetime import datetime, timezone, timedelta
from typing import Any, Dict

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MKTCAP_PATH = os.path.join(_ROOT, "data", "us_market_caps.json")
FIN_DIR = os.path.join(_ROOT, "data", "us_financials")
UNIVERSE_PATH = os.path.join(_ROOT, "data", "us_universe_combined.json")
FORENSICS_PATH = os.path.join(_ROOT, "data", "us_disclosure_forensics.json")
OUTPUT_PATH = os.path.join(_ROOT, "data", "us_smallcap_corner.json")

KST = timezone(timedelta(hours=9))
_MUSD = 1_000_000  # 백만달러

# 코너 시총 밴드 (튜닝가능). us_financials_builder.SMALLCAP_CAP_MAX 와 정합 — 시총 분포 후 조정.
CAP_MIN = 50 * _MUSD       # $50M — shell/dead 차단
CAP_MAX = 5_000 * _MUSD    # $5B — 대형 제외 (소형~중소형)


def _now_kst() -> datetime:
    return datetime.now(KST)


def _load_market_caps() -> Dict[str, float]:
    if not os.path.exists(MKTCAP_PATH):
        return {}
    try:
        d = json.load(open(MKTCAP_PATH, encoding="utf-8"))
        mc = d.get("market_caps") or {}
        return {str(k).upper(): float(v) for k, v in mc.items()
                if isinstance(v, (int, float)) and v == v and v > 0}
    except Exception:  # noqa: BLE001
        return {}


def _load_names() -> Dict[str, str]:
    if not os.path.exists(UNIVERSE_PATH):
        return {}
    try:
        return json.load(open(UNIVERSE_PATH, encoding="utf-8")).get("names") or {}
    except Exception:  # noqa: BLE001
        return {}


def _forensic_tickers() -> set:
    if not os.path.exists(FORENSICS_PATH):
        return set()
    try:
        return {str(s.get("ticker")) for s in
                (json.load(open(FORENSICS_PATH, encoding="utf-8")).get("stocks") or [])}
    except Exception:  # noqa: BLE001
        return set()


def main() -> int:
    caps = _load_market_caps()
    if not caps:
        print(f"[us_smallcap_corner] 시총 부재: {MKTCAP_PATH} — fetch_us_market_caps --universe combined 먼저. skip")
        return 0
    names = _load_names()
    forensic_tickers = _forensic_tickers()

    stocks = []
    for tk, mc in caps.items():
        if not (CAP_MIN <= mc < CAP_MAX):
            continue
        fp = os.path.join(FIN_DIR, f"{tk}.json")
        if not os.path.exists(fp):  # 재무 floor (결측/delisted 탈락)
            continue
        try:
            d = json.load(open(fp, encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        der = d.get("derived") or {}
        if der.get("debt_to_equity") is None:  # 재무 floor — Brain fact 최소조건
            continue
        az = der.get("altman_z") or {}
        stocks.append({
            "ticker": tk,
            "name": names.get(tk) or (d.get("meta") or {}).get("entity_name") or "",
            "market": "US",
            "mktcap_musd": round(mc / _MUSD),
            "financials": {
                "debt_to_equity": der.get("debt_to_equity"),
                "net_margin_pct": der.get("net_margin_pct"),
                "roe_pct": der.get("roe_pct"),
                "operating_margin_pct": der.get("operating_margin_pct"),
                "altman_z": az.get("z_score"),
                "fscore": der.get("fscore"),
                "fetched_at": d.get("fetched_at"),
            },
            "has_forensic_depth": tk in forensic_tickers,
        })

    stocks.sort(key=lambda s: s["mktcap_musd"])
    forensic_n = sum(1 for s in stocks if s["has_forensic_depth"])
    out = {
        "_meta": {
            "generated_at": _now_kst().isoformat(),
            "track": "us_smallcap_corner",
            "band_musd": [CAP_MIN // _MUSD, CAP_MAX // _MUSD],
            "count": len(stocks),
            "with_forensic_depth": forensic_n,
            "source": "us_market_caps × us_financials × us_universe_combined × us_disclosure_forensics",
            "note": "Polygon CS active ∪ sp1500 + 시총 컷 = 자체 소형주 정의(RULE 7). 메인 funnel/VAMS 와 별개 "
                    "병렬 트랙. forensic 깊이=8-K(Phase 4). 점수/Brain=held(2027).",
        },
        "stocks": stocks,
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"[us_smallcap_corner] 적재 OK at={out['_meta']['generated_at']} | "
          f"{len(stocks)}종목 (forensic 깊이 {forensic_n}) | band ${CAP_MIN // _MUSD}M~${CAP_MAX // _MUSD}M | out={OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
