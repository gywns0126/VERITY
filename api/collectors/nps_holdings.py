"""국민연금(NPS) 보유종목 집계 — AlphaNest 공개 패널용.

🚨 데이터 현실(RULE 7 출처·시점 명시 의무):
  - "실시간 전체 보유종목"을 주는 공식 API 없음.
  - 즉시 가용(신규 secret 0) = DART 5% 대량보유 공시 부산물(reporter='국민연금공단'). 분기 지연, 5%+ 만.
  - 전체 5%+ ~111종목 = data.go.kr #15106890(국민연금 대량보유) — 키+API URL 등록 시 unlock(graceful).
  - 전체 ~1,200종목 = fund.nps.or.kr 연 1회 9개월 지연 공시(미연결).
  - 운용수익률/AUM = 전용 API 없음 → data/nps_fund_overview.json(수기/분기 갱신) seed.

출력 = data/nps_holdings.json. 점수·추천 없음 — 공시 사실(지분율)만, 판단은 사용자.
"""
import json
import os
import re
from typing import Any, Dict, List

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PORTFOLIO_PATH = os.path.join(_ROOT, "data", "portfolio.json")
NAMES_PATH = os.path.join(_ROOT, "data", "kr_stock_names.json")
CATALYST_PATH = os.path.join(_ROOT, "data", "dart_catalyst_alerts.jsonl")
FUND_OVERVIEW_PATH = os.path.join(_ROOT, "data", "nps_fund_overview.json")
OUTPUT_PATH = os.path.join(_ROOT, "data", "nps_holdings.json")

NPS_NAME = "국민연금"


def _load_json(path: str, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return default


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", str(s or "")).strip()


def _strip_corp(s: str) -> str:
    """법인 접미사 제거 정규화 — '코스맥스(주)'/'(주)케이씨씨' → '코스맥스'/'케이씨씨'."""
    s = re.sub(r"\(주\)|㈜|\(유\)|\(재\)|\(사\)|주식회사|\(주식회사\)", "", str(s or ""))
    return _norm(s)


# 영문 이니셜 ↔ 한글 음차 (data.go.kr=한글표기 vs kr_stock_names=영문약칭 불일치 해소)
_INITIALISM = {
    "LG": "엘지", "SK": "에스케이", "GS": "지에스", "KT": "케이티", "CJ": "씨제이",
    "OCI": "오씨아이", "HDC": "에이치디씨", "LIG": "엘아이지", "DL": "디엘", "KCC": "케이씨씨",
    "HD": "에이치디", "HL": "에이치엘", "KB": "케이비", "NH": "엔에이치", "SM": "에스엠",
    "DB": "디비", "BGF": "비지에프", "DN": "디엔", "HMM": "에이치엠엠", "POSCO": "포스코",
}


def _translit_key(nm: str) -> str:
    """선두 영문 이니셜을 한글 음차로 치환한 정규화 키 (LG이노텍 → 엘지이노텍)."""
    s = _strip_corp(nm)
    for en, ko in _INITIALISM.items():
        if s.upper().startswith(en):
            return _norm(ko + s[len(en):])
    return ""


def _name_to_ticker(names: Dict[str, str]) -> Dict[str, str]:
    """{ticker: name} → {정규화 name: ticker}. raw + 접미사제거 + 음차 키 등록. 동명 우선순위 첫 등장."""
    rev: Dict[str, str] = {}
    for tk, nm in (names or {}).items():
        for key in (_norm(nm), _strip_corp(nm), _translit_key(nm)):
            if key and key not in rev:
                rev[key] = tk
    return rev


def _lookup_ticker(name2tk: Dict[str, str], nm: str) -> str:
    return name2tk.get(_norm(nm)) or name2tk.get(_strip_corp(nm)) or ""


def _from_dart_existing(name2tk: Dict[str, str]) -> Dict[str, Dict[str, Any]]:
    """portfolio.json institutional_holders + dart_catalyst 의 국민연금 reporter 집계.

    신규 secret 0 — 이미 적재된 DART 공시 부산물. 운영풀 한정 커버리지.
    """
    out: Dict[str, Dict[str, Any]] = {}
    pf = _load_json(PORTFOLIO_PATH, {})
    recs = (pf.get("recommendations") if isinstance(pf, dict) else None) or []
    for r in recs:
        if not isinstance(r, dict):
            continue
        tk = str(r.get("ticker") or "")
        nm = r.get("name") or r.get("company_name") or ""
        mh = r.get("dart_major_holders") or {}
        for ih in (mh.get("institutional_holders") or []):
            if not isinstance(ih, dict):
                continue
            if NPS_NAME not in str(ih.get("reporter") or ""):
                continue
            pct = ih.get("pct")
            if tk:
                out[tk] = {
                    "ticker": tk,
                    "name": nm or tk,
                    "pct": pct,
                    "qty_change": ih.get("qty_change"),
                    "date": ih.get("date"),
                    "src": "DART majorstock",
                }
    # dart_catalyst jsonl (국민연금 지분공시)
    try:
        with open(CATALYST_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or NPS_NAME not in line:
                    continue
                try:
                    o = json.loads(line)
                except Exception:  # noqa: BLE001
                    continue
                if NPS_NAME not in str(o.get("flr_nm") or ""):
                    continue
                tk = str(o.get("ticker") or "")
                nm = o.get("corp_name") or o.get("name") or ""
                if not tk and nm:
                    tk = _lookup_ticker(name2tk, nm)
                if tk and tk not in out:
                    out[tk] = {
                        "ticker": tk,
                        "name": nm or tk,
                        "pct": o.get("stkrt") or o.get("pct"),
                        "qty_change": None,
                        "date": o.get("rcept_dt") or o.get("date"),
                        "src": "DART 지분공시",
                    }
    except Exception:  # noqa: BLE001
        pass
    return out


# data.go.kr #15106890 국민연금 대량보유 — odcloud OAS(분기별 uddi). 최신=20251231(차기 20260331 등록 2026-06-30).
ODCLOUD_BASE = "https://api.odcloud.kr/api/15106890/v1/"
ODCLOUD_DEFAULT_UDDI = "uddi:1f30a355-f5be-4b09-81c1-a09ba1f4e234"  # 20251231 보고기준일
ODCLOUD_OAS = "https://infuser.odcloud.kr/oas/docs?namespace=15106890/v1"


def _resolve_latest_url() -> str:
    """OAS 명세에서 최신 보고기준일 uddi 경로를 자동 발견(분기 갱신 대비). 실패 시 기본 uddi."""
    env_url = os.environ.get("NPS_DATA_GO_KR_URL", "").strip()
    if env_url:
        return env_url
    try:
        import re as _re
        import requests
        r = requests.get(ODCLOUD_OAS, timeout=12)
        if r.status_code == 200:
            spec = r.json()
            paths = (spec.get("paths") if isinstance(spec, dict) else {}) or {}
            best_date, best_path = "", ""
            for p, ops in paths.items():
                blob = p + " " + json.dumps(ops, ensure_ascii=False)
                dates = _re.findall(r"20\d{6}", blob)
                d = max(dates) if dates else ""
                if "uddi:" in p and d >= best_date:
                    best_date, best_path = d, p
            if best_path:
                return "https://api.odcloud.kr/api" + (best_path if best_path.startswith("/") else "/" + best_path)
    except Exception:  # noqa: BLE001
        pass
    return ODCLOUD_BASE + ODCLOUD_DEFAULT_UDDI


def _from_data_go_kr(name2tk: Dict[str, str]) -> Dict[str, Dict[str, Any]]:
    """data.go.kr #15106890 국민연금 대량보유(5%+ ~111종목). serviceKey 있으면 unlock.

    serviceKey = PUBLIC_DATA_API_KEY(기존 data.go.kr 계정 키, 활용신청한 전 데이터셋 공통) 또는 DATA_GO_KR_KEY.
    엔드포인트 = OAS 자동발견 최신 uddi(분기 갱신 대비) 또는 NPS_DATA_GO_KR_URL env override.
    키 부재/실패 시 {} (DART 경로로 graceful).
    """
    key = ""
    try:
        from api.config import PUBLIC_DATA_API_KEY
        key = (PUBLIC_DATA_API_KEY or "").strip()
    except Exception:  # noqa: BLE001
        key = ""
    key = key or os.environ.get("DATA_GO_KR_KEY", "").strip() or os.environ.get("PUBLIC_DATA_API_KEY", "").strip()
    if not key:
        return {}

    url = _resolve_latest_url()
    out: Dict[str, Dict[str, Any]] = {}
    try:
        import requests
        r = requests.get(url, params={"serviceKey": key, "page": 1, "perPage": 500, "returnType": "JSON"}, timeout=20)
        if r.status_code != 200:
            return {}
        data = r.json()
        rows = data.get("data") if isinstance(data, dict) else None
        for row in (rows or []):
            if not isinstance(row, dict):
                continue
            nm = ""
            pct = None
            asof = None
            for k, v in row.items():
                kk = str(k)
                if "발행" in kk or "기관명" in kk:
                    nm = str(v)
                elif "지분" in kk or "보유비율" in kk:
                    pct = v
                elif "기준일" in kk or "작성" in kk:
                    asof = str(v)
            if not nm:
                continue
            tk = _lookup_ticker(name2tk, nm)
            try:
                pctf = float(str(pct).replace("%", "").replace(",", "")) if pct is not None else None
            except Exception:  # noqa: BLE001
                pctf = None
            rec = {"ticker": tk, "name": nm, "pct": pctf, "qty_change": None, "date": asof, "src": "data.go.kr #15106890"}
            out[tk or ("name:" + _norm(nm))] = rec
    except Exception:  # noqa: BLE001
        return {}
    return out


FULL_OAS = "https://infuser.odcloud.kr/oas/docs?namespace=3070507/v1"


def _from_full_list(name2tk: Dict[str, str]) -> List[Dict[str, Any]]:
    """국민연금 국내주식 전체 투자현황 (data.go.kr 3070507, 연말 기준 ~1,400종목 · 평가액·지분율).

    🚨 계정 활용신청 필요 (2026-07-07 실측: 미신청 = 401 '유효하지 않은 인증키') — 신청 즉시 자동 활성.
    반환 = [{ticker, name, pct, eval_amt_100m, as_of}] · 실패/미신청 = [] (기존 5%+ 경로 무영향).
    용도 = 공개 패널 '내 종목 겹침(5% 미만 포함)' — 리스트 전체 노출은 5%+ 유지(볼륨).
    """
    key = ""
    try:
        from api.config import PUBLIC_DATA_API_KEY
        key = (PUBLIC_DATA_API_KEY or "").strip()
    except Exception:  # noqa: BLE001
        key = ""
    # 경로 A: 수동 CSV 시드 (data/nps_full_holdings.csv — data.go.kr 파일 다운로드 그대로 투입, 연 1회)
    csv_path = os.path.join(_ROOT, "data", "nps_full_holdings.csv")
    if os.path.isfile(csv_path):
        try:
            import csv as _csv
            rows: List[Dict[str, Any]] = []
            with open(csv_path, encoding="utf-8-sig", newline="") as f:
                for row in _csv.DictReader(f):
                    nm, pct, amt, asof = "", None, None, ""
                    for k, v in row.items():
                        kk = str(k or "")
                        if "종목명" in kk or kk == "종목":
                            nm = str(v or "").strip()
                        elif "지분율" in kk or "지분" in kk:
                            try:
                                pct = float(str(v).replace("%", "").replace(",", ""))
                            except (TypeError, ValueError):
                                pct = None
                        elif "평가액" in kk:
                            try:
                                amt = float(str(v).replace(",", ""))
                            except (TypeError, ValueError):
                                amt = None
                        elif "기준" in kk or "년도" in kk:
                            asof = str(v or "").strip()
                    if not nm:
                        continue
                    tk = _lookup_ticker(name2tk, nm)
                    if tk:
                        rows.append({"ticker": tk, "name": nm, "pct": pct, "eval_amt_100m": amt, "as_of": asof or "csv"})
            if rows:
                meta = _load_json(os.path.join(_ROOT, "data", "nps_full_holdings.meta.json"), {}) or {}
                asof2 = str(meta.get("as_of") or "")
                if asof2:
                    for r0 in rows:
                        if r0.get("as_of") in ("", "csv"):
                            r0["as_of"] = asof2
                return rows
        except Exception:  # noqa: BLE001
            pass

    # 경로 B: odcloud API (활용신청 후 활성)
    key = key or os.environ.get("PUBLIC_DATA_API_KEY", "").strip()
    if not key:
        return []
    try:
        import requests
        spec = requests.get(FULL_OAS, timeout=15).json()
        paths = list(((spec.get("paths") if isinstance(spec, dict) else {}) or {}).keys())
        if not paths:
            return []
        # 각 uddi 의 데이터 기준일은 경로로 판별 불가 → 첫 200 응답 중 '기준일' 최댓값 path 선택
        best_rows, best_asof = [], ""
        for p in paths:
            try:
                r = requests.get("https://api.odcloud.kr/api" + p,
                                 params={"serviceKey": key, "page": 1, "perPage": 3, "returnType": "JSON"}, timeout=15)
                if r.status_code != 200:
                    continue
                sample = (r.json().get("data") or [])
                if not sample:
                    continue
                asof = ""
                for k, v in sample[0].items():
                    if "기준" in str(k) or "년도" in str(k):
                        asof = str(v)
                asof = asof or p[-12:]
                if asof >= best_asof:
                    best_asof, best_path = asof, p
                    best_rows = [1]  # 존재 표식
            except Exception:  # noqa: BLE001
                continue
        if not best_rows:
            return []
        rows: List[Dict[str, Any]] = []
        page = 1
        while page <= 6:  # ~1,400행 = perPage 500 × 3 (여유 6)
            r = requests.get("https://api.odcloud.kr/api" + best_path,
                             params={"serviceKey": key, "page": page, "perPage": 500, "returnType": "JSON"}, timeout=25)
            if r.status_code != 200:
                break
            batch = r.json().get("data") or []
            if not batch:
                break
            for row in batch:
                nm, pct, amt, asof = "", None, None, best_asof
                for k, v in row.items():
                    kk = str(k)
                    if "종목명" in kk or "종목" == kk:
                        nm = str(v)
                    elif "지분율" in kk or "지분" in kk:
                        try:
                            pct = float(str(v).replace("%", "").replace(",", ""))
                        except (TypeError, ValueError):
                            pct = None
                    elif "평가액" in kk:
                        try:
                            amt = float(str(v).replace(",", ""))
                        except (TypeError, ValueError):
                            amt = None
                if not nm:
                    continue
                tk = _lookup_ticker(name2tk, nm)
                if not tk:
                    continue
                rows.append({"ticker": tk, "name": nm, "pct": pct, "eval_amt_100m": amt, "as_of": asof})
            page += 1
        return rows
    except Exception:  # noqa: BLE001
        return []


def _norm_us(nm: str) -> str:
    """미장 영문 종목명 정규화 — 'APPLE INC' ↔ 'Apple Inc.' 매칭용."""
    s = re.sub(r"[^A-Z0-9 ]", " ", str(nm or "").upper())
    for suf in (" INCORPORATED", " CORPORATION", " COMPANY", " HOLDINGS", " HOLDING", " GROUP",
                " INC", " CORP", " LTD", " PLC", " CO", " SA", " NV", " AG", " ADR", " CL A", " CL B", " CLASS A", " CLASS B"):
        while s.endswith(suf):
            s = s[: -len(suf)]
    return re.sub(r"\s+", " ", s).strip()


def _from_full_overseas() -> List[Dict[str, Any]]:
    """해외주식 전체 투자현황 CSV (data/nps_full_holdings_overseas.csv) → 미국 티커 매칭 행만.

    매칭 = us_stock_report_public(+smallcap) 종목명 정규화 사전. 미매칭(비미국·매핑실패) = 제외(사실만).
    """
    csv_path = os.path.join(_ROOT, "data", "nps_full_holdings_overseas.csv")
    if not os.path.isfile(csv_path):
        return []
    name2tk: Dict[str, str] = {}
    for fn in ("us_stock_report_public.json", "us_stock_report_us_smallcap.json"):
        doc = _load_json(os.path.join(_ROOT, "data", fn), {}) or {}
        arr = doc.get("stocks") or []
        rows0 = arr if isinstance(arr, list) else list(arr.values())
        for s in rows0:
            tk = str(s.get("ticker") or "")
            for cand in (s.get("name"), s.get("name_en")):
                key = _norm_us(cand or "")
                if tk and key and key not in name2tk:
                    name2tk[key] = tk
    if not name2tk:
        return []
    meta = _load_json(os.path.join(_ROOT, "data", "nps_full_holdings.meta.json"), {}) or {}
    asof = str(meta.get("as_of") or "")
    out: List[Dict[str, Any]] = []
    try:
        import csv as _csv
        with open(csv_path, encoding="utf-8-sig", newline="") as f:
            for row in _csv.DictReader(f):
                nm, pct, amt = "", None, None
                for k, v in row.items():
                    kk = str(k or "")
                    if "종목명" in kk:
                        nm = str(v or "").strip()
                    elif "지분율" in kk:
                        try:
                            pct = float(str(v).replace(",", ""))
                        except (TypeError, ValueError):
                            pct = None
                    elif "평가액" in kk:
                        try:
                            amt = float(str(v).replace(",", ""))
                        except (TypeError, ValueError):
                            amt = None
                tk = name2tk.get(_norm_us(nm))
                if tk:
                    out.append({"ticker": tk, "name": nm, "pct": pct, "eval_amt_100m": amt, "as_of": asof or "csv"})
    except Exception:  # noqa: BLE001
        return []
    return out


def build_nps_holdings() -> Dict[str, Any]:
    from datetime import datetime, timezone, timedelta
    kst = timezone(timedelta(hours=9))

    names = _load_json(NAMES_PATH, {}) or {}
    name2tk = _name_to_ticker(names)

    merged: Dict[str, Dict[str, Any]] = {}
    merged.update(_from_dart_existing(name2tk))
    # data.go.kr 가 더 권위(전체 5%+) — 같은 ticker 면 덮어씀
    for k, v in _from_data_go_kr(name2tk).items():
        merged[v.get("ticker") or k] = v

    holdings = [h for h in merged.values() if h.get("pct") is not None]
    holdings.sort(key=lambda h: (-(h.get("pct") or 0), h.get("ticker") or ""))

    fund = _load_json(FUND_OVERVIEW_PATH, None)

    full_rows = _from_full_list(name2tk)
    full_us_rows = _from_full_overseas()
    has_full = any(h.get("src", "").startswith("data.go.kr") for h in holdings)
    return {
        "generated_at": datetime.now(kst).isoformat(),
        "source": "DART 5% 대량보유 공시" + (" + data.go.kr 국민연금 대량보유" if has_full else ""),
        "coverage": "full_5pct" if has_full else "operating_pool",
        "count": len(holdings),
        "holdings": holdings,
        "full": full_rows,          # 전체 투자현황(연말, KR ~1,200) — 겹침 검사용 (5% 미만 포함)
        "full_n": len(full_rows),
        "full_us": full_us_rows,    # 해외(미장 매칭분) 전체 투자현황 — 미장 겹침 검사용
        "full_us_n": len(full_us_rows),
        "fund": fund,  # 운용수익률/AUM (data/nps_fund_overview.json, 수기·분기 갱신). 없으면 null
        "note": "국민연금 5% 이상 대량보유 공시 기준 — 전체 보유종목(약 1,200) 아님 · 분기 지연 · 지분율은 법적 강제공시 사실, 점수·추천 아님.",
    }


def main() -> int:
    try:
        out = build_nps_holdings()
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
        print(f"[nps_holdings] {out['count']}종목 ({out['coverage']}) → {OUTPUT_PATH}")
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[nps_holdings] FAIL: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
