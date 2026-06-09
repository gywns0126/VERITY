"""
FRED API — 공식 거시 시계열
  미국: DGS10, CPILFESL, M2SL, VIXCLS, RECPROUSM156N, BAMLH0A0HYM2, T10YIE, WALCL
  한국(ECOS 대체): IRLTLT01KRA156N(국채10Y·OECD), INTDSRKRM193N(할인율·IMF)
https://fred.stlouisfed.org/docs/api/fred/

2026-05-16 silent skip audit:
  _fetch_series 가 except return [] 3개 path (no key / HTTP != 200 / requests exception)
  로 silent skip 했음. 결과: hy_spread / breakeven_10y null 지속, 운영 진단 불가.
  → 호출당 health entry 기록 (data/metadata/fred_health.jsonl).
  → 정정: failure reason 명시 + stderr 로그 + ledger 누적.
"""
import json
import os
import sys
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import requests

from api.config import FRED_API_KEY, DATA_DIR

FRED_OBS_URL = "https://api.stlouisfed.org/fred/series/observations"
FRED_HEALTH_PATH = os.path.join(DATA_DIR, "metadata", "fred_health.jsonl")

_TREND_DAYS = {"1m": 30, "3m": 90, "6m": 180, "1y": 365}


def _log_fred_health(series_id: str, status: str, reason: str = "",
                     points: int = 0, elapsed_ms: int = 0) -> None:
    """FRED 호출 결과 ledger 누적 — silent skip 감지용 (feedback_data_collection_verification_mandatory).

    status: ok / no_api_key / http_error / network_error / parse_error / empty
    """
    try:
        os.makedirs(os.path.dirname(FRED_HEALTH_PATH), exist_ok=True)
        entry = {
            "ts_utc": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "series_id": series_id,
            "status": status,
            "reason": reason[:200] if reason else "",
            "points": points,
            "elapsed_ms": elapsed_ms,
        }
        with open(FRED_HEALTH_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        # silent skip 절대 금지 — fail 은 stderr 명시
        if status not in ("ok", "empty"):
            sys.stderr.write(f"[fred_health] {series_id} {status}: {reason[:160]}\n")
    except Exception as _e:
        sys.stderr.write(f"[fred_health] ledger write fail: {_e}\n")


def _parse_observations(payload: dict) -> List[Tuple[str, float]]:
    out: List[Tuple[str, float]] = []
    for obs in payload.get("observations", []) or []:
        raw = obs.get("value")
        if raw in (".", "", None):
            continue
        try:
            out.append((str(obs.get("date", "")), float(raw)))
        except (TypeError, ValueError):
            continue
    return out


def _value_minus_approx_12m_prior(points: List[Tuple[str, float]]) -> Optional[float]:
    """최신값 − 약 12개월 전(±2M) 관측. 없으면 직전 관측 대비."""
    if len(points) < 2:
        return None
    d0_s, v0 = points[0]
    try:
        d0 = datetime.strptime(d0_s[:10], "%Y-%m-%d")
    except ValueError:
        return round(v0 - points[1][1], 4)
    best_v: Optional[float] = None
    best_dm = 99
    for d_s, v in points[1:]:
        try:
            d = datetime.strptime(d_s[:10], "%Y-%m-%d")
        except ValueError:
            continue
        dm = abs((d0.year - d.year) * 12 + (d0.month - d.month))
        if 10 <= dm <= 14 and dm < best_dm:
            best_v = v
            best_dm = dm
    if best_v is not None:
        return round(v0 - best_v, 4)
    return round(v0 - points[1][1], 4)


def _fetch_series(series_id: str, limit: int) -> List[Tuple[str, float]]:
    """FRED 시계열 fetch — silent skip 절대 금지.

    실패 시 health ledger + stderr 명시. 빈 리스트는 (1) no key (2) HTTP fail
    (3) network exception (4) parse 빈 결과 — 모두 health log 필수.
    """
    t0 = time.time()
    if not FRED_API_KEY:
        _log_fred_health(series_id, "no_api_key",
                         "FRED_API_KEY env missing (collect aborted)")
        return []
    try:
        r = requests.get(
            FRED_OBS_URL,
            params={
                "series_id": series_id,
                "api_key": FRED_API_KEY,
                "file_type": "json",
                "sort_order": "desc",
                "limit": int(limit),
            },
            timeout=20,
        )
        elapsed_ms = int((time.time() - t0) * 1000)
        if r.status_code != 200:
            _log_fred_health(series_id, "http_error",
                             f"status={r.status_code} body={r.text[:120]}",
                             elapsed_ms=elapsed_ms)
            return []
        points = _parse_observations(r.json())
        if not points:
            _log_fred_health(series_id, "empty",
                             "API responded but no parseable observations",
                             points=0, elapsed_ms=elapsed_ms)
        else:
            _log_fred_health(series_id, "ok", points=len(points),
                             elapsed_ms=elapsed_ms)
        return points
    except requests.exceptions.Timeout:
        elapsed_ms = int((time.time() - t0) * 1000)
        _log_fred_health(series_id, "network_error", "timeout 20s",
                         elapsed_ms=elapsed_ms)
        return []
    except Exception as e:
        elapsed_ms = int((time.time() - t0) * 1000)
        _log_fred_health(series_id, "network_error", str(e),
                         elapsed_ms=elapsed_ms)
        return []


def _compute_series_trend(points: List[Tuple[str, float]], rnd: int = 3) -> Dict[str, Any]:
    """시계열 관측값으로부터 1M/3M/6M/1Y trend + 주간 sparkline을 계산."""
    if len(points) < 2:
        return {}
    latest_date_str, latest_val = points[0]
    try:
        latest_dt = datetime.strptime(latest_date_str[:10], "%Y-%m-%d")
    except ValueError:
        return {}

    trend: Dict[str, Any] = {}
    for label, days in _TREND_DAYS.items():
        cutoff = latest_dt - timedelta(days=days)
        candidates = [(d, v) for d, v in points if d[:10] >= cutoff.strftime("%Y-%m-%d")]
        if not candidates:
            trend[label] = None
            continue
        oldest_d, oldest_v = candidates[-1]
        trend[label] = {
            "start": round(oldest_v, rnd),
            "end": round(latest_val, rnd),
            "change": round(latest_val - oldest_v, rnd),
        }

    chronological = list(reversed(points))
    week_vals: List[float] = []
    if chronological:
        bucket_end = None
        bucket_val = None
        for d_s, v in chronological:
            try:
                d = datetime.strptime(d_s[:10], "%Y-%m-%d")
            except ValueError:
                continue
            if bucket_end is None:
                bucket_end = d
                bucket_val = v
                continue
            if (d - bucket_end).days >= 5:
                week_vals.append(round(bucket_val, rnd))
                bucket_end = d
            bucket_val = v
        if bucket_val is not None:
            week_vals.append(round(bucket_val, rnd))

    return {"trend": trend, "sparkline": week_vals[-52:]}


def get_fred_macro_block() -> Dict[str, Any]:
    """
    미국: DGS10·근원CPI·M2(기존), VIX 종가, 스무딩 리세션 확률.
    한국: OECD 10Y 국채, IMF 할인율(ECOS 미가입 시 방어용 대체).
    API 키 없거나 오류 시 부분/빈 블록.
    """
    if not FRED_API_KEY:
        return {"available": False, "error": "no_api_key"}

    out: Dict[str, Any] = {"available": False}

    vix_c = _fetch_series("VIXCLS", 260)
    if len(vix_c) >= 1:
        vd, vv = vix_c[0]
        v_ch5: Optional[float] = None
        if len(vix_c) >= 6:
            v_ch5 = round(vv - vix_c[5][1], 3)
        vix_trend = _compute_series_trend(vix_c, rnd=2)
        out["vix_close"] = {
            "value": round(vv, 2),
            "date": vd,
            "change_5d": v_ch5,
            "series_id": "VIXCLS",
            **vix_trend,
        }

    dgs = _fetch_series("DGS10", 260)
    if len(dgs) >= 1:
        latest_d, latest_v = dgs[0]
        ch5: Optional[float] = None
        if len(dgs) >= 6:
            ch5 = round(latest_v - dgs[5][1], 4)
        dgs_trend = _compute_series_trend(dgs)
        out["dgs10"] = {
            "value": round(latest_v, 3),
            "date": latest_d,
            "change_5d_pp": ch5,
            **dgs_trend,
        }

    cpi = _fetch_series("CPILFESL", 16)
    if len(cpi) >= 13:
        cur_d, cur_v = cpi[0]
        _, yago_v = cpi[12]
        if yago_v and yago_v > 0:
            yoy = round((cur_v / yago_v - 1) * 100, 2)
            out["core_cpi"] = {
                "index": round(cur_v, 2),
                "date": cur_d,
                "yoy_pct": yoy,
            }

    m2 = _fetch_series("M2SL", 60)
    if len(m2) >= 53:
        cur_d, cur_v = m2[0]
        _, yago_v = m2[52]
        if yago_v and yago_v > 0:
            yoy = round((cur_v / yago_v - 1) * 100, 2)
            out["m2"] = {
                "billions_usd": round(cur_v, 1),
                "date": cur_d,
                "yoy_pct": yoy,
            }

    kr10 = _fetch_series("IRLTLT01KRA156N", 36)
    if len(kr10) >= 1:
        kd, kv = kr10[0]
        yoy_pp = _value_minus_approx_12m_prior(kr10)
        out["korea_gov_10y"] = {
            "value": round(kv, 3),
            "date": kd,
            "yoy_pp": yoy_pp,
            "series_id": "IRLTLT01KRA156N",
            "source_note": "OECD Main Economic Indicators (빈도·시차 ECOS와 다를 수 있음)",
        }

    krd = _fetch_series("INTDSRKRM193N", 24)
    if len(krd) >= 1:
        dd, dv = krd[0]
        d_yoy: Optional[float] = None
        if len(krd) >= 13:
            d_yoy = round(dv - krd[12][1], 4)
        out["korea_discount_rate"] = {
            "value": round(dv, 3),
            "date": dd,
            "yoy_pp": d_yoy,
            "series_id": "INTDSRKRM193N",
            "source_note": "IMF IFS (BOK 기준금리와 시차·정의 다를 수 있음)",
        }

    rec = _fetch_series("RECPROUSM156N", 8)
    if len(rec) >= 1:
        rd, rv = rec[0]
        mom: Optional[float] = None
        if len(rec) >= 2:
            mom = round(rv - rec[1][1], 3)
        out["us_recession_smoothed_prob"] = {
            "pct": round(rv, 2),
            "date": rd,
            "mom_change_pp": mom,
            "series_id": "RECPROUSM156N",
            "source_note": "Smoothed U.S. recession probability (monthly model)",
        }

    # 실업률 (UNRATE)
    unr = _fetch_series("UNRATE", 16)
    if len(unr) >= 1:
        ud, uv = unr[0]
        u_mom: Optional[float] = None
        if len(unr) >= 2:
            u_mom = round(uv - unr[1][1], 2)
        u_yoy: Optional[float] = None
        if len(unr) >= 13:
            u_yoy = round(uv - unr[12][1], 2)
        out["unemployment_rate"] = {
            "pct": round(uv, 1),
            "date": ud,
            "mom_change_pp": u_mom,
            "yoy_change_pp": u_yoy,
            "series_id": "UNRATE",
        }

    # 미시간 소비자 심리지수 (UMCSENT)
    umc = _fetch_series("UMCSENT", 16)
    if len(umc) >= 1:
        cd, cv = umc[0]
        c_mom: Optional[float] = None
        if len(umc) >= 2:
            c_mom = round(cv - umc[1][1], 1)
        out["consumer_sentiment"] = {
            "value": round(cv, 1),
            "date": cd,
            "mom_change": c_mom,
            "series_id": "UMCSENT",
        }

    # 하이일드 스프레드 (ICE BofA, BAMLH0A0HYM2)
    hy = _fetch_series("BAMLH0A0HYM2", 260)
    if len(hy) >= 1:
        hd, hv = hy[0]
        h_ch5: Optional[float] = None
        if len(hy) >= 6:
            h_ch5 = round(hv - hy[5][1], 3)
        hy_trend = _compute_series_trend(hy)
        out["hy_spread"] = {
            "pct": round(hv, 3),
            "date": hd,
            "change_5d_pp": h_ch5,
            "series_id": "BAMLH0A0HYM2",
            **hy_trend,
        }

    # 10년 기대인플레이션 (T10YIE)
    t10ie = _fetch_series("T10YIE", 260)
    if len(t10ie) >= 1:
        id_, iv = t10ie[0]
        i_ch5: Optional[float] = None
        if len(t10ie) >= 6:
            i_ch5 = round(iv - t10ie[5][1], 3)
        ie_trend = _compute_series_trend(t10ie)
        out["breakeven_inflation_10y"] = {
            "pct": round(iv, 3),
            "date": id_,
            "change_5d_pp": i_ch5,
            "series_id": "T10YIE",
            **ie_trend,
        }

    # Fed 대차대조표 총자산 (WALCL, 주간)
    wal = _fetch_series("WALCL", 12)
    if len(wal) >= 1:
        wd, wv = wal[0]
        w_ch4: Optional[float] = None
        if len(wal) >= 5:
            w_ch4 = round((wv - wal[4][1]) / wal[4][1] * 100, 2) if wal[4][1] > 0 else None
        out["fed_balance_sheet"] = {
            "trillions_usd": round(wv / 1e6, 2),
            "date": wd,
            "change_4w_pct": w_ch4,
            "series_id": "WALCL",
        }

    # 2026-05-07: Shiller CAPE — FRED 시리즈 없어 multpl.com 스크래핑 (별 collector)
    try:
        from api.collectors.cape_multpl import fetch_cape
        cape_data = fetch_cape()
        if cape_data:
            out["cape"] = cape_data
    except Exception:  # noqa: BLE001
        pass  # 스크래핑 실패는 무시 (market_horizon 가 cape_pctile=None 처리)

    # ── 2026-05-18 F1+F2 (PM 승인) — detect_economic_quadrant 입력 키 derivation ──
    # docs/QUADRANT_REGRESSION_AUDIT_20260518.md 참조. 함수가 찾는 fred.cpi_yoy /
    # fred.gdp_growth 키가 부재해 fallback (cpi=2.5 하드코드 + gdp=mood proxy) 영구 trip,
    # growth_down_inflation_down 25/25 종목 단일 강제로 constitution 5분면 차등 무효화.
    # 실데이터 (core_cpi.yoy_pct + us_recession_smoothed_prob.pct) 는 정상 수집됨 — 매핑만 추가.
    cpi_block = out.get("core_cpi") or {}
    cpi_yoy_val = cpi_block.get("yoy_pct")
    if cpi_yoy_val is not None:
        out["cpi_yoy"] = {
            "value": float(cpi_yoy_val),
            "date": cpi_block.get("date"),
            "series_id": "CPILFESL",
            "source_note": "derived from core_cpi.yoy_pct (F1 2026-05-18)",
        }

    rec_block = out.get("us_recession_smoothed_prob") or {}
    rec_prob = rec_block.get("pct")
    if rec_prob is not None:
        # Hamilton smoothed recession prob (RECPROUSM156N) → gdp_growth proxy.
        # 산식: gdp_growth = 2.5 - 0.08 × recession_prob_pct
        #   recession_prob <5%: expansion (gdp ≈ +2~+3)
        #   recession_prob 12.5%: growth_up 임계 (gdp = 1.5)
        #   recession_prob 50%: 침체 (gdp ≈ -1.5)
        #   recession_prob 100%: 심각 침체 (gdp ≈ -5.5)
        # PM 승인 (2026-05-18) — 단일 변수 통제, ism_pmi 수집 가능 시점에 재검토.
        gdp_proxy = round(2.5 - 0.08 * float(rec_prob), 2)
        out["gdp_growth"] = {
            "value": gdp_proxy,
            "date": rec_block.get("date"),
            "series_id": "RECPROUSM156N",
            "source_note": (
                f"proxy from us_recession_smoothed_prob.pct={rec_prob} "
                "(F2 2026-05-18, 산식 2.5 - 0.08×rp)"
            ),
        }

    out["available"] = bool(
        out.get("dgs10")
        or out.get("core_cpi")
        or out.get("cpi_yoy")
        or out.get("gdp_growth")
        or out.get("m2")
        or out.get("vix_close")
        or out.get("korea_gov_10y")
        or out.get("korea_discount_rate")
        or out.get("us_recession_smoothed_prob")
        or out.get("unemployment_rate")
        or out.get("consumer_sentiment")
        or out.get("hy_spread")
        or out.get("breakeven_inflation_10y")
        or out.get("fed_balance_sheet")
        or out.get("cape")
    )
    return out
