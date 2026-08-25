"""us_smart_money_13f_public_builder — 공개 터미널 美 스마트머니(집중형 13F) 빌더.

2026-06-22 신설. 13F 완전판([[project_us_financials_sec_edgar]] (b) / [[feedback_us_expansion_settled_no_relitigate]]).
유명 집중형 액티브 매니저의 13F 보유 → CUSIP→ticker(OpenFIGI) → sp1500 per-stock 스마트머니 신호.
"이 종목을 어떤 거장 펀드가 보유/신규/증액/감액했나" = 증권사·토스에 없는 forensics.

🚨 인덱스펀드(Vanguard/BlackRock/State Street) 제외 — sp1500 전부 수동보유라 신호 0 + CUSIP 수천 비용.
   집중형 액티브(Berkshire/Bridgewater/Renaissance/Pershing/Third Point/Tiger)만 = 신호+비용 bounded.

QoQ: 각 펀드 최근 2개 13F-HR 비교 → NEW/INCREASED/DECREASED/HELD. 분기 1회 갱신(13F = 분기말+45일).
🚨 RULE 7 = 보유 사실(펀드·주식수·평가액·QoQ 변동)만. 자체 점수 0 (기존 brain inst_13f_bonus 와 별개·불간섭).
   [[feedback_us_expansion_settled_no_relitigate]] / [[project_brain_v5_self_attribution]].
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List

from api.collectors.sec_13f_collector import (
    TRACKED_INSTITUTIONS, get_recent_13f_filings, get_quarter_snapshots,
    parse_13f_holdings,
)
from api.collectors.cusip_resolver import resolve_cusips
from api.builders.us_insider_trades_public_builder import _now_kst, _universe

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUTPUT_PATH = os.path.join(_ROOT, "data", "us_smart_money_13f.json")

# 집중형 액티브 매니저만 (인덱스펀드 제외 — 신호 희석·비용 회피).
ACTIVE_MANAGERS = {
    "1067983":  "Berkshire Hathaway",
    "1350694":  "Bridgewater Associates",
    "1037389":  "Renaissance Technologies",
    "1336528":  "Pershing Square",
    "1040273":  "Third Point LLC",
    "1423053":  "Tiger Global",
    # 2026-07-30 확장 (PM "전부 ㄱㄱ") — CIK 전부 SEC EDGAR 실조회 확인.
    # 인물 축 뷰(us_investor_portfolios_public_builder)와 공유하는 단일 명단.
    "1697748":  "ARK Invest",
    "1603466":  "Point72",
    "1536411":  "Duquesne Family Office",
    "1029160":  "Soros Fund Management",
    "1647251":  "TCI Fund Management",
    "1103804":  "Viking Global",
    "1167557":  "AQR Capital",
    "850529":   "Fisher Asset Management",
    "923093":   "Tudor Investment",
    "1166559":  "Gates Foundation Trust",
}
TOP_HOLDINGS_PER_FUND = 300   # 펀드당 평가액 상위 N (롱테일 컷 — CUSIP 비용·노이즈 bound)
HELD_SINCE_QUARTERS = 9       # 연속 보유 역추적 창 (13f_quarter_cache 재사용 — 복제 수익률과 동일 창)


def _norm_us_ticker(tk) -> str:
    """13F/OpenFIGI 클래스주 표기 정규화 — 'BRK/B' → 'BRK-B'.

    2026-08-25 실측: Gates 재단 최대 보유 BRK/B 가 슬래시 표기라 sp1500·universe 의
    'BRK-B' 와 조인 실패 → 종목 축에서 통째 누락. 포맷 차이지 멤버십 차이가 아니다.
    """
    return str(tk or "").strip().upper().replace("/", "-").replace(".", "-")


def _load_etf_set() -> set:
    """ETF 티커 집합 (제외용) — us_etf_universe + universe_search(market=ETF) 합집합.

    🚨 2026-08-25 PM 승인 필터 재정의: 종전 'sp1500 만 유지' → 'ETF 만 제외'.
    sp1500 게이트가 거장 실보유 개별주(TSM 8펀드·BRK-B·KOF ADR)를 잘라
    거장 검색이 "보유 없음" 거짓 표면을 만들었다. ETF 제외 취지(신호 희석 방지)만 유지.
    """
    s: set = set()
    for path, pick in (
        (os.path.join(_ROOT, "data", "us_etf_universe.json"), None),
        (os.path.join(_ROOT, "data", "universe_search.json"), "ETF"),
    ):
        try:
            with open(path, encoding="utf-8") as f:
                doc = json.load(f)
            rows = doc.get("stocks") if isinstance(doc, dict) else doc
            for r in rows or []:
                tk = r.get("ticker") if isinstance(r, dict) else r
                if pick and str((r or {}).get("market", "")).upper() != pick:
                    continue
                if tk:
                    s.add(_norm_us_ticker(tk))
        except (OSError, json.JSONDecodeError, AttributeError):
            continue
    return s


def _held_since(qsets: List[tuple], cusip: str):
    """(held_since, quarters_held, floor, qend_price) — 연속 보유 시작 분기 기준.

    qsets = [(report_date, {cusip: 분기말 내재가 or None})] 오래된 → 최근 (최근 = 현 분기).
    최근 분기부터 과거로 걸으며 cusip 이 끊기는 지점에서 멈춘다 — 중간에 청산 후
    재매수한 과거 구간은 세지 않는다 ("언제부터 계속 보유" 의 정의).
    floor=True = 추적창 최고령 분기까지 연속 보유 → 실제 시작은 그 이전일 수 있다.
    qend_price = 연속 보유 시작 **분기말**의 내재가(value/shares) — 🚨 매수 체결가가
    아니다(13F 는 체결가 미공시). 화면 라벨을 '매수가' 로 달지 말 것.
    """
    since, q, price = None, 0, None
    for date, cusips in reversed(qsets):
        if cusip in cusips:
            since, q, price = date, q + 1, cusips.get(cusip)
        else:
            break
    return since, q, q > 0 and q == len(qsets), price


def _holdings_with_change(curr: List[dict], prev: List[dict]) -> List[dict]:
    """현 보유 + QoQ change_type (직전 분기 대비)."""
    pm = {h["cusip"]: h for h in prev if h.get("cusip")}
    out = []
    for h in curr:
        c = h.get("cusip")
        if not c:
            continue
        if c not in pm:
            ct, vc = "NEW", h["value_usd"]
        else:
            ds = h["shares"] - pm[c]["shares"]
            ct = "INCREASED" if ds > 0 else "DECREASED" if ds < 0 else "HELD"
            vc = h["value_usd"] - pm[c]["value_usd"]
        out.append({**h, "change_type": ct, "value_change_usd": vc})
    return out


def main() -> int:
    ok = False
    try:
        sp1500 = {t for t in _universe()}  # sp1500 ticker set (대문자)
        # 1) 각 펀드 최근 2분기 보유 + QoQ (+ 역추적용 분기 스냅샷 — 제출목록 1회 호출 공유)
        fund_holdings: Dict[str, List[dict]] = {}
        fund_meta: Dict[str, Dict[str, Any]] = {}    # fund → report_date/filed_at/총액/분기 cusip 집합
        for cik, name in ACTIVE_MANAGERS.items():
            recent = get_recent_13f_filings(cik, n=HELD_SINCE_QUARTERS)
            if not recent:
                print(f"[smart_money] {name}: 13F-HR 부재 skip", file=sys.stderr)
                continue
            curr_full = parse_13f_holdings(recent[0].get("accession_no", ""), cik)
            curr = curr_full[:TOP_HOLDINGS_PER_FUND]
            prev = parse_13f_holdings(recent[1].get("accession_no", ""), cik) if len(recent) > 1 else []
            fund_holdings[name] = _holdings_with_change(curr, prev)
            snaps = get_quarter_snapshots(cik, filings=recent)   # 캐시 재사용 (복제 수익률과 동일)
            fund_meta[name] = {
                "report_date": recent[0].get("report_date"),
                "filed_at": recent[0].get("filed_at"),
                "total_value_usd": sum((h.get("value_usd") or 0) for h in curr_full),
                # cusip → 분기말 내재가 (0/결측 = None — 가짜 0 금지)
                "qsets": [
                    (d, {
                        r["cusip"]: (
                            round(r["value_usd"] / r["shares"], 2)
                            if (r.get("shares") or 0) > 0 and (r.get("value_usd") or 0) > 0
                            else None
                        )
                        for r in rows
                    })
                    for d, rows in snaps
                ],
            }
            print(f"[smart_money] {name}: 현 {len(curr)} 보유 (filed {recent[0].get('filed_at')}) · 스냅샷 {len(snaps)}분기", file=sys.stderr)

        if not fund_holdings:
            print("[smart_money] 펀드 0 — 기존 보존", file=sys.stderr)
            ok = os.path.isfile(OUTPUT_PATH)
            return 0

        # 2) CUSIP → ticker (OpenFIGI, 캐시)
        all_cusips = {h["cusip"] for hs in fund_holdings.values() for h in hs if h.get("cusip")}
        cmap = resolve_cusips(all_cusips)

        # 3) per-ticker 집계 — 보유 사실 전수 유지 (PM 2026-08-25 "ETF 는 필수지").
        #    종전 sp1500 게이트는 거장 실보유 개별주를 잘랐고(TSM 8펀드 → "보유 없음" 거짓),
        #    1차 정비의 ETF 제외도 같은 종류의 거짓이었다(브리지워터 SPY 보유 = 사실).
        #    🚨 분리 설계: 데이터·검색·보유 표 = ETF 포함(is_etf 플래그) /
        #    순매수 TOP10 랭킹·콘솔 강제편입 = 개별주만(소비자가 is_etf 로 거른다 —
        #    ETF 매수는 개별 종목 확신이 아니라 랭킹 신호 희석).
        etf_set = _load_etf_set()
        unresolved_n = 0
        agg: Dict[str, Dict[str, Any]] = {}
        for fund, hs in fund_holdings.items():
            for h in hs:
                tk = _norm_us_ticker(cmap.get(str(h["cusip"]).upper()))
                if not tk:
                    unresolved_n += 1
                    continue
                e = agg.setdefault(tk, {
                    "ticker": tk,
                    # nameOfIssuer (13F 원문) — 검색창 회사명 매칭용. 없으면 티커 유지.
                    "name": (h.get("issuer") or "").strip() or tk,
                    # ETF 플래그 — 표면은 포함, 랭킹·강제편입 소비자는 이 값으로 거른다.
                    "is_etf": tk in etf_set,
                    "total_value_usd": 0.0, "holder_count": 0, "holders": [],
                })
                m = fund_meta.get(fund, {})
                ft = m.get("total_value_usd") or 0
                since, q_held, floor, since_px = _held_since(m.get("qsets") or [], str(h["cusip"]).upper())
                e["total_value_usd"] += h["value_usd"]
                e["holder_count"] += 1
                e["holders"].append({
                    "fund": fund,
                    "shares": int(h["shares"]),
                    "value_usd": round(h["value_usd"]),
                    # 펀드 공시 총액 대비 비중 (분모 = 상한 300 슬라이스 전 전체 보유 합)
                    "weight_in_fund_pct": round(h["value_usd"] / ft * 100, 2) if ft > 0 else None,
                    "change_type": h["change_type"],            # NEW/INCREASED/DECREASED/HELD
                    "value_change_usd": round(h["value_change_usd"]),
                    # 연속 보유 시작 분기말 (창 = HELD_SINCE_QUARTERS 분기, floor=창 상한 도달
                    # = 실제 시작은 그 이전일 수 있음). 재매수 이전 과거 구간은 미포함.
                    "held_since": since,
                    "quarters_held": q_held,
                    "held_since_floor": floor,
                    # 편입(연속 보유 시작) 분기말 내재가 — 🚨 매수 체결가 아님(13F 미공시).
                    # 화면 라벨 = "편입 분기말 기준가" 류만. '매수가' 단독 표기 금지.
                    "held_since_qend_price_usd": since_px,
                    # 최신 분기말 내재가 (동일 산식 value/shares — 비교 축)
                    "qend_price_usd": (
                        round(h["value_usd"] / h["shares"], 2)
                        if (h.get("shares") or 0) > 0 and (h.get("value_usd") or 0) > 0
                        else None
                    ),
                })

        for e in agg.values():
            e["holders"].sort(key=lambda x: -x["value_usd"])
            e["total_value_usd"] = round(e["total_value_usd"])

        stocks = sorted(agg.values(), key=lambda s: (s["holder_count"], s["total_value_usd"]), reverse=True)

        out = {
            "_meta": {
                "generated_at": _now_kst().isoformat(),
                "source": "SEC EDGAR 13F-HR (집중형 액티브 매니저 보유) + OpenFIGI CUSIP→ticker",
                "managers": list(ACTIVE_MANAGERS.values()),
                "count": len(stocks),
                # fund → 보유 기준일(report_date)·제출일(filed_at). holder 마다 반복하지 않고
                # 여기서 1회 신고 — 화면은 이 맵을 조인해 신선도를 1급 정보로 노출할 것.
                "funds": {
                    f: {"report_date": m.get("report_date"), "filed_at": m.get("filed_at")}
                    for f, m in fund_meta.items()
                },
                "held_since_window_quarters": HELD_SINCE_QUARTERS,
                # 필터 자기신고 (2026-08-25 2차: PM "ETF 는 필수지" — 보유 사실 전수 포함) —
                # 분모를 숨기면 "전부 커버" 로 오독된다 (RULE 13).
                "filter": {
                    "rule": "보유 사실 전수 (ETF 포함, is_etf 플래그) · 순매수 랭킹·강제편입 소비자만 개별주 필터",
                    "etf_kept_n": sum(1 for s in agg.values() if s.get("is_etf")),
                    "unresolved_cusip_n": unresolved_n,
                    "non_sp1500_kept_n": sum(1 for t in agg if t not in sp1500),
                },
                "note": "보유 사실만 — 펀드·주식수·평가액·QoQ 변동(NEW/INCREASED/DECREASED/HELD). 자체 점수·매매신호 아님 (RULE 7). 13F=분기말+45일 지연 공시·롱 미국주식만. 인덱스펀드 제외(집중형만). held_since=연속 보유 시작 분기말(추적창 " + str(HELD_SINCE_QUARTERS) + "분기, held_since_floor=창 상한 도달 → 실제 시작은 그 이전일 수 있음). *_qend_price_usd=분기말 공시 내재가(value/shares) — 매수 체결가 아님(13F 미공시).",
            },
            "stocks": stocks,
        }
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False)
        print(f"[smart_money] logged=True · {len(stocks)} 종목 · 펀드 {len(fund_holdings)} -> {os.path.relpath(OUTPUT_PATH, _ROOT)}", file=sys.stderr)
        ok = True
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[smart_money] FAILED: {e!r}", file=sys.stderr)
        return 1
    finally:
        if not ok:
            print("[smart_money] logged=False", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
