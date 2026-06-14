"""trail_integrity — 결정시점 학습 trail 의 무결성 단일 감사기.

목적 (2026-06-13 신설): N=252 IC 게이트(2027-05)의 입력이 되는 "결정시점 기록"이
손실 없이·끊김 없이 축적되는지 **언제든 검증 가능**하게 한다. 산식·임계 무관 (RULE 7),
순수 데이터 무결성 read-only 검사.

검사 대상 (decision-trail family):
  1. history/YYYY-MM-DD.json   — 일별 portfolio 최종본 (개별 오심 내러티브 + 114필드 팩터 벡터)
  2. metadata/prediction_trail.jsonl     — 예측별 forward-scoring 로그
  3. metadata/postmortem_auto_evolve.jsonl — 오심→factor quarantine 원장
  4. factor_ic_history.json / prediction_ic_history.jsonl — IC 시계열
  5. wide_scan_log.jsonl       — 7차원 funnel SHADOW 누적

각 trail 에 대해:
  · exists / parseable (잘린 쓰기·손상 검출)
  · 최신 append 신선도 (정체 검출)
  · append-only growth (이전 관측 대비 줄어들면 손실 — baseline 비교)
history 에 대해 추가로:
  · 영업일 연속성 gap (빠진 거래일 = 그날 결정시점 벡터 영구 손실)

출력: dict (status PASS/WARNING/FAIL + per-trail 상세). 호출 측에서 jsonl 적재 + 알림.
"""
from __future__ import annotations

import glob
import json
import os
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from api.config import DATA_DIR, now_kst

HISTORY_DIR = os.path.join(DATA_DIR, "history")
META_DIR = os.path.join(DATA_DIR, "metadata")
_BASELINE_PATH = os.path.join(META_DIR, "trail_integrity_baseline.json")

# 신선도 임계 (시간). 초과 = 정체 의심. 일별 산출물 기준 = 36h (주말/휴장 마진 포함은 호출부 weekday 판단).
_FRESHNESS_LIMIT_H = 36.0

# 검사 대상 trail (path, type, ts_key). type=jsonl 는 line count, json 은 top-level 길이로 growth 측정.
_TRAILS = [
    ("metadata/prediction_trail.jsonl", "jsonl", "created_at"),
    ("metadata/postmortem_auto_evolve.jsonl", "jsonl", "ts_kst"),
    ("prediction_ic_history.jsonl", "jsonl", None),
    ("wide_scan_log.jsonl", "jsonl", None),
    ("factor_ic_history.json", "json", None),
    ("metadata/revision_momentum_shadow.jsonl", "jsonl", "ts_kst"),  # A2 SHADOW (2026-06-15)
]

# N=252 IC 게이트(2027)로 누적 중인 shadow 신호 — 진행률 추적용 (path, date_key).
# 거래일 누적 = 고유 날짜 수. ic_crosscheck 는 on-demand(일별 아님)라 제외.
_GATE_N = 252
_SHADOW_GATE_TRAILS = [
    ("metadata/revision_momentum_shadow.jsonl", "ts_kst"),   # A2 리비전 모멘텀
    ("wide_scan_log.jsonl", "ts"),                            # wide_scan 7차원 funnel
]


def _p(rel: str) -> str:
    return os.path.join(DATA_DIR, rel)


def _business_day_gaps(dates: List[date]) -> List[str]:
    """연속 날짜 사이 빠진 영업일(월~금) 목록."""
    missing: List[str] = []
    for i in range(1, len(dates)):
        span = (dates[i] - dates[i - 1]).days
        if span <= 1:
            continue
        for n in range(1, span):
            d = dates[i - 1] + timedelta(days=n)
            if d.weekday() < 5:
                missing.append(d.isoformat())
    return missing


def _check_history() -> Dict[str, Any]:
    files = sorted(glob.glob(os.path.join(HISTORY_DIR, "20*.json")))
    if not files:
        return {"trail": "history", "ok": False, "reason": "history 스냅샷 0개"}

    dates: List[date] = []
    for f in files:
        try:
            dates.append(date.fromisoformat(os.path.basename(f)[:10]))
        except ValueError:
            continue
    dates.sort()

    gaps = _business_day_gaps(dates)

    # 최신 스냅샷 parseable + 신선도 + 핵심 키 존재 (품질)
    latest = files[-1]
    parse_ok, missing_keys, age_h = True, [], None
    try:
        with open(latest, "r", encoding="utf-8") as fh:
            snap = json.load(fh)
        for k in ("recommendations", "postmortem"):
            if k not in snap:
                missing_keys.append(k)
        recs = snap.get("recommendations") or []
        # 결정시점 팩터 벡터 완전성 — recs 중 최대 필드 수 (slim 회귀 검출).
        # 2026-06-13 fix: 옛 recs[0] 은 종목 순서 의존(KR~114 vs US~88 vs COIN 77 변동)으로
        # 거짓 경보. 진짜 slim 회귀 = 전 종목 ~20 붕괴이므로 가장 풍부한 rec(max)가 견고한 신호.
        rec_fields = max((len(r.keys()) for r in recs), default=0)
    except Exception as e:
        parse_ok, rec_fields = False, 0
        missing_keys = [f"parse_error: {str(e)[:60]}"]

    try:
        mtime = datetime.fromtimestamp(os.path.getmtime(latest), tz=now_kst().tzinfo)
        age_h = round((now_kst() - mtime).total_seconds() / 3600, 1)
    except Exception:
        pass

    return {
        "trail": "history",
        "ok": parse_ok and not gaps and not missing_keys,
        "snapshot_count": len(dates),
        "range": f"{dates[0]}~{dates[-1]}" if dates else None,
        "business_day_gaps": gaps,
        "latest_parseable": parse_ok,
        "latest_missing_keys": missing_keys,
        "latest_rec_field_count": rec_fields,
        "latest_age_hours": age_h,
    }


def _read_baseline() -> Dict[str, Any]:
    try:
        with open(_BASELINE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _gate_progress() -> List[Dict[str, Any]]:
    """shadow 신호별 N=252 IC 게이트 진행률 (누적 거래일 = 고유 날짜 수).

    "1년 대기 중 데이터 잘 쌓이는지" 가시화 — PM 진행률 바. 누적 거래일/252 + 잔여.
    """
    out: List[Dict[str, Any]] = []
    for rel, date_key in _SHADOW_GATE_TRAILS:
        path = _p(rel)
        dates = set()
        last_date = None
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue
                    raw = obj.get(date_key)
                    if isinstance(raw, str) and len(raw) >= 10:
                        d = raw[:10]
                        dates.add(d)
                        last_date = d if last_date is None or d > last_date else last_date
        n_days = len(dates)
        out.append({
            "signal": rel.replace("metadata/", "").replace(".jsonl", ""),
            "n_trading_days": n_days,
            "gate_n": _GATE_N,
            "pct_to_gate": round(100.0 * n_days / _GATE_N, 1),
            "remaining_days": max(0, _GATE_N - n_days),
            "last_date": last_date,
        })
    return out


def _jsonl_count_and_last_ts(path: str, ts_key: Optional[str]) -> Dict[str, Any]:
    count, last_ts, parse_fail = 0, None, 0
    last_obj = None
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            count += 1
            try:
                last_obj = json.loads(line)
            except Exception:
                parse_fail += 1
    if last_obj and ts_key:
        last_ts = last_obj.get(ts_key)
    return {"count": count, "last_ts": last_ts, "parse_fail": parse_fail}


def _check_trail(rel: str, kind: str, ts_key: Optional[str],
                 baseline: Dict[str, Any]) -> Dict[str, Any]:
    path = _p(rel)
    out: Dict[str, Any] = {"trail": rel, "ok": True, "issues": []}

    if not os.path.exists(path):
        return {"trail": rel, "ok": False, "issues": ["파일 부재"], "size": 0}

    # growth: append-only trail 은 이전 baseline 보다 줄면 손실
    prev = (baseline.get(rel) or {}).get("size")

    try:
        if kind == "jsonl":
            info = _jsonl_count_and_last_ts(path, ts_key)
            size = info["count"]
            out["last_ts"] = info["last_ts"]
            if info["parse_fail"]:
                out["ok"] = False
                out["issues"].append(f"파싱불가 라인 {info['parse_fail']}건")
        else:  # json
            with open(path, "r", encoding="utf-8") as f:
                obj = json.load(f)
            size = len(obj) if isinstance(obj, (list, dict)) else 1
    except Exception as e:
        return {"trail": rel, "ok": False, "issues": [f"parse_error: {str(e)[:60]}"], "size": 0}

    out["size"] = size
    if prev is not None and size < prev:
        out["ok"] = False
        out["issues"].append(f"축소 손실 의심: {prev} -> {size}")

    # 신선도 (mtime 기준 — CI fresh checkout 영향받으나 로컬/append 트레일은 유효 참고치)
    try:
        mtime = datetime.fromtimestamp(os.path.getmtime(path), tz=now_kst().tzinfo)
        out["age_hours"] = round((now_kst() - mtime).total_seconds() / 3600, 1)
    except Exception:
        out["age_hours"] = None

    return out


def audit() -> Dict[str, Any]:
    """전체 trail 무결성 감사. status PASS/WARNING/FAIL + per-trail 상세 반환."""
    baseline = _read_baseline()
    hist = _check_history()
    trails = [_check_trail(rel, kind, ts, baseline) for rel, kind, ts in _TRAILS]

    # severity 판정
    severity = "PASS"
    findings: List[str] = []

    if not hist["ok"]:
        if hist.get("business_day_gaps"):
            severity = "WARNING" if severity == "PASS" else severity
            findings.append(f"history 영업일 gap {len(hist['business_day_gaps'])}건: "
                            f"{hist['business_day_gaps'][-5:]}")
        if not hist.get("latest_parseable"):
            severity = "FAIL"
            findings.append("history 최신 스냅샷 파싱불가 (손상/잘린쓰기)")
        if hist.get("latest_missing_keys"):
            severity = "WARNING" if severity == "PASS" else severity
            findings.append(f"history 최신 누락 키: {hist['latest_missing_keys']}")

    for t in trails:
        if not t["ok"]:
            # 부재·파싱불가·축소 = FAIL, 그 외 = WARNING
            crit = any("부재" in i or "parse" in i or "축소" in i or "파싱" in i
                       for i in t.get("issues", []))
            severity = "FAIL" if crit else ("WARNING" if severity == "PASS" else severity)
            findings.append(f"{t['trail']}: {', '.join(t.get('issues', []))}")

    return {
        "ts_kst": now_kst().isoformat(),
        "severity": severity,
        "findings": findings,
        "history": hist,
        "trails": trails,
        "gate_progress": _gate_progress(),
    }


def update_baseline(result: Dict[str, Any]) -> None:
    """이번 감사의 trail size 를 다음 growth 비교 baseline 으로 갱신.

    FAIL 이 아닐 때만 갱신 (손실 상태를 baseline 으로 굳히지 않음)."""
    if result.get("severity") == "FAIL":
        return
    baseline = {}
    for t in result.get("trails", []):
        if t.get("ok") and "size" in t:
            baseline[t["trail"]] = {"size": t["size"]}
    try:
        os.makedirs(META_DIR, exist_ok=True)
        tmp = _BASELINE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(baseline, f, ensure_ascii=False, indent=2)
        os.replace(tmp, _BASELINE_PATH)
    except Exception:
        pass


def run_and_log() -> Dict[str, Any]:
    """감사 실행 → metadata/trail_integrity.jsonl append → baseline 갱신 → 결과 반환."""
    result = audit()
    log_path = os.path.join(META_DIR, "trail_integrity.jsonl")
    try:
        os.makedirs(META_DIR, exist_ok=True)
        # 슬림 엔트리만 적재 (per-trail size + severity + findings)
        entry = {
            "ts_kst": result["ts_kst"],
            "severity": result["severity"],
            "findings": result["findings"],
            "history_snapshots": result["history"].get("snapshot_count"),
            "history_gaps": len(result["history"].get("business_day_gaps") or []),
            "trail_sizes": {t["trail"]: t.get("size") for t in result["trails"]},
            "gate_progress": {g["signal"]: g["n_trading_days"] for g in result.get("gate_progress", [])},
        }
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass
    update_baseline(result)
    return result


if __name__ == "__main__":
    import sys
    r = run_and_log()
    print(f"[trail_integrity] {r['severity']}")
    h = r["history"]
    print(f"  history: {h.get('snapshot_count')}일 {h.get('range')} "
          f"gap={len(h.get('business_day_gaps') or [])} "
          f"필드={h.get('latest_rec_field_count')} age={h.get('latest_age_hours')}h")
    for t in r["trails"]:
        flag = "OK " if t["ok"] else "!! "
        print(f"  {flag}{t['trail']}: size={t.get('size')} age={t.get('age_hours')}h "
              f"{t.get('issues') or ''}")
    print("  N=252 게이트 진행률 (shadow 누적 거래일):")
    for g in r.get("gate_progress", []):
        print(f"    {g['signal']:32} {g['n_trading_days']:>4}/{g['gate_n']}일 "
              f"({g['pct_to_gate']}%) 잔여 {g['remaining_days']}일  last={g['last_date']}")
    if r["findings"]:
        print("  findings:")
        for fnd in r["findings"]:
            print(f"    - {fnd}")
    sys.exit(0 if r["severity"] != "FAIL" else 1)
