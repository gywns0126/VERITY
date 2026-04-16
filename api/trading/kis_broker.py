"""
한국투자증권 OpenAPI 브로커 (실전 전용).

REST API 래퍼: 인증(OAuth), 현재가, 호가(10호가), 일봉/분봉 차트,
계좌 잔고 조회, 현금 주문(매수/매도), 주문 체결 조회.

환경변수 (api/config.py 에서 로드):
  KIS_APP_KEY, KIS_APP_SECRET, KIS_ACCOUNT_NO
  KIS_OPENAPI_BASE_URL  (https://openapi.koreainvestment.com:9443)
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))

_PROD_URL = "https://openapi.koreainvestment.com:9443"

# 토큰 파일 캐시 경로 — 하루에 1번만 발급받기 위해 디스크에 저장
# GitHub Actions: workspace 내 경로 우선, 로컬: ~/.cache 폴백
_TOKEN_CACHE_DIR = os.environ.get(
    "KIS_TOKEN_CACHE_DIR",
    os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")),
)
_TOKEN_CACHE_PATH = os.path.join(_TOKEN_CACHE_DIR, "verity_kis_token.json")


class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    MARKET = "00"
    LIMIT = "00"
    MARKET_OPEN = "01"
    MARKET_CLOSE = "02"
    AFTER_MARKET = "05"
    CONDITION_LIMIT = "06"


@dataclass
class OrderResult:
    success: bool
    order_id: Optional[str] = None
    message: str = ""
    filled_qty: int = 0
    filled_price: float = 0.0
    raw: Dict[str, Any] = field(default_factory=dict)


class KISBroker:
    """한국투자증권 OpenAPI REST 래퍼."""

    def __init__(self):
        self.app_key: str = os.environ.get("KIS_APP_KEY", "").strip().strip('"')
        self.app_secret: str = os.environ.get("KIS_APP_SECRET", "").strip().strip('"')
        raw_acct = os.environ.get("KIS_ACCOUNT_NO", "").strip().strip('"').replace("-", "")
        self.account_cano: str = raw_acct[:8] if len(raw_acct) >= 8 else raw_acct
        self.account_prdt: str = raw_acct[8:10] if len(raw_acct) >= 10 else "01"
        self.base_url: str = os.environ.get(
            "KIS_OPENAPI_BASE_URL", _PROD_URL
        ).strip().strip('"').rstrip("/")
        self._token: Optional[str] = None
        self._token_expires: Optional[datetime] = None
        self._issued_date: str = ""
        self._load_cached_token()

    def _load_cached_token(self) -> None:
        """디스크 캐시에서 토큰을 로드한다. 만료 전이면 그대로 사용, 만료 후라도 issued_date는 기억."""
        try:
            with open(_TOKEN_CACHE_PATH, "r", encoding="utf-8") as f:
                cached = json.load(f)
            token = cached.get("access_token", "")
            expires_str = cached.get("expires_at", "")
            app_key = cached.get("app_key", "")
            issued_date = cached.get("issued_date", "")
            if not (token and expires_str and app_key == self.app_key):
                return
            expires = datetime.fromisoformat(expires_str)
            self._issued_date = issued_date
            if datetime.now(KST) < expires:
                self._token = token
                self._token_expires = expires
                logger.info("KIS 토큰 캐시 적중 (만료: %s, 발급일: %s)", expires, issued_date)
            else:
                logger.info("KIS 캐시 토큰 만료됨 (발급일: %s) — 갱신 필요", issued_date)
        except (FileNotFoundError, KeyError, ValueError):
            pass
        except Exception as e:
            logger.debug("KIS 토큰 캐시 로드 오류: %s", e)

    def _save_cached_token(self) -> None:
        """발급된 토큰을 디스크에 저장 (권한 0600). issued_date 포함."""
        try:
            cache_dir = os.path.dirname(_TOKEN_CACHE_PATH)
            if cache_dir:
                os.makedirs(cache_dir, exist_ok=True)
            with open(_TOKEN_CACHE_PATH, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "access_token": self._token,
                        "expires_at": self._token_expires.isoformat() if self._token_expires else "",
                        "app_key": self.app_key,
                        "issued_date": self._issued_date,
                    },
                    f,
                )
            os.chmod(_TOKEN_CACHE_PATH, 0o600)
        except Exception as e:
            logger.debug("KIS 토큰 캐시 저장 오류: %s", e)

    @property
    def is_configured(self) -> bool:
        return bool(self.app_key and self.app_secret)

    @property
    def has_account(self) -> bool:
        return bool(self.account_cano and len(self.account_cano) == 8)

    @property
    def is_paper(self) -> bool:
        """모의투자 서버 여부 (실전: False, 모의: True)."""
        return _PROD_URL not in self.base_url

    def _tr_id(self, real_id: str) -> str:
        return real_id

    def _base_headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "text/plain",
            "charset": "UTF-8",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
        }

    def _auth_headers(self) -> Dict[str, str]:
        token = self._ensure_token()
        h = self._base_headers()
        h["authorization"] = f"Bearer {token}"
        return h

    def _ensure_token(self) -> str:
        now = datetime.now(KST)
        if self._token and self._token_expires and now < self._token_expires:
            return self._token
        return self.authenticate()

    def authenticate(self, force_refresh: bool = False) -> str:
        """OAuth 접근 토큰 발급 (유효기간 약 24시간).

        Args:
            force_refresh: True면 하루 1회 제한을 무시하고 강제 갱신 (00:00 KST 전용).

        KIS는 하루 1개 토큰만 발급 가능. issued_date로 중복 발급을 방어한다.
        """
        now = datetime.now(KST)
        today_str = now.strftime("%Y-%m-%d")

        if not force_refresh and self._token and self._token_expires and now < self._token_expires:
            return self._token

        if not force_refresh and self._issued_date == today_str:
            if self._token:
                logger.warning(
                    "KIS 토큰 만료 근접이나 오늘(%s) 이미 발급됨 — 기존 토큰 재사용",
                    today_str,
                )
                return self._token
            raise RuntimeError(
                f"KIS 토큰 만료, 오늘({today_str}) 이미 발급 완료 → 재발급 불가. "
                "다음 00:00 KST 자동 갱신 대기."
            )

        if not self.is_configured:
            raise RuntimeError("KIS_APP_KEY / KIS_APP_SECRET 미설정")

        url = f"{self.base_url}/oauth2/tokenP"
        body = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
        }
        resp = requests.post(url, json=body, headers=self._base_headers(), timeout=10)
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        expires_str = data.get("access_token_token_expired", "")
        if expires_str:
            self._token_expires = datetime.strptime(
                expires_str, "%Y-%m-%d %H:%M:%S"
            ).replace(tzinfo=KST)
        else:
            self._token_expires = now + timedelta(hours=20)
        self._issued_date = today_str
        logger.info(
            "KIS 토큰 신규 발급 완료 (만료: %s, 발급일: %s)",
            self._token_expires,
            self._issued_date,
        )
        self._save_cached_token()
        return self._token

    def _get(self, path: str, tr_id: str, params: Dict[str, str]) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        headers = self._auth_headers()
        headers["tr_id"] = self._tr_id(tr_id)
        headers["custtype"] = "P"
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, tr_id: str, body: Dict[str, str]) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        headers = self._auth_headers()
        headers["tr_id"] = self._tr_id(tr_id)
        headers["custtype"] = "P"
        resp = requests.post(url, headers=headers, json=body, timeout=10)
        resp.raise_for_status()
        return resp.json()

    # ──────────────────────────────────────────────
    # 시세 조회
    # ──────────────────────────────────────────────

    def get_current_price(self, ticker: str) -> Dict[str, Any]:
        """현재가 시세 조회. 반환: output dict (stck_prpr 등 50+ 필드)."""
        data = self._get(
            "/uapi/domestic-stock/v1/quotations/inquire-price",
            "FHKST01010100",
            {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": ticker},
        )
        if data.get("rt_cd") != "0":
            raise RuntimeError(f"KIS inquire-price 실패: {data.get('msg1', data)}")
        return data.get("output", {})

    def get_asking_price(self, ticker: str) -> Dict[str, Any]:
        """호가(10호가) + 예상 체결가 조회. 반환: {output1: 호가, output2: 예상체결}."""
        data = self._get(
            "/uapi/domestic-stock/v1/quotations/inquire-asking-price-exp-ccn",
            "FHKST01010200",
            {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": ticker},
        )
        if data.get("rt_cd") != "0":
            raise RuntimeError(f"KIS asking-price 실패: {data.get('msg1', data)}")
        return {"output1": data.get("output1", {}), "output2": data.get("output2", {})}

    def get_daily_chart(
        self, ticker: str, start_date: str, end_date: str, period: str = "D"
    ) -> List[Dict[str, Any]]:
        """일/주/월봉 차트. period: D/W/M. 날짜형식: YYYYMMDD."""
        data = self._get(
            "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice",
            "FHKST03010100",
            {
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": ticker,
                "FID_INPUT_DATE_1": start_date,
                "FID_INPUT_DATE_2": end_date,
                "FID_PERIOD_DIV_CODE": period,
                "FID_ORG_ADJ_PRC": "0",
            },
        )
        if data.get("rt_cd") != "0":
            raise RuntimeError(f"KIS daily-chart 실패: {data.get('msg1', data)}")
        return data.get("output2", [])

    def get_minute_chart(
        self, ticker: str, time_from: str = "090000", include_prev: str = "N"
    ) -> List[Dict[str, Any]]:
        """분봉 차트 (당일). time_from: HHMMSS."""
        data = self._get(
            "/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice",
            "FHKST03010200",
            {
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": ticker,
                "FID_INPUT_HOUR_1": time_from,
                "FID_PW_DATA_INCU_YN": include_prev,
                "FID_ETC_CLS_CODE": "",
            },
        )
        if data.get("rt_cd") != "0":
            raise RuntimeError(f"KIS minute-chart 실패: {data.get('msg1', data)}")
        return data.get("output2", [])

    # ──────────────────────────────────────────────
    # 계좌
    # ──────────────────────────────────────────────

    def get_balance(self) -> Dict[str, Any]:
        """계좌 잔고 조회. 반환: {holdings: [...], summary: {...}}."""
        if not self.has_account:
            raise RuntimeError("KIS_ACCOUNT_NO 미설정 (8+2자리)")
        data = self._get(
            "/uapi/domestic-stock/v1/trading/inquire-balance",
            "TTTC8434R",
            {
                "CANO": self.account_cano,
                "ACNT_PRDT_CD": self.account_prdt,
                "AFHR_FLPR_YN": "N",
                "INQR_DVSN": "02",
                "UNPR_DVSN": "01",
                "FUND_STTL_ICLD_YN": "N",
                "FNCG_AMT_AUTO_RDPT_YN": "N",
                "PRCS_DVSN": "00",
                "OFL_YN": "",
                "CTX_AREA_FK100": "",
                "CTX_AREA_NK100": "",
            },
        )
        if data.get("rt_cd") != "0":
            raise RuntimeError(f"KIS balance 실패: {data.get('msg1', data)}")
        holdings = data.get("output1", [])
        summary = data.get("output2", [{}])
        return {"holdings": holdings, "summary": summary[0] if summary else {}}

    # ──────────────────────────────────────────────
    # 주문
    # ──────────────────────────────────────────────

    def place_order(
        self,
        ticker: str,
        side: OrderSide,
        qty: int,
        price: int = 0,
        order_type: str = "00",
    ) -> OrderResult:
        """
        현금 주문 (매수/매도).
        order_type: "00" 지정가, "01" 시장가, "05" 장후시간외 등.
        price: 시장가 주문 시 0.
        """
        if not self.has_account:
            return OrderResult(success=False, message="KIS_ACCOUNT_NO 미설정")

        if side == OrderSide.BUY:
            tr_id = "TTTC0802U" if not self.is_paper else "VTTC0802U"
        else:
            tr_id = "TTTC0801U" if not self.is_paper else "VTTC0801U"

        body = {
            "CANO": self.account_cano,
            "ACNT_PRDT_CD": self.account_prdt,
            "PDNO": ticker,
            "ORD_DVSN": order_type,
            "ORD_QTY": str(qty),
            "ORD_UNPR": str(price),
        }

        try:
            data = self._post("/uapi/domestic-stock/v1/trading/order-cash", tr_id, body)
        except Exception as e:
            return OrderResult(success=False, message=str(e))

        ok = data.get("rt_cd") == "0"
        output = data.get("output", {})
        return OrderResult(
            success=ok,
            order_id=output.get("ODNO", output.get("KRX_FWDG_ORD_ORGNO", "")),
            message=data.get("msg1", ""),
            raw=output,
        )

    def get_order_history(self, start_date: str = "", end_date: str = "") -> List[Dict[str, Any]]:
        """주문 체결 내역 조회."""
        if not self.has_account:
            raise RuntimeError("KIS_ACCOUNT_NO 미설정")
        now = datetime.now(KST)
        if not start_date:
            start_date = now.strftime("%Y%m%d")
        if not end_date:
            end_date = now.strftime("%Y%m%d")

        data = self._get(
            "/uapi/domestic-stock/v1/trading/inquire-daily-ccld",
            "TTTC8001R",
            {
                "CANO": self.account_cano,
                "ACNT_PRDT_CD": self.account_prdt,
                "INQR_STRT_DT": start_date,
                "INQR_END_DT": end_date,
                "SLL_BUY_DVSN_CD": "00",
                "INQR_DVSN": "00",
                "PDNO": "",
                "CCLD_DVSN": "00",
                "ORD_GNO_BRNO": "",
                "ODNO": "",
                "INQR_DVSN_3": "00",
                "INQR_DVSN_1": "",
                "CTX_AREA_FK100": "",
                "CTX_AREA_NK100": "",
            },
        )
        if data.get("rt_cd") != "0":
            raise RuntimeError(f"KIS order-history 실패: {data.get('msg1', data)}")
        return data.get("output1", [])

    # ──────────────────────────────────────────────
    # 헬퍼: portfolio.json용 변환
    # ──────────────────────────────────────────────

    def build_orderbook_snapshot(self, ticker: str) -> Optional[Dict[str, Any]]:
        """StockDetailPanel이 쓸 수 있는 호가 스냅샷 dict."""
        try:
            raw = self.get_asking_price(ticker)
        except Exception as e:
            logger.warning("KIS 호가 조회 실패(%s): %s", ticker, e)
            return None

        o1 = raw["output1"]
        _int = lambda k: int(o1.get(k, "0") or "0")

        rows = []
        for i in range(10, 0, -1):
            ask_p = _int(f"askp{i}")
            ask_v = _int(f"askp_rsqn{i}")
            if ask_p > 0:
                rows.append({"price": ask_p, "ask_vol": ask_v, "bid_vol": None, "side": "ask"})

        current = _int("stck_prpr")
        rows.append({"price": current, "ask_vol": None, "bid_vol": None, "side": "current", "highlight": True})

        for i in range(1, 11):
            bid_p = _int(f"bidp{i}")
            bid_v = _int(f"bidp_rsqn{i}")
            if bid_p > 0:
                rows.append({"price": bid_p, "ask_vol": None, "bid_vol": bid_v, "side": "bid"})

        total_ask = _int("total_askp_rsqn")
        total_bid = _int("total_bidp_rsqn")

        return {
            "current_price": current,
            "rows": rows,
            "total_ask_vol": total_ask,
            "total_bid_vol": total_bid,
            "timestamp": datetime.now(KST).isoformat(),
        }

    def build_price_snapshot(self, ticker: str) -> Optional[Dict[str, Any]]:
        """현재가 + 기본 시세 정보 dict."""
        try:
            o = self.get_current_price(ticker)
        except Exception as e:
            logger.warning("KIS 현재가 조회 실패(%s): %s", ticker, e)
            return None

        _int = lambda k: int(o.get(k, "0") or "0")
        _float = lambda k: float(o.get(k, "0") or "0")

        return {
            "price": _int("stck_prpr"),
            "change_amount": _int("prdy_vrss"),
            "change_pct": _float("prdy_ctrt"),
            "volume": _int("acml_vol"),
            "trading_value": _int("acml_tr_pbmn"),
            "open": _int("stck_oprc"),
            "high": _int("stck_hgpr"),
            "low": _int("stck_lwpr"),
            "high_52w": _int("stck_dryc_hgpr") or _int("w52_hgpr"),
            "low_52w": _int("stck_dryc_lwpr") or _int("w52_lwpr"),
            "upper_limit": _int("stck_mxpr"),
            "lower_limit": _int("stck_llam"),
            "per": _float("per"),
            "pbr": _float("pbr"),
            "eps": _float("eps"),
            "market_cap": _int("hts_avls"),
            "source": "kis",
            "timestamp": datetime.now(KST).isoformat(),
        }

    def build_chart_data(self, ticker: str, days: int = 90) -> Optional[List[Dict[str, Any]]]:
        """일봉 차트 데이터 (OHLCV)."""
        now = datetime.now(KST)
        end = now.strftime("%Y%m%d")
        start = (now - timedelta(days=days)).strftime("%Y%m%d")
        try:
            raw = self.get_daily_chart(ticker, start, end)
        except Exception as e:
            logger.warning("KIS 일봉 조회 실패(%s): %s", ticker, e)
            return None

        candles = []
        for r in reversed(raw):
            candles.append({
                "date": r.get("stck_bsop_date", ""),
                "open": int(r.get("stck_oprc", 0) or 0),
                "high": int(r.get("stck_hgpr", 0) or 0),
                "low": int(r.get("stck_lwpr", 0) or 0),
                "close": int(r.get("stck_clpr", 0) or 0),
                "volume": int(r.get("acml_vol", 0) or 0),
            })
        return candles if candles else None

    # ──────────────────────────────────────────────
    # Brain 분석용 데이터 수집
    # ──────────────────────────────────────────────

    def get_investor_trend(self, ticker: str) -> Dict[str, Any]:
        """종목별 투자자(외인/기관/개인) 매매동향."""
        data = self._get(
            "/uapi/domestic-stock/v1/quotations/inquire-investor",
            "FHKST01010900",
            {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": ticker},
        )
        if data.get("rt_cd") != "0":
            raise RuntimeError(f"KIS investor 실패: {data.get('msg1', data)}")
        return data.get("output", [])

    def get_invest_opinion(self, ticker: str) -> List[Dict[str, Any]]:
        """종목 투자의견 (증권사 목표가/의견)."""
        data = self._get(
            "/uapi/domestic-stock/v1/quotations/invest-opinion",
            "FHKST663300C0",
            {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": ticker},
        )
        if data.get("rt_cd") != "0":
            raise RuntimeError(f"KIS invest-opinion 실패: {data.get('msg1', data)}")
        return data.get("output", [])

    def get_estimate_perform(self, ticker: str) -> Dict[str, Any]:
        """종목 추정실적."""
        data = self._get(
            "/uapi/domestic-stock/v1/quotations/estimate-perform",
            "HHKST668300C0",
            {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": ticker},
        )
        if data.get("rt_cd") != "0":
            raise RuntimeError(f"KIS estimate 실패: {data.get('msg1', data)}")
        return {"output1": data.get("output1", {}), "output2": data.get("output2", [])}

    def get_financial_ratio(self, ticker: str) -> List[Dict[str, Any]]:
        """재무비율 (수익성/안정성/성장성 종합)."""
        data = self._get(
            "/uapi/domestic-stock/v1/finance/financial-ratio",
            "FHKST66430300",
            {
                "FID_DIV_CLS_CODE": "0",
                "fid_cond_mrkt_div_code": "J",
                "fid_input_iscd": ticker,
            },
        )
        if data.get("rt_cd") != "0":
            raise RuntimeError(f"KIS financial-ratio 실패: {data.get('msg1', data)}")
        return data.get("output", [])

    def get_income_statement(self, ticker: str) -> List[Dict[str, Any]]:
        """손익계산서."""
        data = self._get(
            "/uapi/domestic-stock/v1/finance/income-statement",
            "FHKST66430200",
            {
                "FID_DIV_CLS_CODE": "0",
                "fid_cond_mrkt_div_code": "J",
                "fid_input_iscd": ticker,
            },
        )
        if data.get("rt_cd") != "0":
            raise RuntimeError(f"KIS income-statement 실패: {data.get('msg1', data)}")
        return data.get("output", [])

    def get_short_sale_daily(self, ticker: str) -> List[Dict[str, Any]]:
        """공매도 일별 추이."""
        data = self._get(
            "/uapi/domestic-stock/v1/quotations/daily-short-sale",
            "FHPST04830000",
            {
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": ticker,
                "FID_INPUT_DATE_1": "",
                "FID_INPUT_DATE_2": "",
            },
        )
        if data.get("rt_cd") != "0":
            raise RuntimeError(f"KIS short-sale 실패: {data.get('msg1', data)}")
        return data.get("output1", [])

    def get_credit_balance_daily(self, ticker: str) -> List[Dict[str, Any]]:
        """신용잔고 일별 추이."""
        data = self._get(
            "/uapi/domestic-stock/v1/quotations/daily-credit-balance",
            "FHPST04760000",
            {
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": ticker,
                "FID_INPUT_DATE_1": "",
                "FID_INPUT_DATE_2": "",
            },
        )
        if data.get("rt_cd") != "0":
            raise RuntimeError(f"KIS credit-balance 실패: {data.get('msg1', data)}")
        return data.get("output1", [])

    def get_program_trade(self, ticker: str) -> List[Dict[str, Any]]:
        """종목별 프로그램매매 추이 (일별)."""
        data = self._get(
            "/uapi/domestic-stock/v1/quotations/program-trade-by-stock-daily",
            "FHPPG04650201",
            {
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": ticker,
                "FID_INPUT_DATE_1": "",
                "FID_INPUT_DATE_2": "",
            },
        )
        if data.get("rt_cd") != "0":
            raise RuntimeError(f"KIS program-trade 실패: {data.get('msg1', data)}")
        return data.get("output1", [])

    # ──────────────────────────────────────────────
    # Brain용 통합 스냅샷 빌더
    # ──────────────────────────────────────────────

    def build_brain_snapshot(self, ticker: str) -> Dict[str, Any]:
        """종목별 Brain 분석에 필요한 모든 KIS 데이터를 한번에 수집."""
        result: Dict[str, Any] = {}

        try:
            inv_rows = self.get_investor_trend(ticker)
            if inv_rows:
                foreign_net = 0
                inst_net = 0
                for row in (inv_rows if isinstance(inv_rows, list) else [inv_rows]):
                    prsn = str(row.get("prsn_ntby_qty", "0") or "0")
                    frgn = str(row.get("frgn_ntby_qty", "0") or "0")
                    orgn = str(row.get("orgn_ntby_qty", "0") or "0")
                    try:
                        foreign_net = int(frgn.replace(",", ""))
                        inst_net = int(orgn.replace(",", ""))
                    except (ValueError, TypeError):
                        pass
                result["investor"] = {
                    "foreign_net": foreign_net,
                    "institution_net": inst_net,
                    "source": "kis",
                }
        except Exception as e:
            logger.debug("KIS investor(%s): %s", ticker, e)

        try:
            opinions = self.get_invest_opinion(ticker)
            if opinions:
                latest = opinions[0] if isinstance(opinions, list) else opinions
                result["invest_opinion"] = {
                    "opinion": latest.get("invt_opnn", ""),
                    "target_price": int(latest.get("stck_prpr", 0) or 0),
                    "analyst_firm": latest.get("mbcr_name", ""),
                    "date": latest.get("stck_bsop_date", ""),
                    "source": "kis",
                }
        except Exception as e:
            logger.debug("KIS opinion(%s): %s", ticker, e)

        try:
            est = self.get_estimate_perform(ticker)
            if est.get("output2"):
                rows = est["output2"]
                latest = rows[0] if rows else {}
                result["estimate"] = {
                    "est_revenue": latest.get("sals_ntin", ""),
                    "est_operating_profit": latest.get("bsop_prti", ""),
                    "est_net_income": latest.get("thtr_ntin", ""),
                    "period": latest.get("stac_yymm", ""),
                    "source": "kis",
                }
        except Exception as e:
            logger.debug("KIS estimate(%s): %s", ticker, e)

        try:
            ratios = self.get_financial_ratio(ticker)
            if ratios:
                latest = ratios[0] if isinstance(ratios, list) else ratios
                _f = lambda k: float(str(latest.get(k, "0") or "0").replace(",", "") or "0")
                result["financial_ratio"] = {
                    "roe": _f("roe_val"),
                    "roa": _f("bsop_prfi_inrt"),
                    "debt_ratio": _f("lblt_rate"),
                    "current_ratio": _f("crnt_rate"),
                    "operating_margin": _f("bsop_prfi_inrt"),
                    "period": latest.get("stac_yymm", ""),
                    "source": "kis",
                }
        except Exception as e:
            logger.debug("KIS ratio(%s): %s", ticker, e)

        try:
            shorts = self.get_short_sale_daily(ticker)
            if shorts:
                recent = shorts[:5]
                total_short = sum(int(r.get("ssts_cntg_qty", 0) or 0) for r in recent)
                total_vol = sum(int(r.get("acml_vol", 0) or 0) for r in recent)
                short_ratio = (total_short / total_vol * 100) if total_vol > 0 else 0
                result["short_sale"] = {
                    "avg_short_ratio_5d": round(short_ratio, 2),
                    "latest_short_qty": int(shorts[0].get("ssts_cntg_qty", 0) or 0),
                    "latest_short_amt": int(shorts[0].get("ssts_cntg_amt", 0) or 0),
                    "source": "kis",
                }
        except Exception as e:
            logger.debug("KIS short(%s): %s", ticker, e)

        try:
            credits = self.get_credit_balance_daily(ticker)
            if credits:
                latest = credits[0]
                result["credit_balance"] = {
                    "credit_balance_qty": int(latest.get("crdt_ldos_blnc_qty", 0) or 0),
                    "credit_rate": float(latest.get("crdt_rate", 0) or 0),
                    "source": "kis",
                }
        except Exception as e:
            logger.debug("KIS credit(%s): %s", ticker, e)

        try:
            pgm = self.get_program_trade(ticker)
            if pgm:
                recent = pgm[:3]
                net_buys = [int(r.get("ntby_qty", 0) or 0) for r in recent]
                result["program_trade"] = {
                    "net_buy_3d": sum(net_buys),
                    "latest_net_buy": net_buys[0] if net_buys else 0,
                    "source": "kis",
                }
        except Exception as e:
            logger.debug("KIS program(%s): %s", ticker, e)

        return result

    # ══════════════════════════════════════════════════
    #  국내 시장 전반 — 순위/업종/VI/뉴스
    # ══════════════════════════════════════════════════

    def get_volume_rank(self, market: str = "J", top_n: int = 30) -> List[Dict]:
        """거래량 순위."""
        data = self._get(
            "/uapi/domestic-stock/v1/quotations/volume-rank",
            "FHPST01710000",
            {
                "FID_COND_MRKT_DIV_CODE": market,
                "FID_COND_SCR_DIV_CODE": "20171",
                "FID_INPUT_ISCD": "0000",
                "FID_DIV_CLS_CODE": "0",
                "FID_BLNG_CLS_CODE": "0",
                "FID_TRGT_CLS_CODE": "111111111",
                "FID_TRGT_EXLS_CLS_CODE": "000000",
                "FID_INPUT_PRICE_1": "",
                "FID_INPUT_PRICE_2": "",
                "FID_VOL_CNT": "",
                "FID_INPUT_DATE_1": "",
            },
        )
        return (data.get("output", []) or [])[:top_n]

    def get_fluctuation_rank(self, sort: str = "0", top_n: int = 30) -> List[Dict]:
        """등락률 순위. sort: 0=상승, 1=하락."""
        data = self._get(
            "/uapi/domestic-stock/v1/ranking/fluctuation",
            "FHPST01700000",
            {
                "fid_cond_mrkt_div_code": "J",
                "fid_cond_scr_div_code": "20170",
                "fid_input_iscd": "0000",
                "fid_rank_sort_cls_code": sort,
                "fid_input_cnt_1": "0",
                "fid_prc_cls_code": "0",
                "fid_input_price_1": "",
                "fid_input_price_2": "",
                "fid_vol_cnt": "",
                "fid_trgt_cls_code": "0",
                "fid_trgt_exls_cls_code": "0",
                "fid_div_cls_code": "0",
                "fid_rsfl_rate1": "",
                "fid_rsfl_rate2": "",
            },
        )
        return (data.get("output", []) or [])[:top_n]

    def get_market_cap_rank(self, top_n: int = 30) -> List[Dict]:
        """시가총액 순위."""
        data = self._get(
            "/uapi/domestic-stock/v1/ranking/market-cap",
            "FHPST01740000",
            {
                "fid_cond_mrkt_div_code": "J",
                "fid_cond_scr_div_code": "20174",
                "fid_input_iscd": "0000",
                "fid_div_cls_code": "0",
                "fid_input_price_1": "",
                "fid_input_price_2": "",
                "fid_vol_cnt": "",
                "fid_input_date_1": "",
            },
        )
        return (data.get("output", []) or [])[:top_n]

    def get_volume_power_rank(self, top_n: int = 30) -> List[Dict]:
        """체결강도 상위 종목."""
        data = self._get(
            "/uapi/domestic-stock/v1/ranking/volume-power",
            "FHPST01680000",
            {
                "fid_cond_mrkt_div_code": "J",
                "fid_cond_scr_div_code": "20168",
                "fid_input_iscd": "0000",
                "fid_div_cls_code": "0",
                "fid_input_price_1": "",
                "fid_input_price_2": "",
                "fid_vol_cnt": "",
                "fid_input_date_1": "",
            },
        )
        return (data.get("output", []) or [])[:top_n]

    def get_dividend_rate_rank(self, top_n: int = 30) -> List[Dict]:
        """배당률 상위."""
        data = self._get(
            "/uapi/domestic-stock/v1/ranking/dividend-rate",
            "HHKDB13470100",
            {
                "fid_cond_mrkt_div_code": "J",
                "fid_cond_scr_div_code": "13470",
                "fid_input_iscd": "0000",
                "fid_div_cls_code": "0",
                "fid_input_price_1": "",
                "fid_input_price_2": "",
                "fid_vol_cnt": "",
                "fid_input_date_1": "",
            },
        )
        return (data.get("output", []) or [])[:top_n]

    def get_short_sale_rank(self, top_n: int = 30) -> List[Dict]:
        """공매도 상위 종목."""
        data = self._get(
            "/uapi/domestic-stock/v1/ranking/short-sale",
            "FHPST04820000",
            {
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_COND_SCR_DIV_CODE": "20482",
                "FID_INPUT_ISCD": "0000",
                "FID_INPUT_DATE_1": "",
                "FID_INPUT_DATE_2": "",
                "FID_INPUT_CNT_1": "",
            },
        )
        return (data.get("output1", data.get("output", [])) or [])[:top_n]

    def get_foreign_institution_total(self) -> List[Dict]:
        """외인·기관 매매종목 가집계."""
        data = self._get(
            "/uapi/domestic-stock/v1/quotations/foreign-institution-total",
            "FHPTJ04400000",
            {
                "FID_COND_MRKT_DIV_CODE": "V",
                "FID_COND_SCR_DIV_CODE": "16440",
                "FID_INPUT_ISCD": "0000",
                "FID_DIV_CLS_CODE": "0",
                "FID_RANK_SORT_CLS_CODE": "0",
                "FID_ETC_CLS_CODE": "",
                "FID_TRGT_CLS_CODE": "",
                "FID_TRGT_EXLS_CLS_CODE": "",
            },
        )
        return data.get("output", []) or []

    def get_index_price(self, index_cd: str = "0001") -> Dict[str, Any]:
        """업종 현재지수. index_cd: 0001=코스피, 1001=코스닥."""
        data = self._get(
            "/uapi/domestic-stock/v1/quotations/inquire-index-price",
            "FHPUP02100000",
            {"FID_COND_MRKT_DIV_CODE": "U", "FID_INPUT_ISCD": index_cd},
        )
        return data.get("output", {})

    def get_index_daily(self, index_cd: str = "0001", period: str = "D") -> List[Dict]:
        """업종 일자별 지수. index_cd: 0001=코스피, 1001=코스닥."""
        now = datetime.now(KST)
        data = self._get(
            "/uapi/domestic-stock/v1/quotations/inquire-index-daily-price",
            "FHPUP02120000",
            {
                "FID_COND_MRKT_DIV_CODE": "U",
                "FID_INPUT_ISCD": index_cd,
                "FID_INPUT_DATE_1": (now - timedelta(days=90)).strftime("%Y%m%d"),
                "FID_INPUT_DATE_2": now.strftime("%Y%m%d"),
                "FID_PERIOD_DIV_CODE": period,
            },
        )
        return data.get("output", []) or []

    def get_vi_status(self) -> List[Dict]:
        """VI (변동성완화장치) 현황."""
        data = self._get(
            "/uapi/domestic-stock/v1/quotations/inquire-vi-status",
            "FHPST01390000",
            {
                "FID_COND_MRKT_DIV_CODE": "V",
                "FID_INPUT_ISCD": "",
            },
        )
        return data.get("output", []) or []

    def get_news_title(self, ticker: str = "") -> List[Dict]:
        """종합 시황/공시 (제목)."""
        data = self._get(
            "/uapi/domestic-stock/v1/quotations/news-title",
            "FHKST01011800",
            {
                "FID_NEWS_OFER_ENTP_CODE": "0",
                "FID_COND_MRKT_CLS_CODE": "",
                "FID_INPUT_ISCD": ticker,
                "FID_TITL_CNTT": "",
                "FID_INPUT_DATE_1": "",
                "FID_INPUT_SRNO": "",
                "FID_COND_SCR_DIV_CODE": "11800",
            },
        )
        return data.get("output", []) or []

    def get_market_funds(self) -> Dict[str, Any]:
        """증시자금 종합 (고객예탁금, 미수금, 신용 등)."""
        data = self._get(
            "/uapi/domestic-stock/v1/quotations/mktfunds",
            "FHKST649100C0",
            {
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": "0000",
                "FID_INPUT_DATE_1": "",
                "FID_INPUT_DATE_2": "",
            },
        )
        return data.get("output", {})

    def get_credit_balance_rank(self, top_n: int = 20) -> List[Dict]:
        """신용잔고 상위."""
        data = self._get(
            "/uapi/domestic-stock/v1/ranking/credit-balance",
            "FHKST17010000",
            {
                "fid_cond_mrkt_div_code": "J",
                "fid_cond_scr_div_code": "11701",
                "fid_input_iscd": "0000",
                "fid_div_cls_code": "0",
                "fid_input_price_1": "",
                "fid_input_price_2": "",
                "fid_vol_cnt": "",
                "fid_input_date_1": "",
            },
        )
        return (data.get("output", []) or [])[:top_n]

    def get_near_new_highlow(self, cls: str = "0", top_n: int = 20) -> List[Dict]:
        """신고·신저 근접종목. cls: 0=52주신고, 1=52주신저."""
        data = self._get(
            "/uapi/domestic-stock/v1/ranking/near-new-highlow",
            "FHPST01870000",
            {
                "fid_cond_mrkt_div_code": "J",
                "fid_cond_scr_div_code": "20187",
                "fid_input_iscd": "0000",
                "fid_rank_sort_cls_code": cls,
                "fid_div_cls_code": "0",
                "fid_input_price_1": "",
                "fid_input_price_2": "",
                "fid_vol_cnt": "",
                "fid_input_date_1": "",
            },
        )
        return (data.get("output", []) or [])[:top_n]

    def get_finance_ratio_rank(self, top_n: int = 20) -> List[Dict]:
        """재무비율 순위 (전 종목 대상)."""
        data = self._get(
            "/uapi/domestic-stock/v1/ranking/finance-ratio",
            "FHPST01750000",
            {
                "fid_cond_mrkt_div_code": "J",
                "fid_cond_scr_div_code": "20175",
                "fid_input_iscd": "0000",
                "fid_div_cls_code": "0",
                "fid_input_price_1": "",
                "fid_input_price_2": "",
                "fid_vol_cnt": "",
                "fid_input_date_1": "",
            },
        )
        return (data.get("output", []) or [])[:top_n]

    # ── 국내 종목별 심층 ──

    def get_daily_trade_volume(self, ticker: str) -> List[Dict]:
        """종목별 일별 매수매도 체결량."""
        data = self._get(
            "/uapi/domestic-stock/v1/quotations/inquire-daily-trade-volume",
            "FHKST03010800",
            {
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": ticker,
                "FID_INPUT_DATE_1": "",
                "FID_INPUT_DATE_2": "",
                "FID_PERIOD_DIV_CODE": "D",
            },
        )
        return data.get("output", []) or []

    def get_price_distribution(self, ticker: str) -> Dict[str, Any]:
        """매물대/거래비중."""
        data = self._get(
            "/uapi/domestic-stock/v1/quotations/pbar-tratio",
            "FHPST01130000",
            {
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": ticker,
            },
        )
        return {"output1": data.get("output1", {}), "output2": data.get("output2", [])}

    def get_balance_sheet(self, ticker: str) -> List[Dict]:
        """대차대조표."""
        data = self._get(
            "/uapi/domestic-stock/v1/finance/balance-sheet",
            "FHKST66430100",
            {
                "FID_DIV_CLS_CODE": "0",
                "fid_cond_mrkt_div_code": "J",
                "fid_input_iscd": ticker,
            },
        )
        return data.get("output", []) or []

    def get_profit_ratio(self, ticker: str) -> List[Dict]:
        """수익성비율."""
        data = self._get(
            "/uapi/domestic-stock/v1/finance/profit-ratio",
            "FHKST66430400",
            {
                "FID_DIV_CLS_CODE": "0",
                "fid_cond_mrkt_div_code": "J",
                "fid_input_iscd": ticker,
            },
        )
        return data.get("output", []) or []

    def get_stability_ratio(self, ticker: str) -> List[Dict]:
        """안정성비율."""
        data = self._get(
            "/uapi/domestic-stock/v1/finance/stability-ratio",
            "FHKST66430600",
            {
                "FID_DIV_CLS_CODE": "0",
                "fid_cond_mrkt_div_code": "J",
                "fid_input_iscd": ticker,
            },
        )
        return data.get("output", []) or []

    def get_growth_ratio(self, ticker: str) -> List[Dict]:
        """성장성비율."""
        data = self._get(
            "/uapi/domestic-stock/v1/finance/growth-ratio",
            "FHKST66430800",
            {
                "FID_DIV_CLS_CODE": "0",
                "fid_cond_mrkt_div_code": "J",
                "fid_input_iscd": ticker,
            },
        )
        return data.get("output", []) or []

    def get_time_conclusion(self, ticker: str) -> List[Dict]:
        """당일 시간대별 체결."""
        data = self._get(
            "/uapi/domestic-stock/v1/quotations/inquire-time-itemconclusion",
            "FHPST01060000",
            {
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": ticker,
                "FID_INPUT_HOUR_1": "",
            },
        )
        return data.get("output", []) or []

    def build_conclusion_snapshot(self, ticker: str, top_n: int = 20) -> Optional[Dict[str, Any]]:
        """시간대별 체결 데이터를 프론트엔드용으로 변환."""
        try:
            rows = self.get_time_conclusion(ticker)
        except Exception as e:
            logger.warning("KIS 체결 조회 실패(%s): %s", ticker, e)
            return None
        if not rows:
            return None

        trades = []
        total_buy_vol = 0
        total_sell_vol = 0
        for r in rows[:top_n]:
            hour_raw = str(r.get("stck_cntg_hour", "") or "")
            price = int(r.get("stck_prpr", "0") or "0")
            change = int(r.get("prdy_vrss", "0") or "0")
            sign = str(r.get("prdy_vrss_sign", "3") or "3")
            vol = int(r.get("cntg_vol", "0") or "0")
            change_pct = float(r.get("prdy_ctrt", "0") or "0")
            # sign: 1=상한,2=상승,3=보합,4=하한,5=하락
            side = "buy" if sign in ("1", "2") else ("sell" if sign in ("4", "5") else "neutral")
            if side == "buy":
                total_buy_vol += vol
            elif side == "sell":
                total_sell_vol += vol

            time_fmt = f"{hour_raw[:2]}:{hour_raw[2:4]}:{hour_raw[4:6]}" if len(hour_raw) >= 6 else hour_raw
            trades.append({
                "time": time_fmt,
                "price": price,
                "change": change,
                "change_pct": change_pct,
                "volume": vol,
                "side": side,
            })

        strength = 0.0
        if total_sell_vol > 0:
            strength = round(total_buy_vol / total_sell_vol * 100, 1)
        elif total_buy_vol > 0:
            strength = 999.9

        return {
            "trades": trades,
            "strength_pct": strength,
            "total_buy_vol": total_buy_vol,
            "total_sell_vol": total_sell_vol,
            "timestamp": datetime.now(KST).isoformat(),
        }

    def get_invest_opinion_by_sec(self, ticker: str) -> List[Dict]:
        """증권사별 투자의견."""
        data = self._get(
            "/uapi/domestic-stock/v1/quotations/invest-opbysec",
            "FHKST663400C0",
            {
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": ticker,
                "FID_INPUT_DATE_1": "",
                "FID_INPUT_DATE_2": "",
            },
        )
        return data.get("output", []) or []

    def get_investor_daily(self, ticker: str) -> List[Dict]:
        """종목별 투자자매매동향 (일별)."""
        data = self._get(
            "/uapi/domestic-stock/v1/quotations/investor-trade-by-stock-daily",
            "FHPTJ04160001",
            {
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": ticker,
                "FID_INPUT_DATE_1": "",
                "FID_INPUT_DATE_2": "",
            },
        )
        return data.get("output", []) or []

    def get_ksdinfo_dividend(self, ticker: str = "") -> List[Dict]:
        """예탁원 배당일정."""
        data = self._get(
            "/uapi/domestic-stock/v1/ksdinfo/dividend",
            "HHKDB669102C0",
            {
                "HIGH_GB": "",
                "CTS_YN": "N",
                "F_DT": "",
                "T_DT": "",
                "SHT_CD": ticker,
            },
        )
        return data.get("output1", []) or []

    def get_ksdinfo_shareholder_meeting(self, ticker: str = "") -> List[Dict]:
        """예탁원 주주총회 일정."""
        data = self._get(
            "/uapi/domestic-stock/v1/ksdinfo/sharehld-meet",
            "HHKDB669111C0",
            {
                "HIGH_GB": "",
                "CTS_YN": "N",
                "F_DT": "",
                "T_DT": "",
                "SHT_CD": ticker,
            },
        )
        return data.get("output1", []) or []

    # ══════════════════════════════════════════════════
    #  해외주식 — 시세/호가/차트
    # ══════════════════════════════════════════════════

    # 거래소 코드: NAS(나스닥), NYS(뉴욕), AMS(아멕스),
    #   HKS(홍콩), SHS(상해), SZS(심천), TSE(도쿄), HNX(하노이), HSX(호치민)

    _EXCD_TO_EXCG = {
        "NAS": "NASD", "NYS": "NYSE", "AMS": "AMEX",
        "HKS": "SEHK", "SHS": "SHAA", "SZS": "SZAA",
        "TSE": "TKSE", "HNX": "HASE", "HSX": "VNSE",
    }

    def overseas_price(self, excd: str, ticker: str) -> Dict[str, Any]:
        """해외주식 현재체결가."""
        data = self._get(
            "/uapi/overseas-price/v1/quotations/price",
            "HHDFS00000300",
            {"AUTH": "", "EXCD": excd, "SYMB": ticker},
        )
        return data.get("output", {})

    def overseas_price_detail(self, excd: str, ticker: str) -> Dict[str, Any]:
        """해외주식 현재가 상세."""
        data = self._get(
            "/uapi/overseas-price/v1/quotations/price-detail",
            "HHDFS76200200",
            {"AUTH": "", "EXCD": excd, "SYMB": ticker},
        )
        return data.get("output", {})

    def overseas_asking_price(self, excd: str, ticker: str) -> Dict[str, Any]:
        """해외주식 호가."""
        data = self._get(
            "/uapi/overseas-price/v1/quotations/inquire-asking-price",
            "HHDFS76200100",
            {"AUTH": "", "EXCD": excd, "SYMB": ticker},
        )
        return data.get("output", {})

    def overseas_daily_price(self, excd: str, ticker: str, period: str = "D",
                             count: str = "120") -> List[Dict]:
        """해외주식 일별 시세."""
        data = self._get(
            "/uapi/overseas-price/v1/quotations/dailyprice",
            "HHDFS76240000",
            {
                "AUTH": "", "EXCD": excd, "SYMB": ticker,
                "GUBN": "0", "BYMD": "", "MODP": "0", "KEYB": "",
            },
        )
        return data.get("output2", data.get("output", [])) or []

    def overseas_daily_chart(self, excd: str, ticker: str,
                             start: str = "", end: str = "",
                             period: str = "D") -> List[Dict]:
        """해외주식 기간별 시세 (일/주/월/년)."""
        now = datetime.now(KST)
        if not end:
            end = now.strftime("%Y%m%d")
        if not start:
            start = (now - timedelta(days=120)).strftime("%Y%m%d")
        prd_map = {"D": "0", "W": "1", "M": "2"}
        data = self._get(
            "/uapi/overseas-price/v1/quotations/inquire-daily-chartprice",
            "FHKST03030100",
            {
                "FID_COND_MRKT_DIV_CODE": "N",
                "FID_INPUT_ISCD": f"{excd}{ticker}" if len(ticker) < 8 else ticker,
                "FID_INPUT_DATE_1": start,
                "FID_INPUT_DATE_2": end,
                "FID_PERIOD_DIV_CODE": prd_map.get(period, "0"),
            },
        )
        return data.get("output2", []) or []

    def overseas_minute_chart(self, excd: str, ticker: str,
                              nmin: str = "30", keyb: str = "") -> List[Dict]:
        """해외주식 분봉."""
        data = self._get(
            "/uapi/overseas-price/v1/quotations/inquire-time-itemchartprice",
            "HHDFS76950200",
            {
                "AUTH": "", "EXCD": excd, "SYMB": ticker,
                "NMIN": nmin, "PINC": "0",
                "NEXT": "", "NREC": "120", "FILL": "",
                "KEYB": keyb,
            },
        )
        return data.get("output2", []) or []

    def overseas_ccnl(self, excd: str, ticker: str) -> List[Dict]:
        """해외주식 체결 추이."""
        data = self._get(
            "/uapi/overseas-price/v1/quotations/inquire-ccnl",
            "HHDFS76200300",
            {"AUTH": "", "EXCD": excd, "SYMB": ticker},
        )
        return data.get("output", []) or []

    # ── 해외주식 순위/분석 ──

    def overseas_volume_rank(self, excd: str = "NAS", top_n: int = 30) -> List[Dict]:
        """해외주식 거래량 순위."""
        data = self._get(
            "/uapi/overseas-stock/v1/ranking/trade-vol",
            "HHDFS76310010",
            {"AUTH": "", "EXCD": excd, "GUBN": "0", "KEYB": ""},
        )
        return (data.get("output", []) or [])[:top_n]

    def overseas_updown_rank(self, excd: str = "NAS", sort: str = "0",
                             top_n: int = 30) -> List[Dict]:
        """해외주식 등락률 순위. sort: 0=상승, 1=하락."""
        data = self._get(
            "/uapi/overseas-stock/v1/ranking/updown-rate",
            "HHDFS76290000",
            {"AUTH": "", "EXCD": excd, "GUBN": sort, "KEYB": ""},
        )
        return (data.get("output", []) or [])[:top_n]

    def overseas_market_cap_rank(self, excd: str = "NAS", top_n: int = 30) -> List[Dict]:
        """해외주식 시가총액 순위."""
        data = self._get(
            "/uapi/overseas-stock/v1/ranking/market-cap",
            "HHDFS76350100",
            {"AUTH": "", "EXCD": excd, "GUBN": "0", "KEYB": ""},
        )
        return (data.get("output", []) or [])[:top_n]

    def overseas_price_fluct(self, excd: str = "NAS", sort: str = "0",
                             top_n: int = 30) -> List[Dict]:
        """해외주식 가격 급등/급락. sort: 0=급등, 1=급락."""
        data = self._get(
            "/uapi/overseas-stock/v1/ranking/price-fluct",
            "HHDFS76260000",
            {"AUTH": "", "EXCD": excd, "GUBN": sort, "KEYB": ""},
        )
        return (data.get("output", []) or [])[:top_n]

    def overseas_volume_surge(self, excd: str = "NAS", top_n: int = 30) -> List[Dict]:
        """해외주식 거래량 급증."""
        data = self._get(
            "/uapi/overseas-stock/v1/ranking/volume-surge",
            "HHDFS76270000",
            {"AUTH": "", "EXCD": excd, "GUBN": "0", "KEYB": ""},
        )
        return (data.get("output", []) or [])[:top_n]

    def overseas_volume_power_rank(self, excd: str = "NAS", top_n: int = 30) -> List[Dict]:
        """해외주식 체결강도 순위."""
        data = self._get(
            "/uapi/overseas-stock/v1/ranking/volume-power",
            "HHDFS76280000",
            {"AUTH": "", "EXCD": excd, "GUBN": "0", "KEYB": ""},
        )
        return (data.get("output", []) or [])[:top_n]

    def overseas_trade_amount_rank(self, excd: str = "NAS", top_n: int = 30) -> List[Dict]:
        """해외주식 거래대금 순위."""
        data = self._get(
            "/uapi/overseas-stock/v1/ranking/trade-pbmn",
            "HHDFS76320010",
            {"AUTH": "", "EXCD": excd, "GUBN": "0", "KEYB": ""},
        )
        return (data.get("output", []) or [])[:top_n]

    def overseas_new_highlow(self, excd: str = "NAS", cls: str = "0",
                             top_n: int = 30) -> List[Dict]:
        """해외주식 신고/신저가. cls: 0=신고가, 1=신저가."""
        data = self._get(
            "/uapi/overseas-stock/v1/ranking/new-highlow",
            "HHDFS76300000",
            {"AUTH": "", "EXCD": excd, "GUBN": cls, "KEYB": ""},
        )
        return (data.get("output", []) or [])[:top_n]

    def overseas_trade_growth(self, excd: str = "NAS", top_n: int = 30) -> List[Dict]:
        """해외주식 거래증가율 순위."""
        data = self._get(
            "/uapi/overseas-stock/v1/ranking/trade-growth",
            "HHDFS76330000",
            {"AUTH": "", "EXCD": excd, "GUBN": "0", "KEYB": ""},
        )
        return (data.get("output", []) or [])[:top_n]

    # ── 해외 뉴스 ──

    def overseas_news(self, top_n: int = 30) -> List[Dict]:
        """해외뉴스 종합 (제목)."""
        data = self._get(
            "/uapi/overseas-price/v1/quotations/news-title",
            "HHPSTH60100C1",
            {
                "FID_NEWS_OFER_ENTP_CODE": "0",
                "FID_COND_MRKT_CLS_CODE": "",
                "FID_INPUT_ISCD": "",
                "FID_TITL_CNTT": "",
                "FID_INPUT_DATE_1": "",
                "FID_INPUT_SRNO": "",
                "FID_COND_SCR_DIV_CODE": "21601",
            },
        )
        return (data.get("output", []) or [])[:top_n]

    def overseas_breaking_news(self, top_n: int = 20) -> List[Dict]:
        """해외속보 (제목)."""
        data = self._get(
            "/uapi/overseas-price/v1/quotations/brknews-title",
            "FHKST01011801",
            {
                "FID_NEWS_OFER_ENTP_CODE": "0",
                "FID_COND_MRKT_CLS_CODE": "",
                "FID_INPUT_ISCD": "",
                "FID_TITL_CNTT": "",
                "FID_INPUT_DATE_1": "",
                "FID_INPUT_SRNO": "",
                "FID_COND_SCR_DIV_CODE": "11801",
            },
        )
        return (data.get("output", []) or [])[:top_n]

    def overseas_country_holiday(self) -> List[Dict]:
        """국가별 시장 휴장일."""
        data = self._get(
            "/uapi/overseas-stock/v1/quotations/countries-holiday",
            "CTOS5011R",
            {
                "TRAD_DT": datetime.now(KST).strftime("%Y%m%d"),
                "CTX_AREA_NK": "",
                "CTX_AREA_FK": "",
            },
        )
        return data.get("output", []) or []

    # ── 해외주식 주문/계좌 ──

    _US_BUY_TR = "TTTT1002U"
    _US_SELL_TR = "TTTT1006U"
    _OVERSEAS_EXCG_MAP = {
        "NAS": "NASD", "NYS": "NYSE", "AMS": "AMEX",
        "HKS": "SEHK", "SHS": "SHAA", "SZS": "SZAA",
        "TSE": "TKSE", "HNX": "HASE", "HSX": "VNSE",
    }
    _OVERSEAS_TR_MAP = {
        "NASD": {"buy": "TTTT1002U", "sell": "TTTT1006U"},
        "NYSE": {"buy": "TTTT1002U", "sell": "TTTT1006U"},
        "AMEX": {"buy": "TTTT1002U", "sell": "TTTT1006U"},
        "SEHK": {"buy": "TTTS1002U", "sell": "TTTS1001U"},
        "SHAA": {"buy": "TTTS0202U", "sell": "TTTS1005U"},
        "SZAA": {"buy": "TTTS0305U", "sell": "TTTS0304U"},
        "TKSE": {"buy": "TTTS0308U", "sell": "TTTS0307U"},
        "HASE": {"buy": "TTTS0311U", "sell": "TTTS0310U"},
        "VNSE": {"buy": "TTTS0311U", "sell": "TTTS0310U"},
    }

    def overseas_order(self, excd: str, ticker: str, side: str,
                       qty: int, price: float = 0, order_type: str = "00") -> OrderResult:
        """해외주식 매수/매도. side: 'buy'/'sell'. order_type: '00'=지정가, '01'=시장가(미국만)."""
        if not self.has_account:
            raise RuntimeError("KIS_ACCOUNT_NO 미설정")
        excg = self._OVERSEAS_EXCG_MAP.get(excd, excd)
        tr_map = self._OVERSEAS_TR_MAP.get(excg)
        if not tr_map:
            raise ValueError(f"미지원 거래소: {excd}")
        tr_id = tr_map[side]
        body = {
            "CANO": self.account_cano,
            "ACNT_PRDT_CD": self.account_prdt,
            "OVRS_EXCG_CD": excg,
            "PDNO": ticker,
            "ORD_QTY": str(qty),
            "OVRS_ORD_UNPR": f"{price:.2f}" if price else "0",
            "SLL_TYPE": "00",
            "ORD_SVR_DVSN_CD": "0",
            "ORD_DVSN": order_type,
        }
        try:
            data = self._post("/uapi/overseas-stock/v1/trading/order", tr_id, body)
        except Exception as e:
            return OrderResult(success=False, message=str(e))
        ok = data.get("rt_cd") == "0"
        output = data.get("output", {})
        return OrderResult(
            success=ok,
            order_id=output.get("ODNO", output.get("KRX_FWDG_ORD_ORGNO", "")),
            message=data.get("msg1", ""),
            raw=output,
        )

    def overseas_balance(self) -> List[Dict]:
        """해외주식 잔고 조회."""
        if not self.has_account:
            raise RuntimeError("KIS_ACCOUNT_NO 미설정")
        data = self._get(
            "/uapi/overseas-stock/v1/trading/inquire-balance",
            "TTTS3012R",
            {
                "CANO": self.account_cano,
                "ACNT_PRDT_CD": self.account_prdt,
                "OVRS_EXCG_CD": "NASD",
                "TR_CRCY_CD": "USD",
                "CTX_AREA_FK200": "",
                "CTX_AREA_NK200": "",
            },
        )
        return data.get("output1", []) or []

    def overseas_order_history(self, start_date: str = "", end_date: str = "") -> List[Dict]:
        """해외주식 체결 내역."""
        if not self.has_account:
            raise RuntimeError("KIS_ACCOUNT_NO 미설정")
        now = datetime.now(KST)
        if not start_date:
            start_date = (now - timedelta(days=7)).strftime("%Y%m%d")
        if not end_date:
            end_date = now.strftime("%Y%m%d")
        data = self._get(
            "/uapi/overseas-stock/v1/trading/inquire-ccnl",
            "TTTS3035R",
            {
                "CANO": self.account_cano,
                "ACNT_PRDT_CD": self.account_prdt,
                "PDNO": "",
                "ORD_STRT_DT": start_date,
                "ORD_END_DT": end_date,
                "SLL_BUY_DVSN": "00",
                "CCLD_NCCS_DVSN": "00",
                "OVRS_EXCG_CD": "",
                "SORT_SQN": "DS",
                "ORD_DT": "",
                "ORD_GNO_BRNO": "",
                "ODNO": "",
                "CTX_AREA_NK200": "",
                "CTX_AREA_FK200": "",
            },
        )
        return data.get("output", []) or []

    def overseas_psamount(self, excd: str = "NASD", ticker: str = "") -> Dict[str, Any]:
        """해외주식 매수가능금액 조회."""
        if not self.has_account:
            raise RuntimeError("KIS_ACCOUNT_NO 미설정")
        data = self._get(
            "/uapi/overseas-stock/v1/trading/inquire-psamount",
            "TTTS3007R",
            {
                "CANO": self.account_cano,
                "ACNT_PRDT_CD": self.account_prdt,
                "OVRS_EXCG_CD": excd,
                "OVRS_ORD_UNPR": "0",
                "ITEM_CD": ticker,
            },
        )
        return data.get("output", {})

    # ── 해외주식 Brain 스냅샷 ──

    def build_overseas_brain_snapshot(self, excd: str, ticker: str) -> Dict[str, Any]:
        """해외 종목 Brain 분석용 데이터 일괄 수집."""
        result: Dict[str, Any] = {}
        try:
            p = self.overseas_price_detail(excd, ticker)
            if p:
                _f = lambda k: float(str(p.get(k, "0") or "0").replace(",", "") or "0")
                result["price"] = {
                    "current": _f("last"),
                    "change": _f("diff"),
                    "change_pct": _f("rate"),
                    "volume": int(_f("tvol")),
                    "amount": _f("tamt"),
                    "high_52w": _f("h52p"),
                    "low_52w": _f("l52p"),
                    "per": _f("perx"),
                    "pbr": _f("pbrx"),
                    "eps": _f("epsx"),
                    "market_cap": _f("tomv"),
                    "source": "kis",
                }
        except Exception as e:
            logger.debug("KIS overseas price(%s/%s): %s", excd, ticker, e)
        return result

    # ── 시장전반 통합 빌더 ──

    def build_market_overview(self) -> Dict[str, Any]:
        """국내 시장 전반 데이터 일괄 수집 (순위, 업종, VI 등)."""
        result: Dict[str, Any] = {}
        try:
            result["kospi"] = self.get_index_price("0001")
        except Exception as e:
            logger.debug("KIS kospi: %s", e)
        try:
            result["kosdaq"] = self.get_index_price("1001")
        except Exception as e:
            logger.debug("KIS kosdaq: %s", e)
        try:
            result["volume_rank"] = self.get_volume_rank(top_n=20)
        except Exception as e:
            logger.debug("KIS vol rank: %s", e)
        try:
            result["fluctuation_up"] = self.get_fluctuation_rank(sort="0", top_n=15)
        except Exception as e:
            logger.debug("KIS fluct up: %s", e)
        try:
            result["fluctuation_down"] = self.get_fluctuation_rank(sort="1", top_n=15)
        except Exception as e:
            logger.debug("KIS fluct down: %s", e)
        try:
            result["foreign_institution"] = self.get_foreign_institution_total()[:20]
        except Exception as e:
            logger.debug("KIS foreign: %s", e)
        try:
            result["short_sale_rank"] = self.get_short_sale_rank(top_n=15)
        except Exception as e:
            logger.debug("KIS short rank: %s", e)
        try:
            result["vi_status"] = self.get_vi_status()[:10]
        except Exception as e:
            logger.debug("KIS vi: %s", e)
        try:
            result["market_funds"] = self.get_market_funds()
        except Exception as e:
            logger.debug("KIS mktfunds: %s", e)
        try:
            result["news"] = self.get_news_title()[:15]
        except Exception as e:
            logger.debug("KIS news: %s", e)
        result["timestamp"] = datetime.now(KST).isoformat()
        return result

    def build_overseas_market_overview(self, exchanges: List[str] = None) -> Dict[str, Any]:
        """해외 시장 전반 데이터 일괄 수집."""
        if exchanges is None:
            exchanges = ["NAS", "NYS"]
        result: Dict[str, Any] = {}
        for excd in exchanges:
            mkt: Dict[str, Any] = {}
            try:
                mkt["volume_rank"] = self.overseas_volume_rank(excd, top_n=15)
            except Exception as e:
                logger.debug("KIS overseas vol %s: %s", excd, e)
            try:
                mkt["updown_rank"] = self.overseas_updown_rank(excd, sort="0", top_n=15)
            except Exception as e:
                logger.debug("KIS overseas updown %s: %s", excd, e)
            try:
                mkt["price_fluct"] = self.overseas_price_fluct(excd, sort="0", top_n=10)
            except Exception as e:
                logger.debug("KIS overseas fluct %s: %s", excd, e)
            try:
                mkt["volume_surge"] = self.overseas_volume_surge(excd, top_n=10)
            except Exception as e:
                logger.debug("KIS overseas surge %s: %s", excd, e)
            try:
                mkt["market_cap"] = self.overseas_market_cap_rank(excd, top_n=15)
            except Exception as e:
                logger.debug("KIS overseas cap %s: %s", excd, e)
            result[excd] = mkt
        try:
            result["news"] = self.overseas_news(top_n=15)
        except Exception as e:
            logger.debug("KIS overseas news: %s", e)
        try:
            result["breaking"] = self.overseas_breaking_news(top_n=10)
        except Exception as e:
            logger.debug("KIS overseas breaking: %s", e)
        result["timestamp"] = datetime.now(KST).isoformat()
        return result
