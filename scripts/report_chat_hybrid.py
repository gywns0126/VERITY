#!/usr/bin/env python3
"""
VERITY Chat Hybrid — 메트릭 일일 요약 리포트.

Phase 3.10 구조화 JSON 로깅(`chat_hybrid.metrics`) 을 파일/stdin 으로 받아
운영 KPI 를 집계하고 텍스트 리포트로 출력. `--send-telegram` 플래그 시
Telegram 으로 전송 (기본은 안전하게 stdout 출력만).

사용 예:
  # Vercel 로그 파일에서
  vercel logs my-project --since 24h > /tmp/logs.txt
  python3 scripts/report_chat_hybrid.py /tmp/logs.txt

  # 파이프
  vercel logs my-project --since 24h | python3 scripts/report_chat_hybrid.py -

  # Telegram 전송 (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 필요)
  python3 scripts/report_chat_hybrid.py /tmp/logs.txt --send-telegram

  # 윈도 라벨 커스터마이즈 (리포트 헤더용)
  python3 scripts/report_chat_hybrid.py /tmp/logs.txt --label "2026-04-23 KST"

필드 의존성: chat_hybrid.metrics payload 의 다음 필드를 소비.
  t, outcome, intent_type, intent_source, intent_cache_hit,
  total_ms, stages.{intent, brain, external, synth},
  perplexity.{ok, cache_hit}, grounding.{ok, cache_hit},
  cost_est, error_msg
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from statistics import median
from typing import Any, Dict, Iterable, List, Optional


METRIC_PREFIX = "chat_hybrid.metrics"


def _extract_payload(line: str) -> Optional[Dict[str, Any]]:
    """한 줄에서 `chat_hybrid.metrics {...}` payload 를 parse. 실패 시 None."""
    if METRIC_PREFIX not in line:
        return None
    idx = line.find(METRIC_PREFIX)
    rest = line[idx + len(METRIC_PREFIX):].lstrip()
    if not rest.startswith("{"):
        return None
    # 가장 짧게 — JSONDecodeError 시 raw_decode 로 첫 object 만
    try:
        obj, _ = json.JSONDecoder().raw_decode(rest)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        return None


def iter_payloads(lines: Iterable[str]) -> Iterable[Dict[str, Any]]:
    for line in lines:
        p = _extract_payload(line)
        if p is not None:
            yield p


def _percentile(values: List[int], pct: float) -> int:
    """단순 선형 p95 계산. pct in [0, 1]."""
    if not values:
        return 0
    sv = sorted(values)
    k = max(0, min(len(sv) - 1, int(round(pct * (len(sv) - 1)))))
    return sv[k]


def _pct(n: int, d: int) -> float:
    return (n / d * 100.0) if d else 0.0


def _outcome_group(outcome: str) -> str:
    """세부 outcome 을 대분류로. success/reject/error/other."""
    if outcome == "success":
        return "success"
    if outcome.startswith("reject:"):
        return "reject"
    if outcome.startswith("error:") or outcome in ("deadline_exceeded", "synth_error"):
        return "error"
    return "other"


def aggregate(payloads: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """집계 — 순수 함수 (테스트 대상).

    반환값: 리포트 렌더링에 필요한 구조화 통계.
    """
    total = 0
    outcomes: Counter = Counter()
    outcome_groups: Counter = Counter()
    intent_types: Counter = Counter()
    intent_sources: Counter = Counter()

    intent_cache_hit = 0
    intent_cache_seen = 0
    perp_ok = 0
    perp_called = 0
    perp_cache_hit = 0
    grd_ok = 0
    grd_called = 0
    grd_cache_hit = 0

    total_ms_success: List[int] = []
    stage_ms: Dict[str, List[int]] = {"intent": [], "brain": [], "external": [], "synth": []}

    cost_sum = 0.0
    error_samples: List[str] = []

    for p in payloads:
        total += 1
        outcome = str(p.get("outcome", "unknown"))
        outcomes[outcome] += 1
        outcome_groups[_outcome_group(outcome)] += 1

        intent_type = p.get("intent_type")
        if intent_type:
            intent_types[str(intent_type)] += 1

        src = p.get("intent_source")
        if src:
            intent_sources[str(src)] += 1

        if "intent_cache_hit" in p:
            intent_cache_seen += 1
            if p.get("intent_cache_hit"):
                intent_cache_hit += 1

        perp = p.get("perplexity")
        if isinstance(perp, dict):
            perp_called += 1
            if perp.get("ok"):
                perp_ok += 1
            if perp.get("cache_hit"):
                perp_cache_hit += 1

        grd = p.get("grounding")
        if isinstance(grd, dict):
            grd_called += 1
            if grd.get("ok"):
                grd_ok += 1
            if grd.get("cache_hit"):
                grd_cache_hit += 1

        # 지연: success 에 한정 (reject/error 는 의미 없음)
        if outcome == "success":
            t_ms = p.get("total_ms")
            if isinstance(t_ms, (int, float)):
                total_ms_success.append(int(t_ms))
            stages = p.get("stages") or {}
            for k in stage_ms:
                v = stages.get(k)
                if isinstance(v, (int, float)):
                    stage_ms[k].append(int(v))

        # 비용
        try:
            cost_sum += float(p.get("cost_est") or 0)
        except (TypeError, ValueError):
            pass

        # 에러 샘플 (최대 5건)
        if outcome_groups["error"] and outcome.startswith(("error:", "deadline_exceeded", "synth_error")):
            if len(error_samples) < 5:
                msg = str(p.get("error_msg", ""))[:100]
                if msg:
                    error_samples.append(f"{outcome}: {msg}")

    def _stage_summary(vals: List[int]) -> Dict[str, int]:
        if not vals:
            return {"p50": 0, "p95": 0, "max": 0, "n": 0}
        return {
            "p50": int(median(vals)),
            "p95": _percentile(vals, 0.95),
            "max": max(vals),
            "n": len(vals),
        }

    return {
        "total": total,
        "outcomes": dict(outcomes),
        "outcome_groups": dict(outcome_groups),
        "intent_types": dict(intent_types),
        "intent_sources": dict(intent_sources),
        "intent_cache": {
            "hit": intent_cache_hit,
            "seen": intent_cache_seen,
            "hit_pct": round(_pct(intent_cache_hit, intent_cache_seen), 1),
        },
        "perplexity": {
            "called": perp_called,
            "ok": perp_ok,
            "cache_hit": perp_cache_hit,
            "ok_pct": round(_pct(perp_ok, perp_called), 1),
            "cache_hit_pct": round(_pct(perp_cache_hit, perp_called), 1),
        },
        "grounding": {
            "called": grd_called,
            "ok": grd_ok,
            "cache_hit": grd_cache_hit,
            "ok_pct": round(_pct(grd_ok, grd_called), 1),
            "cache_hit_pct": round(_pct(grd_cache_hit, grd_called), 1),
        },
        "latency_success": {
            "total_ms": _stage_summary(total_ms_success),
            "stages": {k: _stage_summary(v) for k, v in stage_ms.items()},
        },
        "cost_est_sum": round(cost_sum, 4),
        "cost_est_avg_success": round(
            cost_sum / max(outcome_groups.get("success", 0), 1), 4
        ),
        "error_samples": error_samples,
    }


def format_report(stats: Dict[str, Any], label: str = "") -> str:
    """플레인 텍스트 요약. Telegram HTML 로도 그대로 쓸 수 있도록 escape 는 최소."""
    lines: List[str] = []
    header = "📊 VERITY Chat Hybrid 일일 메트릭"
    if label:
        header += f" — {label}"
    lines.append(header)
    lines.append("─" * 40)

    total = stats["total"]
    lines.append(f"요청 수: {total}")
    if total == 0:
        lines.append("(해당 윈도 내 chat_hybrid.metrics 로그 없음)")
        return "\n".join(lines)

    g = stats["outcome_groups"]
    succ = g.get("success", 0)
    rej = g.get("reject", 0)
    err = g.get("error", 0)
    lines.append(
        f"결과: ✅ {succ} ({_pct(succ, total):.1f}%) · "
        f"⛔ reject {rej} ({_pct(rej, total):.1f}%) · "
        f"🚨 error {err} ({_pct(err, total):.1f}%)"
    )

    if stats["intent_types"]:
        it = ", ".join(
            f"{k}={v}" for k, v in sorted(
                stats["intent_types"].items(), key=lambda x: -x[1]
            )
        )
        lines.append(f"의도: {it}")

    if stats["intent_sources"]:
        src = ", ".join(
            f"{k}={v}" for k, v in sorted(
                stats["intent_sources"].items(), key=lambda x: -x[1]
            )
        )
        lines.append(f"분류원: {src}")

    ic = stats["intent_cache"]
    lines.append(f"의도 캐시: {ic['hit']}/{ic['seen']} ({ic['hit_pct']}%)")

    p = stats["perplexity"]
    if p["called"]:
        lines.append(
            f"Perplexity: 호출 {p['called']} · ok {p['ok']}({p['ok_pct']}%) · "
            f"cache {p['cache_hit']}({p['cache_hit_pct']}%)"
        )
    gd = stats["grounding"]
    if gd["called"]:
        lines.append(
            f"Grounding : 호출 {gd['called']} · ok {gd['ok']}({gd['ok_pct']}%) · "
            f"cache {gd['cache_hit']}({gd['cache_hit_pct']}%)"
        )

    lat = stats["latency_success"]["total_ms"]
    if lat["n"]:
        lines.append(
            f"총 지연(성공 {lat['n']}건): "
            f"p50 {lat['p50']}ms · p95 {lat['p95']}ms · max {lat['max']}ms"
        )
        stages = stats["latency_success"]["stages"]
        parts = []
        for k in ("intent", "brain", "external", "synth"):
            s = stages.get(k, {})
            if s.get("n"):
                parts.append(f"{k} p95 {s['p95']}ms")
        if parts:
            lines.append("단계 p95: " + " · ".join(parts))

    lines.append(
        f"비용(합): ${stats['cost_est_sum']:.4f} · "
        f"성공당 평균 ${stats['cost_est_avg_success']:.4f}"
    )

    if stats["error_samples"]:
        lines.append("")
        lines.append("최근 에러 샘플 (최대 5건):")
        for s in stats["error_samples"]:
            lines.append(f"  • {s}")

    return "\n".join(lines)


def _send_to_telegram(text: str) -> bool:
    """Telegram 전송 — api.notifications.telegram.send_message 재사용.

    repo root sys.path 에 있어야 import 됨. 실패시 False.
    """
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from api.notifications.telegram import send_message  # type: ignore
    except Exception as e:
        print(f"[telegram] import 실패: {e}", file=sys.stderr)
        return False
    # HTML 로 보내기 — 본문은 plain 이지만 <pre> 로 감싸 monospace 정렬 유지
    html = "<pre>" + (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    ) + "</pre>"
    return bool(send_message(html, dedupe=False))


def _read_input(path: str) -> Iterable[str]:
    if path == "-":
        return sys.stdin
    return open(path, "r", encoding="utf-8", errors="replace")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="chat_hybrid.metrics NDJSON 로그 요약 리포트"
    )
    ap.add_argument(
        "input",
        nargs="?",
        default="-",
        help="로그 파일 경로 또는 '-' (stdin, 기본값)",
    )
    ap.add_argument(
        "--label", default="",
        help="리포트 헤더 라벨 (예: '2026-04-23 KST')",
    )
    ap.add_argument(
        "--send-telegram", action="store_true",
        help="Telegram 으로 전송 (TELEGRAM_BOT_TOKEN/CHAT_ID 필요)",
    )
    ap.add_argument(
        "--json", action="store_true",
        help="집계 결과를 JSON 으로 stdout 출력 (텍스트 리포트 대신)",
    )
    args = ap.parse_args()

    try:
        src = _read_input(args.input)
    except OSError as e:
        print(f"ERROR: 입력 파일 읽기 실패: {e}", file=sys.stderr)
        return 2

    try:
        stats = aggregate(iter_payloads(src))
    finally:
        if args.input != "-":
            src.close()  # type: ignore

    if args.json:
        print(json.dumps(stats, ensure_ascii=False, indent=2))
        return 0

    report = format_report(stats, label=args.label)
    print(report)

    if args.send_telegram:
        ok = _send_to_telegram(report)
        if not ok:
            print("[telegram] 전송 실패 또는 자격증명 미설정", file=sys.stderr)
            return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
