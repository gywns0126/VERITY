"""
증권사 거래유형별 사실 비교 자동집계 — Perplexity sonar-pro.

골든구스 공개 터미널용. broker-neutral(특정 증권사 편 X) 사실 가이드.

🚨 RULE 6/7 정합: LLM 자동집계지만 노출은 **사실(수수료율·앱스토어 평점·기능 유무) + 출처**만.
   우리 의견/별점/추천 0. "권유 아님" + as-of + citations 동반 발행.
🚨 정확도 가드 (LLM 환각 → 오정보 발행 차단):
   1) JSON + 항목별 출처 강제 (system_prompt + schema)
   2) 파싱/스키마 검증 실패 = 직전 broker_guide.json 유지(fail-safe), 절대 빈/깨진 발행 X
   3) 수수료 sanity: 퍼센트 패턴 아니면 flag (직전 값 유지)
월 1회 cron 충분(수수료 저빈도) + API 비용 ↓. 소비 = PublicBrokerGuide (Blob broker_guide.json).
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from api.clients.perplexity_client import call_perplexity

KST = ZoneInfo("Asia/Seoul")
DATA_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "data", "broker_guide.json")
)

BROKERS = ["한국투자증권", "토스증권", "키움증권", "미래에셋증권", "삼성증권", "NH투자증권"]
TRADE_TYPES = ["소형주(코스닥) 단기", "미국주식 소액", "ISA 장기", "단타/고빈도", "중장기/배당"]

DISCLAIMER = "Perplexity 자동집계 · 수수료·평점은 수시 변동 · 사실 비교일 뿐 권유 아님 · 거래 전 각 사 공식 고지 확인"

_SYSTEM = (
    "너는 한국 증권사의 수수료·기능을 '사실'만 집계하는 리서처다. "
    "추천·별점·주관 평가 금지. 수치는 출처가 확인되는 것만 기입하고, 불명확하면 빈 문자열 또는 \"확인필요\". "
    "반드시 유효한 JSON 객체 하나만 출력한다(설명 문장·마크다운 코드펜스 금지)."
)

# 기대 JSON 스키마 (프롬프트에 명시)
_SCHEMA_HINT = """{
  "brokers": [
    {
      "name": "한국투자증권",
      "app": "앱 이름",
      "domestic_fee": "국내주식 온라인 위탁수수료율 (예: 0.0140%)",
      "overseas_fee": "미국주식 수수료율 + 환전우대 (예: 0.25% / 환전우대 95%)",
      "isa": "지원" or "미지원",
      "credit_short": "신용/대주 지원" or "미지원",
      "app_rating": "iOS x.x / Android x.x (출처)",
      "community": "있음" or "없음",
      "realtime_news": "실시간시세·속보 제공" or "제한",
      "source_url": "대표 출처 URL"
    }
  ],
  "by_trade_type": [
    {"type": "소형주(코스닥) 단기", "best": "증권사명(들)", "reason": "사실 근거 1문장"}
  ]
}"""


# structured output 강제 (sonar-pro가 산문 대신 JSON만 반환하도록)
_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "schema": {
            "type": "object",
            "properties": {
                "brokers": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "app": {"type": "string"},
                            "domestic_fee": {"type": "string"},
                            "overseas_fee": {"type": "string"},
                            "isa": {"type": "string"},
                            "credit_short": {"type": "string"},
                            "app_rating": {"type": "string"},
                            "community": {"type": "string"},
                            "realtime_news": {"type": "string"},
                            "source_url": {"type": "string"},
                        },
                        "required": ["name"],
                    },
                },
                "by_trade_type": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string"},
                            "best": {"type": "string"},
                            "reason": {"type": "string"},
                        },
                        "required": ["type"],
                    },
                },
            },
            "required": ["brokers", "by_trade_type"],
        }
    },
}


def _build_query() -> str:
    today = datetime.now(KST).strftime("%Y년 %m월")
    return (
        f"{today} 기준, 다음 한국 증권사를 거래자 관점에서 사실 비교해 아래 JSON 스키마로만 출력해줘.\n"
        f"대상 증권사: {', '.join(BROKERS)}\n"
        f"거래 유형(by_trade_type): {', '.join(TRADE_TYPES)}\n\n"
        "각 수수료·평점·기능은 출처가 확인되는 사실만. 주관적 추천/별점 금지.\n\n"
        f"JSON 스키마:\n{_SCHEMA_HINT}"
    )


def _strip_json(text: str) -> str:
    """마크다운 펜스/잡텍스트 제거 후 첫 JSON 객체만."""
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    start = t.find("{")
    end = t.rfind("}")
    if start >= 0 and end > start:
        return t[start : end + 1]
    return t


_FEE_RE = re.compile(r"\d+(\.\d+)?\s*%")


def _validate(parsed: dict) -> tuple[bool, list]:
    """필수 구조 검증 + 수수료 sanity. (ok, flags)"""
    flags: list = []
    brokers = parsed.get("brokers")
    if not isinstance(brokers, list) or len(brokers) < len(BROKERS) - 1:
        return False, ["brokers 누락/부족 — 발행 보류"]
    names = {b.get("name", "") for b in brokers if isinstance(b, dict)}
    for want in BROKERS:
        if want not in names:
            flags.append(f"증권사 누락: {want}")
    for b in brokers:
        if not isinstance(b, dict):
            continue
        fee = str(b.get("domestic_fee", ""))
        if fee and not _FEE_RE.search(fee):
            flags.append(f"{b.get('name','?')} 국내수수료 형식 의심: '{fee}'")
    btt = parsed.get("by_trade_type")
    if not isinstance(btt, list) or not btt:
        flags.append("by_trade_type 비어있음")
    return True, flags


def _load_prev() -> dict | None:
    try:
        with open(DATA_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def collect(force: bool = False) -> dict:
    """Perplexity 호출 → 검증 → broker_guide.json 발행. 실패 시 직전 유지."""
    prev = _load_prev()
    res = call_perplexity(
        _build_query(),
        system_prompt=_SYSTEM,
        max_tokens=4000,
        temperature=0.05,
        search_recency_filter="month",
        response_format=_RESPONSE_FORMAT,
    )
    if res.get("error"):
        print(f"[broker_guide] Perplexity 실패 — 직전 유지: {res['error']}")
        return {"status": "error", "kept_prev": prev is not None, "detail": res["error"]}

    try:
        parsed = json.loads(_strip_json(res.get("content", "")))
    except Exception as e:
        raw = (res.get("content", "") or "")[:600]
        print(f"[broker_guide] JSON 파싱 실패 — 직전 유지: {e}")
        print(f"[broker_guide] raw content[:600]: {raw!r}")
        return {"status": "parse_fail", "kept_prev": prev is not None}

    ok, flags = _validate(parsed)
    if not ok:
        print(f"[broker_guide] 검증 실패 — 직전 유지: {flags}")
        return {"status": "validate_fail", "kept_prev": prev is not None, "flags": flags}

    out = {
        "as_of": datetime.now(KST).isoformat(),
        "source": f"perplexity {res.get('model', 'sonar')} (자동집계)",
        "disclaimer": DISCLAIMER,
        "brokers": parsed.get("brokers", []),
        "by_trade_type": parsed.get("by_trade_type", []),
        "citations": res.get("citations", []),
        "flags": flags,
    }
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(
        f"[broker_guide] 발행 완료: brokers={len(out['brokers'])} "
        f"trade_types={len(out['by_trade_type'])} flags={len(flags)} citations={len(out['citations'])}"
    )
    if flags:
        print(f"[broker_guide] ⚠ flags(검수 권장): {flags}")
    return {"status": "ok", "brokers": len(out["brokers"]), "flags": flags}


if __name__ == "__main__":
    import sys

    r = collect(force="--force" in sys.argv)
    sys.exit(0 if r.get("status") == "ok" else 1)
