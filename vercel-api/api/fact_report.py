"""Model-free research PDF and own-AI evidence export, using public published feeds.

GET /api/fact_report?ticker=... [&format=prompt]
The legacy ai_report entrypoint delegates here. Never call an LLM from this path.
"""
from __future__ import annotations

import json
import os
import re
import time
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


def _fetch(name: str) -> Any:
    ent = _CACHE.get(name)
    if ent and time.time() - ent[0] < _TTL:
        return ent[1]
    req = urllib.request.Request(BLOB + name, headers={"User-Agent": "AlphaNest fact-report"})
    with urllib.request.urlopen(req, timeout=20) as r:
        d = json.loads(r.read().decode("utf-8", "replace"))
    _CACHE[name] = (time.time(), d)
    return d


def _build_data(ticker: str) -> Optional[Dict[str, Any]]:
    from report_evidence import build_report
    return build_report(ticker, _fetch)


def _render(data: Dict[str, Any]) -> bytes:
    import typst
    return typst.compile(
        TEMPLATE,
        font_paths=[FONT_DIR],
        ignore_system_fonts=True,
        sys_inputs={"data": json.dumps(data, ensure_ascii=False)},
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
