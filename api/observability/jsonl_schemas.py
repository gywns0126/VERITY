"""
jsonl_schemas — pandera DataFrame schema 정의 (적재 hook 사전 차단).

Why: 메모리 [[feedback_data_collection_verification_mandatory]] = try/finally + stderr +
N run 누적 = 사후 detect 만. pandera = 적재 시점 schema 강제 = **사전 차단**.

대상 (가장 결함 자주 발생한 3개 jsonl):
1. data/telegram_volume.jsonl — 텔레그램 발송 volume 추적 (메모리 [[project_telegram_quiet_hours_v0]])
2. data/metadata/wide_scan_log.jsonl — Wide Scan Phase 2-B coarse filter (메모리 [[project_phase_2b_wide_scan]])
3. data/metadata/fred_health.jsonl — FRED 매크로 health (메모리 [[project_fred_silent_skip_audit]])

사용: 적재 hook 에서 record dict → pandera DataFrame 변환 → schema.validate(df).
실패 시 SchemaError raise (적재 차단). 성공 시 정상 append.

wiring: 적재 hook 에 import + validate 호출 의무. 자동 wiring X (사용자 결정).
"""
from __future__ import annotations
import pandera.pandas as pa
from pandera.typing import Series
from typing import Optional


# ──────────────────────────────────────────────────────────────
# 1. telegram_volume.jsonl
# ──────────────────────────────────────────────────────────────
# 메모리 [[project_telegram_quiet_hours_v0]]: 23:00~07:00 KST suppress + dedupe 8h.
# critical bypass 8 사이트. 발송 시점/타입/대상 추적.
TELEGRAM_VOLUME_SCHEMA = pa.DataFrameSchema({
    "timestamp": pa.Column(str, nullable=False, description="ISO timestamp (KST)"),
    "event_type": pa.Column(
        str,
        checks=pa.Check.isin([
            "sent", "suppressed_quiet_hours", "suppressed_dedupe",
            "critical_bypass", "rate_limited", "error",
        ]),
        nullable=False,
    ),
    "category": pa.Column(str, nullable=True, required=False),
    "ticker": pa.Column(str, nullable=True, required=False),
    "level": pa.Column(
        str,
        checks=pa.Check.isin(["CRITICAL", "WARNING", "INFO", "DEBUG"]),
        nullable=True,
        required=False,
    ),
    "message_id": pa.Column(str, nullable=True, required=False),
    "suppressed_reason": pa.Column(str, nullable=True, required=False),
}, strict=False, coerce=True)


# ──────────────────────────────────────────────────────────────
# 2. wide_scan_log.jsonl
# ──────────────────────────────────────────────────────────────
# 메모리 [[project_phase_2b_wide_scan]]: 5000→1000 (22%) coarse filter Phase 2-B.
# PRODUCTION 게이트 8/10. 매 sweep run 의 입력/결과/소요시간 trail.
WIDE_SCAN_LOG_SCHEMA = pa.DataFrameSchema({
    "timestamp": pa.Column(str, nullable=False),
    "stage": pa.Column(
        str,
        checks=pa.Check.isin(["SHADOW", "PRODUCTION", "phase_2a", "phase_2b", "coarse", "fine"]),
        nullable=False,
    ),
    "input_count": pa.Column(int, checks=pa.Check.ge(0), nullable=False),
    "output_count": pa.Column(int, checks=pa.Check.ge(0), nullable=False),
    "elapsed_sec": pa.Column(float, checks=pa.Check.ge(0), nullable=True, required=False),
    "filter_ratio": pa.Column(float, checks=pa.Check.in_range(0.0, 1.0), nullable=True, required=False),
    "verdict": pa.Column(
        str,
        checks=pa.Check.isin(["pass", "fail", "warn", "skip"]),
        nullable=True,
        required=False,
    ),
    "error": pa.Column(str, nullable=True, required=False),
}, strict=False, coerce=True)


# ──────────────────────────────────────────────────────────────
# 3. fred_health.jsonl
# ──────────────────────────────────────────────────────────────
# 메모리 [[project_fred_silent_skip_audit]]: FRED _fetch_series 영구 silent skip fix.
# 각 series 의 fetch 성공/실패 + freshness 추적. silent skip 사전 차단.
FRED_HEALTH_SCHEMA = pa.DataFrameSchema({
    "timestamp": pa.Column(str, nullable=False),
    "series_id": pa.Column(str, nullable=False),  # 예: DGS10, UNRATE, VIXCLS
    "status": pa.Column(
        str,
        checks=pa.Check.isin(["ok", "stale", "error", "rate_limited", "skip"]),
        nullable=False,
    ),
    "last_value": pa.Column(float, nullable=True, required=False),
    "last_date": pa.Column(str, nullable=True, required=False),
    "freshness_days": pa.Column(int, checks=pa.Check.ge(0), nullable=True, required=False),
    "error_message": pa.Column(str, nullable=True, required=False),
    "fetch_duration_ms": pa.Column(int, checks=pa.Check.ge(0), nullable=True, required=False),
}, strict=False, coerce=True)


# ──────────────────────────────────────────────────────────────
# validate helper — 적재 hook 에서 호출
# ──────────────────────────────────────────────────────────────

def validate_record(record: dict, schema: pa.DataFrameSchema) -> dict:
    """단일 record dict → schema validate. 실패 시 SchemaError raise.

    적재 hook 패턴:
        try:
            validate_record(rec, TELEGRAM_VOLUME_SCHEMA)
        except pa.errors.SchemaError as e:
            logger.error(f"jsonl schema 차단: {e}")
            return  # 적재 거부

    Returns: validated record (coerce 적용된 형태)
    """
    import pandas as pd
    df = pd.DataFrame([record])
    validated = schema.validate(df, lazy=False)
    return validated.iloc[0].to_dict()
