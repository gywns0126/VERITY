#!/usr/bin/env python3
"""크립토 레짐 6차원 중 **죽어 있던 2개**를 되살릴 이력 수집 (2026-08-17).

## 왜 — 실측으로 드러난 구조적 사망

`crypto_regime_synthesis.py` 는 6차원 tally 로 레짐을 판정한다. 그런데
`crypto_regime_trail.jsonl` 55행에서 `active_dims` 가 **30일 내내 상수 4** 였다.
원인을 보니 버그가 아니라 **2개 차원이 하드코딩 `active: False`** 였다:

| 차원 | 코드상 활성 조건 | 실제 |
|---|---|---|
| ⑤ 유동성 | `"스테이블 공급 추세 = 이력 누적 후 활성"` | 🚨 누적처 0 |
| ⑥ 펀더멘털·온체인 | `"DeFiLlama 매출 추세 = 이력 누적"` (+ TIDE 브릿지) | 🚨 누적처 0 |

🚨 **활성 조건이 "이력 누적 후" 인데 이력을 누적하는 곳이 없었다.** 30분마다 수집해
`drivers` 에 현재값만 싣고 시계열은 버렸다 — 전수 grep 으로 저장 지점 **0건** 확인
(`crypto_stablecoins.json` = `total_supply_usd` 단일 float · `crypto_defillama.json`
= 현재 fees 스냅샷). 즉 두 차원은 **영원히 활성화될 수 없는 상태**였고, 그동안
레짐 판정은 6차원이 아니라 4차원으로 돌아왔다.

이 파일이 그 누적을 만든다. 다행히 두 원본 모두 **전 구간 백필이 가능**하므로
몇 달을 기다릴 필요가 없다 (실호출 확인: 스테이블 3,184일 · 수수료 3,067일).

## 수집 대상

| 축 | 쓰임 | 출처 |
|---|---|---|
| 스테이블코인 총공급(USD) | 차원⑤ 유동성 추세 | DefiLlama `stablecoins.llama.fi/stablecoincharts/all` |
| DeFi 총수수료 24h(USD) | 차원⑥ 펀더멘털 매출 추세 | DefiLlama `api.llama.fi/overview/fees` |

Attribution: DefiLlama (https://defillama.com), 무료 공개 API·무인증.

## 경계

- 🚨 **수집만 한다.** 두 차원을 실제로 `active: True` 로 바꾸는 것은 레짐 판정을
  움직이므로 **RULE 7 사전등록 + PM 승인 대상**이다. 이 파일은 그 전제 조건만 만든다.
- `crypto_exogenous_history.json` 과 축이 겹치지 않는다 (그쪽 = FNG·펀딩·김프·반감기·ETF,
  `purpose` 도 "TIDE 백테스트용"). 목적·소비처가 달라 파일을 분리한다.
- 멱등 — 매 실행이 전 구간을 다시 받아 덮는다. 호출 2회라 비용이 무시할 수준이고,
  원본이 과거값을 정정해도 따라간다. 하루 1회면 충분하다(일 단위 시계열).

산출 = `data/crypto_regime_history.json`.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import time
import urllib.request

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(_ROOT, "data", "crypto_regime_history.json")

STABLE_URL = "https://stablecoins.llama.fi/stablecoincharts/all"
FEES_URL = ("https://api.llama.fi/overview/fees"
            "?excludeTotalDataChart=false&excludeTotalDataChartBreakdown=true")
UA = {"Accept": "application/json", "User-Agent": "verity-research/1.0"}


def _get(url: str, timeout: int = 30, retries: int = 4):
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except Exception:  # noqa: BLE001 — 네트워크 계열 전부 재시도 대상
            if i == retries - 1:
                return None
            time.sleep(0.8 * (i + 1))
    return None


def _day(unix_like) -> str | None:
    """unix 초(문자열 가능) → 'YYYY-MM-DD'. 파싱 불가면 None (조용히 버리지 않고 셈)."""
    try:
        return dt.datetime.fromtimestamp(int(unix_like), dt.timezone.utc).strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return None


def fetch_stablecoin_supply() -> dict:
    """일자 → USD 페그 스테이블 총공급(USD).

    `totalCirculatingUSD` 는 페그 통화별 dict 다. USD 페그만 쓰지 않고 **전 페그 합**을
    쓴다 — 차원⑤ 가 보는 것은 '스테이블 유동성 전체'이지 달러 페그 한정이 아니다.
    """
    rows = _get(STABLE_URL)
    if not isinstance(rows, list):
        return {}
    out: dict[str, float] = {}
    for r in rows:
        if not isinstance(r, dict):
            continue
        d = _day(r.get("date"))
        circ = r.get("totalCirculatingUSD")
        if d is None or not isinstance(circ, dict):
            continue
        total = sum(v for v in circ.values() if isinstance(v, (int, float)))
        if total > 0:
            out[d] = round(float(total), 2)
    return out


def fetch_defi_fees() -> dict:
    """일자 → DeFi 전체 수수료 24h(USD). `totalDataChart` = [[unix, usd], ...]."""
    doc = _get(FEES_URL)
    if not isinstance(doc, dict):
        return {}
    out: dict[str, float] = {}
    for pair in (doc.get("totalDataChart") or []):
        if not (isinstance(pair, (list, tuple)) and len(pair) >= 2):
            continue
        d = _day(pair[0])
        v = pair[1]
        if d is not None and isinstance(v, (int, float)) and v > 0:
            out[d] = round(float(v), 2)
    return out


def _already_today() -> bool:
    """오늘자가 이미 들어 있으면 True. 30분 크론에 매번 걸어도 하루 1회만 실제 수집한다.

    파일 mtime 이 아니라 **내용의 마지막 날짜**로 판정한다 — CI 는 매 run 체크아웃이라
    mtime 이 항상 '방금' 이고, mtime 기준 게이트는 CI 에서 영원히 거짓이다
    (2026-08-15 `dart_corp_code.ensure_name_map` 이 정확히 이 형태로 죽어 있었다).
    """
    try:
        with open(OUT, encoding="utf-8") as f:
            rng = (json.load(f).get("coverage") or {}).get("range") or []
    except (OSError, ValueError):
        return False
    today = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime("%Y-%m-%d")
    return bool(rng) and rng[-1] >= today


def main() -> int:
    if "--force" not in sys.argv and _already_today():
        print("[crypto_regime_history] 오늘자 이미 수집됨 — 생략 (--force 로 강제)")
        return 0
    supply = fetch_stablecoin_supply()
    fees = fetch_defi_fees()

    # 🚨 부분 실패를 성공으로 넘기지 않는다 — 한쪽이라도 비면 그 차원은 못 살아난다.
    #    (건수 0 + 성공 종료 = 조용한 결손. [[feedback_cluster_silent_defect]])
    if not supply and not fees:
        sys.stderr.write("[crypto_regime_history] 양쪽 원본 모두 수집 실패 — 기존 파일 보존\n")
        return 1

    days = sorted(set(supply) | set(fees))
    rows = [{"date": d,
             "stablecoin_supply_usd": supply.get(d),
             "defi_fees_usd_24h": fees.get(d)} for d in days]

    doc = {
        "collected_at": dt.datetime.now(dt.timezone.utc)
                          .astimezone(dt.timezone(dt.timedelta(hours=9)))
                          .strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "schema_version": "v0",
        "purpose": ("crypto_regime 6차원 중 ⑤유동성·⑥펀더멘털 활성화 전제. "
                    "수집 only — 차원 활성화는 RULE 7 사전등록 별건."),
        "sources": {
            "stablecoin_supply_usd": "DefiLlama stablecoincharts/all (전 페그 합)",
            "defi_fees_usd_24h": "DefiLlama overview/fees totalDataChart",
        },
        "coverage": {
            "days": len(rows),
            "stablecoin_supply_usd": len(supply),
            "defi_fees_usd_24h": len(fees),
            "range": [days[0], days[-1]] if days else None,
        },
        "rows": rows,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
    print(f"[crypto_regime_history] {len(rows)}일 "
          f"(공급 {len(supply)} · 수수료 {len(fees)}) "
          f"{days[0] if days else '-'} ~ {days[-1] if days else '-'} → {OUT}")
    # 한쪽만 비면 성공 종료하되 시끄럽게 신고 (다음 run 이 회복 가능한 형태)
    if not supply or not fees:
        sys.stderr.write("::warning::[crypto_regime_history] 한쪽 축 결손 — "
                         f"공급 {len(supply)} · 수수료 {len(fees)}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
