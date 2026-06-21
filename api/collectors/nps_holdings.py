"""국민연금(NPS) 보유종목 집계 — 골든구스 공개 패널용.

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


def _name_to_ticker(names: Dict[str, str]) -> Dict[str, str]:
    """{ticker: name} → {정규화 name: ticker}. 동명 우선순위는 첫 등장."""
    rev: Dict[str, str] = {}
    for tk, nm in (names or {}).items():
        key = _norm(nm)
        if key and key not in rev:
            rev[key] = tk
    return rev


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
                    tk = name2tk.get(_norm(nm), "")
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


def _from_data_go_kr(name2tk: Dict[str, str]) -> Dict[str, Dict[str, Any]]:
    """data.go.kr #15106890 국민연금 대량보유(5%+ ~111종목). 키+URL env 등록 시 unlock.

    fileData 데이터셋은 odcloud API URL(uddi 포함)이 데이터셋별이라 추측 불가 →
    NPS_DATA_GO_KR_URL(전체 API URL) + DATA_GO_KR_KEY(serviceKey) 둘 다 있을 때만 호출.
    없으면 {} (DART 경로로 graceful).
    """
    url = os.environ.get("NPS_DATA_GO_KR_URL", "").strip()
    key = os.environ.get("DATA_GO_KR_KEY", "").strip()
    if not url or not key:
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    try:
        import requests

        sep = "&" if "?" in url else "?"
        r = requests.get(f"{url}{sep}serviceKey={key}&page=1&perPage=300&returnType=JSON", timeout=15)
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
                if "발행" in kk or "종목" in kk or "기관명" in kk:
                    nm = str(v)
                elif "지분" in kk or "보유비율" in kk:
                    pct = v
                elif "기준일" in kk or "작성" in kk:
                    asof = str(v)
            tk = name2tk.get(_norm(nm), "")
            if not nm:
                continue
            try:
                pctf = float(str(pct).replace("%", "").replace(",", "")) if pct is not None else None
            except Exception:  # noqa: BLE001
                pctf = None
            rec = {"ticker": tk, "name": nm, "pct": pctf, "qty_change": None, "date": asof, "src": "data.go.kr #15106890"}
            out[tk or ("name:" + _norm(nm))] = rec
    except Exception:  # noqa: BLE001
        return {}
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

    has_full = any(h.get("src", "").startswith("data.go.kr") for h in holdings)
    return {
        "generated_at": datetime.now(kst).isoformat(),
        "source": "DART 5% 대량보유 공시" + (" + data.go.kr 국민연금 대량보유" if has_full else ""),
        "coverage": "full_5pct" if has_full else "operating_pool",
        "count": len(holdings),
        "holdings": holdings,
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
