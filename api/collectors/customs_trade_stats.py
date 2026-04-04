"""
관세청 품목별·국가별 수출입실적 OpenAPI (getNitemtradeList) 연동
- 국가코드별 응답을 월 단위로 합산 → 수출 중량·금액
- 최근 3개월 + 전월·전년 동기 대비 수출액 증가율
"""
from __future__ import annotations

import math
import re
import time
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import requests

from api.config import (
    CUSTOMS_TRADE_BASE_CNTY,
    CUSTOMS_TRADE_SURGE_COUNTRIES,
    CUSTOMS_TRADE_SURGE_MOM_PCT,
    PUBLIC_DATA_API_KEY,
)

CUSTOMS_ITEMTRADE_URL = (
    "https://apis.data.go.kr/1220000/nitemtrade/getNitemtradeList"
)


def _local_tag(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def _item_to_dict(elem: ET.Element) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for child in list(elem):
        t = _local_tag(child.tag)
        txt = (child.text or "").strip()
        out[t] = txt
    return out


def _parse_items(xml_bytes: bytes) -> List[Dict[str, str]]:
    root = ET.fromstring(xml_bytes)
    items: List[Dict[str, str]] = []
    for el in root.iter():
        if _local_tag(el.tag).lower() == "item":
            items.append(_item_to_dict(el))
    return items


def _check_header_error(xml_text: str) -> Optional[str]:
    if "SERVICE_KEY_IS_NOT_REGISTERED_ERROR" in xml_text:
        return "SERVICE_KEY_IS_NOT_REGISTERED_ERROR"
    if "LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR" in xml_text:
        return "LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR"
    m = re.search(r"<resultcode>([^<]*)</resultcode>", xml_text, re.I)
    if m:
        code = m.group(1).strip()
        if code and code not in ("00", "0", "NORMAL_SERVICE"):
            msg = re.search(r"<resultmsg>([^<]+)</resultmsg>", xml_text, re.I)
            return (msg.group(1).strip() if msg else code) or code
    return None


def _pick_yymm(row: Dict[str, str]) -> Optional[str]:
    for key in (
        "statYm",
        "prdYm",
        "yrMm",
        "yrmt",
        "ym",
        "hsYyhsMm",
        "statsYymm",
        "statsYm",
    ):
        if key in row and row[key]:
            v = re.sub(r"\D", "", row[key])
            if len(v) >= 6:
                return v[:6]
    return None


def _pick_export_usd(row: Dict[str, str]) -> float:
    for key in (
        "expTwxamt",
        "expTwcifAmt",
        "expDlr",
        "expTotAmt",
        "expAmt",
        "exportAmt",
        "expUsdAmt",
    ):
        if key in row and row[key]:
            try:
                return float(re.sub(r"[^\d.\-]", "", row[key]) or 0)
            except ValueError:
                continue
    return 0.0


def _pick_export_kg(row: Dict[str, str]) -> float:
    for key in ("expWgt", "expWght", "expQty", "exportWgt"):
        if key in row and row[key]:
            try:
                return float(re.sub(r"[^\d.\-]", "", row[key]) or 0)
            except ValueError:
                continue
    return 0.0


def _hs_for_request(h6: str, h10: Optional[str]) -> str:
    if h10 and len(re.sub(r"\D", "", h10)) >= 10:
        return re.sub(r"\D", "", h10)[:10]
    d6 = re.sub(r"\D", "", h6)
    if len(d6) >= 6:
        return (d6[:6] + "0000")[:10]
    return (d6.ljust(6, "0") + "0000")[:10]


def _yymm_add_months(yymm: str, delta: int) -> str:
    y = int(yymm[:4])
    m = int(yymm[4:6])
    m += delta
    while m > 12:
        m -= 12
        y += 1
    while m < 1:
        m += 12
        y -= 1
    return f"{y}{m:02d}"


def _windows_for_yoy(end_yymm: str) -> List[Tuple[str, str]]:
    """API 12개월 이내 제한을 고려한 구간 2개: 최근 12개월 + 그 이전 12개월(전년 동월 포함)."""
    end2 = end_yymm
    start1 = _yymm_add_months(end2, -11)
    end0 = _yymm_add_months(end2, -12)
    start0 = _yymm_add_months(end0, -11)
    return [(start1, end2), (start0, end0)]


def fetch_trade_for_hs_country(
    hs_param: str,
    cnty_cd: str,
    strt_yymm: str,
    end_yymm: str,
    service_key: str,
    session: Optional[requests.Session] = None,
) -> List[Dict[str, str]]:
    sess = session or requests.Session()
    rows: List[Dict[str, str]] = []
    page = 1
    while page <= 50:
        params: Dict[str, Any] = {
            "serviceKey": service_key,
            "strtYymm": strt_yymm,
            "endYymm": end_yymm,
            "cntyCd": cnty_cd,
            "hsSgn": hs_param,
            "numOfRows": 1000,
            "pageNo": page,
        }
        r = sess.get(CUSTOMS_ITEMTRADE_URL, params=params, timeout=45)
        r.raise_for_status()
        text = r.text
        err = _check_header_error(text)
        if err:
            raise RuntimeError(err)
        try:
            chunk = _parse_items(r.content)
        except ET.ParseError as e:
            raise RuntimeError(f"관세청 XML 파싱 실패: {e}") from e
        if not chunk:
            break
        rows.extend(chunk)
        if len(chunk) < 1000:
            break
        page += 1
        time.sleep(0.05)
    return rows


def _hs_jobs_from_mapping(mapping: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    hs_jobs: Dict[str, Dict[str, Any]] = {}
    for _name, info in mapping.items():
        h6 = str(info.get("hscode", "")).strip()
        d6 = re.sub(r"\D", "", h6)
        if len(d6) < 6:
            continue
        h10 = info.get("hscode10")
        hp = _hs_for_request(str(h6), h10 if isinstance(h10, str) else None)
        if hp not in hs_jobs:
            hs_jobs[hp] = {"hscode6": h6, "hscode10": h10}
    return hs_jobs


def _fetch_trade_frames_by_countries(
    hs_jobs: Dict[str, Dict[str, Any]],
    windows: List[Tuple[str, str]],
    country_codes: List[str],
    service_key: str,
    session: requests.Session,
    *,
    tag_cnty: bool,
) -> List[pd.DataFrame]:
    monthly_frames: List[pd.DataFrame] = []
    for hs_param, meta in hs_jobs.items():
        for strt, end in windows:
            for cc in country_codes:
                try:
                    items = fetch_trade_for_hs_country(
                        hs_param, cc, strt, end, service_key, session=session
                    )
                except Exception as e:
                    print(f"[Customs] HS {hs_param} {cc} {strt}-{end}: {e}")
                    time.sleep(0.2)
                    continue
                for row in items:
                    ym = _pick_yymm(row)
                    if not ym:
                        continue
                    rec: Dict[str, Any] = {
                        "yymm": ym,
                        "export_value_usd": _pick_export_usd(row),
                        "export_weight_kg": _pick_export_kg(row),
                        "hs_request": hs_param,
                        "hscode6": meta.get("hscode6"),
                    }
                    if tag_cnty:
                        rec["cnty_cd"] = cc
                    monthly_frames.append(pd.DataFrame([rec]))
                time.sleep(0.12)
    return monthly_frames


def aggregate_monthly_by_hs(
    mapping: Dict[str, Dict[str, Any]],
    country_codes: Optional[List[str]] = None,
    service_key: Optional[str] = None,
) -> pd.DataFrame:
    """
    매핑된 고유 HS(요청용 10자리)별 월 시계열. country_codes 기본은 ZZ(전체) 1건.
    columns: yymm, export_value_usd, export_weight_kg, hs_request, hscode6
    """
    key = service_key or PUBLIC_DATA_API_KEY
    if not key:
        raise ValueError("PUBLIC_DATA_API_KEY 미설정")

    codes = country_codes
    if not codes:
        codes = [CUSTOMS_TRADE_BASE_CNTY or "ZZ"]
    codes = [c.strip().upper() for c in codes if c and str(c).strip()]
    if not codes:
        codes = ["ZZ"]

    hs_jobs = _hs_jobs_from_mapping(mapping)
    if not hs_jobs:
        return pd.DataFrame(
            columns=["yymm", "export_value_usd", "export_weight_kg", "hs_request"]
        )

    end_yymm = _default_end_yymm()
    windows = _windows_for_yoy(end_yymm)
    sess = requests.Session()
    monthly_frames = _fetch_trade_frames_by_countries(
        hs_jobs, windows, codes, key, sess, tag_cnty=False
    )

    if not monthly_frames:
        return pd.DataFrame(
            columns=["yymm", "export_value_usd", "export_weight_kg", "hs_request"]
        )

    df = pd.concat(monthly_frames, ignore_index=True)
    df = (
        df.groupby(["yymm", "hs_request", "hscode6"], as_index=False)
        .agg({"export_value_usd": "sum", "export_weight_kg": "sum"})
        .sort_values("yymm")
    )
    return df


def _recent_stat_yymms(last_n: int = 3) -> List[str]:
    end_yymm = _default_end_yymm()
    recent_yymms: List[str] = []
    y, m = int(end_yymm[:4]), int(end_yymm[4:6])
    for _ in range(last_n):
        recent_yymms.append(f"{y}{m:02d}")
        m -= 1
        if m < 1:
            m = 12
            y -= 1
    recent_yymms.reverse()
    return recent_yymms


def _parse_surge_countries() -> List[str]:
    return [
        c.strip().upper()
        for c in CUSTOMS_TRADE_SURGE_COUNTRIES.split(",")
        if c.strip()
    ]


def _fetch_surge_breakdown_df(
    hs_jobs: Dict[str, Dict[str, Any]],
    service_key: str,
) -> pd.DataFrame:
    """급증 HS만 CN·US·VN 등 국가별 월별(합산 전) DataFrame."""
    if not hs_jobs:
        return pd.DataFrame(
            columns=[
                "yymm",
                "export_value_usd",
                "export_weight_kg",
                "hs_request",
                "hscode6",
                "cnty_cd",
            ]
        )
    end_yymm = _default_end_yymm()
    windows = _windows_for_yoy(end_yymm)
    sess = requests.Session()
    surge_cc = _parse_surge_countries()
    frames = _fetch_trade_frames_by_countries(
        hs_jobs, windows, surge_cc, service_key, sess, tag_cnty=True
    )
    if not frames:
        return pd.DataFrame(
            columns=[
                "yymm",
                "export_value_usd",
                "export_weight_kg",
                "hs_request",
                "hscode6",
                "cnty_cd",
            ]
        )
    df = pd.concat(frames, ignore_index=True)
    return (
        df.groupby(
            ["yymm", "hs_request", "hscode6", "cnty_cd"],
            as_index=False,
        )
        .agg({"export_value_usd": "sum", "export_weight_kg": "sum"})
        .sort_values(["hs_request", "cnty_cd", "yymm"])
    )


def _attach_surge_country_breakdown(
    stock_rows: List[Dict[str, Any]],
    breakdown_df: pd.DataFrame,
    surge_mom_pct: float,
    surge_countries: List[str],
    last_n_months: int = 3,
) -> None:
    if breakdown_df.empty:
        return
    recent_yymms = _recent_stat_yymms(last_n_months)
    for row in stock_rows:
        mom = row.get("mom_export_pct")
        if mom is None or float(mom) < float(surge_mom_pct):
            continue
        hp = row.get("hscode10_request")
        if not hp:
            continue
        sub = breakdown_df[breakdown_df["hs_request"] == hp]
        if sub.empty:
            row["surge_country_breakdown"] = {}
            continue
        by_country: Dict[str, List[Dict[str, Any]]] = {}
        for cc in surge_countries:
            part = sub[sub["cnty_cd"] == cc]
            pivot = part.groupby("yymm", as_index=False).agg(
                {"export_value_usd": "sum", "export_weight_kg": "sum"}
            )
            by_m = {str(r["yymm"]): r for _, r in pivot.iterrows()}
            months_out: List[Dict[str, Any]] = []
            for ym in recent_yymms:
                r = by_m.get(ym)
                months_out.append(
                    {
                        "yymm": ym,
                        "export_weight_kg": float(r["export_weight_kg"]) if r is not None else 0.0,
                        "export_value_usd": float(r["export_value_usd"]) if r is not None else 0.0,
                    }
                )
            by_country[cc] = months_out
        row["surge_country_breakdown"] = by_country


def run_customs_two_phase_analysis(
    mapping: Dict[str, Dict[str, Any]],
    service_key: Optional[str] = None,
    surge_mom_pct: Optional[float] = None,
    last_n_months: int = 3,
) -> Tuple[pd.DataFrame, List[Dict[str, Any]]]:
    """
    1단: 국가코드 ZZ(전체)만으로 월별 수출 시계열 → 전월·전년비 계산.
    2단: 전월 대비 수출액이 surge_mom_pct% 이상인 종목의 HS에 대해서만
         CN·US·VN(환경변수) 국가별 세부 데이터 추가 조회 후 `surge_country_breakdown`에 부착.
    """
    key = service_key or PUBLIC_DATA_API_KEY
    thr = (
        float(surge_mom_pct)
        if surge_mom_pct is not None
        else float(CUSTOMS_TRADE_SURGE_MOM_PCT)
    )
    surge_cc = _parse_surge_countries()

    monthly_zz = aggregate_monthly_by_hs(
        mapping,
        country_codes=[CUSTOMS_TRADE_BASE_CNTY or "ZZ"],
        service_key=key,
    )
    stock_rows = build_stock_analysis(mapping, monthly_zz, last_n_months=last_n_months)

    surge_hps = {
        r["hscode10_request"]
        for r in stock_rows
        if r.get("hscode10_request")
        and r.get("mom_export_pct") is not None
        and float(r["mom_export_pct"]) >= thr
    }

    if not surge_hps:
        print(
            f"[Customs] 전월비 {thr:g}% 이상 급증 종목 없음 — 2차 국가({','.join(surge_cc)}) 조회 생략",
            flush=True,
        )
        return monthly_zz, stock_rows

    hs_all = _hs_jobs_from_mapping(mapping)
    hs_surge = {hp: hs_all[hp] for hp in surge_hps if hp in hs_all}
    print(
        f"[Customs] 전월비 ≥{thr:g}% 종목 {len(surge_hps)}건 HS — 2차 조회 {','.join(surge_cc)}",
        flush=True,
    )
    breakdown_df = _fetch_surge_breakdown_df(hs_surge, key)
    _attach_surge_country_breakdown(
        stock_rows, breakdown_df, thr, surge_cc, last_n_months=last_n_months
    )
    return monthly_zz, stock_rows


def _default_end_yymm() -> str:
    """무역통계 반영 시차 반영: 약 2개월 전까지를 최신 완료 월로 가정."""
    from api.config import now_kst

    t = now_kst()
    y, m = t.year, t.month
    m -= 2
    while m < 1:
        m += 12
        y -= 1
    return f"{y}{m:02d}"


def _pct_change(cur: float, prev: float) -> Optional[float]:
    if prev == 0 or math.isnan(prev) or math.isnan(cur):
        return None
    return round((cur - prev) / prev * 100.0, 2)


def build_stock_analysis(
    mapping: Dict[str, Dict[str, Any]],
    monthly_df: pd.DataFrame,
    last_n_months: int = 3,
) -> List[Dict[str, Any]]:
    if monthly_df.empty:
        rows: List[Dict[str, Any]] = []
        for name, info in mapping.items():
            h6raw = str(info.get("hscode", "")).strip()
            if len(re.sub(r"\D", "", h6raw)) < 6:
                rows.append(
                    {
                        "name": name,
                        "ticker": info.get("ticker"),
                        "product": info.get("product"),
                        "hscode": info.get("hscode") or None,
                        "hscode10_request": None,
                        "monthly": [],
                        "latest_yymm": None,
                        "mom_export_pct": None,
                        "yoy_export_pct": None,
                        "score": None,
                        "note": "HS 미매핑 — 관세청 조회 생략",
                    }
                )
            else:
                rows.append(
                    {
                        "name": name,
                        "ticker": info.get("ticker"),
                        "product": info.get("product"),
                        "hscode": info.get("hscode"),
                        "hscode10_request": _hs_for_request(
                            h6raw,
                            info.get("hscode10") if isinstance(info.get("hscode10"), str) else None,
                        ),
                        "monthly": [],
                        "latest_yymm": None,
                        "mom_export_pct": None,
                        "yoy_export_pct": None,
                        "score": None,
                        "note": "관세청 월별 데이터 없음",
                    }
                )
        return rows

    end_yymm = _default_end_yymm()
    recent_yymms = []
    y, m = int(end_yymm[:4]), int(end_yymm[4:6])
    for _ in range(last_n_months):
        recent_yymms.append(f"{y}{m:02d}")
        m -= 1
        if m < 1:
            m = 12
            y -= 1
    recent_yymms.reverse()

    out: List[Dict[str, Any]] = []
    for name, info in mapping.items():
        h6raw = str(info.get("hscode", "")).strip()
        if len(re.sub(r"\D", "", h6raw)) < 6:
            out.append(
                {
                    "name": name,
                    "ticker": info.get("ticker"),
                    "product": info.get("product"),
                    "hscode": info.get("hscode") or None,
                    "hscode10_request": None,
                    "monthly": [],
                    "latest_yymm": None,
                    "mom_export_pct": None,
                    "yoy_export_pct": None,
                    "score": None,
                    "note": "HS 미매핑 — 관세청 조회 생략",
                }
            )
            continue

        hp = _hs_for_request(
            h6raw,
            info.get("hscode10") if isinstance(info.get("hscode10"), str) else None,
        )
        sub = monthly_df[monthly_df["hs_request"] == hp]
        pivot = sub.groupby("yymm", as_index=False).agg(
            {"export_value_usd": "sum", "export_weight_kg": "sum"}
        )
        by_m = {r["yymm"]: r for _, r in pivot.iterrows()}

        monthly_rows = []
        for ym in recent_yymms:
            r = by_m.get(ym)
            monthly_rows.append(
                {
                    "yymm": ym,
                    "export_weight_kg": float(r["export_weight_kg"]) if r is not None else 0.0,
                    "export_value_usd": float(r["export_value_usd"]) if r is not None else 0.0,
                }
            )

        latest_yymm = recent_yymms[-1] if recent_yymms else None
        prev_yymm = _yymm_add_months(latest_yymm, -1) if latest_yymm else None
        yoy_yymm = _yymm_add_months(latest_yymm, -12) if latest_yymm else None

        cur = by_m.get(latest_yymm, {}).get("export_value_usd", 0.0) if latest_yymm else 0.0
        prev = by_m.get(prev_yymm, {}).get("export_value_usd", 0.0) if prev_yymm else 0.0
        yoy_b = by_m.get(yoy_yymm, {}).get("export_value_usd", 0.0) if yoy_yymm else 0.0

        if hasattr(cur, "item"):
            cur = float(cur)
        if hasattr(prev, "item"):
            prev = float(prev)
        if hasattr(yoy_b, "item"):
            yoy_b = float(yoy_b)

        mom = _pct_change(float(cur), float(prev))
        yoy = _pct_change(float(cur), float(yoy_b))

        parts = [p for p in (mom, yoy) if p is not None]
        score = round(sum(parts) / len(parts), 2) if parts else None

        out.append(
            {
                "name": name,
                "ticker": info.get("ticker"),
                "product": info.get("product"),
                "hscode": info.get("hscode"),
                "hscode10_request": hp,
                "monthly": monthly_rows,
                "latest_yymm": latest_yymm,
                "mom_export_pct": mom,
                "yoy_export_pct": yoy,
                "score": score,
                "note": None,
            }
        )

    return out


def rank_top_export_stocks(stock_rows: List[Dict[str, Any]], top_k: int = 3) -> List[Dict[str, Any]]:
    def key(r: Dict[str, Any]) -> Tuple[int, float]:
        s = r.get("score")
        if s is None or (isinstance(s, float) and math.isnan(s)):
            return (0, float("-inf"))
        return (1, float(s))

    ranked = sorted(stock_rows, key=key, reverse=True)
    return [r for r in ranked if key(r)[0] == 1][:top_k]
