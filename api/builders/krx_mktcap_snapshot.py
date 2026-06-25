"""krx_mktcap_snapshot — KRX 공식 시가총액·상장주식수 스냅샷 (PER/PBR 자체계산 입력).

2026-06-19 신설. yfinance KR trailingPE/priceToBook=None 한계 돌파 — KRX OpenAPI 공식 MKTCAP ÷
DART 순이익·자기자본으로 PER/PBR 자체계산. 이 스냅샷이 그 시총 입력. 빌더(stock_report_public)는
'외부호출 0' 원칙이라 이 네트워크 스텝이 data/krx_mktcap.json 산출 → 빌더가 읽음(순수 변환 유지).

소스 = krx_openapi.krx_stk_ksq_rows_sorted_by_trading_value (sto/stk_bydd_trd + ksq_bydd_trd, KRX_API_KEY).
  KIS 무관(RULE1 안전, 별도 키). daily_analysis_full 에서 stock_report_public_builder 직전 실행.
출력 = data/krx_mktcap.json {_meta, map: {ticker: {mktcap, close, shares, chg}}}. 발행 불요(중간 산출).
  chg = 당일 등락률(%) — public_price_snapshot_builder(순수변환)가 읽어 히트맵 가격% 토글 입력 생성.
        FLUC_RT 우선, 없으면 CMPPREVDD_PRC/전일종가로 자체계산. 값 불가 시 None.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUTPUT_PATH = os.path.join(_ROOT, "data", "krx_mktcap.json")
# 거래대금 상위(검색창 포커스 "지금 거래 활발") — 같은 KRX rows(이미 거래대금 내림차순) 재사용. 발행 O.
# 🚨 RULE 7: 사실(거래대금/등락)만. 추천·인기점수 아님. ETF는 stk/ksq 소스라 애초에 제외됨.
TRENDING_PATH = os.path.join(_ROOT, "data", "trending_kr.json")
TREND_TOP_N = 30
# 검색 universe (전 종목 ticker+name) — 4 검색창(nav/리포트/결정/관심종목) 공유 소스. 발행 O.
# equities = 위 rows 재사용(추가 호출 0). ETF = etf_bydd_trd 1콜. 슬림(ticker/name/market). RULE 7 사실만.
UNIVERSE_SEARCH_PATH = os.path.join(_ROOT, "data", "universe_search_kr.json")
_TREND_SKIP = ("스팩", "제spac")  # SPAC 제외(거래대금 큰 합병前 스팩 노이즈 회피)


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

        # 거래대금 상위 발행 (rows 는 이미 ACC_TRDVAL 내림차순) — 실패해도 mktcap 산출은 보존
        try:
            trending = []
            for r in rows or []:
                tk = str(r.get("ISU_SRT_CD") or r.get("ISU_CD") or "").strip()
                if not (len(tk) == 6 and tk.isdigit()):
                    continue
                name = str(r.get("ISU_NM") or "").strip()
                if not name or any(h in name for h in _TREND_SKIP):
                    continue
                trdval = _int(r.get("ACC_TRDVAL") or r.get("ACC_TRDVALU"))
                if trdval <= 0:
                    continue
                trending.append({"ticker": tk, "name": name, "trdval": trdval, "close": _int(r.get("TDD_CLSPRC")), "chg": _chg_pct(r)})
                if len(trending) >= TREND_TOP_N:
                    break
            if trending:
                tdoc = {
                    "_meta": {"generated_at": datetime.now(KST).isoformat(), "bas_dd": bas_dd, "count": len(trending),
                              "source": "KRX OpenAPI 거래대금 상위(유가+코스닥) · 사실(거래대금/등락) · 추천 아님"},
                    "top": trending,
                }
                with open(TRENDING_PATH, "w", encoding="utf-8") as f:
                    json.dump(tdoc, f, ensure_ascii=False)
                print(f"[krx_mktcap] trending logged=True · {len(trending)} 종목 거래대금 상위 -> "
                      f"{os.path.relpath(TRENDING_PATH, _ROOT)}", file=sys.stderr)
        except Exception as te:  # noqa: BLE001
            print(f"[krx_mktcap] trending FAILED(무시): {te!r}", file=sys.stderr)

        # 검색 universe 발행 (전 종목 ticker+name) — equities rows 재사용 + ETF 1콜. 실패해도 mktcap 보존.
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
            try:
                from api.collectors.krx_openapi import _request_krx
                etf_res = _request_krx("etp/etf_bydd_trd", bas_dd)
                for r in (etf_res.get("rows") or []):
                    tk = str(r.get("ISU_SRT_CD") or r.get("ISU_CD") or "").strip()
                    nm = str(r.get("ISU_NM") or "").strip()
                    if not (len(tk) == 6 and tk.isdigit()) or not nm or tk in seen:
                        continue
                    seen.add(tk)
                    uni.append({"ticker": tk, "name": nm, "market": "ETF"})
            except Exception as ee:  # noqa: BLE001
                print(f"[krx_mktcap] ETF universe 스킵(equities만): {ee!r}", file=sys.stderr)
            if uni:
                udoc = {
                    "_meta": {"generated_at": datetime.now(KST).isoformat(), "bas_dd": bas_dd,
                              "count": len(uni), "equities": eq_n, "etf": len(uni) - eq_n,
                              "source": "KRX OpenAPI stk+ksq+etf — 검색 universe(ticker/name) 사실. 점수·추천 0."},
                    "stocks": uni,
                }
                with open(UNIVERSE_SEARCH_PATH, "w", encoding="utf-8") as f:
                    json.dump(udoc, f, ensure_ascii=False)
                print(f"[krx_mktcap] universe_search logged=True · {len(uni)} 종목"
                      f"(eq {eq_n}+etf {len(uni) - eq_n}) -> {os.path.relpath(UNIVERSE_SEARCH_PATH, _ROOT)}",
                      file=sys.stderr)
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
