"""
무료 대안 데이터 수집기 모음
V6: QuiverQuant(미 의회 매매), Kenneth French(Fama-French 팩터),
    EIA Open Data(에너지 재고/생산), SOV.AI(특허/로비) 통합.

모든 소스는 무료 티어 또는 공개 데이터.
실패 시 graceful fallback — 핵심 파이프라인에 영향 없음.
"""
from __future__ import annotations

import csv
import io
import json
import logging
import os
import time
import zipfile
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import requests

from api.config import DATA_DIR, now_kst

logger = logging.getLogger(__name__)

ALT_DATA_CACHE_DIR = os.path.join(DATA_DIR, "alt_data_cache")

_HEADERS = {
    "User-Agent": "VERITY/6.0 (github.com/verity; research@verity.dev)",
    "Accept": "application/json",
}


def _ensure_cache_dir():
    os.makedirs(ALT_DATA_CACHE_DIR, exist_ok=True)


def _load_cache(name: str, max_age_hours: int = 24) -> Optional[Any]:
    path = os.path.join(ALT_DATA_CACHE_DIR, f"{name}.json")
    try:
        stat = os.stat(path)
        age_h = (time.time() - stat.st_mtime) / 3600
        if age_h > max_age_hours:
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _save_cache(name: str, data: Any):
    _ensure_cache_dir()
    path = os.path.join(ALT_DATA_CACHE_DIR, f"{name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)


# ═══════════════════════════════════════════════════════════════
# 1. QuiverQuant — 미 의회 의원 주식 거래
# ═══════════════════════════════════════════════════════════════

QUIVER_API_KEY = os.environ.get("QUIVER_API_KEY", "").strip()
QUIVER_BASE = "https://api.quiverquant.com/beta"


def fetch_congress_trades(days: int = 30) -> Dict[str, Any]:
    """최근 N일간 미 의회 의원 주식 매매 데이터."""
    cached = _load_cache("quiver_congress", max_age_hours=12)
    if cached:
        return cached

    if not QUIVER_API_KEY:
        return {"ok": False, "error": "QUIVER_API_KEY not set", "trades": []}

    try:
        resp = requests.get(
            f"{QUIVER_BASE}/bulk/congresstrading",
            headers={**_HEADERS, "Authorization": f"Bearer {QUIVER_API_KEY}"},
            timeout=30,
        )
        resp.raise_for_status()
        raw = resp.json()

        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        trades = []
        for t in raw:
            tx_date = t.get("TransactionDate", t.get("Date", ""))
            if tx_date >= cutoff:
                trades.append({
                    "ticker": t.get("Ticker", ""),
                    "representative": t.get("Representative", ""),
                    "transaction": t.get("Transaction", ""),
                    "amount": t.get("Amount", ""),
                    "date": tx_date,
                    "house": t.get("House", ""),
                })

        buys = [t for t in trades if "Purchase" in (t.get("transaction") or "")]
        sells = [t for t in trades if "Sale" in (t.get("transaction") or "")]

        buy_tickers: Dict[str, int] = {}
        for t in buys:
            tk = t["ticker"]
            buy_tickers[tk] = buy_tickers.get(tk, 0) + 1

        top_buys = sorted(buy_tickers.items(), key=lambda x: x[1], reverse=True)[:20]

        result = {
            "ok": True,
            "total_trades": len(trades),
            "buy_count": len(buys),
            "sell_count": len(sells),
            "top_buys": [{"ticker": tk, "count": c} for tk, c in top_buys],
            "recent_trades": trades[:50],
            "fetched_at": str(now_kst()),
        }
        _save_cache("quiver_congress", result)
        return result

    except Exception as e:
        logger.warning("QuiverQuant congress trades failed: %s", e)
        return {"ok": False, "error": str(e), "trades": []}


# ═══════════════════════════════════════════════════════════════
# 2. Kenneth French — Fama-French 3/5 Factor Data
# ═══════════════════════════════════════════════════════════════

FF_BASE = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp"


def fetch_fama_french_factors(dataset: str = "F-F_Research_Data_5_Factors_2x3_daily") -> Dict[str, Any]:
    """Kenneth French 라이브러리에서 Fama-French 팩터 CSV를 fetch."""
    cached = _load_cache("fama_french_5factor", max_age_hours=168)
    if cached:
        return cached

    url = f"{FF_BASE}/{dataset}_CSV.zip"
    try:
        resp = requests.get(url, timeout=60, headers=_HEADERS)
        resp.raise_for_status()

        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            csv_names = [n for n in zf.namelist() if n.endswith(".CSV") or n.endswith(".csv")]
            if not csv_names:
                return {"ok": False, "error": "No CSV in zip"}

            with zf.open(csv_names[0]) as cf:
                text = cf.read().decode("utf-8", errors="replace")

        lines = text.strip().split("\n")
        header_idx = None
        for i, line in enumerate(lines):
            if "Mkt-RF" in line or "Mkt" in line:
                header_idx = i
                break

        if header_idx is None:
            return {"ok": False, "error": "Header not found"}

        reader = csv.reader(lines[header_idx:])
        headers = [h.strip() for h in next(reader)]

        recent_rows = []
        for row in reader:
            if not row or not row[0].strip():
                break
            if len(row[0].strip()) < 6:
                continue
            date_str = row[0].strip()
            vals = {}
            for i, h in enumerate(headers[1:], 1):
                try:
                    vals[h] = float(row[i].strip())
                except (ValueError, IndexError):
                    pass
            if vals:
                recent_rows.append({"date": date_str, **vals})

        last_60 = recent_rows[-60:] if len(recent_rows) > 60 else recent_rows

        avg_factors = {}
        for h in headers[1:]:
            vals = [r.get(h, 0) for r in last_60 if h in r]
            if vals:
                avg_factors[h] = round(sum(vals) / len(vals), 4)

        result = {
            "ok": True,
            "dataset": dataset,
            "total_rows": len(recent_rows),
            "recent_60d_avg": avg_factors,
            "latest_date": recent_rows[-1]["date"] if recent_rows else "",
            "fetched_at": str(now_kst()),
        }
        _save_cache("fama_french_5factor", result)
        return result

    except Exception as e:
        logger.warning("Fama-French fetch failed: %s", e)
        return {"ok": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════
# 3. EIA Open Data — 에너지 생산/재고
# ═══════════════════════════════════════════════════════════════

EIA_API_KEY = os.environ.get("EIA_API_KEY", "").strip()
EIA_BASE = "https://api.eia.gov/v2"


def fetch_eia_petroleum_summary() -> Dict[str, Any]:
    """EIA: 주간 원유 재고, 생산량, 수입 요약."""
    cached = _load_cache("eia_petroleum", max_age_hours=24)
    if cached:
        return cached

    if not EIA_API_KEY:
        return {"ok": False, "error": "EIA_API_KEY not set"}

    series_ids = {
        "crude_inventory_mbbl": "PET.WCESTUS1.W",
        "crude_production_mbpd": "PET.WCRFPUS2.W",
        "crude_imports_mbpd": "PET.WCEIMUS2.W",
    }

    data: Dict[str, Any] = {}
    for label, series_id in series_ids.items():
        try:
            resp = requests.get(
                f"{EIA_BASE}/seriesid/{series_id}",
                params={"api_key": EIA_API_KEY, "num": "4"},
                headers=_HEADERS,
                timeout=20,
            )
            if resp.status_code == 200:
                j = resp.json()
                points = j.get("response", {}).get("data", [])
                if points:
                    latest = points[0]
                    data[label] = {
                        "value": latest.get("value"),
                        "period": latest.get("period"),
                    }
            time.sleep(0.3)
        except Exception as e:
            logger.debug("EIA series %s failed: %s", series_id, e)

    if not data:
        return {"ok": False, "error": "No EIA data fetched"}

    result = {"ok": True, **data, "fetched_at": str(now_kst())}
    _save_cache("eia_petroleum", result)
    return result


# ═══════════════════════════════════════════════════════════════
# 4. SOV.AI — 특허/로비/의회 활동 (트라이얼 기반)
# ═══════════════════════════════════════════════════════════════

SOV_API_KEY = os.environ.get("SOV_API_KEY", "").strip()


def fetch_sov_patent_activity(tickers: List[str]) -> Dict[str, Any]:
    """SOV.AI 특허 출원 활동 요약 (API 키 있을 때만)."""
    cached = _load_cache("sov_patents", max_age_hours=168)
    if cached:
        return cached

    if not SOV_API_KEY:
        return {"ok": False, "error": "SOV_API_KEY not set"}

    try:
        results = {}
        for ticker in tickers[:10]:
            resp = requests.get(
                f"https://api.sov.ai/v1/patents/{ticker}",
                headers={**_HEADERS, "Authorization": f"Bearer {SOV_API_KEY}"},
                timeout=15,
            )
            if resp.status_code == 200:
                results[ticker] = resp.json()
            time.sleep(0.5)

        result = {"ok": True, "tickers": results, "fetched_at": str(now_kst())}
        _save_cache("sov_patents", result)
        return result

    except Exception as e:
        logger.warning("SOV.AI patent fetch failed: %s", e)
        return {"ok": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════
# 통합 수집 함수
# ═══════════════════════════════════════════════════════════════

def collect_all_alt_data(us_tickers: Optional[List[str]] = None) -> Dict[str, Any]:
    """모든 대안 데이터를 한 번에 수집. 각 소스는 독립적으로 실패 가능."""
    _ensure_cache_dir()
    result: Dict[str, Any] = {"collected_at": str(now_kst()), "sources": {}}

    congress = fetch_congress_trades()
    result["sources"]["congress_trades"] = {
        "ok": congress.get("ok", False),
        "buy_count": congress.get("buy_count", 0),
        "top_buys": congress.get("top_buys", [])[:10],
    }

    ff = fetch_fama_french_factors()
    result["sources"]["fama_french"] = {
        "ok": ff.get("ok", False),
        "recent_60d_avg": ff.get("recent_60d_avg", {}),
        "latest_date": ff.get("latest_date", ""),
    }

    eia = fetch_eia_petroleum_summary()
    result["sources"]["eia_petroleum"] = {
        "ok": eia.get("ok", False),
        "crude_inventory_mbbl": eia.get("crude_inventory_mbbl"),
        "crude_production_mbpd": eia.get("crude_production_mbpd"),
    }

    if us_tickers:
        sov = fetch_sov_patent_activity(us_tickers)
        result["sources"]["sov_patents"] = {
            "ok": sov.get("ok", False),
            "tickers_count": len(sov.get("tickers", {})),
        }

    active = sum(1 for s in result["sources"].values() if s.get("ok"))
    result["active_sources"] = active
    result["total_sources"] = len(result["sources"])

    return result
