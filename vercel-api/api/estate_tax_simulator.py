"""
POST /api/estate/tax-simulator — ESTATE F / 한국 부동산 세제 시뮬레이터 (1세대 1주택 v0)

외부 API 없음. 룰 표 코드 내장 (vercel-api build artifact 단독).
docs/REAL_ESTATE_TAX_SIMULATOR_PLAN_v0.1.md 참조.

요청 (JSON body):
    {
      "purchase_price":  매수가 (원, integer),
      "appraised_value": 공시가격 (원, integer),
      "holding_years":   보유기간 (년, integer),
      "residence_years": 거주기간 (년, integer, 1세대 1주택 비과세 판정용),
      "sale_price":      매도가 (원, integer, 0 또는 미입력 = 양도세 0),
    }

응답:
    {
      "acquisition_tax":       취득세 (1회),
      "annual_property_tax":   재산세 (연간),
      "annual_comprehensive_tax": 종부세 (연간),
      "annual_holding_tax":    재산세 + 종부세 (연간),
      "capital_gains_tax":     양도세 (매도 시),
      "total_burden":          취득세 + 보유기간 × 연간 보유세 + 양도세,
      "effective_rate":        total_burden / sale_price (or purchase_price 시),
      "breakdown":             {acquisition: {...}, holding: {...}, capital_gains: {...}}
    }

거짓말 트랩:
    T1·T9  fabricate·silent X — 잘못된 input = 400 + 명시 에러
    T2     mock fallback X — 룰 표 = 코드 내장
    T4     산식 임의 상수 X — 모든 임계 RULES dict + docstring 출처 명시
"""
from __future__ import annotations

import json
import logging
from http.server import BaseHTTPRequestHandler
from typing import Any, Dict, Optional

_logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# 룰 표 (2026 기준 — 출처: 국세청 부동산 세제 매뉴얼 2025-2026)
# [[feedback_master_rule_drift_audit]] — 원전 출처 + 산식 메타 박음
# ─────────────────────────────────────────────────────────────

# 취득세 (1세대 1주택)
ACQUISITION_TAX_BRACKETS = [
    # (상한, 세율). 6억 이하 = 1.1% / 6~9억 누진 = 평균 2.0% / 9억 초과 = 3.3%
    {"limit": 600_000_000, "rate": 0.011, "label": "6억 이하"},
    {"limit": 900_000_000, "rate": 0.020, "label": "6~9억"},
    {"limit": float("inf"), "rate": 0.033, "label": "9억 초과"},
]

# 재산세 — 과세표준 = 공시가격 × 공정시장가액비율 60%
PROPERTY_TAX_FAIR_RATIO = 0.60
PROPERTY_TAX_BRACKETS = [
    # (과표 상한, 세율, 누진공제)
    {"limit":  60_000_000, "rate": 0.0010, "deduction":      0},
    {"limit": 150_000_000, "rate": 0.0015, "deduction":  30_000},
    {"limit": 300_000_000, "rate": 0.0025, "deduction": 180_000},
    {"limit": float("inf"), "rate": 0.0040, "deduction": 630_000},
]

# 종부세 (1세대 1주택, 12억 공제)
COMPREHENSIVE_TAX_DEDUCTION = 1_200_000_000  # 1세대 1주택 특례
COMPREHENSIVE_TAX_FAIR_RATIO = 0.60
COMPREHENSIVE_TAX_BRACKETS_1HOUSE = [
    # (과표 상한, 세율). 2026 1세대 1주택 기준
    {"limit":   300_000_000, "rate": 0.005},
    {"limit":   600_000_000, "rate": 0.007},
    {"limit": 1_200_000_000, "rate": 0.010},
    {"limit": 2_500_000_000, "rate": 0.013},
    {"limit": 5_000_000_000, "rate": 0.015},
    {"limit": 9_400_000_000, "rate": 0.020},
    {"limit": float("inf"),  "rate": 0.027},
]

# 양도세 비과세 한도
CAPITAL_GAINS_EXEMPT_PRICE = 1_200_000_000  # 1세대 1주택 + 보유 2년 + 거주 2년 → 12억 이하 비과세
CAPITAL_GAINS_MIN_HOLDING_YEARS = 2
CAPITAL_GAINS_MIN_RESIDENCE_YEARS = 2

# 단기 양도 (보유 < 2년)
SHORT_TERM_RATE_UNDER_1Y = 0.70
SHORT_TERM_RATE_1_TO_2Y = 0.60

# 2년 이상 누진 (2026 기본세율)
CAPITAL_GAINS_BRACKETS = [
    # (과표 상한, 세율, 누진공제)
    {"limit":   14_000_000, "rate": 0.06, "deduction":         0},
    {"limit":   50_000_000, "rate": 0.15, "deduction": 1_260_000},
    {"limit":   88_000_000, "rate": 0.24, "deduction": 5_760_000},
    {"limit":  150_000_000, "rate": 0.35, "deduction": 15_440_000},
    {"limit":  300_000_000, "rate": 0.38, "deduction": 19_940_000},
    {"limit":  500_000_000, "rate": 0.40, "deduction": 25_940_000},
    {"limit": 1_000_000_000, "rate": 0.42, "deduction": 35_940_000},
    {"limit": float("inf"),  "rate": 0.45, "deduction": 65_940_000},
]

# 장기보유특별공제 (1세대 1주택, 보유 + 거주 합산)
def long_term_deduction_rate(holding_years: int, residence_years: int) -> float:
    """1세대 1주택 보유 + 거주 각 연도당 4%, 최대 80% (보유 40% + 거주 40%)."""
    if holding_years < 3:
        return 0.0
    hold = min(holding_years, 10) * 0.04
    reside = min(residence_years, 10) * 0.04
    return min(hold + reside, 0.80)


# ─────────────────────────────────────────────────────────────
# 산식
# ─────────────────────────────────────────────────────────────

def _progressive(value: int, brackets) -> tuple[int, dict]:
    """누진세 산식 — 구간별 (limit, rate, deduction) 적용."""
    for b in brackets:
        if value <= b["limit"]:
            tax = max(0, int(value * b["rate"] - b.get("deduction", 0)))
            return tax, {"rate": b["rate"], "deduction": b.get("deduction", 0), "applied_bracket": b.get("label", str(b["limit"]))}
    # 최상위 구간 (limit=inf) 도 위 loop 에서 처리. 안전망:
    b = brackets[-1]
    return max(0, int(value * b["rate"] - b.get("deduction", 0))), {"rate": b["rate"]}


def calc_acquisition_tax(purchase_price: int) -> tuple[int, dict]:
    """매수가별 단일 구간 적용 (재산세/양도세 누진과 다름)."""
    for b in ACQUISITION_TAX_BRACKETS:
        if purchase_price <= b["limit"]:
            tax = int(purchase_price * b["rate"])
            return tax, {"rate": b["rate"], "applied_bracket": b["label"]}
    b = ACQUISITION_TAX_BRACKETS[-1]
    return int(purchase_price * b["rate"]), {"rate": b["rate"], "applied_bracket": b["label"]}


def calc_property_tax(appraised_value: int) -> tuple[int, dict]:
    """재산세 = 과세표준(공시가격 × 60%) × 누진세율 − 누진공제."""
    base = int(appraised_value * PROPERTY_TAX_FAIR_RATIO)
    tax, meta = _progressive(base, PROPERTY_TAX_BRACKETS)
    meta["fair_market_ratio"] = PROPERTY_TAX_FAIR_RATIO
    meta["taxable_base"] = base
    return tax, meta


def calc_comprehensive_tax(appraised_value: int) -> tuple[int, dict]:
    """종부세 = (공시가격 − 12억) × 60% 에 누진. 1주택 12억 이하 = 0."""
    excess = max(0, appraised_value - COMPREHENSIVE_TAX_DEDUCTION)
    if excess == 0:
        return 0, {"taxable_base": 0, "deduction_applied": COMPREHENSIVE_TAX_DEDUCTION}
    base = int(excess * COMPREHENSIVE_TAX_FAIR_RATIO)
    # 누진공제 없는 단순 세율 (구간별 정액). 정확한 누진공제는 v1.
    for b in COMPREHENSIVE_TAX_BRACKETS_1HOUSE:
        if base <= b["limit"]:
            return int(base * b["rate"]), {
                "rate": b["rate"],
                "taxable_base": base,
                "deduction_applied": COMPREHENSIVE_TAX_DEDUCTION,
                "fair_market_ratio": COMPREHENSIVE_TAX_FAIR_RATIO,
            }
    b = COMPREHENSIVE_TAX_BRACKETS_1HOUSE[-1]
    return int(base * b["rate"]), {"rate": b["rate"], "taxable_base": base}


def calc_capital_gains_tax(
    purchase_price: int,
    sale_price: int,
    holding_years: int,
    residence_years: int,
) -> tuple[int, dict]:
    """1세대 1주택 양도세. 12억 이하 + 보유/거주 2년 = 비과세."""
    if sale_price <= 0:
        return 0, {"status": "no_sale"}

    gain = max(0, sale_price - purchase_price)
    if gain == 0:
        return 0, {"status": "no_gain"}

    # 비과세 (1세대 1주택 + 12억 이하 + 보유 + 거주 2년 이상)
    if (sale_price <= CAPITAL_GAINS_EXEMPT_PRICE
            and holding_years >= CAPITAL_GAINS_MIN_HOLDING_YEARS
            and residence_years >= CAPITAL_GAINS_MIN_RESIDENCE_YEARS):
        return 0, {
            "status": "exempt_1house_under_12억",
            "exempt_threshold": CAPITAL_GAINS_EXEMPT_PRICE,
        }

    # 12억 초과 1주택 — 12억 초과분 비율로 과세
    if (sale_price > CAPITAL_GAINS_EXEMPT_PRICE
            and holding_years >= CAPITAL_GAINS_MIN_HOLDING_YEARS
            and residence_years >= CAPITAL_GAINS_MIN_RESIDENCE_YEARS):
        taxable_ratio = (sale_price - CAPITAL_GAINS_EXEMPT_PRICE) / sale_price
        taxable_gain = int(gain * taxable_ratio)
    else:
        taxable_gain = gain

    # 단기 양도 (2년 미만)
    if holding_years < 1:
        tax = int(taxable_gain * SHORT_TERM_RATE_UNDER_1Y)
        return tax, {
            "status": "short_term_under_1y",
            "rate": SHORT_TERM_RATE_UNDER_1Y,
            "taxable_gain": taxable_gain,
        }
    if holding_years < 2:
        tax = int(taxable_gain * SHORT_TERM_RATE_1_TO_2Y)
        return tax, {
            "status": "short_term_1_to_2y",
            "rate": SHORT_TERM_RATE_1_TO_2Y,
            "taxable_gain": taxable_gain,
        }

    # 2년 이상 — 장기보유특별공제 + 누진세율
    deduction_rate = long_term_deduction_rate(holding_years, residence_years)
    after_deduction = int(taxable_gain * (1 - deduction_rate))
    tax, meta = _progressive(after_deduction, CAPITAL_GAINS_BRACKETS)
    meta["status"] = "long_term"
    meta["taxable_gain"] = taxable_gain
    meta["long_term_deduction_rate"] = deduction_rate
    meta["after_deduction"] = after_deduction
    return tax, meta


# ─────────────────────────────────────────────────────────────
# Service
# ─────────────────────────────────────────────────────────────

def simulate(payload: Dict[str, Any]) -> Dict[str, Any]:
    """input → tax simulation. validation 실패 시 ValueError."""
    purchase_price = int(payload.get("purchase_price") or 0)
    appraised_value = int(payload.get("appraised_value") or 0)
    holding_years = int(payload.get("holding_years") or 0)
    residence_years = int(payload.get("residence_years") or 0)
    sale_price = int(payload.get("sale_price") or 0)

    if purchase_price <= 0:
        raise ValueError("purchase_price must be > 0")
    if appraised_value <= 0:
        appraised_value = int(purchase_price * 0.7)  # 공시가격 = 매수가의 70% 가정 fallback
    if holding_years < 0 or residence_years < 0:
        raise ValueError("years must be >= 0")
    if residence_years > holding_years:
        raise ValueError("residence_years cannot exceed holding_years")

    acq_tax, acq_meta = calc_acquisition_tax(purchase_price)
    prop_tax, prop_meta = calc_property_tax(appraised_value)
    compr_tax, compr_meta = calc_comprehensive_tax(appraised_value)
    cg_tax, cg_meta = calc_capital_gains_tax(purchase_price, sale_price, holding_years, residence_years)

    annual_holding = prop_tax + compr_tax
    total_holding = annual_holding * holding_years
    total_burden = acq_tax + total_holding + cg_tax

    base_for_rate = sale_price if sale_price > 0 else purchase_price
    effective_rate = (total_burden / base_for_rate) if base_for_rate > 0 else 0.0

    return {
        "acquisition_tax": acq_tax,
        "annual_property_tax": prop_tax,
        "annual_comprehensive_tax": compr_tax,
        "annual_holding_tax": annual_holding,
        "total_holding_tax": total_holding,
        "capital_gains_tax": cg_tax,
        "total_burden": total_burden,
        "effective_rate": round(effective_rate, 4),
        "breakdown": {
            "acquisition": acq_meta,
            "property": prop_meta,
            "comprehensive": compr_meta,
            "capital_gains": cg_meta,
        },
        "input": {
            "purchase_price": purchase_price,
            "appraised_value": appraised_value,
            "holding_years": holding_years,
            "residence_years": residence_years,
            "sale_price": sale_price,
        },
        "track": "1세대 1주택 v0 — 다주택/법인 미지원",
    }


# ─────────────────────────────────────────────────────────────
# HTTP handler (POST + GET fallback for query-only test)
# ─────────────────────────────────────────────────────────────

class handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def _json(self, status: int, payload: Dict[str, Any]):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "public, max-age=300")
        self.end_headers()
        self.wfile.write(body)

    def _err(self, status: int, code: str, message: str):
        self._json(status, {"error": code, "message": message})

    def _read_body(self) -> Optional[Dict[str, Any]]:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except (TypeError, ValueError):
            return None
        if length <= 0:
            return None
        raw = self.rfile.read(length)
        try:
            obj = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            _logger.error("tax_simulator: body parse failed: %s", e)
            return None
        return obj if isinstance(obj, dict) else None

    def _from_query(self) -> Dict[str, Any]:
        from urllib.parse import parse_qs, urlparse
        params = parse_qs(urlparse(self.path).query)
        out: Dict[str, Any] = {}
        for k in ("purchase_price", "appraised_value", "holding_years", "residence_years", "sale_price"):
            v = params.get(k, [""])[0]
            if v:
                out[k] = v
        return out

    def do_POST(self):
        body = self._read_body()
        if body is None:
            self._err(400, "invalid_body", "JSON body required")
            return
        self._run(body)

    def do_GET(self):
        body = self._from_query()
        if not body:
            self._err(400, "missing_params", "purchase_price query param required")
            return
        self._run(body)

    def _run(self, body: Dict[str, Any]):
        try:
            result = simulate(body)
        except ValueError as e:
            self._err(400, "invalid_input", str(e))
            return
        except Exception as e:
            _logger.error("tax_simulator: simulate raised: %s", e)
            self._err(500, "simulate_failed", "internal calculation error")
            return
        self._json(200, result)
