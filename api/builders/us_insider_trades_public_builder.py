"""us_insider_trades_public_builder — 공개 터미널 美 내부자(임원·이사·10%주주) Form4 거래 빌더.

2026-06-22 신설. KR insider_trades_public_builder(DART elestock) 의 美 짝 = SEC Form4.
[[project_us_financials_sec_edgar]] (b) 후속 / [[feedback_us_expansion_settled_no_relitigate]].
증권사·토스·네이버 종목페이지에 없는 forensics 신호 — 공개 US insider 탭(KR 와 대칭).

소스: SEC EDGAR (무료, UA 연락처만). ticker→CIK(company_tickers.json) →
  submissions/CIK{10}.json 의 form=='4' 최근분 → Archives/.../form4.xml 전체 파싱
  (보고자·관계·비파생 거래 주식수·취득(A)/처분(D)·코드·날짜).

🚨 전 종목(sp1500 1505) 확장 설계 (KR 빌더 패턴 그대로):
- 일별 rotation: portfolio US 우선풀 항상 + 나머지 day-of-year offset 회전 → 며칠 내 전 종목 커버.
- carry-forward 병합: 오늘 수집 안 한 종목은 이전 snapshot 유지(내부자 공시=느린 이벤트).
- wall-clock budget(US_INSIDER_MAX_SECONDS 기본 2400s) + MAX_CALLS — 초과 시 안전 정지·보존.
- SEC 10 req/s 준수(0.13s/call). per-stock collected_at 로 신선도 투명.
🚨 RULE 7 = 공시 사실만(보고자·직위·증감(취득+/처분−)·날짜·코드·원문). 자체 점수·매매신호 0. 관측-only.
"""
from __future__ import annotations

import json
import os
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

KST = timezone(timedelta(hours=9))
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SP1500_PATH = os.path.join(_ROOT, "data", "us_universe_sp1500.json")
# 통합 유니버스(sp1500 + Polygon 소형주 ~5,313, tier_map 포함). 심화데이터를 소형주까지 확장(2026-07-09).
COMBINED_PATH = os.path.join(_ROOT, "data", "us_universe_combined.json")
PORTFOLIO_PATH = os.path.join(_ROOT, "data", "portfolio.json")
OUTPUT_PATH = os.path.join(_ROOT, "data", "us_insider_trades.json")

SEC_UA = "VERITY/1.0 (gywns0126@gmail.com)"  # SEC 는 연락처 포함 UA 요구
SEC_TICKERS = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik10}.json"
SEC_ARCHIVE = "https://www.sec.gov/Archives/edgar/data/{cik}/{accn_nodash}/{doc}"
SEC_INDEX = "https://www.sec.gov/Archives/edgar/data/{cik}/{accn_nodash}/{accn}-index.htm"

WINDOW_DAYS = 365
MAX_TRADES = 20            # 종목당 노출 거래 상한
PER_TICKER_CAP = 8         # 종목당 form4.xml 파싱 상한 (균등 커버·runaway 방지)
SEC_DELAY = 0.13           # SEC 10 req/s 안전 마진
MAX_SECONDS = int(os.environ.get("US_INSIDER_MAX_SECONDS", "2400"))
MAX_CALLS = int(os.environ.get("US_INSIDER_MAX_CALLS", "12000"))

DEFAULT_US15 = [
    "MSFT", "JNJ", "BAC", "ADBE", "CRM", "JPM", "DIS", "SOFI",
    "QCOM", "META", "BRK-B", "TMO", "PG", "XOM", "CSCO",
]


def _now_kst() -> datetime:
    return datetime.now(KST)


def _float(v) -> float:
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return 0.0


def _universe() -> List[str]:
    """전체 US 유니버스 = combined(sp1500 + Polygon 소형주 ~5,313). 부재 시 sp1500 → US15 fallback.
    심화데이터(내부자·13F·대량보유·컨센서스) 소형주 확장 (2026-07-09). budget+rotation+carry-forward 로
    회당 예산 내 rotating 커버 — 대형주 데이터는 carry-forward 보존, 소형주는 사이클로 순차 채움."""
    for path in (COMBINED_PATH, SP1500_PATH):
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
            out = [str(t).strip().upper() for t in (d.get("tickers") or []) if str(t).strip()]
            if out:
                return out
        except (OSError, ValueError):
            continue
    return list(DEFAULT_US15)


def _rec_us_set() -> set:
    """우선풀 — portfolio.json USD 종목(항상 수집해 featured 신선 유지)."""
    try:
        with open(PORTFOLIO_PATH, encoding="utf-8") as f:
            p = json.load(f)
    except (OSError, ValueError):
        return set()
    out = set()
    for key in ("recommendations", "candidates"):
        for s in (p.get(key) or []):
            tk = str(s.get("ticker") or "").strip().upper()
            cur = s.get("currency")
            # currency 명시 USD 또는 KR 6자리 아님 → US 로 간주
            if tk and (cur == "USD" or not (tk.isdigit() and len(tk) == 6)):
                out.add(tk)
    return out


_ROTATION_CYCLE_DAYS = 7  # 확장 유니버스(소형주 포함 ~5,313) 전 커버 목표 사이클


def _ordered_universe() -> List[str]:
    """rec 우선풀 먼저 + 나머지를 페이지 단위 회전(~7일 1사이클, 전 종목 순차 커버).
    day-of-year 를 페이지 단위로 회전 — 소형주 확장(5,313)으로 하루 1칸 회전은 꼬리 종목이 수천일
    대기 → 페이지(≈len/7)씩 전진해 대형·소형 모두 주 단위 커버 (2026-07-09)."""
    uni = _universe()
    rec = _rec_us_set()
    priority = [t for t in uni if t in rec]
    rest = [t for t in uni if t not in rec]
    if rest:
        page = max(1, len(rest) // _ROTATION_CYCLE_DAYS)
        start = (_now_kst().timetuple().tm_yday % _ROTATION_CYCLE_DAYS) * page
        rest = rest[start:] + rest[:start]
    return priority + rest


def _load_prev() -> Dict[str, Dict[str, Any]]:
    """이전 snapshot → {ticker: entry} (carry-forward 베이스)."""
    try:
        with open(OUTPUT_PATH, encoding="utf-8") as f:
            doc = json.load(f)
        return {str(s.get("ticker") or ""): s for s in (doc.get("stocks") or []) if s.get("ticker")}
    except (OSError, ValueError):
        return {}


def _ticker_cik_map(sess) -> Dict[str, str]:
    r = sess.get(SEC_TICKERS, headers={"User-Agent": SEC_UA}, timeout=15)
    r.raise_for_status()
    out = {}
    for row in r.json().values():
        out[str(row["ticker"]).upper()] = f"{int(row['cik_str']):010d}"
    return out


def _txt(el: Optional[ET.Element]) -> str:
    return (el.text or "").strip() if el is not None else ""


def _parse_form4(xml_text: str) -> Optional[Tuple[str, str, float, str, str]]:
    """form4.xml → (person, position, net_shares, code, last_date).

    net_shares = Σ 비파생 거래 (취득 A=+ / 처분 D=−) 주식수. code = 대표 거래코드(P/S 우선).
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return None
    owner = root.find(".//reportingOwner")
    person = position = ""
    if owner is not None:
        person = _txt(owner.find(".//rptOwnerName"))
        rel = owner.find(".//reportingOwnerRelationship")
        if rel is not None:
            is_off = _txt(rel.find("isOfficer")) in ("1", "true")
            is_dir = _txt(rel.find("isDirector")) in ("1", "true")
            is_ten = _txt(rel.find("isTenPercentOwner")) in ("1", "true")
            title = _txt(rel.find("officerTitle"))
            if is_off:
                position = title or "Officer"
            elif is_dir:
                position = "Director"
            elif is_ten:
                position = "10% Owner"
    net = 0.0
    codes: List[str] = []
    last_date = ""
    for tx in root.iter("nonDerivativeTransaction"):
        shares = _float(_txt(tx.find(".//transactionShares/value")))
        ad = _txt(tx.find(".//transactionAcquiredDisposedCode/value")).upper()
        code = _txt(tx.find(".//transactionCode"))
        d = _txt(tx.find(".//transactionDate/value"))
        if d > last_date:
            last_date = d
        if code:
            codes.append(code)
        net += shares * (1 if ad == "A" else -1 if ad == "D" else 0)
    if not codes and net == 0.0:
        return None  # 비파생 거래 없음(파생만 — 옵션 등, 방향 신호 약함)
    primary = "P" if "P" in codes else "S" if "S" in codes else (codes[0] if codes else "")
    return person, position, net, primary, last_date


def main() -> int:
    ok = False
    try:
        import requests

        cutoff = (_now_kst().date() - timedelta(days=WINDOW_DAYS)).strftime("%Y-%m-%d")
        today = _now_kst().date().strftime("%Y-%m-%d")
        merged = _load_prev()
        order = _ordered_universe()

        sess = requests.Session()
        try:
            cik_map = _ticker_cik_map(sess)
        except (requests.RequestException, ValueError, KeyError) as e:
            print(f"[us_insider] SEC ticker map 실패: {e!r} — skip(이전 보존)", file=sys.stderr)
            return 0

        t0 = time.monotonic()
        calls = collected = 0
        for tk in order:
            if time.monotonic() - t0 > MAX_SECONDS or calls >= MAX_CALLS:
                print(f"[us_insider] budget 도달 (calls={calls}, {int(time.monotonic()-t0)}s) — 나머지 carry-forward", file=sys.stderr)
                break
            cik = cik_map.get(tk)
            if not cik:
                continue
            try:
                sub = sess.get(SEC_SUBMISSIONS.format(cik10=cik), headers={"User-Agent": SEC_UA}, timeout=15)
                calls += 1
                time.sleep(SEC_DELAY)
                if sub.status_code != 200:
                    continue
                rec = sub.json().get("filings", {}).get("recent", {})
            except (requests.RequestException, ValueError):
                continue
            forms = rec.get("form", [])
            dates = rec.get("filingDate", [])
            accns = rec.get("accessionNumber", [])
            pdocs = rec.get("primaryDocument", [""] * len(forms))

            trades: List[Dict[str, Any]] = []
            net_total = buy_n = sell_n = 0.0
            per = n_form4 = 0
            for i in range(len(forms)):
                if forms[i] != "4" or dates[i] < cutoff:
                    continue
                n_form4 += 1   # 윈도우 내 Form4 존재 여부 (pop 권위성 판단)
                if per >= PER_TICKER_CAP or calls >= MAX_CALLS:
                    break
                accn = accns[i]
                accn_nodash = accn.replace("-", "")
                raw_doc = (pdocs[i] or "").split("/")[-1] or "form4.xml"
                url = SEC_ARCHIVE.format(cik=int(cik), accn_nodash=accn_nodash, doc=raw_doc)
                try:
                    xr = sess.get(url, headers={"User-Agent": SEC_UA}, timeout=12)
                    calls += 1
                    per += 1
                    time.sleep(SEC_DELAY)
                    if xr.status_code != 200:
                        continue
                    parsed = _parse_form4(xr.text)
                except requests.RequestException:
                    continue
                if not parsed:
                    continue
                person, position, net, code, last_date = parsed
                net_total += net
                if net > 0:
                    buy_n += 1
                elif net < 0:
                    sell_n += 1
                trades.append({
                    "date": last_date or dates[i],
                    "person": person,
                    "position": position,
                    "change": int(net),            # +취득 / −처분 (주)
                    "code": code,                  # P=공개매수 / S=공개매도 / A·M·G 등
                    "source_url": SEC_INDEX.format(cik=int(cik), accn_nodash=accn_nodash, accn=accn),
                })

            if trades:
                trades.sort(key=lambda t: t["date"], reverse=True)
                merged[tk] = {
                    "ticker": tk, "name": tk, "cik": cik,
                    "net_change": int(net_total), "buy_n": int(buy_n), "sell_n": int(sell_n),
                    "total": len(trades), "trades": trades[:MAX_TRADES], "collected_at": today,
                }
                collected += 1
            elif n_form4 == 0:
                # 권위적 공백(200 응답 + 윈도우 내 Form4 0건) — 이전 데이터 제거(aged out).
                merged.pop(tk, None)
                collected += 1
            # else: Form4 존재하나 trades 0 (xml 파싱·일시 실패) → 이전 보존, collected 미증가

        stocks = sorted(merged.values(), key=lambda s: -abs(int(s.get("net_change") or 0)))

        if not stocks and os.path.isfile(OUTPUT_PATH):
            print("[us_insider] 0 종목 — 기존 snapshot 보존", file=sys.stderr)
            ok = True
            return 0

        out = {
            "_meta": {
                "generated_at": _now_kst().isoformat(),
                "source": "SEC EDGAR Form 4 (임원·이사·10%주주 거래)",
                "window_days": WINDOW_DAYS,
                "count": len(stocks),
                "universe": len(order),
                "collected_today": collected,
                "note": "공시 사실만 — 보고자·직위·증감(취득+/처분−)·날짜·코드·원문. 자체 점수·매매신호 아님 (RULE 7). KR insider 의 美 Form4 짝. 전 종목(sp1500) 회전 수집(per-stock collected_at).",
            },
            "stocks": stocks,
        }
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False)
        print(f"[us_insider] logged=True · {len(stocks)} 종목(누적) · 오늘수집 {collected}/{len(order)} · calls={calls} -> {os.path.relpath(OUTPUT_PATH, _ROOT)}", file=sys.stderr)
        ok = True
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[us_insider] FAILED: {e!r}", file=sys.stderr)
        return 1
    finally:
        if not ok:
            print("[us_insider] logged=False", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
