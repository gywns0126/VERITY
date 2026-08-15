"""
jsonl_schemas — jsonl 적재 시점 schema 강제 (사전 차단).

Why: [[feedback_data_collection_verification_mandatory]] = try/finally + stderr + N run 누적
= **사후** detect 만 된다. 적재 시점 검사 = **사전** 차단.

🚨 2026-08-15 전면 재작성 — 초판(2026-05-17) 스키마는 **3개 전부 실제와 어긋나 있었다.**
그대로 배선했다면 정상 적재를 전량 차단했다.

```
telegram_volume   초판 요구 timestamp·event_type  →  실제 ts_kst·outcome        (필수 2개 모두 부재)
fred_health       초판 요구 timestamp             →  실제 ts_utc                (필수 1개 부재)
wide_scan_log     초판 경로 data/metadata/…       →  실제 data/wide_scan_log.jsonl (경로부터 오류)
```

교훈 = 스키마는 **실측 레코드로부터** 만든다. 설계 시점의 기대 형상으로 만들면 검사기가
데이터를 막는다. 아래 3종은 전부 실 파일을 전수 프로파일링해 산출했다(레코드 수 명시).

## 안전 설계 — 구조는 막고, 값은 알린다

```
구조 위반(필수 필드 부재 / 타입 불일치 / 음수)  → 차단.  적재 자체가 잘못됐다는 뜻이다
새 enum 값(status/outcome 에 못 보던 값)        → 통과 + 경고. 수집기 확장을 검사기가 막지 않는다
```
enum 을 hard check 로 두면 수집기가 새 상태를 하나 추가하는 순간 수집이 멈춘다.
관측 인프라가 관측 대상을 죽이면 안 된다.

## 사용

    from api.observability.jsonl_schemas import guard_append, TELEGRAM_VOLUME_SCHEMA
    ok, err = guard_append(rec, TELEGRAM_VOLUME_SCHEMA)
    if not ok:
        print(f"[jsonl_guard] 적재 차단 — {err}", file=sys.stderr)
        return
"""
from __future__ import annotations

import sys
from typing import Any, Dict, Optional, Sequence, Tuple

import pandera.pandas as pa


# ──────────────────────────────────────────────────────────────
# 1. data/telegram_volume.jsonl   (실측 2,847 레코드 · 2026-08-15)
#    ts_kst/bypass_quiet/fingerprint/msg_first_line/outcome = 100%
#    source 93.8% · status_code 0.03%(1건)
# ──────────────────────────────────────────────────────────────
TELEGRAM_VOLUME_SCHEMA = pa.DataFrameSchema({
    "ts_kst": pa.Column(str, nullable=False, description="ISO timestamp (KST)"),
    "outcome": pa.Column(str, nullable=False, description="발송 결과"),
    "bypass_quiet": pa.Column(bool, nullable=False, description="quiet hours 우회 여부"),
    "fingerprint": pa.Column(str, nullable=False, description="dedupe 해시"),
    "msg_first_line": pa.Column(str, nullable=True),
    "source": pa.Column(str, nullable=True, required=False),
    # 🚨 "Int64"(nullable) 필수. int 로 두면 coerce 가 결측(NaN)을 int64 로 못 바꿔
    #    **전량 차단**된다 — 실측 2,847건 중 status_code 보유가 1건뿐이라 2,846건이 막혔다.
    #    선택 필드에 numpy int/float 를 쓰지 말 것. (2026-08-15 배선 전 배치 검증에서 적발)
    "status_code": pa.Column("Int64", nullable=True, required=False),
}, strict=False, coerce=True)

# 실측 관측값. hard check 가 아니라 **경고 대상** — 새 값은 통과시킨다.
TELEGRAM_VOLUME_ENUMS = {
    "outcome": {"sent", "dedupe_skip", "quiet_skip", "no_token", "api_fail"},
}


# ──────────────────────────────────────────────────────────────
# 2. data/wide_scan_log.jsonl   (실측 453 레코드 · 2026-08-15)
#    🚨 경로 = data/ 다. data/metadata/ 아니다 (wide_scan.py:47)
#    ts/label/mode/step/input_n/target_n/passed_n/note = 100%
# ──────────────────────────────────────────────────────────────
WIDE_SCAN_LOG_SCHEMA = pa.DataFrameSchema({
    "ts": pa.Column(str, nullable=False),
    "label": pa.Column(str, nullable=False),
    "mode": pa.Column(str, nullable=False),
    "step": pa.Column(str, nullable=False, description="라벨 고정 — rename 금지 (wide_scan.py:620)"),
    "input_n": pa.Column(int, checks=pa.Check.ge(0), nullable=False),
    "target_n": pa.Column(int, checks=pa.Check.ge(0), nullable=False),
    "passed_n": pa.Column(int, checks=pa.Check.ge(0), nullable=False),
    "note": pa.Column(str, nullable=True),
    "cut_score": pa.Column(float, nullable=True, required=False),
    "mode_active": pa.Column(str, nullable=True, required=False),
}, strict=False, coerce=True)

WIDE_SCAN_LOG_ENUMS = {
    "mode": {"SHADOW", "PRODUCTION"},
    "label": {"v0_heuristic"},
}


# ──────────────────────────────────────────────────────────────
# 3. data/metadata/fred_health.jsonl   (실측 35,558 레코드 · 2026-08-15)
#    ts_utc/series_id/status/reason/points/elapsed_ms = 전부 100%
# ──────────────────────────────────────────────────────────────
FRED_HEALTH_SCHEMA = pa.DataFrameSchema({
    "ts_utc": pa.Column(str, nullable=False),
    "series_id": pa.Column(str, nullable=False, description="예: DGS10, UNRATE, VIXCLS"),
    "status": pa.Column(str, nullable=False),
    "reason": pa.Column(str, nullable=True, description="ok 일 때 빈 문자열"),
    "points": pa.Column(int, checks=pa.Check.ge(0), nullable=False),
    "elapsed_ms": pa.Column(int, checks=pa.Check.ge(0), nullable=False),
}, strict=False, coerce=True)

# 실측은 {ok, http_error, network_error} 뿐이나, `fred_macro._log_fred_health` 독시스트링이
# 선언하는 집합이 더 넓다. 코드 선언을 기준으로 둔다 — 드문 경로가 경고를 내지 않도록.
FRED_HEALTH_ENUMS = {
    "status": {"ok", "no_api_key", "http_error", "network_error", "parse_error", "empty"},
}


# ──────────────────────────────────────────────────────────────
# 적재 가드
# ──────────────────────────────────────────────────────────────

def check_enums(record: Dict[str, Any], enums: Dict[str, set]) -> list:
    """못 보던 enum 값을 **경고로만** 수집. 차단하지 않는다.

    수집기가 새 상태를 하나 추가했다는 이유로 수집이 멈추면 안 된다.
    다만 조용히 지나가지도 않는다 — 호출부가 stderr 로 알린다.
    """
    out = []
    for field, allowed in (enums or {}).items():
        v = record.get(field)
        if v is not None and v not in allowed:
            out.append(f"{field}={v!r} 은 기존 관측값 밖 ({sorted(allowed)})")
    return out


def guard_append(
    record: Dict[str, Any],
    schema: pa.DataFrameSchema,
    enums: Optional[Dict[str, set]] = None,
    label: str = "",
) -> Tuple[bool, str]:
    """적재 직전 검사. 구조 위반이면 (False, 사유) — 호출부가 적재를 거부한다.

    enum 이탈은 차단하지 않고 stderr 경고만 낸다.

    🚨 pandas/pandera 부재나 예기치 못한 내부 오류로는 **차단하지 않는다**.
       검사기 자체의 문제로 데이터 수집이 멈추는 것이 원 결함보다 나쁘다.
    """
    try:
        import pandas as pd
    except ImportError:
        return True, ""
    try:
        schema.validate(pd.DataFrame([record]), lazy=True)
    except pa.errors.SchemaErrors as e:
        return False, f"{label or 'jsonl'} schema 위반 — {e.failure_cases.to_dict('records')[:3]}"
    except pa.errors.SchemaError as e:
        return False, f"{label or 'jsonl'} schema 위반 — {e}"
    except Exception as e:  # noqa: BLE001 — 검사기 결함이 수집을 막지 않게
        print(f"[jsonl_guard] 검사기 오류로 통과 처리 ({label}): {e}", file=sys.stderr)
        return True, ""

    for w in check_enums(record, enums or {}):
        print(f"[jsonl_guard] 경고 ({label or 'jsonl'}) — {w}", file=sys.stderr)
    return True, ""


def validate_record(record: Dict[str, Any], schema: pa.DataFrameSchema) -> Dict[str, Any]:
    """구 API 보존 — 실패 시 SchemaError raise. 신규 호출은 guard_append 를 쓴다."""
    import pandas as pd
    return schema.validate(pd.DataFrame([record]), lazy=False).iloc[0].to_dict()


# 경로 → (schema, enums) 등록부. 신규 적재 hook 이 참조한다.
REGISTRY: Dict[str, Tuple[pa.DataFrameSchema, Dict[str, set]]] = {
    "data/telegram_volume.jsonl": (TELEGRAM_VOLUME_SCHEMA, TELEGRAM_VOLUME_ENUMS),
    "data/wide_scan_log.jsonl": (WIDE_SCAN_LOG_SCHEMA, WIDE_SCAN_LOG_ENUMS),
    "data/metadata/fred_health.jsonl": (FRED_HEALTH_SCHEMA, FRED_HEALTH_ENUMS),
}
