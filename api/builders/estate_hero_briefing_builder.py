"""
estate_hero_briefing_builder.py — ESTATE HeroBriefing 통합 빌더 (P2 Step 4)

3단계 폴백 사다리 (사용자 결정 2 — Step 1.2 실증 반영):
    1순위: 24h 정책 → policy trigger
    2순위: 72h 정책 → policy trigger
    3순위: LANDEX max delta → landex_max_delta trigger (룰 기반 narrative)

3단계 분기 (T21 — JSON 갱신 정책):
    [정상]      build() → dict 반환 → main() 이 JSON 새로 씀
    [부분 실패] narrative 호출만 실패 → dict (headline=null, fallback_used=true) → JSON 새로 씀
    [전체 실패] collector·LANDEX 둘 다 실패 → None → JSON 안 씀, 이전 파일 유지

DI (Dependency Injection) — T22 mock 단위 테스트 보장:
    build(_collect=, _classify=, _generate=, _fetch_landex=, _success_rate_7d=)
    각 의존성 인자 주입 가능. None 이면 default (실 모듈) 호출.

거짓말 트랩:
    T1·T9  fabricate·silent X — 모든 실패 명시 로그 + None or fallback 명시
    T20    meta 통계 가짜 X — policy_24h, success_rate_7d 모두 실측
    T21    JSON 갱신 정책 — 3단계 분기 명시 박힘 (단순 try-except 전체 감싸기 X)
    T22    단위 테스트 mock 기반 (실 호출은 V4 cron 통합 테스트)

명령서 결정 3 — LANDEX 매핑 규칙:
    type:               "landex_max_delta"
    category:           Δ 부호 — 상승=catalyst, 하락=anomaly
    stage:              |Δ| 사다리 (<1%→0, 1~2%→1, 2~3%→2, 3~5%→3, >5%→4)
    affected_regions:   |Δ| TOP 3 자치구
    title:              f"{TOP1} LANDEX {sign}{delta}% (WoW), {TOP2}·{TOP3} 동반 {direction}"
    source_url:         f"{LANDEX_DASHBOARD_BASE_URL}/scoredetail?gu={TOP1}"
    source_name:        "VERITY ESTATE LANDEX"
    published_at:       LANDEX 데이터 generated_at (R-ONE 갱신 시각)
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from api.analyzers.policy_classifier import classify
from api.analyzers.policy_keywords import rough_relevance_filter
from api.collectors.policy_collector import collect_policies as fetch_policies
from api.policy_narrative import generate_policy_briefing

logger = logging.getLogger(__name__)

# 출력 JSON 위치 (publish-data action 의 staging 목록에 추가 필요 — Step 7)
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUTPUT_PATH = os.path.join(_REPO_ROOT, "data", "estate_hero_briefing.json")

# T18 anthropic_calls 누적 로그 — narrative_call_success_rate_7d 산출 근거
ANTHROPIC_LOG_PATH = os.path.join(_REPO_ROOT, "logs", "anthropic_calls.jsonl")

LANDEX_DASHBOARD_BASE_URL = os.getenv("LANDEX_DASHBOARD_BASE_URL", "")

# narrative 모델 식별자 — JSON 의 ai.model 슬롯
NARRATIVE_AI_MODEL = "claude-sonnet-4-20250514"
LANDEX_RULE_BASED_MODEL = "rule-based"

SCHEMA_VERSION = "1.0"


# ─────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────

def build(
    now: Optional[datetime] = None,
    _collect: Optional[Callable] = None,
    _classify: Optional[Callable] = None,
    _generate: Optional[Callable] = None,
    _fetch_landex: Optional[Callable] = None,
    _success_rate_7d: Optional[Callable] = None,
) -> Optional[Dict[str, Any]]:
    """
    HeroBriefing JSON 본체 dict 를 반환 (write 는 main 에서).

    Returns:
        dict — 정상 또는 부분 실패 (narrative 만 실패. fallback_used=true 명시).
        None — 전체 실패 (정책 0건 + LANDEX 실패). 호출자는 JSON 갱신하지 말 것.
    """
    now = now or datetime.now(timezone.utc)

    collect = _collect or fetch_policies
    classify_fn = _classify or classify
    generate = _generate or generate_policy_briefing
    fetch_landex = _fetch_landex or _default_fetch_landex_max_delta
    success_rate_fn = _success_rate_7d or _compute_narrative_success_rate_7d

    # ① 24h 별도 호출 — meta 통계용 (T20 — 실측)
    policy_24h_count = _count_policies_24h(collect, now)

    # ② 72h 수집 + prefilter + classify
    classified_72h = _collect_and_classify(collect, classify_fn, now)

    # ③ 트리거 결정 (3단계 사다리)
    trigger = _select_trigger(classified_72h, fetch_landex, now)
    if trigger is None:
        # T21 — 전체 실패. JSON 안 씀.
        logger.error(
            "builder: all triggers failed (24h/72h policy=0, landex=failed) — JSON not written"
        )
        return None

    # ④ narrative 생성 (정책 → AI / LANDEX → 룰 기반)
    narrative_block = _build_narrative_block(trigger, generate, now)

    # ⑤ meta — 모두 실측 (T20)
    success_rate_7d = success_rate_fn(now)
    freshness_minutes = _compute_freshness_minutes(trigger, now)

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now.isoformat(),
        "policy": _trigger_to_policy_section(trigger),
        "narrative": narrative_block,
        "operator_meta": {
            "policy_24h": policy_24h_count,
            "ai_success_7d": success_rate_7d,
            "freshness_minutes": freshness_minutes,
            "data_source": trigger["data_source"],
            "wire_status": "P2",
        },
    }


def main() -> int:
    """cron entry point. 빌드 → JSON write or skip. exit code 반환."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    briefing = build()
    if briefing is None:
        logger.error("main: build returned None — keeping existing JSON file (T21)")
        return 1
    _write_json_atomic(OUTPUT_PATH, briefing)
    logger.info("main: wrote %s", OUTPUT_PATH)
    return 0


# ─────────────────────────────────────────────────
# Trigger selection (3단계 사다리)
# ─────────────────────────────────────────────────

def _collect_and_classify(
    collect: Callable, classify_fn: Callable, now: datetime,
) -> List[Dict[str, Any]]:
    """72h 수집 → prefilter → classify. 단일 item 실패는 skip + 로그 (T9)."""
    try:
        raw_72h = collect(lookback_hours=72, now=now)
    except Exception as e:
        logger.error("builder: collect(72h) raised: %s", e)
        return []

    relevant = [p for p in raw_72h if rough_relevance_filter(p)]

    classified: List[Dict[str, Any]] = []
    for p in relevant:
        try:
            cls = classify_fn(p)
        except Exception as e:
            logger.error("builder: classify failed id=%s: %s", p.get("id"), e)
            continue
        classified.append({**p, **cls})  # policy fields + classification fields
    return classified


def _select_trigger(
    classified_72h: List[Dict[str, Any]],
    fetch_landex: Callable,
    now: datetime,
) -> Optional[Dict[str, Any]]:
    """
    3단계 폴백 사다리. 명령서 결정 2 그대로.

    Returns trigger dict 또는 None (전체 실패).
        trigger = {
            "type": "policy" | "landex_max_delta",
            "data_source": "policy_24h" | "policy_72h" | "landex",
            ...trigger 본문 (정책 dict 또는 LANDEX 산출물)
        }
    """
    # 1순위: 24h 정책
    cand_24h = [
        c for c in classified_72h
        if _is_within_hours(c.get("published_at"), now, 24)
    ]
    if cand_24h:
        top = _sort_by_stage_then_recency(cand_24h)[0]
        return {"type": "policy", "data_source": "policy_24h", "policy": top}

    # 2순위: 72h 정책
    if classified_72h:
        top = _sort_by_stage_then_recency(classified_72h)[0]
        return {"type": "policy", "data_source": "policy_72h", "policy": top}

    # 3순위: LANDEX 폴백
    try:
        landex_payload = fetch_landex(now)
    except Exception as e:
        logger.error("builder: landex fetch raised: %s", e)
        return None

    if landex_payload is None:
        return None
    return {"type": "landex_max_delta", "data_source": "landex", "landex": landex_payload}


def _sort_by_stage_then_recency(classified: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """stage DESC, published_at DESC (큰 stage 먼저, 동률이면 최신 먼저)."""
    return sorted(
        classified,
        key=lambda c: (c.get("stage") or 0, c.get("published_at") or ""),
        reverse=True,
    )


def _is_within_hours(published_at_iso: Optional[str], now: datetime, hours: int) -> bool:
    if not published_at_iso:
        return False
    try:
        pub = datetime.fromisoformat(published_at_iso.replace("Z", "+00:00"))
    except ValueError:
        return False
    if pub.tzinfo is None:
        pub = pub.replace(tzinfo=timezone.utc)
    return (now - pub) <= timedelta(hours=hours)


# ─────────────────────────────────────────────────
# Narrative — 정책은 AI, LANDEX 는 룰 기반
# ─────────────────────────────────────────────────

def _build_narrative_block(
    trigger: Dict[str, Any], generate: Callable, now: datetime,
) -> Dict[str, Any]:
    if trigger["type"] == "policy":
        return _build_policy_narrative(trigger["policy"], generate, now)
    return _build_landex_narrative(trigger["landex"], now)


def _build_policy_narrative(
    policy: Dict[str, Any], generate: Callable, now: datetime,
) -> Dict[str, Any]:
    """AI 호출. 실패 시 fallback_used=true + headline=null (T2 — mock 텍스트 X)."""
    result = generate(policy)
    if result is None:
        return {
            "headline": None,
            "body": "",
            "ai": {
                "model": NARRATIVE_AI_MODEL,
                "confidence": None,
                "tokens": 0,
                "fallback_used": True,
                "generated_at": now.isoformat(),
            },
            "fallback_reason": "anthropic_call_failed",
        }
    return {
        "headline": result["headline"],
        "body": "",
        "ai": {
            "model": NARRATIVE_AI_MODEL,
            "confidence": result.get("confidence"),
            "tokens": result.get("tokens_used", 0),
            "fallback_used": False,
            "generated_at": now.isoformat(),
        },
    }


def _build_landex_narrative(landex: Dict[str, Any], now: datetime) -> Dict[str, Any]:
    """룰 기반 — title 자체가 시그널 톤 (사용자 결정 3). AI 호출 X."""
    return {
        "headline": landex["title"],
        "body": "",
        "ai": {
            "model": LANDEX_RULE_BASED_MODEL,
            "confidence": 1.0,  # 룰 결정적 — 산식 도출 (T4)
            "tokens": 0,
            "fallback_used": False,
            "generated_at": now.isoformat(),
        },
    }


# ─────────────────────────────────────────────────
# Trigger → policy section (Mock JSON 형식 일치)
# ─────────────────────────────────────────────────

def _trigger_to_policy_section(trigger: Dict[str, Any]) -> Dict[str, Any]:
    if trigger["type"] == "policy":
        p = trigger["policy"]
        return {
            "id": p.get("id"),
            "title": p.get("title"),
            "source": p.get("source_name"),
            "source_url": p.get("source_url"),
            "published_at": p.get("published_at"),
            "category": p.get("category"),
            "summary": p.get("raw_text", "")[:500],
            "key_metrics": [],  # 정책에서는 key_metrics 별도 추출 안 함 (P3+ 영역)
            "affected_regions": p.get("affected_regions") or [],
        }
    # landex_max_delta
    lx = trigger["landex"]
    top1 = lx["top3"][0]
    return {
        "id": lx["id"],
        "title": lx["title"],
        "source": "VERITY ESTATE LANDEX",
        "source_url": f"{LANDEX_DASHBOARD_BASE_URL}/scoredetail?gu={top1['gu']}",
        "published_at": lx["published_at"],
        "category": lx["category"],
        "summary": "",
        "key_metrics": [
            {
                "label": x["gu"], "value": round(x["delta_pct"], 2),
                "unit": "%", "context": lx["time_unit"],
            }
            for x in lx["top3"]
        ],
        "affected_regions": [x["gu"] for x in lx["top3"]],
    }


# ─────────────────────────────────────────────────
# LANDEX max delta — 명령서 결정 3 매핑
# ─────────────────────────────────────────────────

def build_landex_fallback(
    deltas: List[Dict[str, Any]],
    latest_month: str,
    prev_month: str,
    time_unit: str,
    generated_at: str,
) -> Optional[Dict[str, Any]]:
    """
    LANDEX 25구 delta → max delta trigger payload (schema-agnostic).

    Args:
        deltas: [{gu, delta_pct, current, previous}, ...] — 사전 계산된 25구 delta_pct (%)
        latest_month:  schema 의 가장 최근 row 의 month 값 (YYYY-MM 또는 YYYY-MM-DD)
        prev_month:    직전 row 의 month 값
        time_unit:     자동 추론 결과 ("MoM" / "WoW" / "QoQ" / "vs prev")
        generated_at:  trigger 의 published_at 으로 쓸 ISO 8601 (보통 fetch 시각)

    Returns:
        {id, title, category, stage, time_unit, latest_month, prev_month, top3,
         published_at} 또는 None (입력 부족).

    schema-agnostic: 시간 단위는 _infer_time_unit 으로 row 간격에서 결정.
    현재 schema (monthly) → MoM. 미래 weekly history 추가 시 자동 WoW.
    """
    if not deltas:
        logger.error("landex_fallback: empty deltas")
        return None
    if len(deltas) < 3:
        logger.error("landex_fallback: insufficient deltas (need 3, got %d)", len(deltas))
        return None

    sorted_by_abs = sorted(deltas, key=lambda d: abs(d["delta_pct"]), reverse=True)
    top3 = sorted_by_abs[:3]
    top1, top2, top3_row = top3[0], top3[1], top3[2]

    delta1 = top1["delta_pct"]
    category = "catalyst" if delta1 >= 0 else "anomaly"
    direction = "상승" if delta1 >= 0 else "하락"
    sign = "+" if delta1 >= 0 else ""
    stage = _landex_stage(abs(delta1))

    title = (
        f"{top1['gu']} LANDEX {sign}{round(delta1, 1)}% ({time_unit}), "
        f"{top2['gu']}·{top3_row['gu']} 동반 {direction}"
    )

    return {
        "id": f"landex-fallback-{generated_at[:10]}",
        "title": title,
        "category": category,
        "stage": stage,
        "time_unit": time_unit,
        "latest_month": latest_month,
        "prev_month": prev_month,
        "top3": top3,  # 각 항목: {gu, delta_pct, current, previous}
        "published_at": generated_at,
    }


def _infer_time_unit(latest: str, prev: str) -> str:
    """
    schema 의 month 값 두 개 → 시간 단위 자동 추론 (schema-agnostic 패턴).

    YYYY-MM 형식 (현재 schema, monthly snapshot) → MoM/QoQ/...
    YYYY-MM-DD 형식 (미래 weekly history)        → WoW/MoM/QoQ/...
    """
    try:
        if len(latest) == 7 and len(prev) == 7:
            l_dt = datetime.strptime(latest, "%Y-%m")
            p_dt = datetime.strptime(prev, "%Y-%m")
            months_diff = (l_dt.year - p_dt.year) * 12 + (l_dt.month - p_dt.month)
            if months_diff == 1:
                return "MoM"
            if months_diff == 3:
                return "QoQ"
            return f"{months_diff}M"
        if len(latest) == 10 and len(prev) == 10:
            l_dt = datetime.strptime(latest, "%Y-%m-%d")
            p_dt = datetime.strptime(prev, "%Y-%m-%d")
            days_diff = (l_dt - p_dt).days
            if 6 <= days_diff <= 8:
                return "WoW"
            if 28 <= days_diff <= 31:
                return "MoM"
            if 88 <= days_diff <= 92:
                return "QoQ"
            return f"{days_diff}D"
    except (ValueError, TypeError):
        pass
    return "vs prev"


def _landex_stage(abs_delta: float) -> int:
    """명령서 결정 3 사다리: <1%→0, 1~2%→1, 2~3%→2, 3~5%→3, >5%→4."""
    if abs_delta < 1.0:
        return 0
    if abs_delta < 2.0:
        return 1
    if abs_delta < 3.0:
        return 2
    if abs_delta < 5.0:
        return 3
    return 4


def _default_fetch_landex_max_delta(now: datetime) -> Optional[Dict[str, Any]]:
    """
    LANDEX Supabase fetch — 실 호출은 V4 cron 통합 테스트에서 검증 (T22).
    단위 테스트는 _fetch_landex DI 로 mock.

    Returns:
        landex payload 또는 None (Supabase 5xx, 또는 25구 row 부족).
    """
    url = (os.getenv("SUPABASE_URL") or "").rstrip("/")
    # ESTATE 표준 패턴 (estate_alerts 등) — 서버사이드 cron 은 service_role 사용.
    # service_role 은 RLS bypass 권한이라 빌더 모듈 내부에서만 사용. 외부 leak 절대 금지.
    service_role = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or ""
    if not url or not service_role:
        logger.error("landex_fetch: SUPABASE_URL/SERVICE_ROLE_KEY missing")
        return None

    import requests
    headers = {"apikey": service_role, "Authorization": f"Bearer {service_role}"}
    base_url = f"{url}/rest/v1/estate_landex_snapshots"
    base_params = {
        "select": "gu,landex,month",
        "preset": "eq.balanced",  # _methodology.py 의 default preset
        "order": "month.desc,gu.asc",
        "limit": "25",
    }

    # ① 최신 시점 25구
    try:
        r_latest = requests.get(base_url, headers=headers, params=base_params, timeout=10)
    except requests.RequestException as e:
        logger.error("landex_fetch: HTTP error (latest): %s", e)
        return None
    if r_latest.status_code != 200:
        logger.error("landex_fetch: non-200 %d (latest)", r_latest.status_code)
        return None
    rows_latest = r_latest.json() or []
    if not rows_latest:
        logger.error("landex_fetch: 0 latest rows")
        return None

    latest_month = rows_latest[0]["month"]

    # ② 직전 시점 25구
    prev_params = {**base_params, "month": f"lt.{latest_month}"}
    try:
        r_prev = requests.get(base_url, headers=headers, params=prev_params, timeout=10)
    except requests.RequestException as e:
        logger.error("landex_fetch: HTTP error (prev): %s", e)
        return None
    if r_prev.status_code != 200:
        logger.error("landex_fetch: non-200 %d (prev)", r_prev.status_code)
        return None
    rows_prev = r_prev.json() or []
    if not rows_prev:
        logger.error(
            "landex_fetch: 0 prev rows (snapshot history insufficient — need >=2 months)",
        )
        return None

    prev_month = rows_prev[0]["month"]
    prev_map = {r["gu"]: r["landex"] for r in rows_prev}

    # ③ gu 매칭 → delta_pct 계산
    deltas: List[Dict[str, Any]] = []
    for r in rows_latest:
        gu = r["gu"]
        cur = r.get("landex")
        prev = prev_map.get(gu)
        if cur is None or prev is None or prev == 0:
            continue
        delta_pct = ((cur - prev) / prev) * 100
        deltas.append({
            "gu": gu,
            "delta_pct": round(delta_pct, 2),
            "current": cur,
            "previous": prev,
        })

    if len(deltas) < 3:
        logger.error("landex_fetch: insufficient gu matches (need 3, got %d)", len(deltas))
        return None

    time_unit = _infer_time_unit(latest_month, prev_month)
    return build_landex_fallback(
        deltas=deltas,
        latest_month=latest_month,
        prev_month=prev_month,
        time_unit=time_unit,
        generated_at=now.isoformat(),
    )


# ─────────────────────────────────────────────────
# Meta 산출 — T20 (실측 only)
# ─────────────────────────────────────────────────

def _count_policies_24h(collect: Callable, now: datetime) -> int:
    """24h 별도 호출 — '정책 한산기' 시그널. 실패 시 0."""
    try:
        rows = collect(lookback_hours=24, now=now)
    except Exception as e:
        logger.error("builder: 24h collect raised: %s — count=0", e)
        return 0
    return len([p for p in rows if rough_relevance_filter(p)])


def _compute_narrative_success_rate_7d(now: datetime) -> Optional[float]:
    """
    T18 anthropic_calls.jsonl 7일 윈도우 — narrative 호출 성공률.

    성공 = generate_policy_briefing 함수 진입 후 로그 기록 (즉 LLM 응답 받음).
    실패 = LLM 호출 자체 실패 (5xx/timeout) — 로그 안 찍힘.
    분모 = build() 실행 횟수 ≈ cron 실행 횟수. 정확 측정은 별도 카운터 필요.

    P2 단순 산식: 7일 내 generate_policy_briefing 함수 로그 건수 ÷ cron 호출 추정 건수.
    cron 추정 = 평일 1회/일 = 7일에 5회. 단순화: 로그건수/5 (cap 1.0).
    실 운영시 P3 에서 build_attempts 카운터 추가 후 정확화.

    Returns:
        float 0.0~1.0 또는 None (로그 파일 없음).
    """
    if not os.path.exists(ANTHROPIC_LOG_PATH):
        return None

    cutoff = now - timedelta(days=7)
    success_count = 0
    try:
        with open(ANTHROPIC_LOG_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("function_name") != "generate_policy_briefing":
                    continue
                ts_str = rec.get("timestamp")
                if not ts_str:
                    continue
                try:
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                except ValueError:
                    continue
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if ts >= cutoff:
                    success_count += 1
    except OSError as e:
        logger.error("builder: anthropic log read failed: %s", e)
        return None

    expected_attempts = 5  # 평일 1회/일 (결정 1) × 7일 ≈ 5
    return round(min(1.0, success_count / expected_attempts), 3)


def _compute_freshness_minutes(trigger: Dict[str, Any], now: datetime) -> Optional[int]:
    """trigger 의 published_at 기준 freshness (분)."""
    if trigger["type"] == "policy":
        pub_iso = trigger["policy"].get("published_at")
    else:
        pub_iso = trigger["landex"].get("published_at")
    if not pub_iso:
        return None
    try:
        pub = datetime.fromisoformat(pub_iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    if pub.tzinfo is None:
        pub = pub.replace(tzinfo=timezone.utc)
    delta_sec = (now - pub).total_seconds()
    return max(0, int(delta_sec // 60))


# ─────────────────────────────────────────────────
# JSON write — atomic
# ─────────────────────────────────────────────────

def _write_json_atomic(path: str, data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


if __name__ == "__main__":
    raise SystemExit(main())
