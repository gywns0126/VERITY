#!/usr/bin/env python3
"""크립토 국면 트리거 감시 — 판단을 바꿀 사건만 알린다.

## 왜 (2026-08-22, PM 지시)

2026-08-20~22 BTC 가 3일 만에 +20% 급등했다(65,385 → 78,473). 촉매는 미 재무부 장기물
바이백 확대(회당 $2B→$4B, **시행 9/9**) + 백악관 크립토 회의 + SEC 제안이고, $10억 숏 청산이
증폭했다. 그 시점 우리 축은 **펀딩 중립·롱숏 1.2 = 과열 아님**, FNG 71 로 임계 근접이었다.

즉 "지금 팔아야 하나" 가 아니라 **"무엇이 바뀌면 판단을 바꾸나"** 가 실제 질문이었고,
그 조건들이 사람 머릿속에만 있었다. 이 스크립트가 그걸 기계로 옮긴다.

## 무엇을 감시하지 '않는가' — 이게 설계의 핵심

🚨 **레짐 call 전이(risk_on↔off)는 넣지 않았다.** 60일 trail 실측 = **전환 23회 / 59일
= 2.6일마다 1회**, 연속 유지 중앙값 2일, 하루 만에 뒤집힌 게 24건 중 10건이다.
알림으로 걸면 이틀에 한 번 울리고 절반이 다음 날 취소된다 — RULE 1 계열 알림 폭주다.
원인은 활성 축이 4개뿐이라 한 축만 흔들려도 net≥+2 경계를 넘나드는 것.

🚨 **TIDE 국면 감시와 겹치지 않는다.** FNG>60 국면 도래·독립관측 k·성과 게이트 전이는
`TIDE/tide/risk/regime_watch.py` (2026-08-17) 가 이미 한다. 여기서 또 하면 두 정의가
갈라진다. 이쪽은 **FNG 75 과열**(그쪽은 60 국면 시작)로 축이 다르다.

## 임계 — 전부 기존 상수 재사용, 새 숫자 0개

    FNG 과열      api.builders.crypto_regime_synthesis.FNG_EXTREME_GREED   = 75
    펀딩 과열     api.config.CRYPTO_FUNDING_OVERHEAT                       = 0.06 (%)
    ETF 순유출    부호 반전 — 임계 없음
    바이백 시행   2026-09-09 (외부 확정 날짜, 우리 추정 아님)

🚨 유일한 임의값 = `CONFIRM_DAYS`. 임계 근처 진동(74↔76)으로 반복 발화하지 않게 하는
확인일수이고, TIDE `REGIME_GATE_CONFIRM_DAYS=3` 과 같은 문법이다. **1회 고정 · 이후 조정 금지**
(조정하려면 사전등록 — 알림이 시끄럽다고 늘리면 진짜 신호도 같이 늦어진다).

## 이력을 왜 자체로 쌓는가

전이 판정에는 어제 값이 필요하다. `crypto_exogenous_history.json` 에 FNG 3,115일·펀딩
2,533일이 있지만 🚨 **그 파일은 어느 워크플로에도 물려 있지 않은 1회성 백필**이라
2026-08-16 에서 멈춰 있다(실측). 죽은 파일을 이력으로 쓰면 전이를 영영 못 잡는다.
그래서 매 run 관측을 `crypto_trigger_trail.jsonl` 에 append 한다 — git 커밋되므로
러너가 ephemeral 이어도 남는다(TIDE 가 폐기한 것은 **러너 로컬 상태파일**이지 커밋 이력이 아니다).

출력: data/observations/crypto_trigger_trail.jsonl (append) + 발화 시 텔레그램
사용: python3 scripts/audit/crypto_trigger_watch.py [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)

KST = timezone(timedelta(hours=9))
_DATA = os.path.join(_ROOT, "data")
TRAIL = os.path.join(_DATA, "observations", "crypto_trigger_trail.jsonl")

CONFIRM_DAYS = 3          # 🚨 1회 고정 · 조정 금지 (TIDE REGIME_GATE_CONFIRM_DAYS 문법 승계)
BUYBACK_DATE = date(2026, 9, 9)   # 미 재무부 장기물 바이백 확대 시행일 (외부 확정)
BUYBACK_LEAD_DAYS = (3, 0)        # D-3 · D-0 에 한 번씩


def _now():
    return datetime.now(KST)


def _load(name):
    try:
        with open(os.path.join(_DATA, name), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def observe() -> dict:
    """오늘 관측 1행. 값이 없으면 None — 🚨 0 으로 채우지 않는다(부재와 0은 다른 사건)."""
    macro = _load("crypto_macro.json")
    etf = _load("crypto_etf_flow.json")
    fng = (macro.get("fear_and_greed") or {})
    fund = (macro.get("funding_rate") or {})
    btc = (etf.get("btc") or {})
    eth = (etf.get("eth") or {})
    net = None
    if btc.get("ok") or eth.get("ok"):
        net = float(btc.get("daily_net_inflow_usd") or 0) + float(eth.get("daily_net_inflow_usd") or 0)
    return {
        "date": _now().date().isoformat(),
        "fng": float(fng["value"]) if fng.get("ok") and fng.get("value") is not None else None,
        "funding_pct": float(fund["rate_pct"]) if fund.get("ok") and fund.get("rate_pct") is not None else None,
        "etf_net_usd": net,
        "etf_as_of": btc.get("as_of") or eth.get("as_of"),
    }


def read_trail() -> list:
    if not os.path.exists(TRAIL):
        return []
    out = []
    try:
        with open(TRAIL, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        out.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except OSError:
        pass
    return out


def _fired_recently(hist: list, key, days: int) -> bool:
    """직전 `days` 일 안에 이미 조건을 만족했나 = 전이가 아니라 지속."""
    prev = [r for r in hist][-days:] if days else []
    return any(key(r) for r in prev)


def evaluate(today: dict, hist: list) -> list:
    """발화할 트리거 목록. 지속 중인 상태는 발화하지 않는다(전이만)."""
    from api.builders.crypto_regime_synthesis import FNG_EXTREME_GREED
    from api.config import CRYPTO_FUNDING_OVERHEAT
    fired = []

    # ① FNG 과열 진입 — 오늘 ≥75 이고 직전 CONFIRM_DAYS 일이 전부 미만
    f = today.get("fng")
    if f is not None and f >= FNG_EXTREME_GREED:
        if not _fired_recently(hist, lambda r: (r.get("fng") or 0) >= FNG_EXTREME_GREED, CONFIRM_DAYS):
            fired.append(("FNG 과열 진입", f"FNG {f:.0f} ≥ {FNG_EXTREME_GREED} "
                                          f"— 레짐 심리 축이 off 로 전환됩니다"))

    # ② 펀딩 과열 진입 — 레버리지 쏠림. 청산 캐스케이드 전조
    fp = today.get("funding_pct")
    if fp is not None and fp >= CRYPTO_FUNDING_OVERHEAT:
        if not _fired_recently(hist, lambda r: (r.get("funding_pct") or -99) >= CRYPTO_FUNDING_OVERHEAT,
                               CONFIRM_DAYS):
            fired.append(("펀딩 과열 진입", f"펀딩 {fp:.4f}% ≥ {CRYPTO_FUNDING_OVERHEAT}% "
                                          f"— 롱 레버리지 쏠림, 청산 캐스케이드 위험 구간"))

    # ③ ETF 순유출 전환 — 부호 반전. 🚨 임계 없음(0 기준)이라 CONFIRM_DAYS 를 그대로 적용
    net = today.get("etf_net_usd")
    if net is not None and net < 0:
        if not _fired_recently(hist, lambda r: (r.get("etf_net_usd") if r.get("etf_net_usd") is not None else 1) < 0,
                               CONFIRM_DAYS):
            fired.append(("ETF 순유출 전환", f"BTC+ETH ETF 일일 순유출 ${abs(net)/1e6:,.0f}M "
                                           f"— 자금흐름 축 off"))

    # ④ 바이백 시행 리마인더 — 상태가 아니라 날짜. 이력 대조 불필요
    d = (BUYBACK_DATE - _now().date()).days
    if d in BUYBACK_LEAD_DAYS:
        when = "오늘" if d == 0 else f"D-{d}"
        fired.append((f"재무부 바이백 시행 {when}",
                      f"{BUYBACK_DATE} 장기물 바이백 확대(회당 $2B→$4B) 시행. "
                      f"8/20 급등의 촉매가 실물로 바뀌는 날 — sell-the-news 구간"))
    return fired


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="알림 미발송 · 판정만 출력")
    a = ap.parse_args()

    today = observe()
    hist = read_trail()
    hist = [r for r in hist if r.get("date") != today["date"]]   # 같은 날 재실행 대비

    missing = [k for k in ("fng", "funding_pct", "etf_net_usd") if today.get(k) is None]
    if len(missing) == 3:
        # 🚨 입력 전멸 = 수집기 장애다. 조용히 "발화 0" 으로 끝내면 그게 침묵 실패다.
        print("[trigger] 입력 3종 전부 부재 — 수집기 장애 의심. exit 1", file=sys.stderr)
        return 1
    if missing:
        print(f"[trigger] 입력 일부 부재 {missing} — 해당 트리거는 판정 skip", file=sys.stderr)

    fired = evaluate(today, hist)

    # 🚨 dry-run 은 이력을 오염시키지 않는다. 기록하면 다음 실행이 "어제 이미 발화" 로 읽어
    #    진짜 전이를 삼킨다 — 점검하려다 감시를 끄는 꼴이다.
    if not a.dry_run:
        os.makedirs(os.path.dirname(TRAIL), exist_ok=True)
        with open(TRAIL, "a", encoding="utf-8") as f:
            row = dict(today)
            if fired:
                row["fired"] = [t for t, _ in fired]
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"[trigger] {today['date']} · FNG {today.get('fng')} · 펀딩 {today.get('funding_pct')}% "
          f"· ETF ${(today.get('etf_net_usd') or 0)/1e6:,.0f}M · 이력 {len(hist)}일", file=sys.stderr)
    if not fired:
        print("[trigger] 발화 0 — 판단 바꿀 사건 없음", file=sys.stderr)
        return 0

    lines = ["<b>🔔 크립토 트리거</b>"]
    for title, detail in fired:
        lines.append(f"<b>{title}</b>\n{detail}")
        print(f"[trigger] 🔔 {title} — {detail}", file=sys.stderr)
    lines.append(f"<i>기준 {today['date']} · 임계는 기존 상수 재사용(새 숫자 0)</i>")
    msg = "\n\n".join(lines)

    if a.dry_run:
        print("\n--- dry-run 메시지 ---\n" + msg)
        return 0
    try:
        from api.notifications.telegram import send_message
        send_message(msg, source="crypto_trigger_watch")
    except Exception as e:  # noqa: BLE001
        print(f"[trigger] 발송 실패(판정은 trail 에 기록됨): {e!r}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
