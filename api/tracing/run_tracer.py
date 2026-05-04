"""
VERITY Run Tracer — 실행 단위 완전 추적 아카이브

수집·분석·판단·학습 전 과정을 run_id별로 기록.
  data/runs/{YYYY-MM-DD}T{HHMMSS}_{mode}.json.gz

설계 원칙:
  1. 메모리 수집 → 종료 시 1회 gzip 기록 (I/O 최소)
  2. 모든 public 메서드는 try/except 래핑 (트레이서 장애가 본체 방해 금지)
  3. 싱글톤 — 어디서든 get_tracer()로 접근
"""
from __future__ import annotations

import gzip
import json
import math
import os
import time
import glob as _glob
from contextlib import contextmanager
from datetime import timedelta
from typing import Any, Dict, List, Optional

from api.config import DATA_DIR, now_kst

TRACE_DIR = os.path.join(DATA_DIR, "runs")

_TRACE_ENABLED = os.environ.get("TRACE_ENABLED", "1").strip().lower() in (
    "1", "true", "yes", "on",
)
_TRACE_AI = os.environ.get("TRACE_AI_CALLS", "1").strip().lower() in (
    "1", "true", "yes", "on",
)
_TRACE_FEATURES = os.environ.get("TRACE_FEATURES", "1").strip().lower() in (
    "1", "true", "yes", "on",
)
_RETENTION_DAYS = int(os.environ.get("TRACE_RETENTION_DAYS", "90"))
_COMPRESS = os.environ.get("TRACE_COMPRESS", "1").strip().lower() in (
    "1", "true", "yes", "on",
)
_MAX_TEXT_LEN = int(os.environ.get("TRACE_MAX_TEXT_LEN", "3000"))


def _sanitize(obj: Any, depth: int = 0) -> Any:
    if depth > 20:
        return "<depth_limit>"
    if isinstance(obj, dict):
        return {k: _sanitize(v, depth + 1) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        items = [_sanitize(v, depth + 1) for v in obj]
        return items
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, str) and len(obj) > _MAX_TEXT_LEN:
        return obj[:_MAX_TEXT_LEN] + f"…(+{len(obj) - _MAX_TEXT_LEN})"
    return obj


class RunTracer:
    """단일 실행 사이클의 모든 데이터를 수집하는 인메모리 트레이서."""

    def __init__(self):
        self._active = False
        self._data: Dict[str, Any] = {}
        self._steps: List[Dict[str, Any]] = []
        self._ai_calls: List[Dict[str, Any]] = []
        self._predictions: Dict[str, Dict[str, Any]] = {}
        self._filters: List[Dict[str, Any]] = []
        self._errors: List[Dict[str, Any]] = []
        self._collectors: Dict[str, Any] = {}
        self._run_id: str = ""
        self._t0: float = 0

    @property
    def active(self) -> bool:
        return self._active and _TRACE_ENABLED

    def start(self, mode: str, run_id: Optional[str] = None):
        if not _TRACE_ENABLED:
            return
        try:
            now = now_kst()
            self._run_id = run_id or now.strftime("%Y-%m-%dT%H%M%S") + f"_{mode}"
            self._t0 = time.monotonic()
            self._active = True
            self._data = {
                "run_id": self._run_id,
                "mode": mode,
                "started_at": now.isoformat(),
                "verity_version": "",
            }
            self._steps = []
            self._ai_calls = []
            self._predictions = {}
            self._filters = []
            self._errors = []
            self._collectors = {}
        except Exception:
            self._active = False

    @contextmanager
    def step(self, name: str):
        """단계별 실행시간 자동 계측 컨텍스트 매니저."""
        if not self.active:
            yield
            return
        t0 = time.monotonic()
        entry: Dict[str, Any] = {"name": name, "started": time.time()}
        try:
            yield
        except Exception as e:
            entry["error"] = str(e)[:200]
            raise
        finally:
            entry["elapsed_ms"] = round((time.monotonic() - t0) * 1000)
            self._steps.append(entry)

    def log(self, key: str, data: Any):
        if not self.active:
            return
        try:
            self._data[key] = data
        except Exception:
            pass

    def log_collector(self, name: str, data: Any):
        """수집기 원천 데이터 기록."""
        if not self.active:
            return
        try:
            self._collectors[name] = _sanitize(data)
        except Exception:
            pass

    def log_ai(
        self,
        provider: str,
        model: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        prompt_preview: str = "",
        response_preview: str = "",
        ticker: str = "",
        call_type: str = "",
        cached_tokens: int = 0,
    ):
        """AI API 호출 1건 기록.

        cached_tokens: Gemini explicit caching 적중분 (usage_metadata.cached_content_token_count).
        prompt_tokens 의 일부 — 캐시 적중률 계측용 (1주 누적 hit ratio).
        """
        if not self.active or not _TRACE_AI:
            return
        try:
            self._ai_calls.append({
                "provider": provider,
                "model": model,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "cached_tokens": cached_tokens,
                "prompt_preview": prompt_preview[:_MAX_TEXT_LEN] if prompt_preview else "",
                "response_preview": response_preview[:_MAX_TEXT_LEN] if response_preview else "",
                "ticker": ticker,
                "call_type": call_type,
                "ts": time.time(),
            })
        except Exception:
            pass

    def log_prediction(self, ticker: str, features: Dict[str, Any], result: Dict[str, Any]):
        """ML 예측 피처 벡터 + 결과 기록."""
        if not self.active or not _TRACE_FEATURES:
            return
        try:
            self._predictions[ticker] = {
                "features": _sanitize(features),
                "result": _sanitize(result),
            }
        except Exception:
            pass

    def log_filter(self, stage: str, before: int, after: int, removed_tickers: Optional[List[str]] = None):
        """필터링 단계별 통과/탈락 기록."""
        if not self.active:
            return
        try:
            self._filters.append({
                "stage": stage,
                "before": before,
                "after": after,
                "removed": len(removed_tickers) if removed_tickers else before - after,
                "removed_tickers": (removed_tickers or [])[:50],
            })
        except Exception:
            pass

    def log_error(self, step: str, error: Any):
        if not self.active:
            return
        try:
            self._errors.append({"step": step, "error": str(error)[:500], "ts": time.time()})
        except Exception:
            pass

    def log_brain_detail(self, ticker: str, detail: Dict[str, Any]):
        """Brain 채점 상세 내역 기록."""
        if not self.active:
            return
        try:
            brain_details = self._data.setdefault("brain_details", {})
            brain_details[ticker] = _sanitize(detail)
        except Exception:
            pass

    def log_vams_decision(self, decisions: List[Dict[str, Any]]):
        if not self.active:
            return
        try:
            self._data["vams_decisions"] = _sanitize(decisions)
        except Exception:
            pass

    def end(self) -> Optional[str]:
        """실행 종료 — 전체 데이터를 아카이브 파일로 기록. 반환: 파일 경로."""
        if not self.active:
            return None
        try:
            elapsed = time.monotonic() - self._t0
            self._data["ended_at"] = now_kst().isoformat()
            self._data["total_elapsed_sec"] = round(elapsed, 1)
            self._data["steps"] = self._steps
            self._data["ai_calls"] = self._ai_calls
            self._data["ai_call_count"] = len(self._ai_calls)
            self._data["ai_total_tokens"] = sum(
                c.get("prompt_tokens", 0) + c.get("completion_tokens", 0)
                for c in self._ai_calls
            )
            self._data["predictions"] = self._predictions
            self._data["filters"] = self._filters
            self._data["errors"] = self._errors
            self._data["error_count"] = len(self._errors)
            self._data["collectors"] = self._collectors

            path = self._write()
            self._cleanup()
            self._active = False
            return path
        except Exception as e:
            print(f"[tracer] 아카이브 저장 실패: {e}")
            self._active = False
            return None

    def _write(self) -> str:
        os.makedirs(TRACE_DIR, exist_ok=True)
        payload = json.dumps(
            _sanitize(self._data), ensure_ascii=False, indent=None, default=str,
        ).encode("utf-8")

        if _COMPRESS:
            path = os.path.join(TRACE_DIR, f"{self._run_id}.json.gz")
            with gzip.open(path, "wb", compresslevel=6) as f:
                f.write(payload)
        else:
            path = os.path.join(TRACE_DIR, f"{self._run_id}.json")
            with open(path, "wb") as f:
                f.write(payload)

        size_kb = round(os.path.getsize(path) / 1024, 1)
        print(f"[tracer] 아카이브 저장: {path} ({size_kb}KB)")
        return path

    def _cleanup(self):
        """보관 기한 초과 파일 삭제."""
        try:
            cutoff = (now_kst() - timedelta(days=_RETENTION_DAYS)).strftime("%Y-%m-%d")
            for f in _glob.glob(os.path.join(TRACE_DIR, "*.json*")):
                basename = os.path.basename(f)
                date_part = basename[:10]
                if date_part < cutoff:
                    os.remove(f)
        except Exception:
            pass


_tracer: Optional[RunTracer] = None


def get_tracer() -> RunTracer:
    """모듈 레벨 싱글톤 트레이서."""
    global _tracer
    if _tracer is None:
        _tracer = RunTracer()
    return _tracer
