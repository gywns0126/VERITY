"""GET /api/verity/fact-report?ticker= — 팩트 리포트 PDF (Typst 조판, 다운로드 파일).

(deploy marker v2 2026-07-05: 머지-후-커밋 선형 push — ignoreCommand 1차부모 diff 정합)

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

    # 밸류에이션 팩트 (지표 | 값 | 업종 중앙값 | 업종 대비) — 값은 빌더 포맷 문자열 그대로 (단위 포함)
    peer = s.get("peer") or {}
    _VS = {"above": "높음", "below": "낮음", "similar": "비슷"}
    rows = []
    for r in (peer.get("rows") or []):
        pct = r.get("pct")
        rows.append([str(r.get("key") or ""), str(r.get("value") or "—"), str(r.get("median") or "—"),
                     _VS.get(str(r.get("vs") or ""), "—"),
                     f"{pct}%" if isinstance(pct, (int, float)) else "—"])
    if not rows:
        facts0 = s.get("facts") or {}
        rows = [[k, str(v), "—", "—", "—"] for k, v in list(facts0.items())[:8] if v not in (None, "")]
    sections.append(_sec(
        "밸류에이션 팩트", f"업종 비교 = {peer.get('sector') or '—'} · 중앙값·백분위 = 같은 섹터 내 위치(사실 · 평가 아님)",
        ["지표", "값", "업종 중앙값", "업종 대비", "업종 백분위"], ["l", "r", "r", "c", "r"], [1.3, 0.85, 0.9, 0.6, 0.8], rows))

    # 재무 요약 — 최근 결산 재무제표 그룹 전체 (손익·재무상태·현금흐름 등)
    fin = s.get("financials") or {}
    rows = []
    for g in (fin.get("groups") or []):
        gt = str(g.get("title") or "")
        for i, kv2 in enumerate(g.get("rows") or []):
            rows.append([gt if i == 0 else "", str(kv2.get("k") or ""), str(kv2.get("v") or "")])
    if rows:
        sections.append(_sec(
            "재무 요약", f"{fin.get('period') or ''} 결산 · DART" if kr else f"{fin.get('period') or ''} · SEC",
            ["구분", "항목", "값"], ["l", "l", "r"], [0.8, 1.4, 1.0], rows))

    # 연간 재무 추이 — 과거 백필분 순이익=영업이익 복제(수집 결함, 보강 큐) → 동일값은 "—" 정직 표기
    fs = s.get("fin_series") or []
    rows = []
    net_gap = False
    for r in fs[-10:]:
        op, net = r.get("op"), r.get("net")
        dup = op is not None and net is not None and op == net
        if dup:
            net_gap = True
        rows.append([str(r.get("year") or ""), money(r.get("revenue")), money(op), "—" if dup else money(net)])
    note = ("DART 사업보고서" if kr else "SEC 10-K") + (" · 순이익 — = 과거분 보강 수집 중" if net_gap else "")
    sections.append(_sec(
        "연간 재무 추이", note,
        ["연도", "매출", "영업이익", "순이익"], ["l", "r", "r", "r"], [0.7, 1.2, 1.2, 1.2], rows))

    # 분기 재무 비율 (최근 8)
    try:
        qdoc = _fetch("dart_quarterly_public.json" if kr else "us_quarterly_public.json")
        qs = ((qdoc.get("stocks") or {}).get(ticker) or {}).get("quarters") or []
        qs = sorted(qs, key=lambda q: str(q.get("q")))[-8:]
        rows = [[str(q.get("q") or "")[:7], _num(q.get("debt_ratio"), 1, "%"), _num(q.get("roa"), 2, "%"),
                 _num(q.get("current_ratio"), 2), _num(q.get("gross_margin"), 1, "%")] for q in qs]
        sections.append(_sec(
            "분기 재무 비율", "분기·반기·사업보고서 · 비율 자체계산 · 과거 분기 = 최신 연도부터 백필 진행 중",
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

    # 내부자 거래 (최근) — 타임라인에도 합류 (_insider_rows_cache)
    _insider_rows_cache: List[List[str]] = []
    try:
        idoc = _fetch("insider_trades.json" if kr else "us_insider_trades.json")
        irec = _stock_of(idoc, ticker) or {}
        rows = []
        for t in (irec.get("trades") or [])[:10]:
            ch = t.get("change")
            side = "매수" if isinstance(ch, (int, float)) and ch > 0 else "매도"
            desc = f"{abs(float(ch)):,.0f}주 {side}" if isinstance(ch, (int, float)) else "—"
            rows.append([str(t.get("date") or ""), str(t.get("person") or ""), desc])
            if str(t.get("date") or "") >= (now - timedelta(days=365)).strftime("%Y-%m-%d"):
                _insider_rows_cache.append([str(t.get("date") or ""), "내부자", f"{t.get('person') or ''} {desc}"])
        sections.append(_sec("내부자 거래", "임원·주요주주 보고 사실 (증감 주식수)",
                             ["보고일", "보고자", "증감"], ["l", "l", "r"], [0.9, 1.6, 1.1], rows))
    except Exception:  # noqa: BLE001
        pass

    # 대차잔고 (KRX 사실)
    if kr:
        try:
            ldoc = _fetch("securities_lending.json")
            arr = ldoc.get("stocks") or ldoc
            lrec = arr.get(ticker) if isinstance(arr, dict) else next((x for x in arr if str(x.get("ticker")) == ticker), None)
            if lrec and lrec.get("lending_amt"):
                rows = [
                    ["대차잔고 금액", _krw(lrec.get("lending_amt"))],
                    ["대차잔고 수량", _num(lrec.get("lending_qty"), 0, "주")],
                    ["신규 대차", _num(lrec.get("new_qty"), 0, "주")],
                    ["상환", _num(lrec.get("redemption_qty"), 0, "주")],
                ]
                sections.append(_sec("대차잔고", "KRX 대차거래 사실 (공매도 선행지표 아님 — 해석 없음)",
                                     ["항목", "값"], ["l", "r"], [1.2, 1.4], rows))
        except Exception:  # noqa: BLE001
            pass

    # ── 최근 1년 타임라인 (공시 + 내부자 + 포렌식 이벤트 + 실적 제출 통합 연표) ──
    lo1y = (now - timedelta(days=365)).strftime("%Y-%m-%d")
    tl: List[List[str]] = []
    for d in (s.get("disclosures") or []):
        dt = str(d.get("rcept_dt") or d.get("date") or "")
        if len(dt) == 8:
            dt = f"{dt[:4]}-{dt[4:6]}-{dt[6:]}"
        if dt:
            tl.append([dt, str(d.get("pblntf_label") or d.get("kind") or "공시"),
                       str(d.get("report_nm") or d.get("title") or "")[:56]])
    foren = None
    try:
        fdoc = _fetch("disclosure_forensics.json" if kr else "us_disclosure_feed.json")
        foren = _stock_of(fdoc, ticker)
    except Exception:  # noqa: BLE001
        foren = None
    for e in ((foren or {}).get("events") or [])[:12]:
        dt = str(e.get("date") or "")
        if dt >= lo1y:
            tl.append([dt, str(e.get("category") or "이벤트"), str(e.get("title") or "")[:56]])
    for t in _insider_rows_cache or []:
        tl.append(t)
    try:
        pdoc = _fetch("kr_earnings_pattern.json" if kr else "us_earnings_pattern.json")
        for pr in ((pdoc.get("patterns") or {}).get(ticker) or [])[:5]:
            dt = str(pr.get("filed") or "")
            if dt >= lo1y:
                tl.append([dt, "실적 공시", str(pr.get("form") or "")])
    except Exception:  # noqa: BLE001
        pass
    seen_tl = set()
    tl2 = []
    for r in sorted(tl, key=lambda x: x[0], reverse=True):
        key = (r[0], r[2][:30])
        if key in seen_tl:
            continue
        seen_tl.add(key)
        tl2.append(r)
    sections.append(_sec("최근 1년 타임라인", "공시·내부자·이벤트·실적 제출 통합 (사실 연표)",
                         ["일자", "유형", "내용"], ["l", "l", "l"], [0.75, 0.95, 2.4], tl2[:18]))

    # ── 외인·기관 수급 (최근 5거래일) ──
    if kr:
        try:
            fdoc2 = _fetch("stock_flow_5d.json")
            frows = (fdoc2.get("flows") or {}).get(ticker) or []
            rows = []
            for r in frows[-5:]:
                fn, inn, close = r.get("foreign_net"), r.get("inst_net"), r.get("close")
                rows.append([str(r.get("date") or "")[5:],
                             _num(fn, 0, "주") if isinstance(fn, (int, float)) else "—",
                             _num(inn, 0, "주") if isinstance(inn, (int, float)) else "—",
                             _num(close, 0, "원") if isinstance(close, (int, float)) else "—"])
            sections.append(_sec("외인·기관 수급", "최근 5거래일 순매매(주식수) · 종가",
                                 ["일자", "외국인", "기관", "종가"], ["l", "r", "r", "r"], [0.6, 1.1, 1.1, 0.9], rows))
        except Exception:  # noqa: BLE001
            pass

    # ── 공시 포렌식 요약 (유형별 건수 — 수집창 내 사실) ──
    if kr and foren and (foren.get("counts") or {}):
        rows = [[k2, _num(v2, 0, "건")] for k2, v2 in sorted((foren.get("counts") or {}).items(), key=lambda x: -x[1])]
        sections.append(_sec("공시 이벤트 유형 집계", "DART 원문 제목 기준 · 현재 수집창 한정 · 위험점수 아님",
                             ["유형", "건수"], ["l", "r"], [2.0, 0.6], rows[:10]))

    # ── 국민연금 보유 (공시 사실) ──
    if kr:
        try:
            ndoc = _fetch("nps_holdings.json")
            nrec = next((h for h in (ndoc.get("holdings") or []) if str(h.get("ticker")) == ticker), None)
            if nrec and nrec.get("pct") is not None:
                rows = [["보유 지분율", _num(nrec.get("pct"), 2, "%")], ["기준일", str(nrec.get("date") or "—")]]
                sections.append(_sec("국민연금 보유", str(nrec.get("src") or "공공데이터포털"),
                                     ["항목", "값"], ["l", "r"], [1.2, 1.2], rows))
        except Exception:  # noqa: BLE001
            pass

    # ── (미장) 13F 스마트머니 · 13D/G 대량보유 ──
    if not kr:
        try:
            mdoc = _fetch("us_smart_money_13f.json")
            mrec = (mdoc.get("stocks") or {}).get(ticker)
            rows = []
            for h in ((mrec or {}).get("holders") or [])[:8]:
                ct = {"INCREASED": "확대", "DECREASED": "축소", "NEW": "신규", "UNCHANGED": "유지"}.get(str(h.get("change_type") or ""), "")
                rows.append([str(h.get("fund") or ""), _usd(h.get("value_usd")), ct])
            if rows:
                sections.append(_sec("13F 기관 보유 (스마트머니)", "SEC 13F 분기 공시 사실 · 보유가치 기준",
                                     ["펀드", "보유가치", "직전 대비"], ["l", "r", "c"], [1.7, 0.9, 0.6], rows))
        except Exception:  # noqa: BLE001
            pass
        try:
            hdoc = _fetch("us_major_holdings.json")
            hrec = (hdoc.get("stocks") or {}).get(ticker)
            rows = []
            for f2 in ((hrec or {}).get("filings") or [])[:6]:
                rows.append([str(f2.get("date") or ""), str(f2.get("type") or ""), str(f2.get("filer") or "")[:36],
                             _num(f2.get("pct"), 1, "%") if f2.get("pct") is not None else "—"])
            if rows:
                sections.append(_sec("대량보유 공시 (13D/G)", "SEC Schedule 13D/G 사실",
                                     ["제출일", "유형", "보고자", "지분"], ["l", "l", "l", "r"], [0.8, 0.6, 1.6, 0.6], rows))
        except Exception:  # noqa: BLE001
            pass

    # ── 실적 제출 이력 (자체계산 캘린더 근거) ──
    try:
        pdoc = _fetch("kr_earnings_pattern.json" if kr else "us_earnings_pattern.json")
        prs = ((pdoc.get("patterns") or {}).get(ticker) or [])[:6]
        rows = [[str(p2.get("filed") or ""), str(p2.get("form") or "")] for p2 in prs]
        sections.append(_sec("실적 공시 제출 이력", "제출 리듬 = 다음 예상 창의 계산 근거 (자체계산)",
                             ["제출일", "보고서"], ["l", "l"], [0.9, 1.5], rows))
    except Exception:  # noqa: BLE001
        pass

    # ── 시장경보 (KRX 플래그) ──
    if kr:
        try:
            wdoc = _fetch("market_warnings.json")
            wrec = (wdoc.get("warnings") or {}).get(ticker)
            labels = (wrec or {}).get("labels") if isinstance(wrec, dict) else wrec
            if labels:
                rows = [[str(l2.get("label") if isinstance(l2, dict) else l2), str(l2.get("severity") or "") if isinstance(l2, dict) else ""] for l2 in labels]
                sections.append(_sec("시장경보", "KRX 시장경보·종목상태 공식 플래그",
                                     ["구분", "수준"], ["l", "l"], [1.4, 0.8], rows))
        except Exception:  # noqa: BLE001
            pass

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
    facts = s.get("facts") or {}
    kv = [["시장", str(s.get("market") or ("KR" if kr else "US"))]]
    if facts.get("시가총액"):
        kv.append(["시가총액", str(facts.get("시가총액"))])
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
