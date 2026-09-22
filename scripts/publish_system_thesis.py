#!/usr/bin/env python3
"""Publish grounded AlphaNest Observation Notes to the public thesis feed.

Cadence is stored in Supabase: one run becomes due every 1-3 days and publishes
1-3 records. Copy is deterministic and source-bound; no LLM is used. Every item
stays neutral (stance=watch) and points to an official DART or SEC filing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
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
GENERATOR_VERSION = "public_observation_rule_v4"
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
    explanation: str
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


def _event_explanation(market: str, label: str, title: str) -> str:
    text = f"{label} {title}".upper()
    if market == "US":
        form = label.upper().strip()
        mapping = {
            "8-K": "중요 사건을 수시로 알리는 SEC 서류예요. 사건 종류와 재무 영향을 본문에서 확인해야 해요.",
            "10-Q": "분기 재무와 위험요인을 확인하는 SEC 정기보고서예요. 직전 분기와 같은 기준으로 비교해야 해요.",
            "10-K": "연간 재무와 사업·위험요인을 확인하는 SEC 정기보고서예요.",
            "6-K": "미국 외 기업이 제출한 수시 공시예요. 제출 사유가 건마다 달라 원문 확인이 필요해요.",
            "20-F": "미국 외 기업의 연간 사업·재무·위험요인을 담은 SEC 정기보고서예요.",
        }
        return mapping.get(form, "SEC 제출 사실이 확인됐어요. 제목만으로 영향과 방향을 단정할 수 없어 원문 확인이 필요해요.")
    if any(k in text for k in ("유상증자", "전환사채", "신주인수권")):
        return "새 주식이나 주식으로 바뀔 수 있는 증권이 늘어날 수 있어요. 발행 규모와 조건에 따라 기존 주주 지분이 달라질 수 있어요."
    if any(k in text for k in ("단일판매", "공급계약", "수주")):
        return "계약 사실이 확인됐어요. 계약금액을 최근 매출과 비교하고 기간·해지 조건을 함께 봐야 해요."
    if any(k in text for k in ("자산양수도", "영업양수도", "합병", "분할")):
        return "회사 자산이나 사업 구조가 달라질 수 있는 사건이에요. 거래 규모와 자금 조달 방식을 확인해야 해요."
    if any(k in text for k in ("잠정실적", "영업실적", "사업보고서", "분기보고서")):
        return "실적 자료가 새로 제출됐어요. 같은 기간의 매출·이익·현금흐름을 함께 비교해야 해요."
    if any(k in text for k in ("대량보유", "임원", "주요주주")):
        return "주요 보유자의 지분 변동이 보고됐어요. 변동 수량·비율과 보유 목적을 원문에서 확인해야 해요."
    return "새 공시가 제출됐어요. 제목만으로 실제 규모와 주가 방향을 단정할 수 없어 원문 확인이 필요해요."


def _priority(market: str, label: str, title: str, event_date: date, now: datetime) -> int:
    text = f"{label} {title}".upper()
    age = max(0, (now.date() - event_date).days)
    score = max(0, 28 - age * 4)
    if any(k in text for k in ("유상증자", "전환사채", "신주인수권", "감자")):
        score += 95
    elif any(k in text for k in ("합병", "분할", "자산양수도", "영업양수도")):
        score += 90
    elif any(k in text for k in ("잠정실적", "영업실적", "사업보고서", "분기보고서", "10-Q", "10-K", "20-F")):
        score += 80
    elif any(k in text for k in ("단일판매", "공급계약", "수주")):
        score += 75
    elif any(k in text for k in ("대량보유", "임원", "주요주주")):
        score += 55
    elif market == "US" and "8-K" in text:
        score += 65
    elif market == "US" and "6-K" in text:
        score += 50
    else:
        score += 35
    return score


def _next_check(label: str, title: str) -> str:
    text = f"{label} {title}".upper()
    if any(k in text for k in ("유상증자", "전환사채", "신주인수권")):
        return "발행 규모·가격·일정·전환 조건과 추가 정정공시"
    if any(k in text for k in ("단일판매", "공급계약", "수주")):
        return "계약금액의 최근 매출 대비 비중·계약기간·해지 조건"
    if any(k in text for k in ("자산양수도", "영업양수도", "합병", "분할")):
        return "거래금액·장부가·대금 지급 방식과 향후 현금흐름"
    if any(k in text for k in ("잠정실적", "영업실적", "10-Q", "10-K", "20-F")):
        return "비교 기간·일회성 항목·현금흐름·회사 설명"
    if any(k in text for k in ("대량보유", "임원", "주요주주")):
        return "변동 수량·변동 비율·보유 목적·후속 보고"
    return "원문 핵심 항목·금액·일정·정정 여부"


def _topic(label: str, title: str) -> str:
    text = f"{label} {title}".upper()
    if any(k in text for k in ("유상증자", "전환사채", "신주인수권", "감자")):
        return "capital_change"
    if any(k in text for k in ("합병", "분할", "자산양수도", "영업양수도")):
        return "structure"
    if any(k in text for k in ("잠정실적", "영업실적", "사업보고서", "분기보고서", "10-Q", "10-K", "20-F")):
        return "earnings"
    if any(k in text for k in ("단일판매", "공급계약", "수주")):
        return "contract"
    if any(k in text for k in ("대량보유", "임원", "주요주주")):
        return "ownership"
    if "8-K" in text or "6-K" in text:
        return "current_report"
    return "other"


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
        for event in company.get("disclosures") or []:
            disclosure_total += 1
            event_date = _parse_date(event.get("date"))
            source_url = _official_url(event.get("source_url"))
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
            if reason:
                reject_counts[reason] = reject_counts.get(reason, 0) + 1
                continue
            label = str(event.get("label") or event.get("title") or "공시").strip()
            title = str(event.get("title") or label).strip()
            explanation = _event_explanation(market, label, title)
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
                explanation=explanation,
                priority=_priority(market, label, title, event_date, now),
                topic=_topic(label, title),
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
    used = used_keys or set()
    pool = [row for row in candidates if row.source_key not in used]
    pool.sort(key=lambda row: (row.priority, row.event_date, row.ticker), reverse=True)
    # Cadence/count are random, but public value should not be. Randomize only
    # inside the recent, high-load-bearing candidate pool.
    pool = pool[: min(len(pool), max(50, count * 25))]
    rng.shuffle(pool)
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
    note = (
        "확인한 사실\n"
        f"• {row.event_date.isoformat()} {row.name}의 ‘{row.title}’ 공시가 제출됐어요.\n\n"
        "가능한 해석\n"
        f"• {row.explanation}\n\n"
        "반대 근거\n"
        "• 공시 제출 사실만 확인한 기록이에요. 실제 규모·후속 실행·시장 반응에 따라 의미가 달라질 수 있어요.\n\n"
        "다음 확인\n"
        f"• {_next_check(row.label, row.title)}\n\n"
        f"자료 기준 {row.event_date.isoformat()} · 게시 {stamp} · v1\n"
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
        "content_version": 1,
        "observation_meta": {
            "generator": GENERATOR_VERSION,
            "generated_by_ai": False,
            "source_name": row.source_name,
            "source_label": row.label,
            "source_published_date": row.event_date.isoformat(),
            "source_artifact_generated_at": row.artifact_generated_at,
            "selection_priority": row.priority,
            "source_topic": row.topic,
            "copy_sections": ["fact", "interpretation", "counterevidence", "next_check"],
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
    desired = rng.randint(1, 3)
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
