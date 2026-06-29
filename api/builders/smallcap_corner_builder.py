"""KR 소형주 코너 유니버스 빌더 (AlphaNest 병렬 트랙 Phase 0).

방치된 중·소형주 코너 = 애널리스트 0~1명 / 기관 capacity 못 드는 구간 = 우리 홈그라운드 엣지.
메인 funnel(25) · brain 산식 · VAMS 검증 trail 과 **완전 별개** — 새 파일만 만든다(teardown 0).

코너 정의 (투명, 튜닝가능 상수):
  · 시총 MKTCAP_MIN ~ MKTCAP_MAX (300억~3000억) — <300억 dead/shell 차단, >3000억 = 대형(타사 커버) 제외
  · 재무 보유 (debt_ratio non-null) — Brain fact 입력 최소조건
출력: data/smallcap_corner.json — 트랙의 funnel-top. Phase 3 에서 이 리스트를 verity_brain.analyze_all 별도 호출.

입력(read-only):
  · data/krx_mktcap.json          — ticker -> {mktcap, close, shares}
  · data/dart_quarterly_snapshots.jsonl — 종목별 재무 (최신 분기)
  · data/kr_listed.json           — ticker -> {name, market(KS/KQ)}
  · data/disclosure_forensics.json — 공시 forensic 깊이 보유 여부 플래그

LLM 0 (RULE 6). 점수/랭킹 0 — 유니버스 정의일 뿐 (Brain 통과는 Phase 3, 공개 노출은 사실만 RULE 7).
"""
import json
import os
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MKTCAP_PATH = os.path.join(_ROOT, "data", "krx_mktcap.json")
FINANCIALS_PATH = os.path.join(_ROOT, "data", "dart_quarterly_snapshots.jsonl")
LISTED_PATH = os.path.join(_ROOT, "data", "kr_listed.json")
FORENSICS_PATH = os.path.join(_ROOT, "data", "disclosure_forensics.json")
OUTPUT_PATH = os.path.join(_ROOT, "data", "smallcap_corner.json")

KST = timezone(timedelta(hours=9))
_EOK = 100_000_000  # 1억

# 코너 밴드 (튜닝가능). 텐배거 핵심은 300~1500억이나 코너 풀은 300~3000억으로 잡는다.
MKTCAP_MIN = 300 * _EOK
MKTCAP_MAX = 3000 * _EOK


def _now_kst() -> datetime:
    return datetime.now(KST)


def _latest_financials() -> Dict[str, Dict[str, Any]]:
    """종목별 최신 분기 재무. 스냅샷 placeholder(재무 전부 null) 행은 제외."""
    latest: Dict[str, Dict[str, Any]] = {}
    if not os.path.exists(FINANCIALS_PATH):
        return latest
    with open(FINANCIALS_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("debt_ratio") is None:  # placeholder 행 skip
                continue
            tk = str(r.get("ticker") or "").strip()
            if not tk:
                continue
            qe = str(r.get("quarter_end") or "")
            prev = latest.get(tk)
            if prev is None or qe > str(prev.get("quarter_end") or ""):
                latest[tk] = r
    return latest


def _mktcap_of(v: Any) -> Optional[float]:
    if isinstance(v, dict):
        m = v.get("mktcap")
        return float(m) if m is not None else None
    if isinstance(v, (int, float)):
        return float(v)
    return None


def main() -> int:
    if not os.path.exists(MKTCAP_PATH):
        print(f"[smallcap_corner] 입력 부재: {MKTCAP_PATH} — skip")
        return 0
    mkt = (json.load(open(MKTCAP_PATH, encoding="utf-8")).get("map")) or {}
    fin = _latest_financials()
    listed = json.load(open(LISTED_PATH, encoding="utf-8")) if os.path.exists(LISTED_PATH) else {}
    forensic_tickers = set()
    if os.path.exists(FORENSICS_PATH):
        forensic_tickers = {
            str(s.get("ticker")) for s in (json.load(open(FORENSICS_PATH, encoding="utf-8")).get("stocks") or [])
        }

    stocks = []
    for tk, v in mkt.items():
        tk = str(tk)
        mc = _mktcap_of(v)
        if mc is None or not (MKTCAP_MIN <= mc < MKTCAP_MAX):
            continue
        f = fin.get(tk)
        if f is None:  # 재무 floor — Brain fact 입력 최소조건
            continue
        meta = listed.get(tk) or {}
        stocks.append({
            "ticker": tk,
            "name": meta.get("name") or (v.get("name") if isinstance(v, dict) else "") or "",
            "market": meta.get("market") or "",
            "mktcap_eok": round(mc / _EOK),
            "close": (v.get("close") if isinstance(v, dict) else None),
            "financials": {
                "debt_ratio": f.get("debt_ratio"),
                "roa": f.get("roa"),
                "gross_margin": f.get("gross_margin"),
                "net_income": f.get("net_income"),
                "quarter_end": f.get("quarter_end"),
            },
            "has_forensic_depth": tk in forensic_tickers,
        })

    stocks.sort(key=lambda s: s["mktcap_eok"])
    forensic_n = sum(1 for s in stocks if s["has_forensic_depth"])
    out = {
        "_meta": {
            "generated_at": _now_kst().isoformat(),
            "track": "kr_smallcap_corner",
            "band_eok": [MKTCAP_MIN // _EOK, MKTCAP_MAX // _EOK],
            "count": len(stocks),
            "with_forensic_depth": forensic_n,
            "source": "krx_mktcap × dart_quarterly_snapshots × kr_listed × disclosure_forensics",
            "note": "메인 funnel/VAMS 와 별개 병렬 트랙. 유동성(거래대금) enrichment = Phase 1. 점수/Brain = Phase 3.",
        },
        "stocks": stocks,
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"[smallcap_corner] 적재 OK at={out['_meta']['generated_at']} | "
          f"{len(stocks)}종목 (forensic 깊이 {forensic_n}) | band {MKTCAP_MIN // _EOK}~{MKTCAP_MAX // _EOK}억 | out={OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
