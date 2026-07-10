"""market_warnings_public_builder — 공개 터미널 KRX 시장경보(투자주의/경고/위험·단기과열·관리종목) 빌더.

2026-06-20 신설. PM "투자경고 빌드". 에이전트 가치판정 — KRX 공식 시장경보 = 우리 리스크 forensics 정합,
KIS 현재가 응답(이미 호출하는 inquire-price output)에 플래그가 이미 들어옴 → 토스·Railway Pro 불요.
🚨 RULE 1 — KISBroker(cache_only=True) 만 사용(신규 토큰 발급 절대 금지, read 전용). KIS 단일 발급원 무관.
🚨 RULE 7 — KRX 공식 지정(사실)만 노출. 자체 점수·판단 0. 경보 없음 = 그 자체로 신뢰 신호.

입력 = KIS inquire-price output (mrkt_warn_cls_code / iscd_stat_cls_code / short_over_yn 등). 유니버스 = recommendations KR.
출력 = data/market_warnings.json (action.yml 등재). daily_analysis_full 실행(KIS 토큰 보유 env).
v0 커버리지 = 운영풀(대부분 clean) — 전종목 경보는 KIS 호출예산 별도 의제.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

KST = timezone(timedelta(hours=9))
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REC_PATH = os.path.join(_ROOT, "data", "recommendations.json")
OUTPUT_PATH = os.path.join(_ROOT, "data", "market_warnings.json")
DELAY = 0.12

# KIS iscd_stat_cls_code → 라벨 (KRX 종목상태)
_STAT = {"51": "관리종목", "52": "투자위험", "53": "투자경고", "54": "투자주의", "58": "거래정지", "59": "단기과열"}
# 심각도 → 색 토큰(컴포넌트 매핑용): danger(빨강)/warn(amber)/caution(sub)
_SEV = {"투자위험": "danger", "거래정지": "danger", "관리종목": "danger", "정리매매": "danger",
        "투자경고": "warn", "단기과열": "warn", "투자주의": "caution"}


def _now_kst() -> datetime:
    return datetime.now(KST)


def _labels(o: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    def add(x):
        if x and x not in out:
            out.append(x)
    mw = str(o.get("mrkt_warn_cls_code") or "00")
    add({"01": "투자주의", "02": "투자경고", "03": "투자위험"}.get(mw))
    if str(o.get("short_over_yn") or "N") == "Y":
        add("단기과열")
    if str(o.get("invt_caful_yn") or "N") == "Y":
        add("투자주의")
    add(_STAT.get(str(o.get("iscd_stat_cls_code") or "")))
    if str(o.get("mang_issu_cls_code") or "") not in ("", "0", "00", "N"):
        add("관리종목")
    if str(o.get("sltr_yn") or "N") == "Y":
        add("정리매매")
    return out


def _kr_tickers() -> List[Dict[str, str]]:
    try:
        with open(REC_PATH, "r", encoding="utf-8") as f:
            recs = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    out = []
    for r in (recs if isinstance(recs, list) else []):
        tk = str(r.get("ticker") or "").strip()
        if tk.isdigit() and len(tk) == 6:
            out.append({"ticker": tk, "name": r.get("name") or tk})
    return out


def main() -> int:
    ok = False
    try:
        from api.trading.kis_broker import KISBroker

        broker = KISBroker(cache_only=True)  # 🚨 발급 금지, cache read 전용
        warnings: Dict[str, Any] = {}
        n_warn = 0
        n_checked = 0  # 조회 성공 수 — 0 = 토큰사(침묵 실패), >0 이고 경보 0 = clean 사실
        for u in _kr_tickers():
            tk, name = u["ticker"], u["name"]
            try:
                o = broker.get_current_price(tk) or {}
                n_checked += 1
            except Exception as e:  # noqa: BLE001 (cache 토큰 없으면 여기서 skip — RULE1 안전)
                print(f"[market_warnings] {tk} skip: {str(e)[:80]}", file=sys.stderr)
                time.sleep(DELAY)
                continue
            labs = _labels(o)
            if labs:
                warnings[tk] = {
                    "name": name,
                    "labels": [{"label": x, "severity": _SEV.get(x, "caution")} for x in labs],
                }
                n_warn += 1
            time.sleep(DELAY)

        # 🚨 2026-07-10 침묵 실패 차단 — "조회 0건(토큰사)" 과 "경보 0건(clean)" 구분.
        #   옛 로직 = 둘 다 조용히 return 0 → 6/20~7/10 3주 동결에도 run success (사용자 발견 사고).
        if n_checked == 0:
            print("[market_warnings] 전량 조회 실패 (토큰/네트워크) — exit 1 (침묵 금지)", file=sys.stderr)
            return 1
        # n_checked > 0 이고 경보 0 = clean 사실 → 빈 결과도 publish (generated_at 갱신 = 신선도 추적 가능)

        out = {
            "_meta": {
                "generated_at": _now_kst().isoformat(),
                "source": "KIS inquire-price (KRX 시장경보·종목상태 공식 플래그)",
                "universe": "recommendations KR",
                "count": len(warnings),
                "note": "KRX 공식 시장경보(투자주의/경고/위험·단기과열·관리종목 등) 사실만 — 자체 점수·판단 0 (RULE 7). 경보 없는 종목은 미포함(=현재 지정 없음).",
            },
            "warnings": warnings,
        }
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False)
        print(f"[market_warnings] logged=True · 경보 {len(warnings)} 종목 -> {os.path.relpath(OUTPUT_PATH, _ROOT)}", file=sys.stderr)
        ok = True
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[market_warnings] FAILED: {e!r}", file=sys.stderr)
        return 1
    finally:
        if not ok:
            print("[market_warnings] logged=False", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
