#!/usr/bin/env python3
"""Publish grounded AlphaNest Observation Notes to the public thesis feed.

Cadence is stored in Supabase: one run becomes due every 1-3 days and publishes
one high-signal record. Copy is deterministic and source-bound; no LLM is used.
Every item stays neutral (stance=watch) and points to an official DART or SEC
filing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
KR_FEED = ROOT / "data" / "public_disclosure_feed.json"
US_FEED = ROOT / "data" / "us_disclosure_feed.json"
SCHEDULE_ID = "alphaconsole_public"
SYSTEM_LABEL = "알파네스트 관찰 노트"
GENERATOR_VERSION = "public_observation_rule_v5"
MAX_ARTIFACT_AGE_HOURS = 48
MAX_EVENT_AGE_DAYS = 7
OFFICIAL_HOSTS = {"dart.fss.or.kr", "www.sec.gov"}
PROHIBITED_COPY = (
    "지금 매수", "지금 매도", "매수 추천", "매도 추천", "목표가", "권장 비중",
    "수익 보장", "원금 보장", "확실한 수익", "무조건 오른", "무조건 내린",
)


@dataclass(frozen=True)
class Candidate:
    ticker: str
    market: str
    name: str
    event_date: date
    title: str
    label: str
    source_url: str
    source_name: str
    artifact_generated_at: str
    item_codes: tuple[str, ...]
    is_correction: bool
    priority: int
    topic: str

    @property
    def source_key(self) -> str:
        raw = f"{self.market}|{self.ticker}|{self.source_url}".encode("utf-8")
        return "obs_" + hashlib.sha256(raw).hexdigest()[:32]


def _parse_dt(raw: Any) -> datetime | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        value = datetime.fromisoformat(text)
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    except ValueError:
        return None


def _parse_date(raw: Any) -> date | None:
    try:
        return date.fromisoformat(str(raw or "")[:10])
    except ValueError:
        return None


def _official_url(raw: Any) -> str:
    text = str(raw or "").strip()
    try:
        parsed = urlparse(text)
    except ValueError:
        return ""
    if parsed.scheme != "https" or parsed.hostname not in OFFICIAL_HOSTS:
        return ""
    return text


def _dart_receipt_number(raw: Any) -> int | None:
    try:
        values = urllib.parse.parse_qs(urlparse(str(raw or "")).query).get("rcpNo") or []
        return int(values[0]) if values and values[0].isdigit() else None
    except (ValueError, TypeError):
        return None


SEC_ITEM_TOPICS = {
    "1.01": "material_agreement",
    "1.02": "material_agreement_end",
    "2.01": "structure",
    "2.02": "earnings",
    "2.03": "debt_financing",
    "2.04": "obligation_trigger",
    "2.05": "restructuring",
    "2.06": "accounting_risk",
    "3.01": "listing_risk",
    "3.02": "unregistered_equity_sale",
    "4.01": "audit_change",
    "4.02": "accounting_risk",
    "5.01": "control_change",
    "5.02": "governance",
    "5.03": "charter_or_fiscal_year_change",
}

SEC_TOPIC_ORDER = (
    "listing_risk", "accounting_risk", "obligation_trigger", "restructuring",
    "unregistered_equity_sale", "debt_financing", "structure", "control_change",
    "material_agreement_end", "earnings", "material_agreement", "audit_change",
    "charter_or_fiscal_year_change", "governance",
)


def _sec_topic(item_codes: tuple[str, ...]) -> str:
    topics = {SEC_ITEM_TOPICS[code] for code in item_codes if code in SEC_ITEM_TOPICS}
    return next((topic for topic in SEC_TOPIC_ORDER if topic in topics), "current_report")


def _normalized_title_family(raw: Any) -> str:
    """Group an original KR filing with follow-up correction filings.

    The public feed does not carry a correction-to-original relationship or a
    before/after diff. Removing the correction prefix therefore gives us a
    conservative family key; if a correction exists, the family is skipped
    until the changed fields are available.
    """
    text = str(raw or "").strip()
    while re.match(r"^\[[^\]]*정정\]\s*", text):
        text = re.sub(r"^\[[^\]]*정정\]\s*", "", text, count=1)
    return re.sub(r"\s+", "", text).upper()


def _topic(market: str, label: str, title: str, item_codes: tuple[str, ...] = ()) -> str:
    if market == "US":
        return _sec_topic(item_codes)
    text = f"{label} {title}".upper()
    if "유동성공급계약" in text:
        return "market_liquidity"
    if "회생절차" in text:
        return "distress"
    if any(k in text for k in ("상장폐지", "관리종목", "거래정지", "감사의견")):
        return "kr_listing_risk"
    if any(k in text for k in ("유상증자결정", "전환사채권발행결정", "신주인수권부사채권발행결정")):
        return "dilutive_financing"
    if "감자결정" in text:
        return "capital_reduction"
    if "채무증권발행결정" in text:
        return "debt_financing"
    if any(k in text for k in ("합병", "분할", "자산양수도", "영업양수도")):
        return "structure"
    if any(k in text for k in ("잠정실적", "영업실적", "사업보고서", "분기보고서")):
        return "earnings"
    if any(k in text for k in ("단일판매", "공급계약", "수주")):
        return "contract"
    if any(k in text for k in ("자기주식처분", "자사주처분")):
        return "treasury_sale"
    if any(k in text for k in ("자기주식취득", "자사주취득")):
        return "treasury_buyback"
    if any(k in text for k in ("대량보유", "임원", "주요주주")):
        return "ownership"
    return "other"


PUBLISHABLE_TOPICS = {
    "accounting_risk", "audit_change", "capital_reduction", "contract",
    "control_change", "debt_financing", "dilutive_financing", "distress",
    "earnings", "governance", "kr_listing_risk", "listing_risk",
    "material_agreement", "material_agreement_end", "obligation_trigger",
    "ownership", "restructuring", "structure", "treasury_buyback",
    "treasury_sale", "unregistered_equity_sale", "charter_or_fiscal_year_change",
}


def _priority(topic: str, event_date: date, now: datetime) -> int:
    age = max(0, (now.date() - event_date).days)
    score = max(0, 28 - age * 4)
    weights = {
        "distress": 115,
        "listing_risk": 112,
        "accounting_risk": 110,
        "obligation_trigger": 109,
        "restructuring": 108,
        "dilutive_financing": 100,
        "capital_reduction": 100,
        "debt_financing": 98,
        "structure": 95,
        "earnings": 85,
        "contract": 80,
        "material_agreement": 84,
        "material_agreement_end": 86,
        "unregistered_equity_sale": 100,
        "treasury_buyback": 72,
        "treasury_sale": 74,
        "audit_change": 68,
        "governance": 60,
        "control_change": 88,
        "charter_or_fiscal_year_change": 62,
        "ownership": 55,
    }
    return score + weights.get(topic, 0)


COPY_BY_TOPIC = {
    "dilutive_financing": {
        "angle": "{name}의 자금 조달, 조달 소식보다 기존 주주의 희석 부담이 먼저예요.",
        "meaning": "신주나 전환 가능 증권은 현금을 늘릴 수 있지만 기존 주주의 몫도 줄일 수 있어요.",
        "unknown": "현재 수집된 공시 요약에는 신규 물량의 기존 주식 대비 비율, 발행가 조건, 자금 용도가 없습니다.",
        "condition": "신규 물량과 할인 폭이 작고 자금이 성장 투자로 이어지면 부담이 낮아집니다. 희석 폭이 크거나 운영자금 보전에 머물면 부담이 커집니다.",
    },
    "debt_financing": {
        "angle": "{name}의 차입·채권 발행, 조달액보다 이자와 상환 부담을 먼저 봐야 해요.",
        "meaning": "부채 조달은 주식 희석을 피할 수 있지만 이자 비용과 만기 상환 부담을 늘려요.",
        "unknown": "현재 수집된 공시 요약에는 조달금액, 금리, 만기, 자금 용도가 없습니다.",
        "condition": "영업현금흐름으로 이자와 만기를 감당할 수 있으면 부담이 낮아집니다. 차환 의존이 커지면 위험이 높아집니다.",
    },
    "capital_reduction": {
        "angle": "{name}의 감자 결정, 주식 수 감소보다 감자 이유와 주주 손실 여부가 핵심이에요.",
        "meaning": "감자는 결손 보전이나 자본 구조 조정에 쓰이며 유상·무상 방식에 따라 주주 영향이 달라요.",
        "unknown": "현재 수집된 공시 요약에는 감자 비율, 유상 여부, 기준일과 거래정지 일정이 없습니다.",
        "condition": "재무 구조 개선 효과와 주주 보상 조건이 분명하면 부담이 낮아집니다. 손실만 이전되면 부담이 커집니다.",
    },
    "contract": {
        "angle": "{name}의 계약 공시, 계약 체결보다 매출 대비 규모와 이행 조건이 본론이에요.",
        "meaning": "계약은 수주잔고를 늘릴 수 있지만 체결 금액이 곧바로 같은 금액의 매출이 되는 것은 아니에요.",
        "unknown": "현재 수집된 공시 요약에는 계약금액의 최근 매출 대비 비중, 수행 기간, 해지 조건이 없습니다.",
        "condition": "매출 대비 비중이 크고 이행 조건이 확정적이면 의미가 커집니다. 규모가 작거나 해지 범위가 넓으면 의미가 줄어듭니다.",
    },
    "material_agreement": {
        "angle": "{name}의 중요 계약 8-K, 계약 이름보다 회사가 새로 지는 의무와 해지 조건이 핵심이에요.",
        "meaning": "SEC Item 1.01은 통상 영업 밖의 중요한 계약 체결이나 중대한 변경을 알리는 항목이며, 매출 계약으로 한정되지 않아요.",
        "unknown": "현재 수집된 공시 요약에는 계약 종류, 상대방, 지급·이행 의무와 해지 조건이 없습니다.",
        "condition": "회사가 얻는 권리와 반복 현금흐름이 의무보다 크면 의미가 좋아집니다. 큰 지급 의무나 해지 비용이 붙으면 부담이 커집니다.",
    },
    "material_agreement_end": {
        "angle": "{name}의 중요 계약 종료 8-K, 종료 사실보다 사라지는 권리·의무와 위약 비용이 핵심이에요.",
        "meaning": "SEC Item 1.02는 중요한 계약의 종료를 알리며, 매출 계약뿐 아니라 자금·제휴·기타 계약도 포함할 수 있어요.",
        "unknown": "현재 수집된 공시 요약에는 종료된 계약의 종류, 종료 사유, 위약금과 남은 의무가 없습니다.",
        "condition": "종료 비용이 작고 대체 계약이나 권리가 있으면 영향이 줄어듭니다. 핵심 권리를 잃거나 큰 지급 의무가 생기면 부담이 커집니다.",
    },
    "obligation_trigger": {
        "angle": "{name}의 채무 의무 발생 8-K, 사건 이름보다 당겨진 상환액과 지급 시점이 핵심이에요.",
        "meaning": "SEC Item 2.04는 회사의 직접 또는 부외 채무가 빨라지거나 늘어나는 사건을 알리는 항목이에요.",
        "unknown": "현재 수집된 공시 요약에는 대상 채무, 가속·증가 금액, 지급 기한과 면제 협상 여부가 없습니다.",
        "condition": "금액이 작고 면제나 충분한 현금이 확인되면 부담이 낮아집니다. 단기 상환액이 유동성을 넘으면 위험이 커집니다.",
    },
    "unregistered_equity_sale": {
        "angle": "{name}의 미등록 증권 발행 8-K, 발행 사실보다 새 물량과 조건이 기존 주주에게 어떤 영향을 주는지가 핵심이에요.",
        "meaning": "SEC Item 3.02는 등록 절차 없이 지분 증권을 발행한 사실을 알리며, 현금 조달 외 거래 대가나 보상도 포함할 수 있어요.",
        "unknown": "현재 수집된 공시 요약에는 증권 종류, 발행 수량·가격, 수령인과 발행 목적이 없습니다.",
        "condition": "신규 물량이 작고 회사가 받는 대가가 충분하면 부담이 낮아집니다. 할인과 잠재 희석이 크면 기존 주주 부담이 커집니다.",
    },
    "control_change": {
        "angle": "{name}의 지배권 변화 8-K, 명칭보다 의결권과 이사회 통제가 누구에게 이동했는지가 핵심이에요.",
        "meaning": "SEC Item 5.01은 회사 지배권의 변화를 알리는 항목으로 소유권, 의결권, 이사회 구성과 연결될 수 있어요.",
        "unknown": "현재 수집된 공시 요약에는 새 지배 주체, 의결권 비율, 거래 대가와 이사회 변화가 없습니다.",
        "condition": "책임 주체와 사업 계획이 분명하면 불확실성이 줄어듭니다. 자금 출처나 소수주주 조건이 불투명하면 부담이 커집니다.",
    },
    "charter_or_fiscal_year_change": {
        "angle": "{name}의 정관·회계연도 변경 8-K, 제목보다 실제로 바뀐 조항이나 결산 기준이 핵심이에요.",
        "meaning": "SEC Item 5.03은 정관·부속 규정의 변경 또는 회계연도 변경을 알리는 항목이에요.",
        "unknown": "현재 수집된 공시 요약에는 변경 유형, 바뀐 조항·회계연도, 효력 발생일과 주주 영향이 없습니다.",
        "condition": "단순한 운영 일정 정비라면 영향이 작습니다. 발행 권한 확대나 주주 권리 축소가 포함되면 주의가 필요합니다.",
    },
    "structure": {
        "angle": "{name}의 합병·분할, 결정 사실보다 거래 조건과 기존 주주의 몫이 본론이에요.",
        "meaning": "회사 구조가 바뀌면 자산과 사업뿐 아니라 주식 수와 현금흐름도 함께 달라질 수 있어요.",
        "unknown": "현재 수집된 공시 요약에는 거래가액, 합병·분할 비율, 대금 지급 방식이 없습니다.",
        "condition": "거래 조건이 기존 주주에게 유리하고 현금 부담이 감당 가능하면 의미가 좋아집니다. 거래가액이 과도하거나 현금 유출과 희석이 크면 부담이 커집니다.",
    },
    "earnings": {
        "angle": "{name}의 실적 공시, 숫자의 방향보다 반복 가능한 본업 변화인지가 핵심이에요.",
        "meaning": "매출과 이익의 증감은 일회성 항목이나 비용 인식 시점에 따라 다르게 보일 수 있어요.",
        "unknown": "현재 수집된 공시 요약에는 전년 동기 대비 증감 원인, 일회성 항목, 영업현금흐름이 없습니다.",
        "condition": "본업에서 매출·이익·현금흐름이 함께 개선되면 해석이 강해집니다. 일회성 이익만 늘었다면 의미가 약해집니다.",
    },
    "ownership": {
        "angle": "{name}의 지분 변동, 매수·매도보다 누가 왜 움직였는지가 더 중요해요.",
        "meaning": "같은 지분 변동도 경영 참여, 단순 투자, 담보 계약에 따라 뜻이 달라져요.",
        "unknown": "현재 수집된 공시 요약에는 변동 수량·비율과 보유 목적의 변화가 없습니다.",
        "condition": "보유 목적 변경과 연속 거래가 확인되면 의미가 커집니다. 단순 보고 기준 변경이면 의미가 줄어듭니다.",
    },
    "treasury_buyback": {
        "angle": "{name}의 자사주 결정, 발표보다 실제 취득·소각 여부가 핵심이에요.",
        "meaning": "자사주 취득은 유통 주식 수를 줄일 수 있지만, 처분이나 신탁 해지로 효과가 달라질 수 있어요.",
        "unknown": "현재 수집된 공시 요약에는 취득·처분 규모, 기간, 소각 계획이 없습니다.",
        "condition": "실제 취득 뒤 소각까지 이어지면 주당 가치 효과가 선명해집니다. 미취득이나 재처분이면 효과가 약해집니다.",
    },
    "treasury_sale": {
        "angle": "{name}의 자사주 처분, 처분 목적과 시장에 나오는 물량이 핵심이에요.",
        "meaning": "보유 자사주가 다시 유통되면 주식 공급이 늘 수 있고, 처분 상대와 가격에 따라 의미가 달라져요.",
        "unknown": "현재 수집된 공시 요약에는 처분 수량, 가격, 상대방과 자금 용도가 없습니다.",
        "condition": "임직원 보상이나 전략적 제휴에 제한적으로 쓰이면 부담이 낮아집니다. 할인 폭과 유통 물량이 크면 기존 주주 부담이 커집니다.",
    },
    "distress": {
        "angle": "{name}의 회생 관련 공시, 신청과 법원의 개시 결정은 다른 단계예요.",
        "meaning": "신청 사실은 유동성 위험을 보여주지만 절차 개시와 최종 회생 여부까지 확정한 것은 아니에요.",
        "unknown": "현재 수집된 공시 요약에는 법원의 결정 여부, 채무 조정 범위, 주주에게 적용될 조건이 없습니다.",
        "condition": "채무 부담이 줄고 영업 지속 가능성이 확인되면 회생 가능성이 높아집니다. 큰 출자전환이나 감자가 필요하면 주주 부담이 커집니다.",
    },
    "accounting_risk": {
        "angle": "{name}의 회계 관련 8-K, 발표보다 손실 규모와 기존 숫자의 신뢰가 핵심이에요.",
        "meaning": "자산 손상이나 기존 재무제표 비신뢰 공시는 이익과 재무 수치를 다시 보게 만드는 사건이에요.",
        "unknown": "현재 수집된 공시 요약에는 조정 금액, 영향을 받는 기간, 감사 절차와 현금 유출 여부가 없습니다.",
        "condition": "영향이 한 기간에 그치고 현금 유출이 제한적이면 부담이 줄어듭니다. 여러 기간의 재작성으로 번지면 위험이 커집니다.",
    },
    "listing_risk": {
        "angle": "{name}의 상장 관련 8-K, 통지 사실보다 개선 기한과 실제 상장 유지 조건이 핵심이에요.",
        "meaning": "상장 요건 통지는 즉시 상장폐지를 뜻하지 않지만 정해진 기간 안에 요건을 회복해야 해요.",
        "unknown": "현재 수집된 공시 요약에는 미충족 요건, 개선 기한, 회사의 회복 계획이 없습니다.",
        "condition": "기한 안에 요건을 회복하면 위험이 낮아집니다. 개선 계획이 지연되거나 추가 요건까지 어기면 위험이 커집니다.",
    },
    "kr_listing_risk": {
        "angle": "{name}의 상장 관련 공시, 지정·통지 사실보다 개선 기한과 거래 가능 여부가 핵심이에요.",
        "meaning": "관리종목 지정이나 상장폐지 사유 발생은 즉시 최종 폐지를 뜻하지 않지만 후속 심사와 개선 절차가 남아요.",
        "unknown": "현재 수집된 공시 요약에는 발생 사유, 이의신청·개선 기한, 거래정지 조건이 없습니다.",
        "condition": "기한 안에 사유를 해소하고 거래가 재개되면 위험이 낮아집니다. 개선 실패나 추가 사유가 생기면 위험이 커집니다.",
    },
    "restructuring": {
        "angle": "{name}의 구조조정 8-K, 비용 절감 기대보다 현금 비용과 실행 기간을 먼저 봐야 해요.",
        "meaning": "구조조정은 장기 비용을 낮출 수 있지만 단기 퇴직·폐쇄 비용과 사업 차질을 만들 수 있어요.",
        "unknown": "현재 수집된 공시 요약에는 예상 비용, 현금 지출액, 완료 시점과 절감 예상치가 없습니다.",
        "condition": "현금 비용이 제한적이고 절감 효과가 반복되면 의미가 좋아집니다. 비용이 늘거나 매출 훼손이 크면 부담이 커집니다.",
    },
    "audit_change": {
        "angle": "{name}의 감사인 변경, 교체 사실보다 사임 이유와 회계 이견 여부가 핵심이에요.",
        "meaning": "감사인 변경은 통상 절차일 수도 있지만 회계 처리나 내부통제 갈등과 연결될 수도 있어요.",
        "unknown": "현재 수집된 공시 요약에는 변경 사유, 회계 이견, 후임 감사인의 선임 조건이 없습니다.",
        "condition": "이견이 없고 후임 선임이 원활하면 부담이 낮아집니다. 재무제표나 내부통제 갈등이 확인되면 위험이 커집니다.",
    },
    "governance": {
        "angle": "{name}의 임원·이사 변화 8-K, 이름보다 이탈 이유와 의사결정 공백이 핵심이에요.",
        "meaning": "SEC Item 5.02는 주요 이사·임원의 사임, 해임, 선임이나 보상 변경을 알리는 항목이에요.",
        "unknown": "현재 수집된 공시 요약에는 변경 사유, 후임자의 역할, 보상 조건과 회계 이견 여부가 없습니다.",
        "condition": "독립성과 전문성이 강화되면 의미가 좋아집니다. 갑작스러운 이탈이나 재무보고 갈등이 확인되면 위험이 커집니다.",
    },
}


def _load_candidates(path: Path, market: str, now: datetime) -> tuple[list[Candidate], dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    meta = payload.get("_meta") if isinstance(payload, dict) else {}
    items = payload.get("items") if isinstance(payload, dict) else []
    generated = _parse_dt((meta or {}).get("generated_at"))
    artifact_age = ((now - generated).total_seconds() / 3600) if generated else None
    usable_artifact = artifact_age is not None and 0 <= artifact_age <= MAX_ARTIFACT_AGE_HOURS
    out: list[Candidate] = []
    disclosure_total = 0
    reject_counts: dict[str, int] = {}

    for company in items or []:
        ticker = str(company.get("ticker") or "").strip().upper()
        name = str(company.get("name") or company.get("filer") or ticker).strip()
        disclosures = company.get("disclosures") or []
        correction_family_markers: dict[str, list[tuple[date | None, int | None]]] = {}
        for disclosure in disclosures:
            disclosure_title = str(disclosure.get("title") or disclosure.get("label") or "").strip()
            if bool(disclosure.get("is_correction")) or bool(re.match(r"^\[[^\]]*정정\]", disclosure_title)):
                family = _normalized_title_family(disclosure_title)
                correction_family_markers.setdefault(family, []).append((
                    _parse_date(disclosure.get("date")),
                    _dart_receipt_number(disclosure.get("source_url")),
                ))
        for event in disclosures:
            disclosure_total += 1
            event_date = _parse_date(event.get("date"))
            source_url = _official_url(event.get("source_url"))
            receipt_number = _dart_receipt_number(source_url) if market == "KR" else None
            label = str(event.get("label") or event.get("title") or "공시").strip()
            title = str(event.get("title") or label).strip()
            item_codes = tuple(str(code).strip() for code in (event.get("item_codes") or []) if str(code).strip())
            is_correction = bool(event.get("is_correction")) or bool(re.match(r"^\[[^\]]*정정\]", title))
            title_family = _normalized_title_family(title)
            topic = _topic(market, label, title, item_codes)
            age_days = (now.date() - event_date).days if event_date else None
            reason = ""
            if not usable_artifact:
                reason = "artifact_stale"
            elif not ticker:
                reason = "ticker_missing"
            elif event_date is None or age_days is None or age_days < 0 or age_days > MAX_EVENT_AGE_DAYS:
                reason = "event_outside_window"
            elif not source_url:
                reason = "source_not_official"
            elif is_correction:
                # The feed does not contain a before/after diff. Publishing an
                # interpretation here would repeat the original event without
                # explaining what actually changed.
                reason = "correction_without_diff"
            elif title_family and any(
                correction_date is None
                or correction_date > event_date
                or (
                    correction_date == event_date
                    and (
                        correction_receipt is None
                        or receipt_number is None
                        or correction_receipt > receipt_number
                    )
                )
                for correction_date, correction_receipt in correction_family_markers.get(title_family, [])
            ):
                reason = "correction_family_without_diff"
            elif topic not in PUBLISHABLE_TOPICS:
                reason = "insufficient_context"
            if reason:
                reject_counts[reason] = reject_counts.get(reason, 0) + 1
                continue
            out.append(Candidate(
                ticker=ticker,
                market=market.lower(),
                name=name,
                event_date=event_date,
                title=title,
                label=label,
                source_url=source_url,
                source_name="DART" if market == "KR" else "SEC EDGAR",
                artifact_generated_at=(generated.isoformat() if generated else ""),
                item_codes=item_codes,
                is_correction=is_correction,
                priority=_priority(topic, event_date, now),
                topic=topic,
            ))

    try:
        display_path = str(path.relative_to(ROOT))
    except ValueError:
        display_path = path.name
    return out, {
        "file": display_path,
        "companies": len(items or []),
        "disclosures": disclosure_total,
        "eligible": len(out),
        "artifact_generated_at": generated.isoformat() if generated else None,
        "artifact_age_hours": round(artifact_age, 2) if artifact_age is not None else None,
        "rejects": reject_counts,
    }


def collect_candidates(now: datetime, kr_path: Path = KR_FEED, us_path: Path = US_FEED) -> tuple[list[Candidate], list[dict[str, Any]]]:
    candidates: list[Candidate] = []
    coverage: list[dict[str, Any]] = []
    for path, market in ((kr_path, "KR"), (us_path, "US")):
        rows, report = _load_candidates(path, market, now)
        candidates.extend(rows)
        coverage.append(report)
    # Same filing URL can appear more than once in carried-forward source data.
    deduped = {row.source_key: row for row in candidates}
    return list(deduped.values()), coverage


def select_candidates(candidates: Iterable[Candidate], count: int, rng: random.Random, used_keys: set[str] | None = None) -> list[Candidate]:
    del rng  # Candidate quality and recency decide publication order.
    used = used_keys or set()
    pool = [row for row in candidates if row.source_key not in used]
    pool.sort(key=lambda row: (row.priority, row.event_date, row.ticker), reverse=True)
    selected: list[Candidate] = []
    tickers: set[str] = set()
    topics: set[str] = set()
    for row in pool:
        if row.ticker in tickers or row.topic in topics:
            continue
        selected.append(row)
        tickers.add(row.ticker)
        topics.add(row.topic)
        if len(selected) >= count:
            return selected
    for row in pool:
        if row.ticker in tickers:
            continue
        selected.append(row)
        tickers.add(row.ticker)
        if len(selected) >= count:
            break
    return selected


def make_note(row: Candidate, published_at: datetime) -> str:
    stamp = published_at.astimezone(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M KST")
    copy = COPY_BY_TOPIC[row.topic]
    codes = f" SEC 항목 {', '.join(row.item_codes)}가 포함됐어요." if row.market == "us" and row.item_codes else ""
    note = (
        "한줄로 보면\n"
        f"지금 나온 정보만으로는 영향이 큰지 작은지 아직 판단하기 어려워요. {copy['angle'].format(name=row.name)}\n\n"
        "무슨 일이 있었나\n"
        f"{row.event_date.isoformat()} {row.name}가 ‘{row.title}’ 공시를 냈어요.{codes} {copy['meaning']}\n\n"
        "아직 확인할 것\n"
        f"{copy['unknown']}\n\n"
        "생각이 달라지는 조건\n"
        f"{copy['condition']}\n\n"
        f"자료 기준 {row.event_date.isoformat()} · 게시 {stamp} · v2\n"
        f"출처: {row.source_name} 원문 {row.source_url}"
    )
    if any(term in note for term in PROHIBITED_COPY):
        raise ValueError("prohibited investment-direction copy detected")
    return note


def make_row(row: Candidate, published_at: datetime) -> dict[str, Any]:
    data_as_of = datetime.combine(row.event_date, time.min, tzinfo=timezone.utc)
    return {
        "user_id": None,
        "ticker": row.ticker,
        "market": row.market,
        "stance": "watch",
        "note": make_note(row, published_at),
        "entry_price": None,
        "is_public": True,
        "hidden": False,
        "author_kind": "system",
        "system_label": SYSTEM_LABEL,
        "data_as_of": data_as_of.isoformat(),
        "published_at": published_at.isoformat(),
        "source_url": row.source_url,
        "source_title": row.title[:500],
        "source_key": row.source_key,
        "content_version": 2,
        "observation_meta": {
            "generator": GENERATOR_VERSION,
            "generated_by_ai": False,
            "source_name": row.source_name,
            "source_label": row.label,
            "source_published_date": row.event_date.isoformat(),
            "source_artifact_generated_at": row.artifact_generated_at,
            "source_item_codes": list(row.item_codes),
            "source_is_correction": row.is_correction,
            "selection_priority": row.priority,
            "source_topic": row.topic,
            "copy_sections": ["summary", "event", "unknowns", "decision_conditions"],
            "quality_gate": "event_type_signal_required_v1",
            "stance_policy": "watch_only",
        },
    }


class SupabaseRest:
    def __init__(self, base_url: str, service_key: str):
        self.base = base_url.rstrip("/")
        self.headers = {
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Content-Type": "application/json",
        }

    def request(self, method: str, path: str, body: Any = None, prefer: str = "") -> Any:
        headers = dict(self.headers)
        if prefer:
            headers["Prefer"] = prefer
        data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(f"{self.base}/rest/v1/{path}", data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=25) as response:
            raw = response.read().decode("utf-8")
        return json.loads(raw) if raw.strip() else None


def _is_missing_relation(exc: urllib.error.HTTPError) -> bool:
    try:
        raw = exc.read().decode("utf-8")
        payload = json.loads(raw)
    except Exception:
        return exc.code == 404
    return exc.code == 404 or payload.get("code") in {"42P01", "PGRST205"}


def _existing_source_keys(client: SupabaseRest, now: datetime) -> set[str]:
    since = urllib.parse.quote((now - timedelta(days=30)).isoformat(), safe="")
    path = f"user_thesis?author_kind=eq.system&created_at=gte.{since}&select=source_key&limit=500"
    rows = client.request("GET", path) or []
    return {str(row.get("source_key") or "") for row in rows if row.get("source_key")}


def _schedule(client: SupabaseRest) -> dict[str, Any] | None:
    sid = urllib.parse.quote(SCHEDULE_ID, safe="")
    rows = client.request("GET", f"system_thesis_schedule?schedule_id=eq.{sid}&select=*&limit=1") or []
    return rows[0] if rows else None


def _update_schedule(client: SupabaseRest, now: datetime, next_run: datetime, result: dict[str, Any]) -> None:
    sid = urllib.parse.quote(SCHEDULE_ID, safe="")
    client.request("PATCH", f"system_thesis_schedule?schedule_id=eq.{sid}", {
        "next_run_at": next_run.isoformat(),
        "last_run_at": now.isoformat(),
        "last_result": result,
        "updated_at": now.isoformat(),
    }, prefer="return=minimal")


def run(now: datetime, dry_run: bool, force: bool, seed: int | None = None) -> dict[str, Any]:
    rng: random.Random = random.Random(seed) if seed is not None else random.SystemRandom()
    candidates, coverage = collect_candidates(now)
    desired = 1
    base_result: dict[str, Any] = {
        "generated_at": now.isoformat(),
        "candidate_count": len(candidates),
        "requested_count": desired,
        "coverage": coverage,
        "generator": GENERATOR_VERSION,
    }

    if dry_run:
        selected = select_candidates(candidates, desired, rng)
        return {**base_result, "status": "dry_run", "selected": [make_row(row, now) for row in selected]}

    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required")
    client = SupabaseRest(url, key)
    try:
        schedule = _schedule(client)
    except urllib.error.HTTPError as exc:
        if _is_missing_relation(exc):
            return {**base_result, "status": "not_ready", "reason": "migration_not_applied"}
        raise
    if not schedule:
        return {**base_result, "status": "not_ready", "reason": "schedule_row_missing"}

    due_at = _parse_dt(schedule.get("next_run_at"))
    if not force and due_at and now < due_at:
        return {**base_result, "status": "not_due", "next_run_at": due_at.isoformat()}

    used = _existing_source_keys(client, now)
    selected = select_candidates(candidates, desired, rng, used)
    inserted: list[dict[str, Any]] = []
    for candidate in selected:
        row = make_row(candidate, now)
        try:
            result = client.request("POST", "user_thesis", row, prefer="return=representation")
        except urllib.error.HTTPError as exc:
            if exc.code == 409:
                continue
            raise
        if isinstance(result, list) and result:
            inserted.append({"id": result[0].get("id"), "ticker": candidate.ticker, "source_key": candidate.source_key})
        else:
            inserted.append({"ticker": candidate.ticker, "source_key": candidate.source_key})

    interval_days = rng.randint(1, 3) if inserted else 1
    next_run = now + timedelta(days=interval_days)
    status = "published" if inserted else "skipped_no_fresh_source"
    final = {**base_result, "status": status, "published_count": len(inserted), "published": inserted, "next_run_at": next_run.isoformat()}
    _update_schedule(client, now, next_run, final)
    return final


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--now", help="ISO-8601 UTC clock for deterministic verification")
    args = parser.parse_args()
    now = _parse_dt(args.now) if args.now else datetime.now(timezone.utc)
    if now is None:
        parser.error("--now must be ISO-8601")
    try:
        result = run(now, args.dry_run, args.force, args.seed)
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": type(exc).__name__, "detail": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
