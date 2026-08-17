"""dart_kam — 감사보고서 **핵심감사사항(KAM)** 추출. 🚨 **LLM 미사용** (2026-08-17 전환).

## 왜 LLM 을 뺐나 — PM 지시 "재미나이 호출이 무의미하면 아예 배제해"

2026-08-16 에 이 모듈을 Gemini 판독기로 만들었다. 8/17 실측이 그 설계를 기각했다:

| 관측 | 값 |
|---|---|
| Gemini 결과 | **5/5 종목 `kam_count=0`** ("원문에서 핵심감사사항을 찾을 수 없습니다") |
| 원인 | 모델이 아니라 내가 만든 `kam_text` 슬라이스가 **사업보고서 표지**를 담았다 |
| 증거 | `'핵심감사사항'` 출현 = `raw_text` **8회** vs `kam_text` **0회** |
| 부수 결함 | 구버전 SDK + 타임아웃 부재 → 한 종목이 wall 13분 07초 · CPU 4초로 배치를 세웠다 |

그런데 슬라이스를 고치기 전에 한 가지가 드러났다 — **필요한 사실이 이미 정형 표에 있다.**
사업보고서 'V. 회계감사인의 감사의견' 표는 8열 `\n\n` 구분 고정이고 마지막 열이
핵심감사사항이다. 즉 **LLM 이 할 일이 없다.**

결정론 파서가 LLM 보다 **더 많이** 준다:
  · 감사인 · 감사의견 · 의견변형사유 · 계속기업 관련중요한 불확실성 · 강조사항 · 핵심감사사항
  · **3개 연도(당기/전기/전전기) × 개별/연결 = 6행** — 감사인 교체(한미→삼일 · 한영→서현)까지
  · 비용 **0** · 네트워크 **0**(이미 캐시된 `raw_text` 만 읽는다) · 결정론 · 추출 정확도로 검증 가능

## 커버리지의 정직한 형태

표본 5 중 **2종목만** 표가 있다. 나머지 3은 사업보고서에 감사보고서가 첨부되지 않은 경우로,
**결손이 아니라 별도 공시**다. 그런 종목은 `_skip_reason="no_audit_table"` 로 남긴다 —
"못 찾았다" 와 "없다" 를 섞지 않는다.

## 경계

🚨 관측 only. Brain 점수 미반영 (RULE 7 — 점수 반영은 사전등록 + PM 승인 후).
산출 = `data/dart_kam_cache.json` `{"by_ticker": {ticker: {bsns_year: 결과}}}`.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from typing import Any, Dict, Optional

from api.config import DATA_DIR, now_kst

logger = logging.getLogger(__name__)

CACHE_PATH = os.path.join(DATA_DIR, "dart_kam_cache.json")

# 표의 '없음' 표기들 — 이걸 KAM 제목으로 오인하면 전 종목이 거짓 양성이 된다
_EMPTY_TOKENS = {"-", "", "해당사항 없음", "해당사항없음", "없음", "N/A", "해당없음"}


def _load_cache() -> Dict[str, Any]:
    try:
        with open(CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_cache(cache: Dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=1)
    except OSError as e:
        logger.warning("[kam] 캐시 저장 실패: %s", e)


def _is_empty(v: Any) -> bool:
    return str(v or "").strip() in _EMPTY_TOKENS


def extract_kam(raw_text: str) -> Dict[str, Any]:
    """`raw_text` 에서 감사의견 표를 파싱해 KAM 사실을 뽑는다. LLM 호출 0.

    반환 = {kam_count, matters[{title, fiscal_year, scope, auditor, opinion}],
            auditor, opinion, going_concern, emphasis, history[...]}
    표가 없으면 {"_skip_reason": "no_audit_table"}.
    """
    from api.collectors.DartScout import parse_audit_opinion_table
    tbl = parse_audit_opinion_table(raw_text)
    if not tbl or not tbl.get("rows"):
        return {"_skip_reason": "no_audit_table"}

    rows = tbl["rows"]
    # 당기 = 표의 첫 사업연도. '연결' 이 아닌 개별 감사보고서를 우선 대표로 본다.
    cur_year = rows[0].get("사업연도")
    cur = [r for r in rows if r.get("사업연도") == cur_year]
    lead = next((r for r in cur if r.get("구분") == "감사보고서"), cur[0])

    matters = []
    seen = set()
    for r in cur:
        t = str(r.get("핵심감사사항") or "").strip()
        if _is_empty(t) or t in seen:
            continue
        seen.add(t)
        matters.append({"title": t, "fiscal_year": r.get("사업연도"),
                        "scope": r.get("구분"), "auditor": r.get("감사인"),
                        "opinion": r.get("감사의견")})

    def _g(row, key):
        v = row.get(key)
        return None if _is_empty(v) else str(v).strip()

    return {
        "kam_count": len(matters),
        "matters": matters,
        "auditor": _g(lead, "감사인"),
        "opinion": _g(lead, "감사의견"),
        "opinion_modification": _g(lead, "의견변형사유"),
        # 열 이름이 공시 서식마다 미세하게 다르므로 부분 일치로 찾는다
        "going_concern": next((_g(lead, k) for k in lead if "계속기업" in k), None),
        "emphasis": next((_g(lead, k) for k in lead if "강조사항" in k), None),
        # 3개 연도 전체 — 감사인 교체·KAM 변화 추적용 (LLM 으로는 못 얻던 부분)
        "history": [{"fiscal_year": r.get("사업연도"), "scope": r.get("구분"),
                     "auditor": _g(r, "감사인"), "opinion": _g(r, "감사의견"),
                     "kam": (None if _is_empty(r.get("핵심감사사항"))
                             else str(r.get("핵심감사사항")).strip())}
                    for r in rows],
        "_method": "deterministic_table_parse",
        "_extracted_at": now_kst().isoformat(),
    }


def analyze_all_kam(stocks: Dict[str, Any],
                    auto_fetch_missing: bool = True) -> Dict[str, Dict[str, Any]]:
    """stocks dict 일괄 KAM 추출.

    `raw_text` 우선순위: (1) `business_facilities_raw.raw_text`,
    (2) `auto_fetch_missing` 이면 `corp_code` 로 DartScout fetch (디스크 캐시 read-through).
    🚨 (2)가 없으면 백필 경로가 raw_text 를 못 넘겨 전 종목 skip 된다 — 커버리지 0 이
       조용히 유지되는 형태다 (2026-08-16 학습).
    """
    cache = _load_cache()
    by_ticker: Dict[str, Any] = cache.get("by_ticker", {})
    out: Dict[str, Dict[str, Any]] = {}
    fresh = cached = skipped = 0

    for ticker, info in (stocks or {}).items():
        if not isinstance(info, dict):
            continue
        year = str(info.get("bsns_year") or "")
        name = info.get("name") or info.get("corp_name") or ticker
        corp_code = info.get("corp_code")

        tc = by_ticker.get(ticker, {})
        hit = tc.get(year)
        if hit and hit.get("kam_count") is not None:
            out[ticker] = hit
            cached += 1
            continue

        # 🚨 `audit_opinion_text`(섹션 V 표) 우선. `raw_text`(= 'II. 사업의 내용')로는
        #   섹션 V 가 밖이라 커버리지가 2/10 이었고 그 2건도 슬라이스 과다 연장의 우연이었다.
        bf = info.get("business_facilities_raw") or {}
        raw = (info.get("audit_opinion_text")
               or (bf.get("audit_opinion_text") if isinstance(bf, dict) else "") or "")
        t_fetch = 0.0
        from_cache = None
        if not raw and auto_fetch_missing and corp_code:
            _t0 = time.monotonic()
            try:
                from api.collectors.DartScout import fetch_business_facilities_raw
                r = fetch_business_facilities_raw(corp_code, year)
                raw = (r or {}).get("audit_opinion_text", "")
                from_cache = bool((r or {}).get("_from_cache"))
            except Exception as e:  # noqa: BLE001
                logger.warning("[kam] fetch 실패(%s): %s", name, str(e)[:60])
                raw = ""
            t_fetch = time.monotonic() - _t0

        res = extract_kam(raw) if raw else {"_skip_reason": "no_raw_text"}
        # 구간 계측 — 장시간 배치에서 진척과 병목이 보여야 한다 (2026-08-17 학습:
        # 계측 없이 대기 시간을 처리 시간으로 읽어 80시간이라 오판했다)
        sys.stderr.write(
            f"[kam] {ticker} {str(name)[:12]} fetch {t_fetch:5.1f}s"
            f"{' (캐시)' if from_cache else ''} · "
            + (f"KAM {res['kam_count']}건" if "kam_count" in res
               else f"skip {res.get('_skip_reason')}") + "\n")
        sys.stderr.flush()

        if "_skip_reason" in res:
            out[ticker] = {**res, "ticker": ticker}
            skipped += 1
            continue
        res["ticker"] = ticker
        res["bsns_year"] = year
        out[ticker] = res
        tc[year] = res
        by_ticker[ticker] = tc
        fresh += 1

    if fresh:
        cache["by_ticker"] = by_ticker
        cache["updated_at"] = now_kst().isoformat()
        cache["_method"] = "deterministic_table_parse"
        _save_cache(cache)
    logger.info("[kam] 신규 %d · 캐시 %d · 스킵 %d", fresh, cached, skipped)
    return out
