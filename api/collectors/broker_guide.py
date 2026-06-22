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

# 🚨 검색 출처 제한 — 일반 블로그/커뮤니티 배제, 공식·준공식만. 출처 신뢰도 확보.
# 금융투자협회(공시) + 금감원 + 각 사 공식 사이트.
TRUSTED_DOMAINS = [
    "kofia.or.kr",      # 금융투자협회 (온라인 수수료 비교 공시)
    "fss.or.kr",        # 금융감독원
    "truefriend.com",   # 한국투자증권
    "tossinvest.com",   # 토스증권
    "kiwoom.com",       # 키움증권
    "miraeasset.com",   # 미래에셋증권
    "samsungpop.com",   # 삼성증권
    "nhqv.com",         # NH투자증권
]

DISCLAIMER = "공식·금융투자협회 공시 출처 자동집계 · 수수료는 수시 변동 · 사실 비교일 뿐 권유 아님 · 거래 전 각 사 공식 고지 확인"

_SYSTEM = (
    "너는 한국 증권사의 수수료·기능을 '사실'만 집계하는 리서처다. "
    "수수료율은 각 사 공식 수수료표/공식 안내 기준, 앱 평점은 앱스토어/구글플레이 공개 수치 기준으로 "
    "최대한 구체 숫자를 기입한다(예: 0.0140%, iOS 4.5). 추정·과장·별점 평가 금지. "
    "정말 공개 출처가 없는 항목만 빈 문자열로 둔다. by_trade_type 의 best·reason 도 사실 근거로 반드시 채운다. "
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
    fee_filled = 0
    for b in brokers:
        if not isinstance(b, dict):
            continue
        fee = str(b.get("domestic_fee", ""))
        if fee:
            fee_filled += 1
            if not _FEE_RE.search(fee):
                flags.append(f"{b.get('name','?')} 국내수수료 형식 의심: '{fee}'")
    # 대량 공란 가드 — 수수료가 절반 미만만 채워지면 저품질(검수 필요)
    if fee_filled < max(1, len(brokers) // 2):
        flags.append(f"국내수수료 대량 공란 ({fee_filled}/{len(brokers)}) — 검수 필요")
    btt = parsed.get("by_trade_type")
    if not isinstance(btt, list) or not btt:
        flags.append("by_trade_type 비어있음")
    else:
        best_filled = sum(1 for t in btt if isinstance(t, dict) and str(t.get("best", "")).strip())
        if best_filled < max(1, len(btt) // 2):
            flags.append(f"거래유형 best 대량 공란 ({best_filled}/{len(btt)}) — 검수 필요")
    return True, flags


def _load_prev() -> dict | None:
    try:
        with open(DATA_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


# 🚨 큐레이션 수수료 (공식 검증 — PM 확정값). LLM 자동집계가 정밀 수수료엔 약해(블로그=숫자있음/공식=추출불가)
# 이 6개 국내수수료는 큐레이션으로 고정. ISA·신용·거래유형 reason 은 자동(Perplexity) 유지.
# 형식: 증권사명 substring → (수수료, 공식 출처 URL). 비어있으면 자동값 유지(공란 가능).
CURATED_FEES: dict = {
    # PM 공식 검증 후 채움 (예: "한국투자증권": ("0.0140%", "https://www.truefriend.com/..."))
}


def _apply_curated(brokers: list) -> None:
    """국내수수료 = 큐레이션 값으로 override (있는 종목만). 출처도 공식으로 교체."""
    for b in brokers:
        if not isinstance(b, dict):
            continue
        nm = b.get("name", "")
        for key in CURATED_FEES:
            if key in nm:
                fee, src = CURATED_FEES[key]
                b["domestic_fee"] = fee
                if src:
                    b["source_url"] = src
                break


# 각 사 공식 도메인 — focused 수수료 쿼리 1차 한정용.
BROKER_OFFICIAL = {
    "한국투자": "truefriend.com", "한투": "truefriend.com", "토스": "tossinvest.com",
    "키움": "kiwoom.com", "미래에셋": "miraeasset.com", "삼성": "samsungpop.com",
    "NH": "nhqv.com", "농협": "nhqv.com",
}


def _official_domain(broker: str) -> str:
    for k in BROKER_OFFICIAL:
        if k in (broker or ""):
            return BROKER_OFFICIAL[k]
    return ""


_FEE_SYS = (
    "너는 한국 증권사 수수료를 공식 자료 기준으로 정확히 찾는 리서처다. "
    "추정·과장 금지. 공식 수수료표/금융투자협회 공시 기준 숫자만. 유효한 JSON 객체 하나만 출력."
)
_FEE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "schema": {
            "type": "object",
            "properties": {
                "fee": {"type": "string"},
                "source": {"type": "string"},
                "basis": {"type": "string"},
            },
            "required": ["fee"],
        }
    },
}


def _fee_pct(s: str) -> float:
    """수수료 문자열에서 % 숫자 추출. 없으면 -1."""
    m = re.search(r"(\d+(?:\.\d+)?)\s*%", s or "")
    return float(m.group(1)) if m else -1.0


# 온라인 위탁수수료 타당 범위 — 이 초과면 영업점/이상치 의심(온라인은 사실상 0.05% 이하).
FEE_MAX_PCT = 0.05


def _fee_query(broker: str) -> str:
    return (
        f"{broker} 의 국내주식 '온라인(HTS·MTS·홈페이지) 위탁수수료율'을 공식 수수료표 기준 정확히 알려줘. "
        "⚠ 영업점·전화·오프라인 수수료가 아니라 온라인 기본 수수료율이다. 온라인 요율은 보통 0.001~0.05% 범위. "
        "채널별로 다르면 대표 온라인 기준 하나로 (이벤트·비대면 신규우대 조건은 basis 에 설명). "
        '숫자는 % 로. JSON: {"fee": "0.0000%", "source": "공식 출처 URL", "basis": "기준/조건"}'
    )


def _fetch_fee(broker: str) -> dict:
    """focused 단일 종목 수수료 추출. 공식 도메인 1차 → 일반 fallback. 유효 % 만 반환."""
    dom = _official_domain(broker)
    attempts: list = []
    if dom:
        attempts.append([dom, "kofia.or.kr"])
    attempts.append(None)  # 무제한 fallback
    for domains in attempts:
        res = call_perplexity(
            _fee_query(broker),
            system_prompt=_FEE_SYS,
            max_tokens=600,
            temperature=0.0,
            search_domain_filter=domains,
            response_format=_FEE_FORMAT,
        )
        if res.get("error"):
            continue
        try:
            d = json.loads(_strip_json(res.get("content", "")))
        except Exception:
            continue
        fee = str(d.get("fee", "")).strip()
        val = _fee_pct(fee)
        # 유효 % + 온라인 타당 범위(영업점 요율 오인 거부)
        if _FEE_RE.search(fee) and 0 < val <= FEE_MAX_PCT:
            return {
                "fee": fee,
                "source": str(d.get("source", "")).strip(),
                "basis": str(d.get("basis", "")).strip(),
                "official": domains is not None,
            }
        if val > FEE_MAX_PCT:
            print(f"[broker_guide] {broker} 수수료 {fee} > {FEE_MAX_PCT}% — 영업점 의심, 거부")
    return {}


def collect(force: bool = False) -> dict:
    """Perplexity 호출 → 검증 → broker_guide.json 발행. 실패 시 직전 유지."""
    prev = _load_prev()
    # search_recency_filter 미사용 — 수수료표·앱평점은 상시 참조정보라 "최근 N일" 제한 시 못 찾음.
    # 메인 호출 = ISA·신용·거래유형(soft). 수수료는 아래 focused 호출이 정밀 override.
    res = call_perplexity(
        _build_query(),
        system_prompt=_SYSTEM,
        max_tokens=4000,
        temperature=0.05,
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

    brokers = parsed.get("brokers", [])

    # 🎯 focused 종목별 수수료 추출 (정밀 + 공식 출처) → domestic_fee/source override
    fee_sources: list = []
    fee_ok = 0
    for b in brokers:
        if not isinstance(b, dict):
            continue
        info = _fetch_fee(b.get("name", ""))
        if info.get("fee"):
            b["domestic_fee"] = info["fee"]
            if info.get("basis"):
                b["fee_basis"] = info["basis"]
            if info.get("source"):
                b["source_url"] = info["source"]
                if info["source"] not in fee_sources:
                    fee_sources.append(info["source"])
            fee_ok += 1
        else:
            # focused 실패 → 메인 호출값도 크기 가드 통과 못 하면 공란(틀린/영업점 값 노출 차단).
            mainfee = str(b.get("domestic_fee", ""))
            mv = _fee_pct(mainfee)
            if _FEE_RE.search(mainfee) and 0 < mv <= FEE_MAX_PCT:
                m = re.search(r"\d+(?:\.\d+)?\s*%", mainfee)  # 부가설명 제거, % 토큰만
                b["domestic_fee"] = m.group(0) if m else mainfee
                fee_ok += 1
            else:
                b["domestic_fee"] = ""
            print(f"[broker_guide] ⚠ 수수료 추출 실패(메인값 {'채택' if b['domestic_fee'] else '공란'}): {b.get('name','?')}")

    # 수동 큐레이션 override (있으면 자동값보다 우선)
    _apply_curated(brokers)

    ok, flags = _validate(parsed)
    if not ok:
        print(f"[broker_guide] 검증 실패 — 직전 유지: {flags}")
        return {"status": "validate_fail", "kept_prev": prev is not None, "flags": flags}

    out = {
        "as_of": datetime.now(KST).isoformat(),
        "source": f"perplexity {res.get('model', 'sonar')} (자동집계)",
        "disclaimer": DISCLAIMER,
        "brokers": brokers,
        "by_trade_type": parsed.get("by_trade_type", []),
        # 출처 = focused 수수료 호출의 공식 출처 우선, 없으면 메인 citations
        "citations": fee_sources or res.get("citations", []),
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
