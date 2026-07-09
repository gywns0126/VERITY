"""krx_mktcap_snapshot — KRX 공식 시가총액·상장주식수 스냅샷 (PER/PBR 자체계산 입력).

2026-06-19 신설. yfinance KR trailingPE/priceToBook=None 한계 돌파 — KRX OpenAPI 공식 MKTCAP ÷
DART 순이익·자기자본으로 PER/PBR 자체계산. 이 스냅샷이 그 시총 입력. 빌더(stock_report_public)는
'외부호출 0' 원칙이라 이 네트워크 스텝이 data/krx_mktcap.json 산출 → 빌더가 읽음(순수 변환 유지).

소스 = krx_openapi.krx_stk_ksq_rows_sorted_by_trading_value (sto/stk_bydd_trd + ksq_bydd_trd, KRX_API_KEY).
  KIS 무관(RULE1 안전, 별도 키). daily_analysis_full 에서 stock_report_public_builder 직전 실행.
출력 = data/krx_mktcap.json {_meta, map: {ticker: {mktcap, close, shares, chg}}}. 발행 불요(중간 산출).
  chg = 당일 등락률(%) — 내부 참고. FLUC_RT 우선, 없으면 CMPPREVDD_PRC/전일종가로 자체계산. 값 불가 시 None.
🚨 시세 재배포 컴플라이언스(2026-07-03 Phase 2): trending_kr.json(거래대금 상위 KRX raw) 생성 중단.
  공개 소비처(StockSearch/StockReport 드롭다운) = 네이버 link-out 이전 완료, 내부 소비 0(ranking_board 동시 은퇴).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUTPUT_PATH = os.path.join(_ROOT, "data", "krx_mktcap.json")
# 검색 universe (전 실상장종목 ticker+name) — 검색창(nav/리포트/결정/관심종목) 공유 소스. 발행 O.
# equities = 위 rows 재사용(추가 호출 0). ETF/ETN/KONEX = 각 1콜. ELW 제외(파생·노이즈). 슬림(ticker/name/market). RULE 7 사실만.
UNIVERSE_SEARCH_PATH = os.path.join(_ROOT, "data", "universe_search_kr.json")
# 통합 검색 universe (KR + US) — 검색창 4종 단일 소스(괴리 제거). KR=위 universe_search_kr 재사용,
# US=us_stock_report_public + us_stock_report_us_smallcap 에서 slim(ticker/name/market) 추출. 발행 O.
UNIVERSE_SEARCH_ALL_PATH = os.path.join(_ROOT, "data", "universe_search.json")
_KR_REPORT_PATH = os.path.join(_ROOT, "data", "stock_report_public.json")
_US_REPORT_PATHS = (
    os.path.join(_ROOT, "data", "us_stock_report_public.json"),
    os.path.join(_ROOT, "data", "us_stock_report_us_smallcap.json"),
)
def _build_unified_universe(kr_uni):
    """KR universe(KRX) + KR/US report slim 병합 → 통합 검색 universe 발행.
    🚨 KRX universe 콜이 메인보드 대형주(삼성전자·SK하이닉스 등)를 누락 → 리포트 보유 종목 union 으로 보강
       (2026-07-08: 페이지가 있는 종목은 정의상 검색돼야 함. universe_search 에 005930 부재 사고).
    US·KR report 파일은 로컬 data/ 읽기 — 외부호출 0. 실패해도 가능한 만큼 발행."""
    try:
        uni = list(kr_uni)
        seen = {str(s.get("ticker") or "") for s in uni}
        # KR 리포트 보유 종목 union (KRX universe 누락분 보강)
        kr_rep_n = 0
        try:
            with open(_KR_REPORT_PATH, "r", encoding="utf-8") as f:
                kd = json.load(f)
            for s in (kd.get("stocks") or []):
                tk = str(s.get("ticker") or "").strip()
                nm = str(s.get("name") or "").strip()
                if not tk or not nm or tk in seen:
                    continue
                seen.add(tk)
                uni.append({"ticker": tk, "name": nm, "market": "KR"})
                kr_rep_n += 1
        except Exception:  # noqa: BLE001
            pass
        us_n = 0
        for p in _US_REPORT_PATHS:
            try:
                with open(p, "r", encoding="utf-8") as f:
                    d = json.load(f)
            except Exception:  # noqa: BLE001
                continue
            arr = d if isinstance(d, list) else (d.get("stocks") or d.get("data") or [])
            for s in (arr or []):
                tk = str(s.get("ticker") or "").strip()
                nm = str(s.get("name") or "").strip()
                if not tk or not nm or tk in seen:
                    continue
                seen.add(tk)
                uni.append({"ticker": tk, "name": nm, "market": "US"})
                us_n += 1
        # 🚨 combined 유니버스 union (2026-07-09) — 리포트 미보유 US 보통주(WULF 등 신규·외국 상장)도
        #   검색 가능하게. 리포트는 없어도 검색→클릭 시 slice stub 안내(리포트 채워지면 자동 상세).
        #   combined = Polygon CS active ∪ sp1500 = 미국 보통주 사실상 전체(~5,313). names 맵 사용.
        # US 한글명 맵 (네이버 autocomplete 수집) — 한글 검색("테라울프") 매칭용 name_ko.
        ko_map = {}
        try:
            ko_map = json.loads(open(os.path.join(_ROOT, "data", "us_stock_names_ko.json"),
                                     encoding="utf-8").read()).get("names") or {}
        except (OSError, ValueError):
            pass
        # 기존 US 엔트리(리포트 유래)에도 name_ko 소급 주입
        for s in uni:
            if s.get("market") == "US" and not s.get("name_ko"):
                k = ko_map.get(str(s.get("ticker") or "").upper())
                if k:
                    s["name_ko"] = k
        us_comb_n = 0
        try:
            cdoc = json.loads(open(os.path.join(_ROOT, "data", "us_universe_combined.json"), encoding="utf-8").read())
            cnames = cdoc.get("names") or {}
            for tk in (cdoc.get("tickers") or []):
                tk = str(tk).strip().upper()
                if not tk or tk in seen:
                    continue
                nm = str(cnames.get(tk) or tk).strip()
                # 표시명 정리 — "XXX Inc. Common Stock" → "XXX Inc." (검색·표시 간결)
                for suf in (" Common Stock", " Common Shares", " Ordinary Shares", " Class A Common Stock"):
                    if nm.endswith(suf):
                        nm = nm[: -len(suf)].strip()
                        break
                seen.add(tk)
                entry = {"ticker": tk, "name": nm or tk, "market": "US"}
                if ko_map.get(tk):
                    entry["name_ko"] = ko_map[tk]  # 한글 검색 매칭
                uni.append(entry)
                us_comb_n += 1
        except Exception:  # noqa: BLE001
            pass
        us_n += us_comb_n
        # 채권·금리 리포트 진입 항목 (2026-07-08) — 검색으로 PublicBondRegime 도달(통합 리포트).
        #   type=rates → PublicStockReport 는 렌더 생략(가드), PublicBondRegime(searchMode)이 표시.
        #   kw = 검색 키워드(비표시 필드, 두 검색창이 kw 도 매칭). ticker RATES_* = 가상 id(실 종목 아님).
        uni.append({"ticker": "RATES_KR", "name": "한국 국채·금리", "market": "채권", "type": "rates",
                    "kw": "채권 국채 금리 수익률 수익률곡선 장단기 스프레드 한국 국고채 bond rates yield"})
        uni.append({"ticker": "RATES_US", "name": "미국 국채·금리", "market": "채권", "type": "rates",
                    "kw": "채권 국채 금리 수익률 수익률곡선 스프레드 미국 미국채 treasury bond rates yield"})
        udoc = {
            "_meta": {"generated_at": datetime.now(KST).isoformat(),
                      "count": len(uni), "kr": len(kr_uni) + kr_rep_n, "us": us_n, "kr_report_union": kr_rep_n,
                      "source": "KRX universe(KR/ETF/ETN/KONEX) + KR/US report(보유 종목 union) slim 병합 — "
                                "검색창 4종 단일 소스. ticker/name 사실. 점수·추천 0."},
            "stocks": uni,
        }
        with open(UNIVERSE_SEARCH_ALL_PATH, "w", encoding="utf-8") as f:
            json.dump(udoc, f, ensure_ascii=False)
        print(f"[krx_mktcap] universe_search(통합) logged=True · {len(uni)} 종목"
              f"(kr {len(kr_uni)}+us {us_n}) -> {os.path.relpath(UNIVERSE_SEARCH_ALL_PATH, _ROOT)}",
              file=sys.stderr)
    except Exception as ue:  # noqa: BLE001
        print(f"[krx_mktcap] universe_search(통합) FAILED(무시): {ue!r}", file=sys.stderr)


def _int(v):
    try:
        return int(float(str(v).replace(",", "").strip()))
    except (TypeError, ValueError):
        return 0


def _flt(v):
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _chg_pct(r):
    """당일 등락률(%). FLUC_RT(KRX 표준 필드) 우선, 없으면 전일대비÷전일종가 자체계산."""
    f = _flt(r.get("FLUC_RT"))
    if f is not None:
        return round(f, 2)
    diff = _flt(r.get("CMPPREVDD_PRC"))
    cls = _int(r.get("TDD_CLSPRC"))
    if diff is not None and cls:
        prev = cls - diff
        if prev:
            return round(diff / prev * 100.0, 2)
    return None


def _append_universe(uni, seen, path, bas_dd, label):
    """KRX OpenAPI 1콜로 검색 universe 에 (ticker/name/market) 추가. 독립 try — 실패 시 0 반환(나머지 소스 보존).
    엔드포인트는 KRX 규약(sto/ 보드 · etp/ ETP) 추론분 포함 → 실 cron 결과(N=2 audit)로 검증."""
    n0 = len(uni)
    try:
        from api.collectors.krx_openapi import _request_krx
        res = _request_krx(path, bas_dd)
        for r in (res.get("rows") or []):
            tk = str(r.get("ISU_SRT_CD") or r.get("ISU_CD") or "").strip()
            nm = str(r.get("ISU_NM") or "").strip()
            if not (len(tk) == 6 and tk.isdigit()) or not nm or tk in seen:
                continue
            seen.add(tk)
            uni.append({"ticker": tk, "name": nm, "market": label})
    except Exception as ee:  # noqa: BLE001
        print(f"[krx_mktcap] {label} universe 스킵: {ee!r}", file=sys.stderr)
    return len(uni) - n0


def main() -> int:
    ok = False
    try:
        from api.collectors.krx_openapi import krx_stk_ksq_rows_sorted_by_trading_value

        bas_dd, rows = krx_stk_ksq_rows_sorted_by_trading_value()
        out = {}
        for r in rows or []:
            tk = str(r.get("ISU_SRT_CD") or r.get("ISU_CD") or "").strip()
            if not (len(tk) == 6 and tk.isdigit()):
                continue
            mktcap = _int(r.get("MKTCAP"))
            if mktcap <= 0:
                continue
            out[tk] = {"mktcap": mktcap, "close": _int(r.get("TDD_CLSPRC")), "shares": _int(r.get("LIST_SHRS")), "chg": _chg_pct(r)}

        if not out and os.path.isfile(OUTPUT_PATH):
            print("[krx_mktcap] 0 rows — 기존 snapshot 보존", file=sys.stderr)
            ok = True
            return 0

        doc = {
            "_meta": {
                "generated_at": datetime.now(KST).isoformat(),
                "bas_dd": bas_dd,
                "count": len(out),
                "source": "KRX OpenAPI sto/stk_bydd_trd + ksq_bydd_trd (MKTCAP·LIST_SHRS)",
            },
            "map": out,
        }
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False)
        print(f"[krx_mktcap] logged=True · {len(out)} 종목 시총 (basDd {bas_dd}) -> "
              f"{os.path.relpath(OUTPUT_PATH, _ROOT)}", file=sys.stderr)

        # trending_kr(거래대금 상위) 생성 = 2026-07-03 컴플라이언스로 은퇴 — KRX raw 재배포. 네이버 link-out 대체.

        # 검색 universe 발행 (전 실상장종목 ticker+name) — equities rows 재사용 + ETF/ETN/KONEX 추가콜.
        # 실패해도 mktcap 보존. 🚫 ELW 제외(파생 워런트·리포트 불가·검색 노이즈, 2026-06-27 PM 결정).
        try:
            uni = []
            seen = set()
            for r in rows or []:
                tk = str(r.get("ISU_SRT_CD") or r.get("ISU_CD") or "").strip()
                nm = str(r.get("ISU_NM") or "").strip()
                if not (len(tk) == 6 and tk.isdigit()) or not nm or tk in seen:
                    continue
                seen.add(tk)
                uni.append({"ticker": tk, "name": nm, "market": "KR"})
            eq_n = len(uni)
            # 추가 실상장 소스 — 각 1콜, 독립 try(하나 실패해도 나머지 보존).
            etf_n = _append_universe(uni, seen, "etp/etf_bydd_trd", bas_dd, "ETF")
            etn_n = _append_universe(uni, seen, "etp/etn_bydd_trd", bas_dd, "ETN")
            knx_n = _append_universe(uni, seen, "sto/knx_bydd_trd", bas_dd, "KONEX")
            if uni:
                udoc = {
                    "_meta": {"generated_at": datetime.now(KST).isoformat(), "bas_dd": bas_dd,
                              "count": len(uni), "equities": eq_n, "etf": etf_n, "etn": etn_n, "konex": knx_n,
                              "source": "KRX OpenAPI stk+ksq+etf+etn+knx — 검색 universe(ticker/name) 사실. ELW 제외. 점수·추천 0."},
                    "stocks": uni,
                }
                with open(UNIVERSE_SEARCH_PATH, "w", encoding="utf-8") as f:
                    json.dump(udoc, f, ensure_ascii=False)
                print(f"[krx_mktcap] universe_search logged=True · {len(uni)} 종목"
                      f"(eq {eq_n}+etf {etf_n}+etn {etn_n}+knx {knx_n}) -> {os.path.relpath(UNIVERSE_SEARCH_PATH, _ROOT)}",
                      file=sys.stderr)
            # 통합 universe(KR+US) 발행 — 검색창 4종 단일 소스
            _build_unified_universe(uni)
        except Exception as ue:  # noqa: BLE001
            print(f"[krx_mktcap] universe_search FAILED(무시): {ue!r}", file=sys.stderr)

        ok = True
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[krx_mktcap] FAILED: {e!r}", file=sys.stderr)
        return 1
    finally:
        if not ok:
            print("[krx_mktcap] logged=False", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
