"""us_form144_public_builder — 美 Form 144(제한주식 매도 **예정** 신고) 빌더. 2026-08-09 신설.

**왜 이 축인가.** 우리가 이미 가진 Form 4 는 내부자가 **판 뒤에** 나온다. Form 144 는 팔기
**전에** 낸다 — "누가·몇 주·얼마어치를·언제쯤·어느 브로커로" 팔 예정인지의 사전 신고다.
같은 내부자 축인데 시점이 반대라 Form 4 로는 대체되지 않는다. 2026-08-09 커버리지 점검에서
미장 미사용 SEC 축으로 남아 있던 것을 채운다.

RULE 10 실호출 검증(2026-08-09): 대상회사 CIK submissions 에 form="144" 로 cross-index 된다
  (최근 1,000건 중 AAPL 44 · NVDA 243). Form 4·13D/G 와 동일한 per-ticker 경로라 새 소스·키 0.
  🚨 submissions 의 primaryDocument 는 `xsl144X01/primary_doc.xml`(XSL 렌더 HTML)을 가리킨다.
     구조화 원본은 그 디렉터리를 뺀 `primary_doc.xml` 이다. HTML 을 파싱하면 태그가 tr/td 뿐이라
     값이 하나도 안 나온다(실측 확인).

파싱 필드(ownership 스키마):
  nameOfPersonForWhoseAccountTheSecuritiesAreToBeSold · relationshipToIssuer ·
  noOfUnitsSold(= 매도 **예정** 수량) · aggregateMarketValue · approxSaleDate · 브로커명

🚨 RULE 7 = 공시 사실만(신고자·수량·금액·예정일·원문 링크). 자체 점수·매매신호 0. 관측-only.
   "예정" 이지 체결이 아니다 — 신고 후 미집행도 흔하다. 표기에서 이 구분을 지운다면 거짓이 된다.

설계 = us_insider_trades_public_builder(Form 4) 와 동일: 전 유니버스 rotation + carry-forward +
  wall-clock budget + SEC 10 req/s. 공유 헬퍼 import 로 단일 출처.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import timedelta
from typing import Any, Dict, List, Optional

from api.builders.us_insider_trades_public_builder import (  # noqa: E402
    SEC_UA, SEC_SUBMISSIONS, _now_kst, _float, _txt,
    _ticker_cik_map, _ordered_universe,
)

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUTPUT_PATH = os.path.join(_ROOT, "data", "us_form144.json")
SEC_PRIMARY = "https://www.sec.gov/Archives/edgar/data/{cik}/{accn_nodash}/primary_doc.xml"
SEC_INDEX = "https://www.sec.gov/Archives/edgar/data/{cik}/{accn_nodash}/{accn}-index.htm"

WINDOW_DAYS = 180          # 매도 예정 신고는 단기 신호 — 반년 창
MAX_FILINGS = 15           # 종목당 보존 상한
PER_TICKER_CAP = 12        # 종목당 primary_doc.xml 파싱 상한(대형주는 분기당 수십 건)
SEC_DELAY = 0.13           # SEC 10 req/s 준수
MAX_SECONDS = int(os.environ.get("US_FORM144_MAX_SECONDS", "1800"))
MAX_CALLS = int(os.environ.get("US_FORM144_MAX_CALLS", "10000"))


def _strip_ns(xml_text: str) -> str:
    """namespace 제거 (ownership + ns2:) → local tag 파싱."""
    x = re.sub(r'\sxmlns(:\w+)?="[^"]*"', "", xml_text)
    x = re.sub(r"<(/?)\w+:", r"<\1", x)
    return x


def _iso_date(us: str) -> str:
    """MM/DD/YYYY → YYYY-MM-DD. 형식이 다르면 원문 유지."""
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})$", (us or "").strip())
    return f"{m.group(3)}-{m.group(1)}-{m.group(2)}" if m else (us or "").strip()


def _parse_144(xml_text: str) -> Optional[Dict[str, Any]]:
    """primary_doc.xml → 매도 예정 1건. 구조화 부재 시 None."""
    try:
        root = ET.fromstring(_strip_ns(xml_text))
    except ET.ParseError:
        return None
    # 🚨 발행사 CIK 를 같이 돌려준다 — 호출자가 우리 종목인지 대조한다(2026-08-15 감사).
    #   Form 4 에서 같은 계열이 터졌다: EDGAR 가 양쪽 CIK 에 색인하는 서식을 발행사 확인
    #   없이 수집해, VisionWave 가 SaverOne 지분을 산 거래가 VWAV 내부자 매수로 실렸다.
    #   Form 144 에서 판매자 CIK 색인은 아직 관측되지 않았지만, `issuerCik` 이 원문에
    #   그대로 들어 있어 대조 비용이 0 이다. 한 번 물린 계열은 공짜면 막아 둔다.
    issuer_cik = _txt(root.find(".//issuerInfo/issuerCik")) or _txt(root.find(".//issuerCik"))
    person = _txt(root.find(".//nameOfPersonForWhoseAccountTheSecuritiesAreToBeSold"))
    units = _float(_txt(root.find(".//securitiesInformation/noOfUnitsSold")))
    value = _float(_txt(root.find(".//securitiesInformation/aggregateMarketValue")))
    if not person and units <= 0:
        return None
    rels = [_txt(e) for e in root.findall(".//relationshipToIssuer") if _txt(e)]
    broker = _txt(root.find(".//brokerOrMarketmakerDetails/name"))
    return {
        "_issuer_cik": issuer_cik.lstrip("0") if issuer_cik else "",
        "person": person,
        "relationship": ", ".join(dict.fromkeys(rels)) or None,
        "units": int(units) if units > 0 else None,
        "value_usd": round(value, 2) if value > 0 else None,
        "approx_sale_date": _iso_date(_txt(root.find(".//securitiesInformation/approxSaleDate"))),
        "exchange": _txt(root.find(".//securitiesInformation/securitiesExchangeName")) or None,
        "broker": broker or None,
    }


_SPOT_PATH = os.path.join(_ROOT, "data", "us_options.json")
_spot_cache: Optional[Dict[str, float]] = None


def _spot_map() -> Dict[str, float]:
    """티커 → 참조 현재가(us_options.json 의 spot, 3,500+ 종목).

    🚨 이건 **평가 기준가가 아니라 자릿수 검증용 앵커**다. 회전 수집이라 며칠 stale 할 수
    있으나, 주당 환산이 맞는 자릿수인지 보는 데는 충분하다. 평가·수익률 계산에 쓰지 말 것
    ([[feedback_rotating_collector_not_a_price_source]] 는 그 용도를 금지한 것이고,
     자릿수 sanity 앵커는 별개다).
    """
    global _spot_cache
    if _spot_cache is not None:
        return _spot_cache
    m: Dict[str, float] = {}
    try:
        with open(_SPOT_PATH, encoding="utf-8") as f:
            for s in (json.load(f).get("stocks") or []):
                t, sp = s.get("ticker"), s.get("spot")
                if t and isinstance(sp, (int, float)) and sp > 0:
                    m[str(t).upper()] = float(sp)
    except (OSError, ValueError, TypeError):
        pass
    _spot_cache = m
    return m


def _flag_implied_price_outliers(notices: List[Dict[str, Any]], factor: float = 20.0,
                                 ticker: str = "") -> None:
    """제출인 기입 오류를 잡는다. 제자리 수정(in-place).

    **왜 필요한가.** aggregate market value 는 제출인이 직접 적는 칸이라 오기가 들어온다.
    2026-08-15 실측 — SYF: 동일 인물(COVIELLO ARTHUR W JR)의 동일 4,000주가 5/1 신고
    $305,788, 8/3 신고 **$25,240,000,000**. 주당 631만 달러(SYF 는 $81)로, 총액 $25.3B 가
    SYF 시가총액과 맞먹는 채로 공개 발행물에 실려 있었다. 원인이 남의 오기여도 그대로
    싣는 순간 우리 숫자가 된다 ([[project_dividend_ledger_unit_error_2026_08_15]] 와 동형).

    🚨 **기준점은 외부 참조가(spot) 우선.** 처음엔 종목 내부 중앙값만 썼는데 감사에서
    깨졌다 — BKNG 는 신고 7건 중 2건이 주당 $4,241·$4,141(분할 전 가격대)이고 5건이
    $181~207 인데, 실제 주가는 **$212.06**(52주 $150~232, 야후 실호출 확인)이다.
    내부 중앙값 $200 은 우연히 맞았지만, 다수가 틀린 종목에서는 중앙값이 오류 쪽으로
    뒤집혀 **정답을 이상치로 거는** 구조적 위험이 있다. 판정 근거를 종목 밖에 두어야 한다.
    (여기서 나 자신도 "BKNG 는 $4,200 대" 라고 기억으로 단정했다가 실호출에서 틀렸다 —
     앵커를 데이터로 두는 이유가 정확히 이것이다.)

    spot 이 없는 종목만 내부 중앙값으로 폴백하고, 그때는 표본 <3 이면 판정하지 않는다
    — 근거 없이 지우느니 남긴다. 이상치는 삭제가 아니라 `value_suspect` 사유를 달고
    합계에서만 빠진다(추적 가능).
    """
    px = [(n["value_usd"] / n["units"], n)
          for n in notices
          if n.get("value_usd") and n.get("units") and n["units"] > 0]
    if not px:
        return
    ref = _spot_map().get(str(ticker).upper()) if ticker else None
    label = "참조가"
    if not ref:
        # 폴백 — 표본이 얇으면 판정하지 않는다. 근거 없이 지우느니 남긴다.
        if len(px) < 3:
            return
        ordered = sorted(p for p, _ in px)
        ref = ordered[len(ordered) // 2]
        label = "동일종목 중앙값"
    if not ref or ref <= 0:
        return
    for p, n in px:
        if p > ref * factor or p < ref / factor:
            n["value_suspect"] = (
                f"주당 환산 ${p:,.2f} vs {label} ${ref:,.2f} "
                f"({p / ref:.1f}배) — 제출인 기입 오류 의심. 합계에서 제외")


def _load_prev() -> Dict[str, Dict[str, Any]]:
    try:
        with open(OUTPUT_PATH, encoding="utf-8") as f:
            doc = json.load(f)
        return {str(s.get("ticker") or ""): s for s in (doc.get("stocks") or []) if s.get("ticker")}
    except (OSError, ValueError):
        return {}


def build() -> int:
    import requests

    prev = _load_prev()
    order = _ordered_universe()
    cutoff = (_now_kst() - timedelta(days=WINDOW_DAYS)).strftime("%Y-%m-%d")

    sess = requests.Session()
    try:
        cik_map = _ticker_cik_map(sess)
    except (requests.RequestException, ValueError, KeyError) as e:
        print(f"[us_form144] SEC ticker map 실패: {e!r} — skip(이전 보존)", file=sys.stderr)
        return 0

    t0 = time.monotonic()
    calls = touched = 0
    fresh: Dict[str, Dict[str, Any]] = {}

    for tk in order:
        if time.monotonic() - t0 > MAX_SECONDS or calls >= MAX_CALLS:
            print(f"[us_form144] budget 도달 (calls={calls}, {int(time.monotonic()-t0)}s) "
                  f"— 나머지 carry-forward", file=sys.stderr)
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
        touched += 1

        forms = rec.get("form", [])
        dates = rec.get("filingDate", [])
        accns = rec.get("accessionNumber", [])

        notices: List[Dict[str, Any]] = []
        per = 0
        for i in range(len(forms)):
            if forms[i] != "144" or dates[i] < cutoff:
                continue
            if per >= PER_TICKER_CAP or calls >= MAX_CALLS:
                break
            accn_nodash = accns[i].replace("-", "")
            # 🚨 xsl 렌더본이 아니라 구조화 원본을 받는다(위 docstring 참조).
            url = SEC_PRIMARY.format(cik=int(cik), accn_nodash=accn_nodash)
            try:
                xr = sess.get(url, headers={"User-Agent": SEC_UA}, timeout=12)
                calls += 1
                per += 1
                time.sleep(SEC_DELAY)
                if xr.status_code != 200:
                    continue
                parsed = _parse_144(xr.text)
            except requests.RequestException:
                continue
            if not parsed:
                continue
            # 발행사 대조 — 우리 종목이 아니라 우리 종목이 **남의 주식을 파는** 신고면 버린다.
            if parsed.get("_issuer_cik") and parsed["_issuer_cik"] != str(int(cik)):
                continue
            parsed.pop("_issuer_cik", None)
            parsed["filing_date"] = dates[i]
            parsed["source_url"] = SEC_INDEX.format(
                cik=int(cik), accn_nodash=accn_nodash, accn=accns[i])
            notices.append(parsed)

        if not notices:
            continue
        notices.sort(key=lambda n: n.get("filing_date") or "", reverse=True)
        _flag_implied_price_outliers(notices, ticker=tk)
        # 이상치는 합계에서 제외한다 — 하나가 총액을 통째로 지배한다.
        total_value = sum(n["value_usd"] for n in notices
                          if n.get("value_usd") and not n.get("value_suspect"))
        fresh[tk] = {
            "ticker": tk,
            "notice_count": len(notices),
            "total_value_usd": round(total_value, 2) if total_value else None,
            "latest_filing_date": notices[0].get("filing_date"),
            "notices": notices[:MAX_FILINGS],
            "collected_at": _now_kst().isoformat(),
        }

    merged = dict(prev)
    merged.update(fresh)
    stocks = sorted(merged.values(),
                    key=lambda s: (s.get("latest_filing_date") or ""), reverse=True)

    doc = {
        "_meta": {
            "generated_at": _now_kst().isoformat(),
            "source": "SEC EDGAR Form 144 (제한주식·지배증권 매도 예정 신고) · 대상회사 submissions cross-index",
            "window_days": WINDOW_DAYS,
            "stock_count": len(stocks),
            "notice_count": sum(s.get("notice_count") or 0 for s in stocks),
            "touched_this_run": touched,
            "fresh_this_run": len(fresh),
            "calls": calls,
            "note": "🚨 '매도 예정' 신고이지 체결이 아니다 — 신고 후 미집행도 흔하다. "
                    "Form 4(사후 체결)와 시점이 반대인 별개 축. 공시 사실만, 점수·신호 0(RULE 7).",
        },
        "stocks": stocks,
    }

    # 🚨 [[feedback_silent_total_failure_guard]] — 이번 run 이 한 건도 못 얻었는데 이전 스냅샷을
    #    그대로 다시 써서 성공으로 끝내면 mtime 만 갱신돼 신선해 보인다. 첫 run 이면 실패로 끝낸다.
    if not stocks:
        print("[us_form144] 산출 0건 — 발행하지 않는다", file=sys.stderr)
        return 1
    if not fresh and prev:
        print(f"[us_form144] 이번 run 신규 0건(이전 {len(prev)}종 보존) — budget/차단 의심",
              file=sys.stderr)

    tmp = OUTPUT_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, OUTPUT_PATH)
    m = doc["_meta"]
    print(f"[us_form144] {m['stock_count']:,}종 · 신고 {m['notice_count']:,}건 "
          f"(이번 run 신규 {m['fresh_this_run']:,} · 조회 {touched:,}종 · calls {calls:,})")
    return 0


if __name__ == "__main__":
    raise SystemExit(build())
