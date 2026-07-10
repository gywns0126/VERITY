"""ETF 자금흐름(설정/환매) 누적 로거 — AlphaNest 'ETF 자금흐름 → 구성종목 압력' 렌즈의 1차 소스.

🚨 진짜 자금흐름 = Δ상장좌수(LIST_SHRS) = 설정/환매 = 패시브 자금 순유입/유출. 가격효과 제거.
  · AUM(시총) 변화는 "가격 × 좌수" 혼재라 흐름 신호로 부정확 → 좌수 변화만이 순수 흐름.
  · est_flow_won = Δ상장좌수 × NAV (그날 설정/환매된 자금 규모 추정).
  · 일별 시계열 누적(단일 writer data/etf_flow.json). 첫 신호 = 거래일 ≥2 (누적형, [[project_kr_flow_crowding_trail_2026_06_15]] 결).

🚨 소스 = 기존에 이미 호출 중인 KRX OpenAPI etf_bydd_trd (etfdata.py). 신규 vendor/키 0.
  · 상장좌수/순자산 키명은 KRX 표준(stk_bydd_trd LIST_SHRS = universe_builder 사용)이나, ETF 응답 키는
    방어적 fallback 후보로 추출 + 매칭된 키를 field_map 으로 기록 → prod 첫 run 로그로 확정(RULE 8 N=2).

🚨 RULE 7: 관측 사실(좌수·NAV·순자산)만 적재. 점수·추천·등급 0. 구성종목 압력 매핑은 별건(PDF 수집 후).
🚨 RULE 4: data/ broad git add 자동 포함. feedback_publish_data_file_list_audit: publish-data 목록 추가 의무.
"""
import json
import os
import sys
from typing import Any, Dict, List, Optional

from api.config import now_kst
from api.collectors.etfdata import (
    _TICKER_META,
    _fetch_etf_day,
    _parse_float,
    _recent_business_day,
)

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUTPUT_PATH = os.path.join(_ROOT, "data", "etf_flow.json")

HISTORY_CAP = 40  # 티커당 보관 거래일 수 (≈2개월)

# KRX etf_bydd_trd 응답 키 후보 (표준 우선, 변형 fallback) — 매칭 키는 field_map 으로 기록
_SHRS_KEYS = ["LIST_SHRS", "LISTSHRS", "LIST_SHRS_CO", "INVSTASST_LIST_SHRS"]
_NETASST_KEYS = ["NETASST_TOTAMT", "INVSTASST_NETASST_TOTAMT", "NETASST", "NETASST_AMT"]
_NAV_KEYS = ["NAV"]
_CLOSE_KEYS = ["TDD_CLSPRC"]
_BASDD_KEYS = ["BAS_DD", "TRD_DD"]


def _pick(row: Dict[str, Any], keys: List[str]) -> (Optional[float], Optional[str]):
    """후보 키 중 첫 유효값 → (값, 매칭키). 숫자 파싱."""
    for k in keys:
        if k in row:
            v = _parse_float(row.get(k))
            if v is not None:
                return v, k
    return None, None


def _pick_str(row: Dict[str, Any], keys: List[str]) -> Optional[str]:
    for k in keys:
        v = row.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return None


def _load_existing() -> Dict[str, Any]:
    try:
        with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
            d = json.load(f)
            return d if isinstance(d, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


# ── ETF 부가정보 (보수율·기초지수·운용사·구성종목 top10) — 네이버 금융 (2026-07-10 PM) ──
# 모바일 integration API totalInfos(펀드보수·기초지수·운용사) + PC CU 표(구성 상위 10, 비중%).
# 사실 metadata (시세 재배포 아님). 실패 시 이전 값 carry(graceful). 25종 × 2콜/일.
import re as _re
import time as _time
import urllib.request as _ur

def _fetch_etf_extras(ticker: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    hdr = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
    try:
        d = json.loads(_ur.urlopen(_ur.Request(
            f"https://m.stock.naver.com/api/stock/{ticker}/integration", headers=hdr), timeout=10).read())
        for it in (d.get("totalInfos") or []):
            k, v = str(it.get("key") or ""), str(it.get("value") or "")
            if k == "펀드보수" and v:
                out["ter"] = v
            elif k == "기초지수" and v:
                out["base_index"] = v
            elif k == "운용사" and v:
                out["manager"] = v.replace("(ETF)", "").strip()
    except Exception:  # noqa: BLE001
        pass
    _time.sleep(0.25)
    try:
        html = _ur.urlopen(_ur.Request(
            f"https://finance.naver.com/item/main.naver?code={ticker}", headers=hdr), timeout=12).read().decode("utf-8", "replace")
        i = html.find("1CU")
        seg = html[max(0, i - 9000):i] if i > 0 else ""
        rows = _re.findall(r'code=(\d{6})[^>]*>([^<]{1,40})</a>\s*</td>\s*<td>\s*[\d,]+\s*</td>\s*<td class="per">\s*([\d.]+)%', seg)
        if rows:
            out["top_holdings"] = [{"t": tk2, "n": nm.strip(), "w": float(w)} for tk2, nm, w in rows[:10]]
    except Exception:  # noqa: BLE001
        pass
    return out


def build_etf_flow() -> Dict[str, Any]:
    """KRX etf_bydd_trd 에서 상장좌수/NAV/순자산 추출 → 일별 누적 + Δ좌수 흐름 산출 → data/etf_flow.json.

    반환: 요약 dict {status, n, with_flow, bas_dd, field_map}.
    """
    logged = False
    summary: Dict[str, Any] = {"status": "skip", "n": 0, "with_flow": 0}
    try:
        ts = now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00")

        # 최근 5거래일 중 데이터 있는 일자 (etfdata 와 동일 패턴)
        rows: Dict[str, Dict[str, Any]] = {}
        bas_dd_used = ""
        for offset in range(5):
            bas_dd = _recent_business_day(offset)
            rows = _fetch_etf_day(bas_dd)
            if rows:
                bas_dd_used = bas_dd
                break
        if not rows:
            print("[ETF_FLOW] KRX 응답 없음(키 미설정/비거래일) — 기존 파일 유지, skip", file=sys.stderr)
            return summary

        existing = _load_existing()
        history: Dict[str, List[Dict[str, Any]]] = existing.get("history") or {}

        field_map: Dict[str, str] = {}
        sample_keys: List[str] = []
        etfs: List[Dict[str, Any]] = []
        with_flow = 0

        for ticker, (name_fallback, category) in _TICKER_META.items():
            row = rows.get(ticker)
            if not row:
                continue
            if not sample_keys:
                sample_keys = sorted(row.keys())

            list_shrs, k_shrs = _pick(row, _SHRS_KEYS)
            netasset, k_net = _pick(row, _NETASST_KEYS)
            nav, _ = _pick(row, _NAV_KEYS)
            close, _ = _pick(row, _CLOSE_KEYS)
            row_basdd = _pick_str(row, _BASDD_KEYS) or bas_dd_used
            name = _pick_str(row, ["ISU_NM"]) or name_fallback

            if k_shrs and "list_shrs" not in field_map:
                field_map["list_shrs"] = k_shrs
            if k_net and "netasset" not in field_map:
                field_map["netasset"] = k_net

            # 상장좌수 없으면 흐름 산출 불가 — 그래도 history 는 NAV/순자산만이라도 적재 skip (좌수 핵심)
            if list_shrs is None:
                continue

            # 시계열 적재 (같은 거래일이면 갱신, 아니면 append)
            ser = history.get(ticker) or []
            entry = {"date": row_basdd, "list_shrs": list_shrs, "nav": nav, "netasset": netasset, "close": close}
            if ser and ser[-1].get("date") == row_basdd:
                ser[-1] = entry
            else:
                ser.append(entry)
            ser = ser[-HISTORY_CAP:]
            history[ticker] = ser

            # 직전 '다른 거래일' 대비 Δ좌수
            prev = None
            for e in reversed(ser[:-1]):
                if e.get("date") != row_basdd and e.get("list_shrs") is not None:
                    prev = e
                    break

            rec: Dict[str, Any] = {
                "ticker": ticker, "name": name, "category": category,
                "list_shrs": list_shrs, "nav": nav, "netasset": netasset, "close": close,
                "days_n": len(ser),
            }
            if prev:
                d_shrs = list_shrs - float(prev["list_shrs"])
                rec["prev_date"] = prev["date"]
                rec["d_shrs"] = d_shrs
                rec["flow_pct"] = round(d_shrs / float(prev["list_shrs"]) * 100, 3) if prev["list_shrs"] else None
                rec["est_flow"] = round(d_shrs * nav, 0) if nav is not None else None  # 원
                if d_shrs != 0:
                    with_flow += 1
            # 부가정보 — 신규 수집 성공분만 갱신, 실패 시 이전 값 carry
            prev_rec = next((x for x in (existing.get("etfs") or []) if str(x.get("ticker")) == ticker), {})
            extras = _fetch_etf_extras(ticker)
            for k2 in ("ter", "base_index", "manager", "top_holdings"):
                v2 = extras.get(k2) or prev_rec.get(k2)
                if v2:
                    rec[k2] = v2
            etfs.append(rec)

        # 흐름 큰 순(절대값) 정렬 — 흐름 있는 것 우선
        etfs.sort(key=lambda e: abs(e.get("est_flow") or 0), reverse=True)

        out = {
            "updated_at": ts,
            "bas_dd": bas_dd_used,
            "field_map": field_map,
            "etf_count": len(etfs),
            "with_flow_count": with_flow,
            "note": "Δ상장좌수=설정/환매(가격효과 제거) · est_flow=Δ좌수×NAV(원) · 관측 사실, 점수 아님 · 첫 흐름신호 거래일≥2",
            "etfs": etfs,
            "history": history,
        }
        if not field_map.get("list_shrs"):
            # 좌수 키 미매칭 — prod 진단용으로 실제 키 노출 (RULE 8 자가검증)
            out["_available_keys"] = sample_keys
            print(f"[ETF_FLOW] ⚠ 상장좌수 키 미매칭 — 응답 키: {sample_keys}", file=sys.stderr)

        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False)
        logged = True

        summary = {
            "status": "ok",
            "n": len(etfs),
            "with_flow": with_flow,
            "bas_dd": bas_dd_used,
            "field_map": field_map,
        }
        print(f"[ETF_FLOW] {len(etfs)}개 적재(흐름 {with_flow}) bas_dd={bas_dd_used} key={field_map.get('list_shrs','?')}", file=sys.stderr)
        return summary
    finally:
        if not logged and summary.get("status") != "ok":
            print("[ETF_FLOW] 적재 미완료(graceful) — 파이프라인 무중단", file=sys.stderr)


if __name__ == "__main__":
    s = build_etf_flow()
    print(json.dumps(s, ensure_ascii=False, indent=2))
