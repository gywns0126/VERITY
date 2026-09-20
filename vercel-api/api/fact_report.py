"""Model-free research PDF and own-AI evidence export, using public published feeds.

GET /api/fact_report?ticker=... [&format=prompt]
The legacy ai_report entrypoint delegates here. Never call an LLM from this path.
"""
from __future__ import annotations

import json
import os
import re
import time
import threading
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler
from typing import Any, Dict, Optional

KST = timezone(timedelta(hours=9))
_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(_DIR, "_templates", "fact_report.typ")
FONT_DIR = os.path.join(_DIR, "_fonts")

BLOB = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/"
_TICKER_KR = re.compile(r"^\d{6}$")
_TICKER_US = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")

# 발행 피드 인스턴스 캐시 (Vercel warm instance 재사용, TTL 10분)
_CACHE: Dict[str, Any] = {}
_TTL = 600.0
_SEC_CACHE = {}
_SEC_LOCK = threading.Lock()


def _fetch_sec(name):
    """Only fixed SEC paths; bounded cache, response size and timeout; no API key."""
    facts = re.fullmatch(r"sec-companyfacts/(\d{10})\.json", name)
    filing = re.fullmatch(r"sec-filing/(\d{1,10})/(\d{10}-\d{2}-\d{6})/([\w.-]+\.html?)", name)
    if facts:
        url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{facts[1]}.json"
    elif filing:
        url = f"https://www.sec.gov/Archives/edgar/data/{int(filing[1])}/{filing[2].replace('-', '')}/{filing[3]}"
    else:
        raise ValueError("invalid_sec_path")
    with _SEC_LOCK:
        ent = _SEC_CACHE.get(name)
        if ent and time.time() - ent[0] < (3600 if ent[2] is None else 300):
            if ent[2]:
                raise RuntimeError("sec_temporarily_unavailable")
            return ent[1]
    # A slow filing must not hold up unrelated CIKs on the warm instance.
    result, failed = None, False
    try:
        req = urllib.request.Request(url, headers={"User-Agent": os.environ.get("SEC_USER_AGENT") or os.environ.get("SEC_API_USER_AGENT") or "AlphaNest public research contact@verity.local"})
        with urllib.request.urlopen(req, timeout=8) as response:
            raw = response.read(12 * 1024 * 1024 + 1)
        if len(raw) > 12 * 1024 * 1024:
            raise ValueError("sec_document_size_limit")
        body = raw.decode("utf-8", "replace")
        result = json.loads(body) if facts else body
    except Exception:
        failed = True
    with _SEC_LOCK:
        _SEC_CACHE[name] = (time.time(), result, failed or None)
        while len(_SEC_CACHE) > 16:
            del _SEC_CACHE[min(_SEC_CACHE, key=lambda k: _SEC_CACHE[k][0])]
    if failed:
        raise RuntimeError("sec_temporarily_unavailable") from None
    return result


def _fetch(name: str) -> Any:
    if name.startswith("sec-"):
        return _fetch_sec(name)
    ent = _CACHE.get(name)
    if ent and time.time() - ent[0] < _TTL:
        return ent[1]
    if name.startswith('report-news/'):
        if __package__:
            from .stock_news import _fetch_google_news
        else:
            from stock_news import _fetch_google_news
        query = urllib.parse.unquote(name.removeprefix('report-news/'))
        d = {'items': _fetch_google_news(query, limit=50, strict=True),
             'fetched_at': datetime.now(timezone.utc).isoformat()}
        _CACHE[name] = (time.time(), d)
        return d
    req = urllib.request.Request(BLOB + name, headers={"User-Agent": "AlphaNest fact-report"})
    with urllib.request.urlopen(req, timeout=20) as r:
        d = json.loads(r.read().decode("utf-8", "replace"))
    _CACHE[name] = (time.time(), d)
    return d


def _build_data(ticker: str) -> Optional[Dict[str, Any]]:
    if __package__:
        from .report_evidence import build_report
    else:
        from report_evidence import build_report
    return build_report(ticker, _fetch)


def _render(data: Dict[str, Any]) -> bytes:
    import typst
    if __package__:
        from .report_visuals import chart_svg
    else:
        from report_visuals import chart_svg
    # Vector markup is only a render asset, not research material in the prompt.
    charts = data.get("reader", {}).get("visuals", {}).get("charts", {})
    rendered = {**data, "chart_images": {key: chart_svg(chart) for key, chart in charts.items()}}
    return typst.compile(
        TEMPLATE,
        font_paths=[FONT_DIR],
        ignore_system_fonts=True,
        sys_inputs={"data": json.dumps(rendered, ensure_ascii=False)},
    )


class handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _err(self, code: int, msg: str):
        body = json.dumps({"error": msg}).encode()
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        try:
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            ticker = (qs.get("ticker", [""])[0] or "").strip().upper()
            if not (_TICKER_KR.match(ticker) or _TICKER_US.match(ticker)):
                return self._err(400, "invalid_ticker")
            data = _build_data(ticker)
            if not data:
                return self._err(404, "unknown_ticker")
            if __package__:
                from .report_evidence import analysis_prompt
            else:
                from report_evidence import analysis_prompt
            output_format = qs.get("format", ["pdf"])[0]
            if output_format not in ("pdf", "prompt"):
                return self._err(400, "invalid_format")
            data["prompt_url"] = "https://project-yw131.vercel.app/api/fact_report?ticker=" + urllib.parse.quote(ticker) + "&format=prompt"
            pdf = analysis_prompt(data).encode("utf-8") if output_format == "prompt" else _render(data)
            fname = f"AlphaNest_Research_{ticker}_{datetime.now(KST).strftime('%Y%m%d')}." + ("txt" if output_format == "prompt" else "pdf")
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "text/plain; charset=utf-8" if output_format == "prompt" else "application/pdf")
            # inline = 브라우저 새 탭 미리보기(사용자가 저장 선택), filename 지정으로 저장명 정리
            self.send_header("Content-Disposition", f'inline; filename="{fname}"')
            self.send_header("Content-Length", str(len(pdf)))
            self.send_header("Cache-Control", "public, max-age=600")
            self.end_headers()
            self.wfile.write(pdf)
        except Exception as e:  # noqa: BLE001
            self._err(500, f"{type(e).__name__}")


# 로컬 테스트: python api/fact_report.py <ticker> <repo_data_dir>
if __name__ == "__main__":
    import sys
    tk = sys.argv[1] if len(sys.argv) > 1 else "005930"
    if len(sys.argv) > 2:
        _data_dir = sys.argv[2]
        def _fetch(name: str, _d=_data_dir):  # noqa: F811
            with open(os.path.join(_d, name), encoding="utf-8") as f:
                return json.load(f)
        globals()["_fetch"] = _fetch
    d = _build_data(tk)
    if not d:
        print("no data"); sys.exit(1)
    d["prompt_url"] = "https://project-yw131.vercel.app/api/fact_report?ticker=" + urllib.parse.quote(tk) + "&format=prompt"
    pdf = _render(d)
    out = f"/tmp/fact_report_{tk}.pdf"
    with open(out, "wb") as f:
        f.write(pdf)
    print(f"OK {len(pdf):,} bytes → {out} · 섹션 {len(d['sections'])}")
