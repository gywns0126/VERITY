"""brain_breakdown — Prospero-style Component Grade drill-down endpoint.

GET /api/brain_breakdown?ticker=200670

portfolio.json (Blob) 박은 verity_brain.fact_score.components + sentiment_score.components
+ score_breakdown 박은 데이터 추출. Framer BrainGradeBreakdown.tsx 박은 input.

source: [[project_prospero_component_grade_2026_05_27]]
PM 결정 2026-05-27. RULE 7 비대상 (UI 만, 산식 X).

2026-05-27 v2 — footnote drift fix:
  portfolio.validation.cumulative_days / sample_total / target_days +
  vams.reset_meta.reset_at 박음. 컴포넌트 footnote 가 "N=14 / reset 후 0일"
  static 박혀있던 결함 회복. RULE 7 비대상.
"""
import json
import os
import time
import traceback
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from typing import Optional
from urllib.parse import parse_qs, urlparse

PORTFOLIO_URL = os.environ.get(
    "PORTFOLIO_URL",
    "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/portfolio.json",
)

_cache: dict = {}
_cache_ts: float = 0.0
_CACHE_TTL = 600  # 10분


def _fetch_portfolio() -> dict:
    global _cache, _cache_ts
    if time.time() - _cache_ts < _CACHE_TTL and _cache:
        return _cache
    try:
        req = urllib.request.Request(PORTFOLIO_URL, headers={"User-Agent": "VERITY/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            txt = resp.read().decode("utf-8")
            txt = txt.replace("NaN", "null").replace("Infinity", "null").replace("-Infinity", "null")
            _cache = json.loads(txt)
            _cache_ts = time.time()
    except Exception:
        pass
    return _cache


def _find_rec(data: dict, ticker: str) -> Optional[dict]:
    recs = data.get("recommendations") or []
    tk = ticker.strip().replace(".KS", "").replace(".KQ", "")
    for r in recs:
        if str(r.get("ticker", "")).strip() == tk:
            return r
    return None


def _components_to_list(comp_dict: dict) -> list:
    """components dict → list 박음 (sorted by score desc)."""
    if not isinstance(comp_dict, dict):
        return []
    out = []
    for name, score in comp_dict.items():
        if not isinstance(score, (int, float)):
            continue
        # disabled_regime 같은 flag 제외 (score 박지 않은 meta key)
        if name.endswith("_disabled_regime") or name.endswith("_bonus") or name.endswith("_penalty"):
            continue
        out.append({"name": name, "score": round(float(score), 1)})
    return out


def _days_since(iso_str: str) -> Optional[int]:
    """ISO timestamp → 오늘까지 일수. 파싱 실패 시 None."""
    if not iso_str:
        return None
    try:
        # "2026-05-17T14:12:07.968520+09:00" 형식
        ts = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        return (now - ts.astimezone(timezone.utc)).days
    except (ValueError, TypeError):
        return None


def _build_breakdown(rec: dict, data: dict) -> dict:
    """rec → BrainGradeBreakdown.tsx 박은 schema.

    data = portfolio.json 전체 (validation + vams.reset_meta 박음).
    """
    vb = rec.get("verity_brain") or {}
    sb = rec.get("score_breakdown") or {}

    # validation + VAMS reset 일수 (footnote 동적 박음)
    val = data.get("validation") or {}
    vams_reset_meta = (data.get("vams") or {}).get("reset_meta") or {}
    vams_days = _days_since(vams_reset_meta.get("reset_at", ""))

    fact = vb.get("fact_score") or {}
    sent = vb.get("sentiment_score") or {}

    fact_components = _components_to_list(fact.get("components") or {})
    sent_components = _components_to_list(sent.get("components") or {})

    # IC-DEAD freeze 박힌 components ([[project_ic_dead_freeze_2026_05_23]])
    ic_dead = []
    ic_adj = fact.get("ic_adjustments") or {}
    for k, v in ic_adj.items():
        if isinstance(v, dict) and v.get("status") == "DEAD":
            ic_dead.append(k)
            # mark in components
            for c in fact_components:
                if c["name"] == k:
                    c["status"] = "DEAD"

    regime_info = fact.get("regime_weighting") or {}
    regime = regime_info.get("mode", "unknown")

    penalties = sb.get("penalties") or {}
    penalty = sum(v for v in penalties.values() if isinstance(v, (int, float)))

    bonus = 0.0
    for k in ("vci_bonus", "candle_bonus", "gs_bonus", "inst_bonus"):
        v = sb.get(k)
        if isinstance(v, (int, float)):
            bonus += v

    return {
        "ticker": rec.get("ticker", ""),
        "name": rec.get("name", ""),
        "brain_score": round(float(vb.get("brain_score") or 0), 1),
        "grade": vb.get("grade", "UNKNOWN"),
        "grade_label": vb.get("grade_label", ""),
        "fact_score": round(float(fact.get("score") or 0), 1),
        "sentiment_score": round(float(sent.get("score") or 0), 1),
        "fact_contribution": round(float(sb.get("fact_contribution") or 0), 1),
        "sentiment_contribution": round(float(sb.get("sentiment_contribution") or 0), 1),
        "bonus": round(bonus, 1),
        "penalty": round(penalty, 1),
        "fact_components": fact_components,
        "sentiment_components": sent_components,
        "ic_dead": ic_dead,
        "regime": regime,
        "data_coverage": fact.get("data_coverage", 0),
        "as_of": rec.get("date") or rec.get("updated_at", ""),
        # Footnote 동적 박음 — Phase 0 / VAMS reset 후 일수 + validation 표본
        "validation_days": int(val.get("cumulative_days") or 0),
        "validation_target": int(val.get("target_days") or 90),
        "validation_sample": int(val.get("sample_total") or 0),
        "vams_reset_at": vams_reset_meta.get("reset_at", ""),
        "vams_days_since_reset": vams_days if vams_days is not None else 0,
    }


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            ticker = (params.get("ticker", [""])[0] or params.get("q", [""])[0]).strip()

            if not ticker:
                status = 400
                body = {"error": "ticker 파라미터 필요. 예: ?ticker=200670"}
            else:
                data = _fetch_portfolio()
                if not data:
                    status = 503
                    body = {"error": "portfolio 데이터 fetch 실패 (Blob)"}
                else:
                    rec = _find_rec(data, ticker)
                    if not rec:
                        status = 404
                        body = {"error": f"ticker '{ticker}' 박은 recommendation 미존재"}
                    else:
                        status = 200
                        body = _build_breakdown(rec, data)
        except Exception as e:
            status = 500
            body = {"error": f"서버 오류: {type(e).__name__}: {e}", "traceback": traceback.format_exc()[:500]}

        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "s-maxage=300, stale-while-revalidate=600")
        self.end_headers()
        try:
            self.wfile.write(json.dumps(body, ensure_ascii=False).encode())
        except Exception:
            pass
