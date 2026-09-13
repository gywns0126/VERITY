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
import time
from typing import Any, Dict, List, Optional, Tuple

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PORTFOLIO_PATH = os.path.join(_ROOT, "data", "portfolio.json")
NAMES_PATH = os.path.join(_ROOT, "data", "kr_stock_names.json")
CATALYST_PATH = os.path.join(_ROOT, "data", "dart_catalyst_alerts.jsonl")
FUND_OVERVIEW_PATH = os.path.join(_ROOT, "data", "nps_fund_overview.json")
OUTPUT_PATH = os.path.join(_ROOT, "data", "nps_holdings.json")
HEARTBEAT_PATH = os.path.join(_ROOT, "data", "metadata", "nps_holdings_heartbeat.json")

NPS_NAME = "국민연금"

_SOURCE_PRIORITY = {
    "data.go.kr #15106890": 10,
    "data.go.kr #15106890 (분기 확정 CSV)": 20,
    "DART majorstock": 30,
    "DART elestock": 30,
    "DART majorstock live": 40,
    "DART elestock live": 40,
}


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


def _date_key(value: Any) -> str:
    """날짜 비교용 YYYYMMDD. 형식이 불완전하면 빈 문자열."""
    digits = re.sub(r"\D", "", str(value or ""))[:8]
    return digits if len(digits) == 8 else ""


def _iso_date(value: Any) -> str:
    key = _date_key(value)
    return f"{key[:4]}-{key[4:6]}-{key[6:8]}" if key else ""


def _merge_latest(target: Dict[str, Dict[str, Any]], key: str, row: Dict[str, Any]) -> None:
    """종목별 최신 원문을 유지하고 같은 날이면 DART 원문을 우선한다."""
    if not key or not isinstance(row, dict):
        return
    prev = target.get(key)
    if prev is None:
        target[key] = row
        return
    prev_date = _date_key(prev.get("date"))
    new_date = _date_key(row.get("date"))
    prev_rank = _SOURCE_PRIORITY.get(str(prev.get("src") or ""), 0)
    new_rank = _SOURCE_PRIORITY.get(str(row.get("src") or ""), 0)
    if new_date > prev_date or (new_date == prev_date and new_rank >= prev_rank):
        target[key] = row


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
    """portfolio.json institutional_holders의 국민연금 reporter 집계.

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
    return out


def _nps_catalyst_events() -> Tuple[Dict[str, Dict[str, str]], Dict[str, Any]]:
    """국민연금 DART 공시 이벤트와 입력 무결성 감사를 함께 반환한다."""
    out: Dict[str, Dict[str, str]] = {}
    audit: Dict[str, Any] = {
        "event_source_ok": False,
        "event_source_rows": 0,
        "event_source_invalid_rows": 0,
        "event_source_latest": "",
    }
    try:
        with open(CATALYST_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    o = json.loads(line)
                except Exception:  # noqa: BLE001
                    audit["event_source_invalid_rows"] += 1
                    continue
                if not isinstance(o, dict):
                    audit["event_source_invalid_rows"] += 1
                    continue
                audit["event_source_rows"] += 1
                row_date = _date_key(o.get("rcept_dt") or o.get("date"))
                if row_date > audit["event_source_latest"]:
                    audit["event_source_latest"] = row_date
                if NPS_NAME not in str(o.get("flr_nm") or ""):
                    continue
                tk = re.sub(r"\D", "", str(o.get("ticker") or ""))[:6]
                nm = o.get("corp_name") or o.get("name") or ""
                dt = row_date
                if len(tk) != 6 or not dt:
                    audit["event_source_invalid_rows"] += 1
                    continue
                prev = out.get(tk)
                if prev is None or dt > prev.get("event_date", ""):
                    out[tk] = {"ticker": tk, "name": str(nm or tk), "event_date": dt}
    except Exception as exc:  # noqa: BLE001
        audit["event_source_error"] = type(exc).__name__
        return out, audit
    audit["event_source_ok"] = (
        audit["event_source_rows"] > 0
        and audit["event_source_invalid_rows"] == 0
    )
    return out, audit


def _from_previous_live() -> Dict[str, Dict[str, Any]]:
    """이전 공개 산출물의 DART 실조회값을 증분 캐시로 재사용한다."""
    doc = _load_json(OUTPUT_PATH, {}) or {}
    out: Dict[str, Dict[str, Any]] = {}
    for row in doc.get("holdings") or []:
        if not isinstance(row, dict) or not str(row.get("src") or "").endswith(" live"):
            continue
        tk = re.sub(r"\D", "", str(row.get("ticker") or ""))[:6]
        if len(tk) == 6 and row.get("pct") is not None:
            _merge_latest(out, tk, dict(row))
    return out


def _float_or_none(value: Any) -> Optional[float]:
    try:
        return float(str(value).replace(",", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return None


def _latest_nps_from_payloads(
    major_rows: List[Dict[str, Any]], officer_rows: List[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """majorstock·elestock 응답에서 국민연금의 가장 최근 신고값을 고른다."""
    candidates: List[Dict[str, Any]] = []
    for row in major_rows or []:
        if NPS_NAME not in str(row.get("repror") or ""):
            continue
        candidates.append({
            "pct": _float_or_none(row.get("stkrt")),
            "qty_change": _float_or_none(row.get("stkqy_irds")),
            "date": _iso_date(row.get("rcept_dt")),
            "src": "DART majorstock live",
        })
    for row in officer_rows or []:
        if NPS_NAME not in str(row.get("repror") or ""):
            continue
        candidates.append({
            "pct": _float_or_none(row.get("sp_stock_lmp_rate")),
            "qty_change": _float_or_none(row.get("sp_stock_lmp_irds_cnt")),
            "date": _iso_date(row.get("rcept_dt")),
            "src": "DART elestock live",
        })
    candidates = [r for r in candidates if r.get("date") and r.get("pct") is not None]
    if not candidates:
        return None
    return max(candidates, key=lambda r: (_date_key(r.get("date")), _SOURCE_PRIORITY.get(r.get("src"), 0)))


def _dart_api_key() -> str:
    """설정 모듈과 환경변수 양쪽에서 DART 키를 읽는다."""
    imported = ""
    try:
        from api.config import DART_API_KEY
        imported = str(DART_API_KEY or "").strip()
    except Exception:  # noqa: BLE001
        pass
    return imported or os.environ.get("DART_API_KEY", "").strip()


def _from_dart_live(
    name2tk: Dict[str, str], baseline: Dict[str, Dict[str, Any]]
) -> Tuple[Dict[str, Dict[str, Any]], set, Dict[str, Any]]:
    """분기 자료 이후 국민연금 공시가 생긴 종목만 DART 원문으로 증분 갱신한다."""
    dart_api_key = _dart_api_key()
    events, source_audit = _nps_catalyst_events()
    candidates = {
        tk: event for tk, event in events.items()
        if event.get("event_date", "") > _date_key((baseline.get(tk) or {}).get("date"))
    }
    audit: Dict[str, Any] = {
        **source_audit,
        "event_tickers": len(events),
        "candidate_tickers": len(candidates),
        "updated_tickers": 0,
        "retired_tickers": 0,
        "unresolved_tickers": 0,
        "api_calls": 0,
    }
    if not dart_api_key or not candidates:
        audit["unresolved_tickers"] = len(candidates) if not dart_api_key else 0
        return {}, set(), audit

    import requests
    from api.collectors.dart_corp_code import get_corp_code

    session = requests.Session()
    out: Dict[str, Dict[str, Any]] = {}
    retired = set()
    for tk, event in sorted(candidates.items()):
        corp_code = get_corp_code(tk)
        if not corp_code:
            audit["unresolved_tickers"] += 1
            continue
        payloads: Dict[str, List[Dict[str, Any]]] = {"major": [], "officer": []}
        failed = False
        for kind, url in (
            ("major", "https://opendart.fss.or.kr/api/majorstock.json"),
            ("officer", "https://opendart.fss.or.kr/api/elestock.json"),
        ):
            try:
                response = session.get(
                    url,
                    params={"crtfc_key": dart_api_key, "corp_code": corp_code},
                    timeout=15,
                )
                audit["api_calls"] += 1
                time.sleep(0.08)
                body = response.json()
                status = str(body.get("status") or "")
                if status == "000":
                    payloads[kind] = body.get("list") or []
                elif status not in ("013",):
                    failed = True
            except Exception:  # noqa: BLE001
                failed = True
        if failed:
            audit["unresolved_tickers"] += 1
            continue
        latest = _latest_nps_from_payloads(payloads["major"], payloads["officer"])
        if latest is None or _date_key(latest.get("date")) < event.get("event_date", ""):
            audit["unresolved_tickers"] += 1
            continue
        if (latest.get("pct") or 0) <= 0:
            retired.add(tk)
            audit["retired_tickers"] += 1
            continue
        latest.update({
            "ticker": tk,
            "name": str((baseline.get(tk) or {}).get("name") or event.get("name") or tk),
        })
        out[tk] = latest
        audit["updated_tickers"] += 1
        time.sleep(0.05)
    return out, retired, audit


# data.go.kr #15106890 국민연금 대량보유 — odcloud OAS(분기별 uddi).
# 2026-09-13 공식 OAS 확인 최신=20260331. OAS 조회 실패 시에도 같은 분기로 강등한다.
ODCLOUD_BASE = "https://api.odcloud.kr/api/15106890/v1/"
ODCLOUD_DEFAULT_UDDI = "uddi:5536983c-fa78-46c7-bef1-b602ec951fcf"  # 20260331 보고기준일
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
            # 공개 보유 목록은 종목 리포트로 연결되므로 식별 가능한 상장 코드만 포함한다.
            # 원천 이름을 억지로 부분매칭하면 동명사 오염이 생기므로 미매칭은 제외한다.
            if not tk:
                continue
            try:
                pctf = float(str(pct).replace("%", "").replace(",", "")) if pct is not None else None
            except Exception:  # noqa: BLE001
                pctf = None
            # 🚨 '5% 이상 대량보유' 리스트인데 지분율 <1% = CSV 파일판 오값 또는 청산분(현재 5%+ 아님).
            #   실측: 042670 CSV 0.00%(실제 DART 13.63%)·012510 CSV 0.94%(실제 8.22%) — 오값 노출 차단.
            #   DART 소스(_from_dart_existing)에 정확값 있으면 병합에서 대체, 없으면 오값 미노출.
            if pctf is not None and pctf < 1.0:
                continue
            rec = {"ticker": tk, "name": nm, "pct": pctf, "qty_change": None, "date": asof, "src": "data.go.kr #15106890"}
            _merge_latest(out, tk, rec)
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


def _from_major_csv(name2tk: Dict[str, str]) -> Dict[str, Dict[str, Any]]:
    """대량보유(5%+) CSV 시드 (data/nps_major_holdings.csv, data.go.kr 15106890 파일판 — 분기 확정본).

    API/DART 경로보다 권위(최신 기준일 확정) — build 병합에서 마지막 덮어쓰기.
    """
    csv_path = os.path.join(_ROOT, "data", "nps_major_holdings.csv")
    if not os.path.isfile(csv_path):
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    try:
        import csv as _csv
        with open(csv_path, encoding="utf-8-sig", newline="") as f:
            for row in _csv.DictReader(f):
                nm, pct, dt = "", None, ""
                for k, v in row.items():
                    kk = str(k or "").strip()
                    if "발행기관" in kk or "종목명" in kk:
                        nm = str(v or "").strip()
                    elif "지분율" in kk:
                        try:
                            pct = float(str(v).replace(",", ""))
                        except (TypeError, ValueError):
                            pct = None
                    elif "기준일" in kk:
                        dt = str(v or "").strip()
                # 🚨 '5% 이상 대량보유' 시드인데 지분율 <1% = 파일판 CSV 오값/청산분 → 제외.
                #   실측: 042670 0.00%(실제 DART 13.63%)·012510 0.94%(실제 8.22%). DART 소스 정확값이 있으면 병합에서 대체.
                if not nm or pct is None or pct < 1.0:
                    continue
                tk = _lookup_ticker(name2tk, nm)
                if tk:
                    _merge_latest(
                        out,
                        tk,
                        {"ticker": tk, "name": _strip_corp(nm), "pct": pct, "qty_change": None,
                         "date": dt, "src": "data.go.kr #15106890 (분기 확정 CSV)"},
                    )
    except Exception:  # noqa: BLE001
        return {}
    return out


def _asset_mix() -> List[Dict[str, Any]]:
    """기금 포트폴리오 현황 CSV (data/nps_portfolio_mix.csv) → 자산군 비중 (최신 열 기준, 사실)."""
    csv_path = os.path.join(_ROOT, "data", "nps_portfolio_mix.csv")
    if not os.path.isfile(csv_path):
        return []
    try:
        import csv as _csv
        rows = list(_csv.reader(open(csv_path, encoding="utf-8-sig", newline="")))
        if len(rows) < 3:
            return []
        header = rows[0]
        # 최신 데이터 열 = 3번째(현황 다음, 'YYYY년 M월' 형식) — as_of 라벨로 사용
        col = 2
        as_of = str(header[col]).split("(")[0].strip()
        total = None
        mix: List[Dict[str, Any]] = []
        for r in rows[1:]:
            if len(r) <= col or not r[0].strip():
                continue
            name = r[0].strip()
            try:
                amt = float(str(r[col]).replace(",", ""))
            except (TypeError, ValueError):
                continue
            if name.startswith("전체"):
                total = amt
                continue
            label = name.replace("금융부문(", "").replace(")", "").replace("부문", "")
            mix.append({"name": label, "amount_bil": amt})
        if total:
            for m in mix:
                m["pct"] = round(m["amount_bil"] / total * 100, 1)
        return [{"as_of": as_of, "total_bil": total, "mix": mix}]
    except Exception:  # noqa: BLE001
        return []


def build_nps_holdings() -> Dict[str, Any]:
    from datetime import datetime, timezone, timedelta
    kst = timezone(timedelta(hours=9))

    names = _load_json(NAMES_PATH, {}) or {}
    name2tk = _name_to_ticker(names)

    # 분기 원천을 바탕으로 두되, 같은 종목은 출처 순서가 아니라 기준일로 병합한다.
    # 이전 구현은 3월 분기 CSV가 7~9월 DART 값을 무조건 덮어 최신 공시가 사라졌다.
    merged: Dict[str, Dict[str, Any]] = {}
    for source_rows in (
        _from_data_go_kr(name2tk),
        _from_major_csv(name2tk),
        _from_previous_live(),
        _from_dart_existing(name2tk),
    ):
        for k, v in source_rows.items():
            _merge_latest(merged, v.get("ticker") or k, v)

    live_rows, retired, dart_refresh = _from_dart_live(name2tk, merged)
    for tk in retired:
        merged.pop(tk, None)
    for tk, row in live_rows.items():
        _merge_latest(merged, tk, row)

    holdings = [h for h in merged.values() if h.get("pct") is not None]
    holdings.sort(key=lambda h: (-(h.get("pct") or 0), h.get("ticker") or ""))

    fund = _load_json(FUND_OVERVIEW_PATH, None)

    full_rows = _from_full_list(name2tk)
    full_us_rows = _from_full_overseas()
    has_full = any(h.get("src", "").startswith("data.go.kr") for h in holdings)
    as_of_latest = max((_iso_date(h.get("date")) for h in holdings), default="")
    source_counts: Dict[str, int] = {}
    for h in holdings:
        src = str(h.get("src") or "unknown")
        source_counts[src] = source_counts.get(src, 0) + 1
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
        "asset_mix": _asset_mix(),  # 자산군 비중 (기금 포트폴리오 현황 CSV, 분기)
        "fund": fund,  # 운용수익률/AUM (data/nps_fund_overview.json, 수기·분기 갱신). 없으면 null
        "as_of_latest": as_of_latest,
        "source_counts": source_counts,
        "dart_refresh": dart_refresh,
        "note": "국민연금 5% 대량보유 공시 이력의 종목별 최신 신고 기준 — 5% 아래로 내려간 최종 신고 포함 · 전체 보유종목(약 1,200) 아님 · 지분율은 법적 공시 사실, 점수·추천 아님.",
    }


def _semantic_document(doc: Dict[str, Any]) -> Dict[str, Any]:
    """수집 시각만 제외한 공개 산출물의 의미 단위를 반환한다."""
    return {key: value for key, value in doc.items() if key != "generated_at"}


def _write_json(path: str, doc: Dict[str, Any]) -> None:
    """중간 파일을 거쳐 JSON을 교체해 부분 기록을 남기지 않는다."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    os.replace(tmp_path, path)


def _write_success_heartbeat(out: Dict[str, Any], audit: Dict[str, Any]) -> None:
    from datetime import datetime, timedelta, timezone

    kst = timezone(timedelta(hours=9))
    heartbeat = {
        "last_run_at": datetime.now(kst).isoformat(),
        "status": "ok",
        "count": int(out.get("count") or 0),
        "as_of_latest": str(out.get("as_of_latest") or ""),
        "event_source_latest": _iso_date(audit.get("event_source_latest")),
        "event_tickers": int(audit.get("event_tickers") or 0),
        "candidate_tickers": int(audit.get("candidate_tickers") or 0),
        "unresolved_tickers": int(audit.get("unresolved_tickers") or 0),
    }
    _write_json(HEARTBEAT_PATH, heartbeat)


def _notify_failure(reason: str, audit: Dict[str, Any]) -> bool:
    """국민연금 수집 실패를 야간 묵음과 무관하게 즉시 알린다."""
    try:
        from api.notifications.telegram import send_message

        return send_message(
            "\n".join([
                "🔴 국민연금 보유 수집 중단",
                reason,
                (
                    f"이벤트 {int(audit.get('event_tickers') or 0)}개 · "
                    f"신규 대상 {int(audit.get('candidate_tickers') or 0)}개 · "
                    f"미해결 {int(audit.get('unresolved_tickers') or 0)}개"
                ),
                "기존 정상 공개본은 유지했습니다.",
            ]),
            dedupe=True,
            bypass_quiet=True,
            source="nps_holdings",
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[nps_holdings] alert FAIL: {type(exc).__name__}")
        return False


def main() -> int:
    current_audit: Dict[str, Any] = {}
    try:
        previous = _load_json(OUTPUT_PATH, {}) or {}
        out = build_nps_holdings()
        current_audit = out.get("dart_refresh") or {}
        failures = []
        if current_audit.get("event_source_ok", True) is False:
            failures.append(
                "DART 이벤트 입력 무결성 실패"
                f"(유효 {int(current_audit.get('event_source_rows') or 0)}행, "
                f"오류 {int(current_audit.get('event_source_invalid_rows') or 0)}행)"
            )
        if int(current_audit.get("unresolved_tickers") or 0) > 0:
            failures.append(
                f"신규 공시 {int(current_audit.get('unresolved_tickers') or 0)}종목 미해결"
            )
        if failures:
            reason = " · ".join(failures)
            print(f"[nps_holdings] FAIL-CLOSED: {reason}")
            _notify_failure(reason, current_audit)
            return 2

        # 이번 실행의 무결성 감사와 마지막 대량 실조회 감사는 목적이 다르므로 둘 다 보존한다.
        out["dart_check"] = current_audit
        if current_audit.get("candidate_tickers") == 0 and previous.get("dart_refresh"):
            # 새 대상이 없는 반복 실행은 마지막 실조회 감사값을 지우지 않는다.
            out["dart_refresh"] = previous["dart_refresh"]
        if previous and _semantic_document(previous) == _semantic_document(out):
            _write_success_heartbeat(out, current_audit)
            print(f"[nps_holdings] unchanged ({out['count']}종목, {out.get('as_of_latest') or 'n/a'})")
            return 0
        _write_json(OUTPUT_PATH, out)
        _write_success_heartbeat(out, current_audit)
        print(f"[nps_holdings] {out['count']}종목 ({out['coverage']}) → {OUTPUT_PATH}")
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[nps_holdings] FAIL: {e}")
        _notify_failure(f"실행 예외: {type(e).__name__}", current_audit)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
