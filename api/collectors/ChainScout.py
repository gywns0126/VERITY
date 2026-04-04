"""
ChainScout — OpenDART 사업보고서 원문에서 '주요 매출처' 등 앵커 주변 스니펫 추출 (프로토타입).

DartScout와 동일하게 DART_API_KEY·mapping.json(corp_code)을 사용한다.
  - list.json 으로 최근 사업보고서 rcept_no 탐색
  - document.xml 로 공시 원문(zip) 수신 → 텍스트화 → 앵커 기준 ±100자(가변, 총 ~200자대) 윈도우

단독 실행 (프로젝트 루트):
  python -m api.collectors.ChainScout
환경변수: CHAIN_SCOUT_TICKER=005930 (또는 005930.KS), CHAIN_SCOUT_BGN_DE=20240101 (선택)
"""
from __future__ import annotations

import io
import json
import os
import re
import sys
import time
import zipfile
from typing import Any, Dict, List, Optional, Tuple

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from api.collectors.DartScout import BASE_URL
from api.collectors.dart_corp_code import get_corp_code
from api.config import CHAIN_SNIPPETS_PATH, DART_API_KEY, DATA_DIR, now_kst

API_DELAY = 0.5

# 사업보고서 본문에서 매출처·고객 관련 구절 탐색
ANCHOR_PHRASES: Tuple[str, ...] = (
    "주요 매출처",
    "주요매출처",
    "매출처",
    "주요 고객",
    "주요고객",
    "판매처",
)


def _dart_list(corp_code: str, bgn_de: str, end_de: str) -> Dict[str, Any]:
    if not DART_API_KEY:
        raise RuntimeError("DART_API_KEY 환경변수가 설정되지 않았습니다.")
    params = {
        "crtfc_key": DART_API_KEY,
        "corp_code": corp_code,
        "bgn_de": bgn_de,
        "end_de": end_de,
        "page_count": "100",
        "sort": "date",
        "sort_mth": "desc",
    }
    resp = requests.get(f"{BASE_URL}/list.json", params=params, timeout=30)
    resp.raise_for_status()
    time.sleep(API_DELAY)
    data = resp.json()
    if data.get("status") != "000":
        return {"list": [], "message": data.get("message", ""), "status": data.get("status")}
    return data


def find_latest_business_report_rcept_no(
    corp_code: str,
    bgn_de: str,
    end_de: str,
) -> Optional[Tuple[str, str, str]]:
    """(rcept_no, report_nm, rcept_dt) 또는 None."""
    data = _dart_list(corp_code, bgn_de, end_de)
    best: Optional[Tuple[str, str, str]] = None
    for item in data.get("list") or []:
        nm = (item.get("report_nm") or "").strip()
        if "사업보고서" not in nm:
            continue
        rid = (item.get("rcept_no") or "").strip()
        dt = (item.get("rcept_dt") or "").strip()
        if not rid:
            continue
        if best is None or dt > best[2]:
            best = (rid, nm, dt)
    return best


def fetch_document_archive(rcept_no: str) -> bytes:
    params = {"crtfc_key": DART_API_KEY, "rcept_no": rcept_no}
    resp = requests.get(f"{BASE_URL}/document.xml", params=params, timeout=120)
    resp.raise_for_status()
    time.sleep(API_DELAY)
    return resp.content


def _strip_markup(s: str) -> str:
    t = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", s)
    t = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", t)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _archive_to_plain_text(content: bytes) -> str:
    """zip 내 XML/HTML을 평문으로 합침 (lxml 불필요)."""
    buf = io.BytesIO(content)
    if content[:2] != b"PK":
        try:
            txt = content.decode("utf-8", errors="ignore")
            if "status" in txt[:200] and "message" in txt:
                return ""
        except Exception:
            pass
        return ""
    parts: List[str] = []
    try:
        with zipfile.ZipFile(buf) as zf:
            for name in zf.namelist():
                if name.endswith("/"):
                    continue
                raw = zf.read(name)
                try:
                    s = raw.decode("utf-8", errors="ignore")
                except Exception:
                    continue
                if "<" in s and ">" in s:
                    parts.append(_strip_markup(s))
                else:
                    parts.append(s)
    except zipfile.BadZipFile:
        return ""
    merged = " ".join(parts)
    return re.sub(r"\s+", " ", merged).strip()


def extract_anchor_windows(
    text: str,
    half_window: int = 100,
    max_snippets_per_anchor: int = 4,
) -> List[Dict[str, Any]]:
    """
    앵커 문자열 위치 기준 앞뒤 half_window 자(공백 정규화 후) 잘라 스니펫 리스트.
    half_window=100 → 앵커 포함 총 ~200자 + 앵커 길이.
    """
    if not text:
        return []
    out: List[Dict[str, Any]] = []
    seen = set()
    for anchor in ANCHOR_PHRASES:
        start = 0
        n = 0
        while n < max_snippets_per_anchor:
            idx = text.find(anchor, start)
            if idx < 0:
                break
            lo = max(0, idx - half_window)
            hi = min(len(text), idx + len(anchor) + half_window)
            snippet = text[lo:hi].strip()
            key = (anchor, idx)
            if key not in seen and len(snippet) > 5:
                seen.add(key)
                out.append(
                    {
                        "anchor": anchor,
                        "char_start": lo,
                        "char_end": hi,
                        "snippet": snippet,
                    }
                )
            n += 1
            start = idx + len(anchor)
    return out


def scout_major_customer_snippets(
    ticker: str,
    bgn_de: Optional[str] = None,
    end_de: Optional[str] = None,
) -> Dict[str, Any]:
    """
    단일 종목: 최신 사업보고서 원문에서 매출처 관련 스니펫 추출.
    """
    if not DART_API_KEY:
        raise RuntimeError("DART_API_KEY 환경변수가 설정되지 않았습니다.")

    corp_code = get_corp_code(ticker)
    if not corp_code:
        return {"ticker": ticker.split(".")[0], "error": "corp_code 매핑 없음"}

    now = now_kst()
    if end_de is None:
        end_de = now.strftime("%Y%m%d")
    if bgn_de is None:
        bgn_de = f"{now.year - 2}0101"

    picked = find_latest_business_report_rcept_no(corp_code, bgn_de, end_de)
    if not picked:
        return {
            "ticker": ticker.split(".")[0],
            "corp_code": corp_code,
            "error": "사업보고서 공시를 찾지 못함",
            "bgn_de": bgn_de,
            "end_de": end_de,
        }

    rcept_no, report_nm, rcept_dt = picked
    try:
        raw = fetch_document_archive(rcept_no)
    except Exception as e:
        return {
            "ticker": ticker.split(".")[0],
            "corp_code": corp_code,
            "rcept_no": rcept_no,
            "error": f"document.xml 실패: {e}",
        }

    plain = _archive_to_plain_text(raw)
    if not plain:
        return {
            "ticker": ticker.split(".")[0],
            "corp_code": corp_code,
            "rcept_no": rcept_no,
            "report_nm": report_nm,
            "rcept_dt": rcept_dt,
            "error": "원문 텍스트 추출 실패(zip/XML 아님 또는 빈 본문)",
        }

    snippets = extract_anchor_windows(plain, half_window=100)
    return {
        "ticker": ticker.split(".")[0],
        "corp_code": corp_code,
        "rcept_no": rcept_no,
        "report_nm": report_nm,
        "rcept_dt": rcept_dt,
        "plain_text_len": len(plain),
        "snippets": snippets,
        "collected_at": now_kst().isoformat(),
    }


def save_snippets_payload(payload: Dict[str, Any]) -> str:
    os.makedirs(DATA_DIR, exist_ok=True)
    merged: Dict[str, Any]
    if os.path.isfile(CHAIN_SNIPPETS_PATH):
        try:
            with open(CHAIN_SNIPPETS_PATH, "r", encoding="utf-8") as f:
                merged = json.load(f)
        except (json.JSONDecodeError, OSError):
            merged = {"updated_at": None, "by_ticker": {}}
    else:
        merged = {"updated_at": None, "by_ticker": {}}

    merged.setdefault("by_ticker", {})
    key = str(payload.get("ticker", "")).zfill(6)
    merged["by_ticker"][key] = payload
    merged["updated_at"] = now_kst().isoformat()

    with open(CHAIN_SNIPPETS_PATH, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    return CHAIN_SNIPPETS_PATH


if __name__ == "__main__":
    t = os.environ.get("CHAIN_SCOUT_TICKER", "005930.KS")
    bgn = os.environ.get("CHAIN_SCOUT_BGN_DE")
    end = os.environ.get("CHAIN_SCOUT_END_DE")
    print(f"ChainScout — ticker={t}")
    result = scout_major_customer_snippets(t, bgn_de=bgn, end_de=end)
    print(json.dumps(result, ensure_ascii=False, indent=2)[:4000])
    if not result.get("error"):
        path = save_snippets_payload(result)
        print(f"\n저장: {path}")
