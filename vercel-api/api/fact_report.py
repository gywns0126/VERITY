"""GET /api/verity/fact-report?ticker= — 팩트 리포트 PDF (Typst 조판, 다운로드 파일).

(deploy marker 2026-07-05: 데이터 커밋이 평가 HEAD 를 덮어 최초 배포 skip — 재트리거)

브라우저 print 다이얼로그(페이지 덤프) 대체 (PM 2026-07-05) — 서버에서 발행 사실 데이터를
조판한 진짜 PDF 파일. 엔진 = typst-py (Apache-2.0, ms 컴파일 — Zerodha 야간 150만장 실사례).
폰트 = Pretendard(OFL, 사이트 동일). 템플릿 = _templates/fact_report.typ (데이터/조판 분리).

🚨 RULE 7 — 전부 공시·수집 사실 + 자체계산 라벨. 점수·추천·의견 0. LLM 0 (RULE 6).
데이터 = 발행 Blob (stock_report_public / us_* / 분기 / insider) — 사이트와 동일 소스 재사용.
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
from typing import Any, Dict, List, Optional

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


def _stock_of(doc: Any, ticker: str) -> Optional[Dict[str, Any]]:
    arr = (doc or {}).get("stocks")
    if isinstance(arr, dict):
        return arr.get(ticker)
    if isinstance(arr, list):
        for s in arr:
            if str(s.get("ticker")) == ticker:
                return s
    return None


# ─── 포맷터 (한국어 단위 · 콤마) ───
def _num(v: Any, dec: int = 1, suffix: str = "") -> str:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return "—"
    if dec == 0:
        return f"{x:,.0f}{suffix}"
    return f"{x:,.{dec}f}{suffix}"


def _krw(v: Any) -> str:
    """원 단위 금액 → 조/억 표기 (콤마)."""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return "—"
    sign = "-" if x < 0 else ""
    a = abs(x)
    if a >= 1e16:
        return f"{sign}{a / 1e16:,.1f}".rstrip("0").rstrip(".") + "경원"
    if a >= 1e12:
        return f"{sign}{a / 1e12:,.1f}".rstrip("0").rstrip(".") + "조원"
    if a >= 1e8:
        return f"{sign}{a / 1e8:,.0f}억원"
    return f"{sign}{a:,.0f}원"


def _usd(v: Any) -> str:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return "—"
    sign = "-" if x < 0 else ""
    a = abs(x)
    if a >= 1e12:
        return f"{sign}${a / 1e12:,.2f}T"
    if a >= 1e9:
        return f"{sign}${a / 1e9:,.1f}B"
    if a >= 1e6:
        return f"{sign}${a / 1e6:,.0f}M"
    return f"{sign}${a:,.0f}"


def _sec(title: str, note: str, headers: List[str], aligns: List[str],
         widths: List[float], rows: List[List[str]]) -> Optional[Dict[str, Any]]:
    rows = [r for r in rows if any(c and c != "—" for c in r)]
    if not rows:
        return None
    return {"title": title, "note": note, "headers": headers,
            "aligns": aligns, "widths": widths, "rows": rows}


def _build_data(ticker: str) -> Optional[Dict[str, Any]]:
    kr = _TICKER_KR.match(ticker) is not None
    money = _krw if kr else _usd
    s = None
    if kr:
        s = _stock_of(_fetch("stock_report_public.json"), ticker)
    else:
        s = _stock_of(_fetch("us_stock_report_public.json"), ticker)
        if not s:
            try:
                s = _stock_of(_fetch("us_stock_report_us_smallcap.json"), ticker)
            except Exception:  # noqa: BLE001
                s = None
    if not s:
        return None

    now = datetime.now(KST)
    sections: List[Optional[Dict[str, Any]]] = []

    # 밸류에이션 팩트 (지표 | 값 | 업종 중앙값)
    peer = s.get("peer") or {}
    rows = []
    for r in (peer.get("rows") or []):
        rows.append([str(r.get("key") or ""), _num(r.get("value"), 1), _num(r.get("median"), 1)])
    if not rows:
        facts = s.get("facts") or {}
        rows = [[k, str(v), "—"] for k, v in list(facts.items())[:8] if v not in (None, "")]
    sections.append(_sec(
        "밸류에이션 팩트", f"업종 비교 = {peer.get('sector') or '—'} · 같은 섹터 중앙값",
        ["지표", "값", "업종 중앙값"], ["l", "r", "r"], [1.6, 1.0, 1.0], rows))

    # 연간 재무 추이
    fs = s.get("fin_series") or []
    rows = [[str(r.get("year") or ""), money(r.get("revenue")), money(r.get("op")), money(r.get("net"))]
            for r in fs[-8:]]
    sections.append(_sec(
        "연간 재무 추이", "DART 사업보고서" if kr else "SEC 10-K",
        ["연도", "매출", "영업이익", "순이익"], ["l", "r", "r", "r"], [0.7, 1.2, 1.2, 1.2], rows))

    # 분기 재무 비율 (최근 8)
    try:
        qdoc = _fetch("dart_quarterly_public.json" if kr else "us_quarterly_public.json")
        qs = ((qdoc.get("stocks") or {}).get(ticker) or {}).get("quarters") or []
        qs = sorted(qs, key=lambda q: str(q.get("q")))[-8:]
        rows = [[str(q.get("q") or "")[:7], _num(q.get("debt_ratio"), 1, "%"), _num(q.get("roa"), 2, "%"),
                 _num(q.get("current_ratio"), 2), _num(q.get("gross_margin"), 1, "%")] for q in qs]
        sections.append(_sec(
            "분기 재무 비율", "분기·반기·사업보고서 · 비율 자체계산",
            ["분기", "부채비율", "ROA", "유동비율", "매출총이익률"],
            ["l", "r", "r", "r", "r"], [0.9, 1.0, 0.8, 0.9, 1.1], rows))
    except Exception:  # noqa: BLE001
        pass

    # 지분구조 (공정위)
    own = s.get("ownership") or {}
    rows = [[str(sh.get("type") or ""), str(sh.get("name") or ""), _num(sh.get("pct"), 2, "%")]
            for sh in (own.get("shareholders") or [])]
    note = f"총수일가 지배지분 {_num(own.get('family_pct'), 2, '%')} · {own.get('source') or '공정거래위원회'}" if own else ""
    sections.append(_sec("지분구조", note, ["유형", "주주", "의결권 지분율"], ["l", "l", "r"], [0.9, 1.8, 0.9], rows))

    # 내부자 거래 (최근)
    try:
        idoc = _fetch("insider_trades.json" if kr else "us_insider_trades.json")
        irec = _stock_of(idoc, ticker) or {}
        rows = []
        for t in (irec.get("trades") or [])[:10]:
            ch = t.get("change")
            side = "매수" if isinstance(ch, (int, float)) and ch > 0 else "매도"
            rows.append([str(t.get("date") or ""), str(t.get("person") or ""),
                         f"{abs(float(ch)):,.0f}주 {side}" if isinstance(ch, (int, float)) else "—"])
        sections.append(_sec("내부자 거래", "임원·주요주주 보고 사실 (증감 주식수)",
                             ["보고일", "보고자", "증감"], ["l", "l", "r"], [0.9, 1.6, 1.1], rows))
    except Exception:  # noqa: BLE001
        pass

    # 최근 공시
    rows = []
    for d in (s.get("disclosures") or [])[:10]:
        dt = str(d.get("rcept_dt") or d.get("date") or "")
        if len(dt) == 8:
            dt = f"{dt[:4]}-{dt[4:6]}-{dt[6:]}"
        rows.append([dt, str(d.get("pblntf_label") or d.get("kind") or ""), str(d.get("report_nm") or d.get("title") or "")])
    sections.append(_sec("최근 공시", "DART 접수" if kr else "SEC 제출",
                         ["접수일", "유형", "제목"], ["l", "l", "l"], [0.85, 0.8, 2.4], rows))

    # 컨센서스 + 캘린더 (집계 사실)
    con = s.get("consensus") or {}
    rows = []
    if con.get("target_price") is not None:
        rows.append(["컨센서스 목표주가 (증권사 집계)", money(con.get("target_price")) if not kr else _num(con.get("target_price"), 0, "원")])
    if con.get("opinion"):
        rows.append(["컨센서스 의견 분포 (집계)", str(con.get("opinion"))])
    for c in (s.get("calendar") or [])[:2]:
        rows.append([str(c.get("event") or "실적"), f"{c.get('date') or '—'} ({c.get('basis') or '예정'})"])
    sections.append(_sec("컨센서스 · 캘린더", "증권사 집계·자체계산 예상 창 — AlphaNest 의견 아님",
                         ["항목", "내용"], ["l", "l"], [1.2, 2.2], rows))

    ov = s.get("overview") or {}
    kv = [["시장", str(s.get("market") or ("KR" if kr else "US"))]]
    if ov.get("sector"):
        kv.append(["섹터", str(ov.get("sector"))])
    if ov.get("shares"):
        kv.append(["상장주식수", str(ov.get("shares"))])
    hd = s.get("header") or {}
    if hd.get("tagline"):
        kv.append(["사업", str(hd.get("tagline"))])

    return {
        "name": str(s.get("name_ko") or s.get("name") or ticker),
        "ticker": ticker,
        "market": str(s.get("market") or ("KR" if kr else "US")),
        "business": str(s.get("business") or "")[:120],
        "generated": now.strftime("%Y-%m-%d %H:%M KST"),
        "kv": kv[:8],
        "sections": [x for x in sections if x],
        "disclaimer": "전부 공시·수집 사실과 자체계산(라벨 명시) · 점수·등급·추천·매매의견 아님 · AlphaNest 팩트 리포트",
        "source_line": ("DART 전자공시 · KRX 정보데이터시스템 · 공정거래위원회 기업집단포털 · 비율 일부 자체계산(라벨 표기)"
                        if kr else
                        "SEC EDGAR (10-K/Q·Form 4) · 어닝 캘린더 = 제출 패턴 자체계산 · 비율 일부 자체계산(라벨 표기)")
        + f" · 생성 {now.strftime('%Y-%m-%d %H:%M KST')}",
    }


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
            pdf = _render(data)
            fname = f"AlphaNest_FactReport_{ticker}_{datetime.now(KST).strftime('%Y%m%d')}.pdf"
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "application/pdf")
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
            with open(os.path.join(_d, name.replace("dart_quarterly_public.json", "dart_quarterly_public.json")), encoding="utf-8") as f:
                return json.load(f)
        globals()["_fetch"] = _fetch
    d = _build_data(tk)
    if not d:
        print("no data"); sys.exit(1)
    pdf = _render(d)
    out = f"/tmp/fact_report_{tk}.pdf"
    with open(out, "wb") as f:
        f.write(pdf)
    print(f"OK {len(pdf):,} bytes → {out} · 섹션 {len(d['sections'])}")
