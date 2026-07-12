"""
DART 펀더멘털 batch wrapper — Phase 2-A (2026-05-01)

Phase 0.5 결정 2 / 결정 14 적용:
  1순위: DART 분기 보고서 (debt_ratio, op_margin, roe — PL/BS 항목)
  2순위: yfinance .KS suffix (per/pbr 가격 의존 + DART 누락 종목 fallback)
  제외:  pykrx (환경 부적합), KIS (rate limit)

기존 인프라 재활용:
  - api/collectors/dart_corp_code.py — ticker → corp_code 매핑
  - api/collectors/DartScout.py:_get_fnltt_data — 분기 보고서 캐시

설계:
  - 주 1회 (월요일) 갱신 권고 (FUND-CHANGE 측정 결과 — PBR/ROE/op_margin 분기 의존)
  - max_workers=10 (DART rate limit 일 1만건 고려)
  - 모든 외부 호출 timeout 명시 (결정 16 wrapper 의무)
"""
from __future__ import annotations

import functools
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout, as_completed
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

# DART rate limit 안전 마진 — 일 1만건 / 주 1회 갱신 시 5,000 종목 OK
DART_BATCH_MAX_WORKERS_DEFAULT = 10
DART_PER_TICKER_TIMEOUT_S = 15.0


def _parse_int(value) -> int:
    if value is None:
        return 0
    s = str(value).strip().replace(",", "")
    if not s or s == "-":
        return 0
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return 0


def _extract_pl_bs_from_dart(data: dict) -> dict:
    """DART fnlttSinglAcntAll.json 응답에서 PL/BS/CF 핵심 항목 추출.

    2026-05-20 확장 (실호출 audit 005930 2024 CFS 213 항목 기준):
      BS 9 + IS 5 + CF 3 (영업/투자/재무 활동 현금흐름) + 매출원가/매출총이익.
      fnlttSinglAcnt (단일계정) 30 항목 → fnlttSinglAcntAll (전체) 213 항목 전환.

    Returns: {
      total_assets, total_liabilities, equity,
      current_assets, current_liabilities, working_capital,
      retained_earnings, capital,
      revenue, cogs, gross_profit, operating_profit, net_income, pretax_income,
      operating_cashflow, investing_cashflow, financing_cashflow, free_cashflow
    }
    """
    out = {
        "total_assets": 0,
        "total_liabilities": 0,
        "equity": 0,
        "current_assets": 0,
        "current_liabilities": 0,
        "working_capital": 0,
        "retained_earnings": 0,
        "capital": 0,
        "revenue": 0,
        "cogs": 0,
        "gross_profit": 0,
        "operating_profit": 0,
        "net_income": 0,
        "pretax_income": 0,
        "sga": 0,             # 판매비와관리비 (IS)
        "finance_income": 0,  # 금융수익 (IS)
        "finance_cost": 0,    # 금융원가 (IS) — 이자비용+환차손 등 포함(순수 이자비용 아님)
        "income_tax": 0,      # 법인세비용 (IS)
        "investment_property": 0,  # 투자부동산 장부가(BS) — 리포트 '부동산' 섹션용 사실
        "tangible_assets": 0,      # 유형자산 장부가(BS) — 부동산 프록시 상한(토지·건물 미분리 기업 커버)
        "land": 0,                 # 토지 장부가(BS) — 감가 없는 취득원가, 숨은자산 핵심(BS 면 노출 기업만)
        "buildings": 0,            # 건물 장부가(BS)
        "real_estate_book": 0,     # 토지+건물+투자부동산 (소유 부동산 장부가 · 사용권자산 제외) — NAV 프록시 원천
        "operating_cashflow": 0,
        "investing_cashflow": 0,
        "financing_cashflow": 0,
        "free_cashflow": 0,
    }
    for item in data.get("list", []):
        sj = item.get("sj_div", "")
        acct = item.get("account_nm", "")
        aid = item.get("account_id", "")
        amount = _parse_int(item.get("thstrm_amount"))
        if sj == "BS":
            # 🚨 총계류 = account_id(IFRS 표준) 우선 매칭 + 한글 exact fallback.
            #   한글명 exact 만 하면 공백 변형('자산 총계')을 미스 → total_assets=0 → source:none 사고
            #   (2026-07-12 고영 등 21종목 실증: DART 정상 174항목인데 파서 미스). id 는 공백·표기 불변.
            #   부분일치 금지 유지 — '자본과부채총계'(=ifrs-full_EquityAndLiabilities, 별 id) 오염 0
            #   (2026-07-06 부채비율 5.8% 사고 가드 계승).
            if aid == "ifrs-full_Assets" or acct == "자산총계":
                out["total_assets"] = amount
            elif aid == "ifrs-full_Liabilities" or acct == "부채총계":
                out["total_liabilities"] = amount
            elif aid == "ifrs-full_Equity" or acct == "자본총계":
                out["equity"] = amount
            elif aid == "ifrs-full_CurrentAssets" or acct == "유동자산":
                out["current_assets"] = amount
            elif aid == "ifrs-full_CurrentLiabilities" or acct == "유동부채":
                out["current_liabilities"] = amount
            elif aid == "ifrs-full_RetainedEarnings" or "이익잉여금" in acct:
                out["retained_earnings"] = amount
            elif aid == "ifrs-full_IssuedCapital" or acct == "자본금":
                out["capital"] = amount
            elif "투자부동산" in acct:
                out["investment_property"] = max(out["investment_property"], amount)
            elif acct.strip() == "유형자산" or item.get("account_id") == "ifrs-full_PropertyPlantAndEquipment":
                out["tangible_assets"] = max(out["tangible_assets"], amount)
            elif acct.strip() == "토지":
                out["land"] = max(out["land"], amount)
            elif acct.strip() in ("건물", "건물및구축물"):
                out["buildings"] = max(out["buildings"], amount)
        elif sj in ("IS", "CIS"):
            if acct in ("매출액", "영업수익") or "수익(매출액)" in acct:
                out["revenue"] = max(out["revenue"], amount)
            elif acct == "매출원가":
                out["cogs"] = amount
            elif acct == "매출총이익" or "매출총이익" in acct:
                out["gross_profit"] = amount
            elif acct in ("영업이익", "영업이익(손실)"):
                # 🚨 정확일치 필수 — 부분일치는 '계속영업이익(손실)'(세후, ≈순이익)에 걸려 영업이익을 덮어씀
                #   (2026-07-06 실증: 삼성 2018 op 58.9조 → 44.3조 오염, fin_series 전 연도 op==net 사고)
                out["operating_profit"] = amount
            elif "당기순이익" in acct:
                out["net_income"] = max(out["net_income"], amount)
            elif "법인세차감전" in acct or "법인세비용차감전" in acct:
                out["pretax_income"] = amount
            elif "판매비와관리비" in acct:
                out["sga"] = amount
            elif acct in ("금융수익", "금융이익"):
                out["finance_income"] = max(out["finance_income"], amount)
            elif acct in ("금융원가", "금융비용"):
                out["finance_cost"] = max(out["finance_cost"], amount)
            elif acct == "법인세비용":
                out["income_tax"] = amount
        elif sj == "CF":
            if "영업활동현금흐름" in acct or acct == "영업활동으로 인한 현금흐름":
                out["operating_cashflow"] = amount
            elif "투자활동현금흐름" in acct or acct == "투자활동으로 인한 현금흐름":
                out["investing_cashflow"] = amount
            elif "재무활동현금흐름" in acct or acct == "재무활동으로 인한 현금흐름":
                out["financing_cashflow"] = amount
    out["equity"] = out["total_assets"] - out["total_liabilities"]
    out["working_capital"] = out["current_assets"] - out["current_liabilities"]
    out["free_cashflow"] = out["operating_cashflow"] + out["investing_cashflow"]
    # 소유 부동산 장부가 = 토지+건물+투자부동산 (사용권자산=리스라 제외). 토지·건물 미분리 기업은
    # investment_property 만 반영(과소계상) → 광의 상한은 tangible_assets 로 별도 노출.
    out["real_estate_book"] = out["land"] + out["buildings"] + out["investment_property"]
    # gross_profit fallback — 매출 - 매출원가 (account_nm 직접 매칭 부재 시)
    if out["gross_profit"] == 0 and out["revenue"] > 0 and out["cogs"] > 0:
        out["gross_profit"] = out["revenue"] - out["cogs"]
    return out


def _compute_ratios(pl_bs: dict) -> dict:
    """PL/BS 항목 → 펀더멘털 비율 계산.

    2026-05-20 확장: roa / current_ratio / asset_turnover / gross_margin 추가.
    F-Score 단년 9/9 풀가동 + Δ 활성 (시계열 N 누적 후).
    """
    out = {
        "debt_ratio": None, "roe": None, "roa": None,
        "op_margin": None, "current_ratio": None, "asset_turnover": None,
        "gross_margin": None,
        # NAV 프록시(장부가 기반, 시가 아님) — 자산주/숨은부동산 스크리닝. 시총 대비는 다운스트림(시총 보유) 산출.
        "real_estate_to_equity": None, "real_estate_to_assets": None, "land_to_equity": None,
    }
    eq = pl_bs.get("equity", 0)
    ta = pl_bs.get("total_assets", 0)
    ni = pl_bs.get("net_income", 0)
    rev = pl_bs.get("revenue", 0)
    cur_a = pl_bs.get("current_assets", 0)
    cur_l = pl_bs.get("current_liabilities", 0)
    op = pl_bs.get("operating_profit", 0)
    gp = pl_bs.get("gross_profit", 0)

    if eq > 0:
        out["debt_ratio"] = round(pl_bs.get("total_liabilities", 0) / eq * 100, 2)
        if ni:
            out["roe"] = round(ni / eq * 100, 2)
    if ta > 0 and ni:
        out["roa"] = round(ni / ta * 100, 2)
    if ta > 0 and rev > 0:
        out["asset_turnover"] = round(rev / ta, 4)
    if rev > 0:
        out["op_margin"] = round(op / rev * 100, 2)
        if gp > 0:
            out["gross_margin"] = round(gp / rev * 100, 2)
    if cur_l > 0 and cur_a > 0:
        out["current_ratio"] = round(cur_a / cur_l, 4)
    # NAV 프록시 — 소유 부동산 장부가 대비 자본/자산. 토지 단독은 취득원가라 시가 갭이 가장 큼.
    re_book = pl_bs.get("real_estate_book", 0)
    land = pl_bs.get("land", 0)
    if re_book > 0:
        if eq > 0:
            out["real_estate_to_equity"] = round(re_book / eq * 100, 2)
        if ta > 0:
            out["real_estate_to_assets"] = round(re_book / ta * 100, 2)
    if land > 0 and eq > 0:
        out["land_to_equity"] = round(land / eq * 100, 2)
    return out


def _yf_fallback_for_ticker(ticker: str) -> dict:
    """yfinance .KS / .KQ — per/pbr/누락 필드 fallback.

    ticker = 6자리 KR 종목코드.
    """
    # 2026-05-18 fix — [[yfinance_safe.yf_ticker]] anti-bot
    from api.collectors.yfinance_safe import yf_ticker
    out = {"per": None, "pbr": None, "roe": None, "debt_ratio": None, "op_margin": None}
    for suffix in (".KS", ".KQ"):
        try:
            info = yf_ticker(f"{ticker}{suffix}").info or {}
            if not info:
                continue
            per = info.get("trailingPE") or info.get("forwardPE")
            if per:
                out["per"] = round(float(per), 2)
            pbr = info.get("priceToBook")
            if pbr:
                out["pbr"] = round(float(pbr), 2)
            roe = info.get("returnOnEquity")
            if roe is not None:
                out["roe"] = round(float(roe) * 100, 2)
            debt = info.get("debtToEquity")
            if debt is not None:
                out["debt_ratio"] = round(float(debt), 2)
            op = info.get("operatingMargins")
            if op is not None:
                out["op_margin"] = round(float(op) * 100, 2)
            return out
        except Exception:
            continue
    return out


@functools.lru_cache(maxsize=512)
def _fetch_fnltt_all_cached(corp_code: str, bsns_year: str, fs_div: str, reprt_code: str = "11011") -> str:
    """fnlttSinglAcntAll.json 응답 cache (2026-05-20 신설, fs_div 명시).

    fs_div = "CFS" (연결, 한국 상장사 표준) / "OFS" (개별).
    list_n CFS 213 / OFS 131 (005930 2024 audit). 매출원가/CF 섹션 포함.
    reprt_code = "11011" 연간(default) / "11013" 1Q / "11012" 반기 / "11014" 3Q
      — 분기 backfill(2026-06-27) 위해 인자화. 미지정 시 연간 = 기존 주간 batch 무변.

    2026-05-23 (W3 4/4): record_dart_call(status) 로 dart_metrics 누적.
    lru_cache hit 은 미집계 — 실호출만 측정 정합.
    """
    from api.config import DART_API_KEY
    from api.observability.dart_metrics import record_dart_call
    import requests
    url = "https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json"
    params = {
        "crtfc_key": DART_API_KEY, "corp_code": corp_code,
        "bsns_year": bsns_year, "reprt_code": reprt_code, "fs_div": fs_div,
    }
    try:
        resp = requests.get(url, params=params, timeout=(10, 30))
        resp.raise_for_status()
        text = resp.text
        try:
            status = json.loads(text).get("status", "")
        except Exception:
            status = ""
        record_dart_call(status)
        return text
    except Exception as e:
        record_dart_call("error")
        return json.dumps({"status": "error", "message": str(e), "list": []})


def _get_fnltt_all_data(corp_code: str, bsns_year: str, fs_div: str = "CFS", reprt_code: str = "11011") -> dict:
    return json.loads(_fetch_fnltt_all_cached(corp_code, bsns_year, fs_div, reprt_code))


def _fetch_one_dart_fundamentals(ticker: str, bsns_year: str, reprt_code: str = "11011") -> dict:
    """한 종목 펀더멘털 — DART 우선 (fnlttSinglAcntAll CFS → OFS fallback), yfinance fallback.

    2026-05-20 정정 (fs_div audit):
      이전 = fnlttSinglAcnt.json (단일계정, fs_div 미명시, DART default OFS).
      삼성 영업이익 12.36조 (OFS) ≠ 32.73조 (CFS, 표준).
      변경 = fnlttSinglAcntAll.json fs_div=CFS 우선, 0건 시 OFS fallback.
    """
    from api.collectors.dart_corp_code import get_corp_code

    base = {
        "per": None, "pbr": None, "roe": None, "roa": None,
        "debt_ratio": None, "op_margin": None,
        "current_ratio": None, "asset_turnover": None, "gross_margin": None,
        "working_capital": 0, "retained_earnings": 0, "total_assets": 0,
        "current_assets": 0, "current_liabilities": 0, "operating_profit": 0,
        "revenue": 0, "cogs": 0, "gross_profit": 0, "net_income": 0,
        "pretax_income": 0, "sga": 0, "finance_income": 0, "finance_cost": 0, "income_tax": 0,
        "investment_property": 0, "tangible_assets": 0, "land": 0, "buildings": 0, "real_estate_book": 0,
        "real_estate_to_equity": None, "real_estate_to_assets": None, "land_to_equity": None,
        "operating_cashflow": 0, "investing_cashflow": 0, "financing_cashflow": 0,
        "free_cashflow": 0,
        "reprt_code": reprt_code, "fs_div": None,
        "report_date": None, "source": "none",
    }

    corp_code = None
    try:
        corp_code = get_corp_code(ticker)
    except Exception:
        corp_code = None

    if corp_code:
        for fs_div in ("CFS", "OFS"):  # 연결 우선, fallback 개별
            try:
                data = _get_fnltt_all_data(corp_code, bsns_year, fs_div=fs_div, reprt_code=reprt_code)
                if data.get("status") != "000":
                    continue
                pl_bs = _extract_pl_bs_from_dart(data)
                if pl_bs.get("total_assets", 0) <= 0:
                    continue
                ratios = _compute_ratios(pl_bs)
                base.update(ratios)
                for k in ("working_capital", "retained_earnings", "total_assets",
                          "current_assets", "current_liabilities", "operating_profit",
                          "revenue", "cogs", "gross_profit", "net_income",
                          "pretax_income", "sga", "finance_income", "finance_cost", "income_tax",
                          "investment_property", "tangible_assets", "land", "buildings", "real_estate_book",
                          "operating_cashflow", "investing_cashflow",
                          "financing_cashflow", "free_cashflow"):
                    base[k] = pl_bs.get(k, 0)
                base["source"] = "DART"
                base["fs_div"] = fs_div
                base["report_date"] = bsns_year
                break
            except Exception:
                continue

    # yfinance fallback for any None field (특히 per/pbr — DART 가 가격 의존 비율 안 줌)
    needs_fallback = base["per"] is None or base["pbr"] is None
    needs_fallback = needs_fallback or any(base[k] is None for k in ("roe", "debt_ratio", "op_margin"))
    if needs_fallback:
        yf_data = _yf_fallback_for_ticker(ticker)
        for k, v in yf_data.items():
            if base.get(k) is None and v is not None:
                base[k] = v
        if base["source"] == "none" and any(yf_data[k] is not None for k in yf_data):
            base["source"] = "yfinance_fallback"
        elif base["source"] == "DART" and (base["per"] is not None or base["pbr"] is not None):
            base["source"] = "DART+yfinance"

    return base


def fetch_dart_fundamentals_batch(
    tickers: list[str],
    max_workers: int = DART_BATCH_MAX_WORKERS_DEFAULT,
    timeout_per_ticker: float = DART_PER_TICKER_TIMEOUT_S,
    bsns_year: Optional[str] = None,
    reprt_code: str = "11011",
) -> dict[str, dict]:
    """KR 종목 리스트의 펀더멘털 일괄 수집.

    Args:
        tickers: 6자리 KR 종목코드 리스트.
        max_workers: ThreadPool 동시성. 기본 10 (DART rate limit 안전 마진).
        bsns_year: 분기 연도. 미지정 시 직전 회계연도 자동 선택.

    Returns:
        {ticker: {per, pbr, roe, debt_ratio, op_margin, report_date, source}}
    """
    if not tickers:
        return {}

    if bsns_year is None:
        # KST 기준 직전 연도 (3월 사업보고서 기준 — 4월 이후엔 작년 보고서 안정)
        now = datetime.now(ZoneInfo("Asia/Seoul"))
        bsns_year = str(now.year - 1) if now.month <= 4 else str(now.year - 1)

    # batch 전체 deadline — 초과 시 raise 하지 않고 완료분(partial)만 반환.
    # (기존: TimeoutError 가 호출부로 전파 → 그 run 진행분 전부 손실 → 영원히 0 수렴.
    #  이제 부분진행을 저장 → 증분 빌더가 다음 run 에 이어받아 drip-fill 수렴.)
    batch_deadline_s = min(540.0, max(120.0, len(tickers) * 0.5))

    out: dict[str, dict] = {}
    ex = ThreadPoolExecutor(max_workers=max_workers)
    try:
        futures = {
            ex.submit(_fetch_one_dart_fundamentals, t, bsns_year, reprt_code): t
            for t in tickers
        }
        try:
            for fu in as_completed(futures, timeout=batch_deadline_s):
                tk = futures[fu]
                try:
                    out[tk] = fu.result(timeout=timeout_per_ticker)
                except (FutTimeout, Exception):
                    out[tk] = {
                        "per": None, "pbr": None, "roe": None,
                        "debt_ratio": None, "op_margin": None,
                        "report_date": None, "source": "error",
                    }
        except FutTimeout:
            sys.stderr.write(
                f"[dart_fundamentals] batch deadline {batch_deadline_s:.0f}s 초과 — "
                f"완료분 {len(out)}/{len(tickers)} 반환 (나머지 다음 run drip-fill)\n"
            )
    finally:
        # 펜딩 future 즉시 취소 — drain 으로 23분 매달리던 것 방지.
        ex.shutdown(wait=False, cancel_futures=True)
    return out
