"""
Gemini로 종목별 주력 수출 품목 + HS 6자리(및 통계용 10자리) 매핑
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Dict, List, Optional

from api.analyzers.gemini_analyst import init_gemini
from api.collectors.trading_value_scanner import ScannedStock


def _strip_code_fence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t[3:]
        t = t.rsplit("```", 1)[0]
    return t.strip()


def _normalize_hscode_6(s: str) -> str:
    digits = re.sub(r"\D", "", s or "")
    if len(digits) >= 6:
        return digits[:6]
    return digits.ljust(6, "0") if digits else ""


def _is_rate_limit_error(exc: BaseException) -> bool:
    t = repr(exc).lower()
    return "429" in t or "resource_exhausted" in t or "quota" in t or "rate" in t


def _entry_from_raw(entry: Any, stock: ScannedStock) -> Optional[Dict[str, Any]]:
    if not isinstance(entry, dict):
        return None
    product = str(entry.get("product", "")).strip() or "미상"
    h6 = _normalize_hscode_6(str(entry.get("hscode", "")))
    if len(h6) != 6 or not h6.isdigit():
        return None
    h10 = entry.get("hscode10")
    h10s: Optional[str] = None
    if h10 is not None:
        d10 = re.sub(r"\D", "", str(h10))
        if len(d10) >= 10:
            h10s = d10[:10]
        elif len(d10) >= 6:
            h10s = d10.ljust(10, "0")[:10]
    return {
        "product": product,
        "hscode": h6,
        "hscode10": h10s,
        "ticker": stock.ticker,
        "trademoney_million_krw": stock.trademoney_million_krw,
    }


def _stub_mapping(stock: ScannedStock) -> Dict[str, Any]:
    return {
        "product": "Gemini 미매핑(쿼터 초과 또는 오류)",
        "hscode": "",
        "hscode10": None,
        "ticker": stock.ticker,
        "trademoney_million_krw": stock.trademoney_million_krw,
        "mapper_error": True,
    }


def _map_one_stock(client: Any, stock: ScannedStock) -> Optional[Dict[str, Any]]:
    name_lit = json.dumps(stock.name, ensure_ascii=False)
    prompt = f"""한국 상장 기업 {name_lit} (티커 {stock.ticker})의 **주력 수출 제품** 1가지(한국어 짧은 명칭)와
그에 맞는 **HS Code 6자리**, 가능하면 **HS 10자리**를 제시하라. JSON만 출력.

형식:
{{ {name_lit}: {{ "product": "...", "hscode": "XXXXXX", "hscode10": "XXXXXXXXXX 또는 null" }} }}"""

    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
            )
            text = _strip_code_fence(response.text)
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                ent = _entry_from_raw(parsed.get(stock.name), stock)
                if ent:
                    return ent
        except json.JSONDecodeError:
            time.sleep(2)
        except Exception as e:
            if _is_rate_limit_error(e):
                w = min(45, 15 * (attempt + 1))
                print(f"[HS Mapper] 단건 속도 제한 → {w}s")
                time.sleep(w)
            else:
                print(f"[HS Mapper] 단건 오류 ({stock.name}): {e}")
                break
    return None


def map_stocks_to_hscode_batch(
    stocks: List[ScannedStock],
    chunk_size: int = 5,
    sleep_between: float = 8.0,
) -> Dict[str, Dict[str, Any]]:
    """
    종목 리스트를 Gemini에 넘겨
    { "종목명": { "product": str, "hscode": "6자리", "hscode10": str|null } } 형태로 반환.
    """
    if not stocks:
        return {}

    if os.environ.get("TRADE_SKIP_GEMINI", "").lower() in ("1", "true", "yes"):
        print("[HS Mapper] TRADE_SKIP_GEMINI=1 — HS 스텁만 기록", flush=True)
        return {s.name: _stub_mapping(s) for s in stocks}

    client = init_gemini()
    mapping: Dict[str, Dict[str, Any]] = {}
    quota_exhausted = False

    for i in range(0, len(stocks), chunk_size):
        chunk = stocks[i : i + chunk_size]
        if quota_exhausted:
            for s in chunk:
                if s.name not in mapping:
                    mapping[s.name] = _stub_mapping(s)
            if i + chunk_size < len(stocks) and sleep_between > 0:
                time.sleep(sleep_between)
            continue

        lines = "\n".join(f"- {s.name} (티커 {s.ticker})" for s in chunk)
        prompt = f"""다음은 한국 상장 종목 목록이다. 각 기업의 **주력 수출 제품**(실제 사업에서 매출·수출에 가장 큰 비중인 제품 1가지, 한국어 짧은 명칭)을 추론하고,
그 제품에 가장 잘 맞는 **HS Code 앞 6자리**(국제 통일 품목분류)를 제시하라.
통계 API에 넣기 좋도록 가능하면 **HS 10자리**도 추정하라(불확실하면 null).

규칙:
- 확실하지 않은 기업은 product에 "(추정)"을 붙이고 hscode는 업종 대표 품목으로 근사.
- 금융·지주사·리츠 등 비제조업은 해당 산업의 대표 무형·서비스 관련 HS 또는 가장 가까운 물품으로 근사.
- JSON만 출력. 종목명은 아래 목록과 **완전히 동일한 문자열**을 키로 사용.

종목:
{lines}

JSON 형식:
{{
  "삼성전자": {{ "product": "DRAM/낸드 메모리 반도체", "hscode": "854232", "hscode10": "8542320000" }}
}}"""

        raw: Dict[str, Any] = {}
        for attempt in range(2):
            try:
                response = client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=prompt,
                )
                text = _strip_code_fence(response.text)
                parsed = json.loads(text)
                if isinstance(parsed, dict) and parsed:
                    raw = parsed
                    break
            except json.JSONDecodeError:
                time.sleep(2)
            except Exception as e:
                if _is_rate_limit_error(e):
                    wait = 25 * (attempt + 1)
                    print(f"[HS Mapper] 속도 제한 → {wait}s 대기")
                    time.sleep(wait)
                    if attempt == 1:
                        print("[HS Mapper] Gemini 쿼터 한도 — 이후 종목은 HS 스텁 처리")
                        quota_exhausted = True
                else:
                    print(f"[HS Mapper] API 오류: {e}")
                    break

        if isinstance(raw, dict):
            for s in chunk:
                ent = _entry_from_raw(raw.get(s.name), s)
                if ent:
                    mapping[s.name] = ent

        if quota_exhausted:
            for s in chunk:
                if s.name not in mapping:
                    mapping[s.name] = _stub_mapping(s)
            if i + chunk_size < len(stocks) and sleep_between > 0:
                time.sleep(sleep_between)
            continue

        for s in chunk:
            if s.name in mapping:
                continue
            print(f"[HS Mapper] 배치 누락 → 단건: {s.name}")
            one = _map_one_stock(client, s)
            if one:
                mapping[s.name] = one
            time.sleep(6)

        if i + chunk_size < len(stocks) and sleep_between > 0:
            time.sleep(sleep_between)

    for s in stocks:
        if s.name in mapping:
            continue
        mapping[s.name] = _stub_mapping(s)

    return mapping
