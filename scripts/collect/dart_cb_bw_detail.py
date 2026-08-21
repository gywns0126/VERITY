#!/usr/bin/env python3
"""CB/BW 공시 **원천 필드 보존** 수집기 (2026-08-21 신설).

## 왜 신설인가

기존 `api/analyzers/dart_cb_bw.py` 는 응답 46필드 중 **6개만** 남기고 버렸다
(`type·bond_kind·issue_amount·strike·issuable_shares·resolved_date`).
그래서 사전등록 §0 에서 "잔량 없음 · 전환가 파생값 · 리픽싱 미반영" 이라 결론지었는데,
🚨 **원천에는 셋 다 있다**(실호출 확인, 5종목 50행):

    cv_prc                       50/50  전환가액 실측 (기존 strike 는 발행액÷주식수 파생값)
    cvrqpd_bgd / cvrqpd_edd      50/50  전환청구 시작/종료 → 시점별 유효 오버행 판정
    act_mktprcfl_cvprc_lwtrsprc  23/50  리픽싱 최저조정가
    cvisstk_tisstk_vs            38/50  발행주식총수 대비 % (DART 가 공시 시점 기준 계산)

기존 분석기는 **건드리지 않는다** — 생산 경로가 그것을 읽는다. 이 수집기는 별 산출물을 낸다.
사전등록 = `docs/PREREG_DILUTION_INSIDER_CROSS_2026_08_21.md` (개정 3차).

## 비용 (PM 지시 "버셀 요금 걱정도 좀 하면서")

- 🚨 **Vercel 비용 증가 0.** 산출물 `data/dart_cb_bw_detail.json` 을 발행 화이트리스트
  (`.github/actions/publish-data/action.yml`)에 **넣지 않는다.** 현재 발행 65개 89.9MB 에 미포함.
- 🚨 **Vercel deploy 유발 0.** 이 파일은 `scripts/` 아래라 `vercel.json` 의 `ignoreCommand` 가
  건너뛴다(RULE 2).
- DART 쿼터 = 종목당 2호출(CB·BW). 651종목 = 약 1,302호출 (일 20,000 대비 6.5%).
  `--quota-cap` 으로 상한을 두고 **멱등 재개**한다(종목 경계에서 중단해도 다음 run 이 이어받음).

## 시점 재현

`rcept_dt` 필드는 **없다**. 날짜는 `bddd`(이사회결의일)와 `rcept_no[:8]`(접수일) 로 얻는다.
사전등록 §2 의 시점 재현이 이 두 필드에 의존한다.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = os.path.join(_ROOT, "data")
OUT = os.path.join(DATA, "dart_cb_bw_detail.json")
MAPPING = os.path.join(DATA, "mapping.json")

# 🚨 46필드 중 보존 대상. 전부 남기지 않는 이유 = 파일 크기(발행은 안 하지만 커밋된다).
#    빠진 필드가 필요해지면 여기 추가하고 재수집한다 — 다시 "원천에 없다" 고 하지 않도록
#    이 목록이 **우리가 버린 것의 명세**다.
KEEP = (
    "rcept_no", "corp_code", "corp_name", "bddd",          # 식별·날짜
    "bd_knd", "bd_fta", "bd_mtd", "bdis_mthn",             # 사채 성격·총액·만기·공모여부
    "cv_prc", "cv_rt", "cvisstk_cnt", "cvisstk_tisstk_vs", # 🚨 전환가·비율·주식수·총수대비%
    "cvrqpd_bgd", "cvrqpd_edd",                            # 🚨 전환청구 기간
    "act_mktprcfl_cvprc_lwtrsprc",                         # 🚨 리픽싱 최저조정가
    "ex_sm_r",                                             # 전환 제한 특약
)
ENDPOINTS = (("cvbdIsDecsn", "CB"), ("bdwtIsDecsn", "BW"))


def _key() -> str:
    k = os.environ.get("DART_API_KEY")
    if k:
        return k
    env = os.path.join(_ROOT, ".env")
    if os.path.exists(env):
        for line in open(env, encoding="utf-8"):
            if line.strip().startswith("DART_API_KEY"):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("DART_API_KEY 없음")


def _load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _fetch(ep: str, cc: str, key: str, timeout: int = 20):
    """(rows, status) — status 013(데이터 없음)은 정상 종료로 취급한다."""
    url = f"https://opendart.fss.or.kr/api/{ep}.json?" + urllib.parse.urlencode(
        {"crtfc_key": key, "corp_code": cc, "bgn_de": "20150101", "end_de": "20261231"})
    with urllib.request.urlopen(url, timeout=timeout) as r:
        j = json.loads(r.read().decode("utf-8"))
    return (j.get("list") or []), str(j.get("status") or "")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", help="쉼표 구분. 미지정 시 --universe 사용")
    ap.add_argument("--universe", default="dilution+delisted",
                    help="dilution(기존 383) / delisted(상폐 보통주) / dilution+delisted")
    ap.add_argument("--quota-cap", type=int, default=1400, help="이 run 의 최대 호출 수")
    ap.add_argument("--sleep", type=float, default=0.25)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    key = _key()
    mapping = _load(MAPPING, {})
    mapping = mapping.get("map") or mapping

    # 대상 산출 — 🚨 분모를 먼저 확정하고 찍는다(RULE 13)
    todo: list[str] = []
    if a.tickers:
        todo = [t.strip() for t in a.tickers.split(",") if t.strip()]
    else:
        if "dilution" in a.universe:
            cb = (_load(os.path.join(DATA, "dart_cb_bw_cache.json"), {}) or {}).get("by_ticker") or {}
            todo += [t for t, v in cb.items() if (v.get("n_instruments") or 0) > 0]
        if "delisted" in a.universe:
            import glob
            import re
            names = (_load(os.path.join(DATA, "kr_chart_delisted_meta.json"), {}) or {}).get("names") or {}
            dl: set[str] = set()
            for f in glob.glob(os.path.join(DATA, "kr_chart_delisted", "chunk_*.json")):
                dl |= set(((_load(f, {}) or {}).get("stocks") or {}).keys())
            # 🚨 스팩·우선주 제외 — 설계상 소멸하거나 별도 기업이 아니다(사전등록 §3-E-4)
            todo += [t for t in sorted(dl)
                     if not re.search(r"(우$|우B$|\d우|스팩)", str(names.get(t) or ""))]
    todo = sorted({t for t in todo if mapping.get(t)})

    prev = _load(OUT, {}) or {}
    done = prev.get("by_ticker") or {}
    remain = [t for t in todo if t not in done]
    print(f"[cb_bw_detail] 대상 {len(todo)} · 완료 {len(todo)-len(remain)} · 잔여 {len(remain)} "
          f"· quota_cap {a.quota_cap}")
    if a.dry_run:
        print("  --dry-run: 호출 없이 종료")
        return 0

    calls = 0
    added = 0
    for tk in remain:
        if calls + len(ENDPOINTS) > a.quota_cap:
            print(f"  quota_cap 도달 — {tk} 앞에서 중단(다음 run 이 이어받음)")
            break
        rec: dict = {"ticker": tk, "corp_code": mapping[tk], "instruments": []}
        ok = True
        for ep, kind in ENDPOINTS:
            try:
                rows, st = _fetch(ep, mapping[tk], key)
                calls += 1
            except Exception as e:
                print(f"  {tk} {ep} 실패: {e!r}", file=sys.stderr)
                ok = False
                calls += 1
                continue
            for x in rows:
                item = {k: x.get(k) for k in KEEP}
                item["kind"] = kind
                rec["instruments"].append(item)
            time.sleep(a.sleep)
        if not ok and not rec["instruments"]:
            continue          # 🚨 실패는 기록하지 않는다 — 다음 run 이 재시도한다
        rec["n"] = len(rec["instruments"])
        done[tk] = rec
        added += 1

    out = {
        "_meta": {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "source": "DART cvbdIsDecsn(CB) + bdwtIsDecsn(BW) — 원천 필드 보존",
            "kept_fields": list(KEEP),
            "note": ("🚨 발행 화이트리스트에 넣지 말 것 — 관측 전용이다. "
                     "rcept_dt 는 원천에 없다. 날짜 = bddd(이사회결의일) · rcept_no[:8](접수일). "
                     "🚨 잔량이 아니라 잔량의 상한 — cvrqpd_edd 로 유효 여부만 판정한다."),
            "universe": a.universe,
            "target_total": len(todo),
            "collected": len(done),
        },
        "by_ticker": done,
    }
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, OUT)
    inst = sum(v.get("n") or 0 for v in done.values())
    print(f"[cb_bw_detail] 이번 run 호출 {calls} · 신규 {added}종목 · 누적 {len(done)}/{len(todo)} "
          f"· instrument {inst} · {os.path.getsize(OUT)/1e6:.2f}MB")
    if not remain:
        print("  전량 완료")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
