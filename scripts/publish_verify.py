"""발행 후 실물 검증 (P2) — 업로드된 실제 CDN 산출물을 재fetch 해 핵심 필드 채움율 단언.

발행 성공 ≠ 배달 정합: 업로드 손상·CDN 스테일 갭 차단. 로컬 빌드가 아니라 '배달된 것'을 본다.
절차(guarded 파일별):
  (1) 캐시버스트 fetch(?v=ts) = origin 진실(방금 발행본) 채움율 검사 — 배달 손상 감지.
  (2) plain fetch = 사용자 edge 가 받는 것의 age 헤더(CDN 스테일 지표) 수집 — max-age 초과 서빙 감시.
출력: data/metadata/publish_verify.json(최신) + publish_verify.jsonl(추이) — admin 데이터-헬스 피드가 소비.
규율: 측정만(RULE 7). 핵심 붕괴 감지 시 exit 1 → 워크플로 red.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
BLOB_HOST = os.environ.get("VERITY_BLOB_HOST", "https://rte5guenhonw9fzn.public.blob.vercel-storage.com")
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_META = os.path.join(_ROOT, "data", "metadata")
OUT = os.path.join(_META, "publish_verify.json")
HIST = os.path.join(_META, "publish_verify.jsonl")

# blob_upload.js 의 CORE_GUARD 와 1:1 (배달 검증 = 발행 가드의 사후 확인)
GUARD = {
    "stock_report_public.json":         {"subfields": ["PER", "PBR"], "floor": 5.0, "min_n": 100, "kr_only": True},
    "us_stock_report_public.json":      {"subfields": ["PER", "PBR"], "floor": 5.0, "min_n": 100, "kr_only": False},
    "us_stock_report_us_smallcap.json": {"subfields": ["PER", "PBR"], "floor": 5.0, "min_n": 50,  "kr_only": False},
}


def _filled(v) -> bool:
    if v is None:
        return False
    if isinstance(v, (list, dict)):
        return len(v) > 0
    if isinstance(v, str):
        return v.strip() not in ("", "—", "-")
    return True


def _fetch(url: str, timeout: int = 45):
    req = urllib.request.Request(url, headers={"User-Agent": "verity-publish-verify"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(), r.headers.get("age")


# ── 섹션 커버리지 (2026-08-08) ─────────────────────────────────────────
# PM "다른 종목들도 이렇게 계속 차야 하는데" — 종전 게이트는 facts.PER/PBR 두 개를
# 하한 5% 로만 봤다. 그래서 2026-08-08 에 발견된 갭(리포트 자체가 없는 종목 198개,
# 공시 없는 종목 570개)은 이 게이트를 그대로 통과했다. 붕괴만 잡고 **미충족은 못 본다**.
#
# 두 가지를 더한다:
#   ① 래칫 — 한 번 찬 섹션이 다시 비면 막는다(회귀 방지). 절대 임계를 사람이 정하지 않고
#      과거 기록 대비로 판단하므로, 커버리지가 늘수록 기준도 같이 올라간다.
#   ② 갭 순위 — 덜 찬 섹션을 매 발행마다 출력해 다음에 채울 곳이 저절로 드러나게 한다.
#      (한 종목씩 사람이 발견하는 방식은 지속 가능하지 않다는 것이 이번 사례의 교훈)
_SECTIONS = ("disclosures", "fin_series", "ownership", "calendar", "peer", "consensus", "business")
# 회귀 판정 여유 — 유니버스 구성이 바뀌면 몇 %p 는 자연 변동한다. 그보다 큰 하락만 잡는다.
_RATCHET_TOL_PCT = 3.0
# 종목 수 감소 허용치(%). 상장폐지 등으로 소폭 줄 수 있으나 대량 이탈은 사고다.
_RATCHET_N_TOL = 2.0
# 기준선 = 최근 이 개수의 기록 중 최댓값 (단발 이상치에 기준이 끌려가지 않도록)
_BASELINE_WINDOW = 10


def _section_coverage(arr: list) -> dict:
    """섹션별 보유 종목 비율(%). 값의 품질이 아니라 '있나 없나'만 본다 = 사실 계측."""
    total = len(arr) or 1
    out = {}
    for sec in _SECTIONS:
        out[sec] = round(sum(1 for s in arr if _filled((s or {}).get(sec))) * 100.0 / total, 1)
    return out


def _baseline_from_history(fname: str, current_total: int) -> dict:
    """현재와 분모가 동급인 과거 기록에서 최고 커버리지·최대 N을 회수한다.

    유니버스 확대 전의 높은 비율을 확대 후 분모와 비교하면 신규 종목 유입을 데이터
    손실로 오판한다. 현재 N의 허용 오차 안에 있는 이력만 동일 cohort로 취급한다.
    """
    best: dict = {}
    best_n = 0
    try:
        with open(HIST, "r", encoding="utf-8") as f:
            lines = f.readlines()[-_BASELINE_WINDOW:]
    except FileNotFoundError:
        return {}
    for line in lines:
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        for r in rec.get("results") or []:
            if r.get("file") != fname:
                continue
            n = r.get("total")
            if not isinstance(n, int) or n <= 0:
                continue
            delta_pct = abs(n - current_total) * 100.0 / max(current_total, 1)
            if delta_pct > _RATCHET_N_TOL:
                continue
            for k, v in (r.get("coverage") or {}).items():
                if isinstance(v, (int, float)) and v > best.get(k, -1):
                    best[k] = v
            if n > best_n:
                best_n = n
    if best_n:
        best["_total"] = best_n
    return best


def verify_one(fname: str, cfg: dict) -> dict:
    res: dict = {"file": fname, "ok": False}
    try:
        raw, _ = _fetch(f"{BLOB_HOST}/{fname}?v={int(time.time())}")  # 캐시버스트 = origin 진실
        doc = json.loads(raw)
    except Exception as e:  # noqa: BLE001
        res["error"] = f"fetch/parse 실패: {e}"
        return res
    arr = doc.get("stocks")
    if not isinstance(arr, list):
        res["error"] = "stocks 배열 부재"
        return res
    if cfg["kr_only"]:
        arr = [s for s in arr if str((s or {}).get("ticker", "")).isdigit() and len(str((s or {}).get("ticker", ""))) == 6]
    total = len(arr)
    res["total"] = total
    try:  # plain fetch age = 사용자 edge 스테일 지표
        _, age = _fetch(f"{BLOB_HOST}/{fname}")
        res["cdn_age_s"] = int(age) if age is not None else None
    except Exception:  # noqa: BLE001
        res["cdn_age_s"] = None
    if total < cfg["min_n"]:
        res["ok"] = True
        res["note"] = "N부족 판단보류"
        return res
    pcts, ok = {}, True
    for sub in cfg["subfields"]:
        filled = sum(1 for s in arr if _filled(((s or {}).get("facts") or {}).get(sub)))
        pct = round(filled * 100.0 / total, 1)
        pcts[sub] = pct
        if pct < cfg["floor"]:
            ok = False
    res["pct"] = pcts
    res["ok"] = ok
    if not ok:
        res["error"] = f"배달 채움율 붕괴 {pcts} < floor {cfg['floor']}%"

    # 섹션 커버리지 + 래칫(회귀 방지). 붕괴(floor)와 별개로 **후퇴**를 잡는다.
    cov = _section_coverage(arr)
    res["coverage"] = cov
    base = _baseline_from_history(fname, total)
    drops = []
    for k, v in cov.items():
        b = base.get(k)
        if isinstance(b, (int, float)) and v < b - _RATCHET_TOL_PCT:
            drops.append(f"{k} {b}%→{v}%")
    bn = base.get("_total")
    if isinstance(bn, int) and bn > 0 and total < bn * (1 - _RATCHET_N_TOL / 100.0):
        drops.append(f"종목수 {bn}→{total}")
    if drops:
        res["ok"] = False
        res["regression"] = drops
        prev = res.get("error")
        res["error"] = ("커버리지 후퇴: " + " · ".join(drops)) + (f" | {prev}" if prev else "")
    # 미충족 상위 — 다음에 채울 곳이 매 발행마다 드러나게 한다(사람이 종목별로 찾지 않도록)
    res["gaps"] = sorted(((k, v) for k, v in cov.items() if v < 95.0), key=lambda x: x[1])[:5]
    return res


# 🚨 2026-08-16 신설 — 배달 '내용' 이 아니라 배달 '시각' 을 본다.
#   사고: VERITY_DATA_PAT 만료로 VERITY-data push 가 23시간 멈췄는데
#   publish_verify 는 그 내내 ok=true 였다. 이 스크립트가 Blob 만 보고,
#   Blob 조회는 stale 한 옛 파일에도 200 을 돌려주기 때문이다(cdn_age_s 는 CDN 캐시
#   나이지 내용 나이가 아니다). publish-data 액션은 gh-pages 를 먼저 돌리고
#   실패 시 composite 이 중단되어 Blob dual-write 까지 skip 되므로, 그 23시간은
#   VERITY-data 와 Blob 이 **양쪽 다** 멈춘 구간이었다.
#   호출부 4곳이 publish 단계에 continue-on-error: true 를 걸어 run 은 초록불이었고,
#   신선도 SLA 는 VERITY repo 안 파일 mtime 만 봐서 33건 전부 stale 0 을 보고했다.
#   즉 기존 신호 전부가 무증상이었고, 유일하게 남는 1차 사실이 VERITY-data 의 push 시각이다.
_DATA_REPO_API = "https://api.github.com/repos/gywns0126/VERITY-data"
_PUSH_SLA_H = 3.0   # cockpit 5분 cron 등 상시 publish 가 있어 3h 는 충분히 느슨하다


def verify_publish_recency() -> dict:
    """VERITY-data 마지막 push 시각 SLA. 배달 자체가 멎은 것을 잡는 유일한 검사."""
    res = {"file": "_verity_data_push_recency", "ok": False}
    try:
        raw, _ = _fetch(_DATA_REPO_API)
        pushed = json.loads(raw).get("pushed_at")
        if not pushed:
            res["error"] = "pushed_at 부재"
            return res
        ts = datetime.strptime(pushed, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        age_h = (datetime.now(timezone.utc) - ts).total_seconds() / 3600.0
        res["pushed_at"] = pushed
        res["age_h"] = round(age_h, 2)
        res["sla_h"] = _PUSH_SLA_H
        res["ok"] = age_h <= _PUSH_SLA_H
        if not res["ok"]:
            res["error"] = (f"VERITY-data push {age_h:.1f}h 정지 (SLA {_PUSH_SLA_H}h) — "
                            "배달 경로 붕괴. run 이 초록불이어도 사이트는 멎어 있다")
    except Exception as e:  # noqa: BLE001
        res["error"] = f"조회 실패: {e}"
    return res


def main() -> None:
    results = [verify_one(f, c) for f, c in GUARD.items()]
    results.append(verify_publish_recency())
    bad = [r for r in results if not r.get("ok")]
    doc = {
        "generated_at": datetime.now(KST).isoformat(),
        "ok": len(bad) == 0,
        "checked": len(results),
        "failed": len(bad),
        "results": results,
    }
    os.makedirs(_META, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    with open(HIST, "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": doc["generated_at"], "ok": doc["ok"], "failed": doc["failed"],
                            "results": [{"file": r["file"], "ok": r.get("ok"), "pct": r.get("pct"),
                                         "total": r.get("total"), "coverage": r.get("coverage"),
                                         "cdn_age_s": r.get("cdn_age_s")} for r in results]},
                           ensure_ascii=False) + "\n")
    for r in results:
        tag = "OK" if r.get("ok") else "FAIL"
        extra = (" · " + r["error"]) if r.get("error") else ""
        print(f"[publish_verify] {tag} {r['file']} · N={r.get('total')} · {r.get('pct')} · CDN age={r.get('cdn_age_s')}s{extra}")
        if r.get("gaps"):
            gap_s = " · ".join(f"{k} {v}%" for k, v in r["gaps"])
            print(f"[publish_verify]   미충족 상위: {gap_s}")
    if bad:
        print(f"::error::publish_verify {len(bad)} 파일 배달 붕괴 — {[b['file'] for b in bad]}")
        raise SystemExit(1)
    print(f"[publish_verify] OK · {len(results)} 파일 배달 정합")


if __name__ == "__main__":
    main()
