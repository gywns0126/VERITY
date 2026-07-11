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
    return res


def main() -> None:
    results = [verify_one(f, c) for f, c in GUARD.items()]
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
                                         "cdn_age_s": r.get("cdn_age_s")} for r in results]},
                           ensure_ascii=False) + "\n")
    for r in results:
        tag = "OK" if r.get("ok") else "FAIL"
        extra = (" · " + r["error"]) if r.get("error") else ""
        print(f"[publish_verify] {tag} {r['file']} · N={r.get('total')} · {r.get('pct')} · CDN age={r.get('cdn_age_s')}s{extra}")
    if bad:
        print(f"::error::publish_verify {len(bad)} 파일 배달 붕괴 — {[b['file'] for b in bad]}")
        raise SystemExit(1)
    print(f"[publish_verify] OK · {len(results)} 파일 배달 정합")


if __name__ == "__main__":
    main()
