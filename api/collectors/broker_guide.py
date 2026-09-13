"""
증권사 거래유형별 사실 비교 자동집계 — Perplexity sonar-pro.

AlphaNest 공개 터미널용. broker-neutral(특정 증권사 편 X) 사실 가이드.

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
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from api.clients.perplexity_client import call_perplexity

KST = ZoneInfo("Asia/Seoul")
DATA_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "data", "broker_guide.json")
)

BROKERS = ["한국투자증권", "토스증권", "키움증권", "미래에셋증권", "삼성증권", "NH투자증권"]
# 거래유형 = 사실 근거(수수료·기능 유무)로 best 도출 가능한 것만. best 는 우리 추천 아님(권유 아님 라벨).
TRADE_TYPES = [
    "소형주(코스닥) 단기", "미국주식 소액", "ISA 장기", "단타/고빈도", "중장기/배당",
    "해외주식 장기(환전우대)", "공모주(IPO) 청약", "연금저축·IRP", "ETF·지수 투자", "채권 투자",
]

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

DISCLAIMER = "공식·금융투자협회 공시 출처 자동집계 · 수수료는 수시 변동 · 거래 전 각 사 공식 고지 확인"

_SYSTEM = (
    "너는 한국 증권사의 수수료·기능을 '사실'만 집계하는 리서처다. "
    "수수료율은 각 사 공식 수수료표/공식 안내 기준, 앱 평점은 앱스토어/구글플레이 공개 수치 기준으로 "
    "최대한 구체 숫자를 기입한다(예: 0.0140%, iOS 4.5). 추정·과장·별점 평가 금지. "
    "정말 공개 출처가 없는 항목만 빈 문자열로 둔다. by_trade_type 의 best·reason 도 사실 근거로 반드시 채운다. "
    "🗣 basis·reason 같은 설명 텍스트는 사이트 전반 톤에 맞춰 **친근한 존댓말(~예요/~요체)**로 쓴다. "
    "문어체(~이다/~한다/~된다/~하며/~되며/~안내되며/~있어)는 쓰지 않는다(사실은 그대로, 어미만 부드럽게). "
    "반드시 유효한 JSON 객체 하나만 출력한다(설명 문장·마크다운 코드펜스 금지)."
)

# 기대 JSON 스키마 (프롬프트에 명시)
_SCHEMA_HINT = """{
  "brokers": [
    {
      "name": "한국투자증권",
      "app": "앱 이름",
      "domestic_fee": "국내주식 온라인 위탁수수료율 (예: 0.0140%)",
      "overseas_fee": "미국주식 온라인 위탁수수료율 (예: 0.25%)",
      "fx_fee": "미국주식 온라인 환전우대율 (예: 95%)",
      "isa": "지원" or "미지원",
      "credit_short": "신용/대주 지원" or "미지원",
      "app_rating": "iOS x.x / Android x.x (출처)",
      "community": "있음" or "없음",
      "realtime_news": "실시간시세·속보 제공" or "제한",
      "event": "현재 진행 중인 공식 이벤트/할인 1건 (반드시 기간 포함, 예: '미국주식 수수료 무료 (~2026-07-31)'). 진행 중 확인 안 되면 빈 문자열 — 만료/불확실 이벤트 금지",
      "event_source": "현재 진행 중인 이벤트의 증권사 공식 안내 URL. 없으면 빈 문자열",
      "source_url": "대표 출처 URL"
    }
  ],
  "by_trade_type": [
    {"type": "소형주(코스닥) 단기", "best": "증권사명(들)", "reason": "정성 근거 1문장 (수수료 %·수치 인용 금지, '최저/최고' 단정 대신 '낮은 편·유리' 완곡, 지원·기능 중심)"}
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
                            "fx_fee": {"type": "string"},
                            "isa": {"type": "string"},
                            "credit_short": {"type": "string"},
                            "app_rating": {"type": "string"},
                            "community": {"type": "string"},
                            "realtime_news": {"type": "string"},
                            "event": {"type": "string"},
                            "event_source": {"type": "string"},
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
        "각 수수료·평점·기능은 출처가 확인되는 사실만. 주관적 추천/별점 금지.\n"
        "event 는 오늘 기준 진행 중인 공식 이벤트/할인만 1건, 반드시 기간을 포함하고 확인 안 되면 빈 문자열(만료·불확실 이벤트는 절대 넣지 말 것). "
        "event_source 에는 해당 증권사 공식 안내 URL만 넣고, 공식 URL이 없으면 event 와 event_source 를 모두 비워둘 것.\n"
        "by_trade_type 의 reason 은 정성 근거만 — 수수료 %·수치 인용 금지, '최저/최고' 단정 대신 '낮은 편·유리' 완곡 표현, 지원 여부·상품·기능 중심(수수료 진짜값은 공식 고지에서 확인이라 숫자 assert 안 함).\n\n"
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
    ov_filled = sum(1 for b in brokers if isinstance(b, dict) and _FEE_RE.search(str(b.get("overseas_fee", ""))))
    if ov_filled < max(1, len(brokers) // 2):
        flags.append(f"해외수수료 대량 공란 ({ov_filled}/{len(brokers)}) — 검수 필요")
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
    # PM 공식 출처 제공 pin (2026-06-22). 자동 추출 불안정 종목만 고정. 값은 draft — 페이지 대조해 수정 가능.
    "삼성증권": ("0.0147%", "https://www.samsungpop.com/?MENU_CODE=M1454054239846"),
    "NH투자증권": ("0.0150%", "https://www.nhsec.com"),
    # 2026-06-27 추가 — 한국투자 focused 추출 간헐 실패(빈값 회귀) 방지. 표준 온라인 요율(직전값 carry, 공식 대조 필요).
    "한국투자증권": ("0.0140527%", "https://securities.koreainvestment.com"),
    # 2026-07-03 재정정 — 앞선 0.0036%는 유관기관 수수료/평생우대 실효값 오인. 타사와 동일한 '비대면 우대 위탁수수료' 기준
    # = 다이렉트 0.014% (공식 표준 0.136% / 평생우대 이벤트 시 90일 0% → 이후 유관기관 0.0036%만). 우대가 기준 통일.
    "미래에셋증권": ("0.014%", "https://securities.miraeasset.com/public/mw/guide/html/20191119095045.html"),
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

BROKER_OFFICIAL_ALIASES = {
    "truefriend.com": ("truefriend.com", "koreainvestment.com"),
    "tossinvest.com": ("tossinvest.com",),
    "kiwoom.com": ("kiwoom.com",),
    "miraeasset.com": ("miraeasset.com",),
    "samsungpop.com": ("samsungpop.com",),
    "nhqv.com": ("nhqv.com",),
}
BROKER_OFFICIAL_HOMES = {
    "truefriend.com": "https://www.truefriend.com",
    "tossinvest.com": "https://tossinvest.com",
    "kiwoom.com": "https://www.kiwoom.com",
    "miraeasset.com": "https://securities.miraeasset.com",
    "samsungpop.com": "https://www.samsungpop.com",
    "nhqv.com": "https://www.nhqv.com",
}


def _official_domain(broker: str) -> str:
    for k in BROKER_OFFICIAL:
        if k in (broker or ""):
            return BROKER_OFFICIAL[k]
    return ""


def _extract_http_url(value: object) -> str:
    """산문이 섞인 응답에서도 첫 http(s) URL만 정규화한다."""
    match = re.search(r"https?://[^\s<>\"']+", str(value or ""), flags=re.I)
    return match.group(0).rstrip("),.;]") if match else ""


def _verified_official_source_url(broker: str, value: object) -> str:
    """입력에 해당 증권사 공식 URL이 실제로 있을 때만 반환한다."""
    primary = _official_domain(broker)
    candidate = _extract_http_url(value)
    if not candidate or not primary:
        return ""
    try:
        host = (urlparse(candidate).hostname or "").lower().removeprefix("www.")
    except ValueError:
        return ""
    allowed = BROKER_OFFICIAL_ALIASES.get(primary, (primary,))
    if any(host == domain or host.endswith("." + domain) for domain in allowed):
        return candidate
    return ""


def _official_source_url(broker: str, value: object) -> str:
    """해당 증권사 공식 도메인만 허용하고 나머지는 공식 홈페이지로 낮춘다."""
    primary = _official_domain(broker)
    home = BROKER_OFFICIAL_HOMES.get(primary, "")
    return _verified_official_source_url(broker, value) or home


_EVENT_UNCERTAIN_RE = re.compile(
    r"추정|미공개|미표기|확인\s*(?:안|어려)|불확실|보도\s*기준|공지상|진행\s*중\s*안내",
    re.I,
)
_EVENT_PERIOD_RE = re.compile(
    r"(?:20\d{2}[-./년]\s*\d{1,2}[-./월]\s*\d{1,2}(?:일)?|"
    r"20\d{2}[-./]\d{1,2}|신청일로부터\s*\d+\s*(?:개월|일)|상시)",
    re.I,
)


def _sanitize_events(brokers: list) -> list[str]:
    """공식 안내 URL과 명시된 기간이 함께 있는 현재 이벤트만 남긴다."""
    flags: list[str] = []
    for broker in brokers:
        if not isinstance(broker, dict):
            continue
        name = str(broker.get("name", ""))
        event = re.sub(r"\[\d+\]", "", str(broker.get("event", "") or ""))
        event = re.sub(r"\s+", " ", event).strip()
        source = _verified_official_source_url(name, broker.get("event_source"))
        period_match = _EVENT_PERIOD_RE.search(event)
        valid = bool(event and source and period_match)
        if _EVENT_UNCERTAIN_RE.search(event):
            valid = False
        if valid and "상시" not in event and "신청일로부터" not in event:
            dates = []
            for year, month, day in re.findall(
                r"(20\d{2})[-./년]\s*(\d{1,2})[-./월]\s*(\d{1,2})(?:일)?",
                event,
            ):
                try:
                    dates.append(datetime(int(year), int(month), int(day)).date())
                except ValueError:
                    valid = False
            if not dates or max(dates) < datetime.now(KST).date():
                valid = False
        if valid:
            broker["event"] = event
            broker["event_source"] = source
        else:
            if event:
                flags.append(f"이벤트 숨김: {name}")
            broker["event"] = ""
            broker["event_source"] = ""
    return flags


def _sanitize_numeric_claims(brokers: list) -> list[str]:
    """공식 상세 URL이 없는 수수료·환전 숫자와 설명을 발행 전에 제거한다."""
    flags: list[str] = []
    claim_fields = (
        ("domestic_fee", "domestic_source", "fee_basis"),
        ("overseas_fee", "overseas_source", "overseas_basis"),
        ("fx_fee", "fx_source", "fx_basis"),
    )
    for broker in brokers:
        if not isinstance(broker, dict):
            continue
        name = str(broker.get("name", ""))
        for value_field, source_field, basis_field in claim_fields:
            value = str(broker.get(value_field, "") or "").strip()
            verified = _verified_official_source_url(name, broker.get(source_field))
            if value and not verified:
                flags.append(f"공식 출처 없는 숫자 숨김: {name}/{value_field}")
                broker[value_field] = ""
                broker[basis_field] = ""
            broker[source_field] = verified or BROKER_OFFICIAL_HOMES.get(
                _official_domain(name), ""
            )
    return flags


def _sanitize_sources(brokers: list) -> list[str]:
    """발행 직전 링크를 공식 도메인으로 제한하고 URL-only citations를 만든다."""
    citations: list[str] = []
    for broker in brokers:
        if not isinstance(broker, dict):
            continue
        name = str(broker.get("name", ""))
        for field in (
            "source_url",
            "domestic_source",
            "overseas_source",
            "fx_source",
            "event_source",
        ):
            clean_url = (
                _verified_official_source_url(name, broker.get(field))
                if field == "event_source"
                else _official_source_url(name, broker.get(field))
            )
            broker[field] = clean_url
            if clean_url and clean_url not in citations:
                citations.append(clean_url)
    return citations


_FEE_SYS = (
    "너는 한국 증권사 수수료를 공식 자료 기준으로 정확히 찾는 리서처다. "
    "추정·과장 금지. 공식 수수료표/금융투자협회 공시 기준 숫자만. 유효한 JSON 객체 하나만 출력. "
    "🗣 basis(기준/조건 설명)는 친근한 존댓말(~예요/~요체)로 쓴다 — 문어체(~이다/~한다/~되며) 금지."
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
    """focused 단일 종목 수수료 추출. 공식 도메인과 공식 URL이 확인된 값만 반환."""
    dom = _official_domain(broker)
    attempts: list = [[dom]] if dom else []
    for domains in attempts:
        res = call_perplexity(
            _fee_query(broker),
            system_prompt=_FEE_SYS,
            max_tokens=600,
            temperature=0.0,
            search_domain_filter=domains,
            response_format=_FEE_FORMAT,
        caller="broker_guide")
        if res.get("error"):
            continue
        try:
            d = json.loads(_strip_json(res.get("content", "")))
        except Exception:
            continue
        fee = str(d.get("fee", "")).strip()
        val = _fee_pct(fee)
        # 유효 % + 온라인 타당 범위(영업점 요율 오인 거부)
        source = _verified_official_source_url(broker, d.get("source"))
        if source and _FEE_RE.search(fee) and 0 < val <= FEE_MAX_PCT:
            return {
                "fee": fee,
                "source": source,
                "basis": str(d.get("basis", "")).strip(),
                "official": domains is not None,
            }
        if val > FEE_MAX_PCT:
            print(f"[broker_guide] {broker} 수수료 {fee} > {FEE_MAX_PCT}% — 영업점 의심, 거부")
    return {}


# 미국주식 온라인 위탁수수료 타당 범위 — KR 브로커 미국주식 요율 ≈ 0.07~0.25%(이벤트 0.07%~). 초과=오프라인/환전우대 오인.
OVERSEAS_FEE_MAX_PCT = 0.5


def _overseas_query(broker: str) -> str:
    return (
        f"{broker} 의 '미국주식 온라인(HTS·MTS) 위탁거래 수수료율'을 공식 수수료표 기준 정확히 알려줘. "
        "⚠ 거래수수료율(%)만 fee 에 (예 0.07%~0.25%, 이벤트 평생우대 포함). 최소수수료·환전우대율은 basis 에 설명. "
        "영업점·전화 요율 아님, 온라인 미국주식 기본 요율. "
        '숫자는 % 로. JSON: {"fee": "0.00%", "source": "공식 출처 URL", "basis": "최소수수료/환전우대/조건"}'
    )


def _fetch_overseas_fee(broker: str) -> dict:
    """focused 미국주식 수수료 추출. 공식 도메인과 공식 URL이 확인된 값만 반환."""
    dom = _official_domain(broker)
    attempts: list = [[dom]] if dom else []
    for domains in attempts:
        res = call_perplexity(
            _overseas_query(broker),
            system_prompt=_FEE_SYS,
            max_tokens=600,
            temperature=0.0,
            search_domain_filter=domains,
            response_format=_FEE_FORMAT,
        caller="broker_guide")
        if res.get("error"):
            continue
        try:
            d = json.loads(_strip_json(res.get("content", "")))
        except Exception:
            continue
        fee = str(d.get("fee", "")).strip()
        val = _fee_pct(fee)
        source = _verified_official_source_url(broker, d.get("source"))
        if source and _FEE_RE.search(fee) and 0 < val <= OVERSEAS_FEE_MAX_PCT:
            m = re.search(r"\d+(?:\.\d+)?\s*%", fee)  # % 토큰만(부가설명 제거)
            return {
                "fee": m.group(0) if m else fee,
                "source": source,
                "basis": str(d.get("basis", "")).strip(),
                "official": domains is not None,
            }
        if val > OVERSEAS_FEE_MAX_PCT:
            print(f"[broker_guide] {broker} 해외수수료 {fee} > {OVERSEAS_FEE_MAX_PCT}% — 환전우대/오프라인 오인 의심, 거부")
    return {}


# 환전 수수료(FX) — KR 브로커 미국주식 환전 비용. 대표값 = 온라인 환전우대율(리테일 비교 헤드라인),
# basis 에 기본 스프레드(매매기준율 대비 편도 ~1%)·조건. 우대율 0~100% 밖이면 오인 거부.
def _fx_query(broker: str) -> str:
    return (
        f"{broker} 의 '미국주식(달러) 온라인 환전' 비용을 공식 안내 기준 정확히 알려줘. "
        "⚠ fee 에는 온라인 기본 '환전우대율'을 % 로 (예: 95%). "
        "기본 환전 스프레드(원/달러 매매기준율 대비 편도, 보통 약 1%)와 우대 적용 조건·시간대는 basis 에 설명. "
        "영업점 아님, 온라인(MTS·HTS) 기본 기준. "
        '숫자는 % 로. JSON: {"fee": "95%", "source": "공식 출처 URL", "basis": "기본 스프레드/우대 조건"}'
    )


def _fetch_fx_fee(broker: str) -> dict:
    """focused 환전우대율 추출. 공식 도메인 1차 → 일반 fallback. 0~100% 타당값만 반환."""
    dom = _official_domain(broker)
    attempts: list = [[dom]] if dom else []
    for domains in attempts:
        res = call_perplexity(
            _fx_query(broker),
            system_prompt=_FEE_SYS,
            max_tokens=600,
            temperature=0.0,
            search_domain_filter=domains,
            response_format=_FEE_FORMAT,
        caller="broker_guide")
        if res.get("error"):
            continue
        try:
            d = json.loads(_strip_json(res.get("content", "")))
        except Exception:
            continue
        fee = str(d.get("fee", "")).strip()
        val = _fee_pct(fee)
        source = _verified_official_source_url(broker, d.get("source"))
        if source and _FEE_RE.search(fee) and 0 < val <= 100:  # 우대율(스프레드 아님) 0~100%
            m = re.search(r"\d+(?:\.\d+)?\s*%", fee)
            return {
                "fee": m.group(0) if m else fee,
                "source": source,
                "basis": str(d.get("basis", "")).strip(),
                "official": domains is not None,
            }
    return {}


def _stale(v) -> bool:
    s = str(v or "").strip()
    return not s or s in ("없음", "미제공", "정보없음", "정보 없음", "N/A", "n/a", "해당없음", "불명")


# sticky 병합 대상. 시효성·금액성 값은 매 실행에서 공식 출처를 다시 확인하므로 이어 쓰지 않는다.
_STICKY_BROKER = (
    "app",
    "isa",
    "credit_short",
    "community",
    "realtime_news",
    "app_rating",
)


def _sticky_merge(brokers: list, btt: list, prev) -> None:
    """이전 발행값과 필드별 병합 — 새 값이 빈칸/불확실이면 이전 값 유지.
    LLM run 마다 랜덤 빈칸/churn 방지 → 데이터가 갈수록 안정. event 는 제외(만료 갱신)."""
    if not isinstance(prev, dict):
        return
    prev_b = {b.get("name", ""): b for b in (prev.get("brokers") or []) if isinstance(b, dict)}
    for b in brokers:
        if not isinstance(b, dict):
            continue
        pv = prev_b.get(b.get("name", ""))
        if not isinstance(pv, dict):
            continue
        for k in _STICKY_BROKER:
            if _stale(b.get(k)) and not _stale(pv.get(k)):
                b[k] = pv[k]
    prev_t = {t.get("type", ""): t for t in (prev.get("by_trade_type") or []) if isinstance(t, dict)}
    for t in btt:
        if not isinstance(t, dict):
            continue
        pv = prev_t.get(t.get("type", ""))
        if not isinstance(pv, dict):
            continue
        for k in ("best", "reason"):
            if _stale(t.get(k)) and not _stale(pv.get(k)):
                t[k] = pv[k]


def collect(force: bool = False) -> dict:
    """Perplexity 호출 → 검증 → sticky 병합 → broker_guide.json 발행. 실패 시 직전 유지."""
    prev = _load_prev()
    # search_recency_filter 미사용 — 수수료표·앱평점은 상시 참조정보라 "최근 N일" 제한 시 못 찾음.
    # 메인 호출 = ISA·신용·거래유형(soft). 수수료는 아래 focused 호출이 정밀 override.
    res = call_perplexity(
        _build_query(),
        system_prompt=_SYSTEM,
        max_tokens=5200,
        temperature=0.05,
        response_format=_RESPONSE_FORMAT,
    caller="broker_guide")
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
                b["domestic_source"] = info["source"]
                if info["source"] not in fee_sources:
                    fee_sources.append(info["source"])
            fee_ok += 1
        else:
            b["domestic_fee"] = ""
            b["fee_basis"] = ""
            b["domestic_source"] = ""
            print(f"[broker_guide] ⚠ 수수료 공식 검증 실패(공란): {b.get('name','?')}")

    # 🎯 focused 미국주식 수수료 추출 (정밀 + 공식 출처) → overseas_fee/basis override
    ov_ok = 0
    for b in brokers:
        if not isinstance(b, dict):
            continue
        info = _fetch_overseas_fee(b.get("name", ""))
        if info.get("fee"):
            b["overseas_fee"] = info["fee"]
            if info.get("basis"):
                b["overseas_basis"] = info["basis"]
            if info.get("source"):
                b["overseas_source"] = info["source"]  # 해외수수료 tile 전용 검증 링크
                if info["source"] not in fee_sources:
                    fee_sources.append(info["source"])
            ov_ok += 1
        else:
            b["overseas_fee"] = ""
            b["overseas_basis"] = ""
            b["overseas_source"] = ""
            print(f"[broker_guide] ⚠ 해외수수료 공식 검증 실패(공란): {b.get('name','?')}")
    print(f"[broker_guide] 해외수수료 채움 {ov_ok}/{len(brokers)}")

    # 🎯 focused 환전(FX)우대율 추출 → fx_fee/fx_basis/fx_source (미국주식 실비용 핵심, 별도 tile)
    fx_ok = 0
    for b in brokers:
        if not isinstance(b, dict):
            continue
        info = _fetch_fx_fee(b.get("name", ""))
        if info.get("fee"):
            b["fx_fee"] = info["fee"]
            if info.get("basis"):
                b["fx_basis"] = info["basis"]
            if info.get("source"):
                b["fx_source"] = info["source"]
                if info["source"] not in fee_sources:
                    fee_sources.append(info["source"])
            fx_ok += 1
        else:
            b["fx_fee"] = ""
            b["fx_basis"] = ""
            b["fx_source"] = ""
            print(f"[broker_guide] ⚠ 환전우대 공식 검증 실패(공란): {b.get('name','?')}")
    print(f"[broker_guide] 환전우대 채움 {fx_ok}/{len(brokers)}")

    # 수동 큐레이션 override (있으면 자동값보다 우선)
    _apply_curated(brokers)
    for b in brokers:
        if isinstance(b, dict) and b.get("source_url") and not b.get("domestic_source"):
            b["domestic_source"] = b["source_url"]

    # 이전 발행값 sticky 병합 (새 run 빈칸/churn → 이전 값 유지, event 제외) — LLM 불안정 완화
    btt = parsed.get("by_trade_type", [])
    _sticky_merge(brokers, btt, prev)

    safety_flags = _sanitize_events(brokers)
    safety_flags.extend(_sanitize_numeric_claims(brokers))

    # 산문 포함·제3자 링크를 발행 전에 제거한다. UI는 이 URL-only 목록만 소비한다.
    fee_sources = _sanitize_sources(brokers)

    ok, flags = _validate(parsed)
    flags.extend(safety_flags)
    if not ok:
        print(f"[broker_guide] 검증 실패 — 직전 유지: {flags}")
        return {"status": "validate_fail", "kept_prev": prev is not None, "flags": flags}

    out = {
        "as_of": datetime.now(KST).isoformat(),
        "source": f"perplexity {res.get('model', 'sonar')} (자동집계)",
        "disclaimer": DISCLAIMER,
        "brokers": brokers,
        "by_trade_type": btt,
        # 출처 = 증권사별 공식 도메인으로 정규화한 URL-only 목록
        "citations": fee_sources,
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
