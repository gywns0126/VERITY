"""stock_flow_public_builder — 공개 터미널 종목 수급(외국인·기관 일별 순매매) public-safe 빌더.

2026-06-19 신설. 2026-06-20 전 종목 확장(시총순 rotation + 일별 캡 anti-bot + carry-forward).
검증된 파서 = scripts/kr/flow_observation_logger (fetch_trend_mobile 모바일 JSON 우선 / fetch_flow_panel
HTML frgn 폴백). 이 빌더는 그 파서를 *재사용*만 — 결정 파이프라인 영향 0 (공개 표시 전용).

🚨 전 종목 확장 설계 (네이버 anti-bot = 진짜 병목, DART 와 달리 IP 차단 위험):
- universe = stock_report_public.json (discovery 동일, 시총 보유) → **시총 desc 정렬**(수급은 유동 대형주서 의미↑).
- **일별 캡**(FLOW_MAX_TICKERS, 기본 300)으로 IP 차단 회피 — 1,635 한방 금지. rotation 으로 ~6일 전 종목 커버.
  · rec 우선풀 항상 + 나머지를 시총 desc 정렬 후 (day-of-year) offset 회전 → 대형주 우선 + 순차 커버.
- **carry-forward 병합**: 오늘 수집 안 한/실패 종목은 이전 snapshot 유지(forward 누적 trail).
- 모바일 JSON 우선(개인 포함·게이트 낮음) → frgn HTML 폴백. ×DELAY 0.4s.
🚨 RULE 7 — 외국인/기관 일별 순매매량(주) = 외부 시장 *사실*. 자체 flow_score·점수 비노출. forward 누적.
publish: data/stock_flow_5d.json (action.yml 등재). 네트워크 — daily_analysis_full 실행(stock_report 뒤).
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

KST = timezone(timedelta(hours=9))
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
UNIVERSE_PATH = os.path.join(_ROOT, "data", "stock_report_public.json")
RECO_PATH = os.path.join(_ROOT, "data", "recommendations.json")
OUTPUT_PATH = os.path.join(_ROOT, "data", "stock_flow_5d.json")
N_DAYS = 5
DELAY = 0.4
MAX_TICKERS = int(os.environ.get("FLOW_MAX_TICKERS", "300"))  # 일별 캡 (anti-bot)


def _now_kst() -> datetime:
    return datetime.now(KST)


def _parse_cap(s: Any) -> float:
    if not s:
        return 0.0
    txt = str(s)
    v = 0.0
    m = re.search(r"([\d.]+)\s*조", txt)
    if m:
        v += float(m.group(1)) * 1e4
    m = re.search(r"([\d.]+)\s*억", txt)
    if m:
        v += float(m.group(1))
    return v


def _load_parser():
    """flow_observation_logger 의 fetch_trend_mobile(모바일 JSON) + fetch_flow_panel(HTML 폴백)."""
    path = os.path.join(_ROOT, "scripts", "kr", "flow_observation_logger.py")
    spec = importlib.util.spec_from_file_location("flow_observation_logger", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.fetch_trend_mobile, mod.fetch_flow_panel


def _rec_kr_set() -> set:
    try:
        with open(RECO_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return set()
    items = data if isinstance(data, list) else (data.get("recommendations") or data.get("stocks") or [])
    out = set()
    for it in items:
        tk = str(it.get("ticker") or it.get("code") or "").strip()
        if tk.isdigit() and len(tk) == 6:
            out.add(tk)
    return out


def _ordered_universe() -> List[str]:
    """시총 desc 정렬 → rec 우선풀 먼저 + 나머지 (day-of-year) offset 회전 (대형주 우선 + 순차 커버)."""
    try:
        with open(UNIVERSE_PATH, "r", encoding="utf-8") as f:
            doc = json.load(f)
        arr = doc.get("stocks") if isinstance(doc, dict) else doc
    except (OSError, json.JSONDecodeError):
        arr = None
    uni: List[tuple] = []
    if arr:
        for s in arr:
            tk = str(s.get("ticker") or "").strip()
            if tk.isdigit() and len(tk) == 6:
                uni.append((tk, _parse_cap((s.get("facts") or {}).get("시가총액"))))
    if not uni:  # fallback: recommendations
        for tk in _rec_kr_set():
            uni.append((tk, 0.0))
    uni.sort(key=lambda x: -x[1])  # 시총 desc
    rec = _rec_kr_set()
    priority = [tk for tk, _ in uni if tk in rec]
    rest = [tk for tk, _ in uni if tk not in rec]
    if rest:
        off = _now_kst().timetuple().tm_yday % len(rest)
        rest = rest[off:] + rest[:off]
    # 중복 제거 유지 순서
    seen, order = set(), []
    for tk in priority + rest:
        if tk not in seen:
            seen.add(tk)
            order.append(tk)
    return order


def _load_prev() -> Dict[str, List[Dict[str, Any]]]:
    try:
        with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
            doc = json.load(f)
        fm = doc.get("flows") if isinstance(doc, dict) else None
        return fm if isinstance(fm, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def main() -> int:
    ok = False
    try:
        import requests

        order = _ordered_universe()
        if not order:
            print("[stock_flow_public] universe 0 — skip", file=sys.stderr)
            return 0
        fetch_mobile, fetch_html = _load_parser()
        today = _now_kst().date().strftime("%Y-%m-%d")

        merged = _load_prev()            # carry-forward 베이스
        sess = requests.Session()
        n_ok = n_fail = collected = 0
        for tk in order[:MAX_TICKERS]:
            collected += 1
            try:
                panel = fetch_mobile(tk, sess) or fetch_html(tk, sess) or []
            except Exception as e:  # noqa: BLE001
                n_fail += 1
                print(f"[stock_flow_public] {tk} 실패: {e!r}", file=sys.stderr)
                time.sleep(DELAY)
                continue
            panel_sorted = sorted(panel, key=lambda r: str(r.get("date") or ""), reverse=True)
            rows = []
            for r in panel_sorted[:N_DAYS]:
                if r.get("foreign_net") is None and r.get("inst_net") is None:
                    continue
                rows.append({
                    "date": r.get("date"),
                    "foreign_net": r.get("foreign_net"),
                    "inst_net": r.get("inst_net"),
                    "close": r.get("close"),
                })
            if rows:
                rows.reverse()  # 오래된→최신 (막대 좌→우)
                merged[tk] = rows
                n_ok += 1
            else:
                n_fail += 1   # 실패/공백 = 이전 snapshot 유지(carry-forward, pop 안 함)
            time.sleep(DELAY)

        if not merged and os.path.isfile(OUTPUT_PATH):
            print("[stock_flow_public] 0 flows — 기존 snapshot 보존", file=sys.stderr)
            ok = True
            return 0

        out = {
            "_meta": {
                "generated_at": _now_kst().isoformat(),
                "source": "네이버 금융 모바일 trend / frgn (외국인·기관 일별 순매매량, 주)",
                "universe": len(order),
                "collected_today": collected,
                "ok": n_ok,
                "count": len(merged),
                "days": N_DAYS,
                "note": "외부 시장 사실(순매매량)만 — 자체 flow_score·점수 비노출 (RULE 7). 시총순 회전 수집·forward 누적.",
            },
            "flows": merged,
        }
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False)
        print(f"[stock_flow_public] logged=True · {len(merged)} 종목(누적) · 오늘 {n_ok}ok/{n_fail}fail/{collected}수집 -> "
              f"{os.path.relpath(OUTPUT_PATH, _ROOT)}", file=sys.stderr)
        ok = True
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[stock_flow_public] FAILED: {e!r}", file=sys.stderr)
        return 1
    finally:
        if not ok:
            print("[stock_flow_public] logged=False", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
