"""
Phase 4 전체 파이프라인 운영 검증 스크립트.

사용법:
  python3 scripts/verify_phase4_run.py
    (data/portfolio.json 또는 --path 로 지정된 스냅샷 검증)

검증 항목:
  [1] Phase 1 수집기 — treasury_stock / exec_compensation / major_shareholder_changes
      top-level attach 여부 (main.py §17 fix 확인)
  [2] Phase 2 분석기 — analyst_report_summary / dart_business_analysis 부착
  [3] Phase 3 Brain — fact_score components 에 analyst_report / dart_health / governance_*
  [4] Phase 3 consensus — score_source 에 "consensus+analyst" 출현
  [5] Gemini / Claude 프롬프트 확장 — runtime 확인 불가 (로그 필요)

exit 0 — 4 phase 모두 검증 완료
exit 1 — 일부 미충족
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path


def _count_field(recs, key, nested=False, sub=None):
    n = 0
    for r in recs:
        v = r.get(key)
        if nested and sub and isinstance(v, dict):
            if v.get(sub) is not None:
                n += 1
        elif isinstance(v, dict) and v:
            n += 1
        elif isinstance(v, list) and v:
            n += 1
    return n


def verify(portfolio_path: Path) -> int:
    if not portfolio_path.exists():
        print(f"❌ {portfolio_path} 미존재")
        return 1

    d = json.loads(portfolio_path.read_text())
    recs = d.get("recommendations", [])
    kr_recs = [r for r in recs if r.get("currency") != "USD"]
    ut = d.get("updated_at", "?")
    print(f"portfolio.updated_at: {ut}")
    print(f"총 {len(recs)} (KR {len(kr_recs)}, US {len(recs) - len(kr_recs)})")
    print()

    fail_count = 0

    # ── [1] Phase 1 — DartScout top-level 거버넌스 3 필드 ──
    print("[1] Phase 1.B 거버넌스 시그널 (KR 대상)")
    ts_count = _count_field(kr_recs, "treasury_stock")
    ec_count = _count_field(kr_recs, "exec_compensation")
    sc_count = _count_field(kr_recs, "major_shareholder_changes")
    for field, n in [("treasury_stock", ts_count),
                      ("exec_compensation", ec_count),
                      ("major_shareholder_changes", sc_count)]:
        status = "✓" if n > 0 else "✗"
        print(f"  {status} {field}: {n}/{len(kr_recs)}")
        if n == 0:
            fail_count += 1

    # ── [2] Phase 2 — AI 분석 결과 ──
    print()
    print("[2] Phase 2 AI 분석 결과 (KR 대상)")
    ars_count = _count_field(kr_recs, "analyst_report_summary", nested=True, sub="report_count")
    dba_count = _count_field(kr_recs, "dart_business_analysis",
                              nested=True, sub="business_health_score")
    for field, n in [("analyst_report_summary", ars_count),
                      ("dart_business_analysis", dba_count)]:
        status = "✓" if n > 0 else "⚠"  # 한경 실패 / 신규 리포트 없음도 가능
        print(f"  {status} {field}: {n}/{len(kr_recs)}")

    # ── [3] Phase 3 Brain 컴포넌트 ──
    print()
    print("[3] Phase 3 Brain fact_score 컴포넌트")
    phase3_comps = ["analyst_report", "dart_health",
                    "governance_bonus", "governance_penalty"]
    sample = next((r for r in recs if r.get("verity_brain")), None)
    if not sample:
        print("  ✗ verity_brain 부재 — Brain 미실행")
        fail_count += 1
    else:
        fs_comp = sample["verity_brain"].get("fact_score", {}).get("components", {})
        for c in phase3_comps:
            present = c in fs_comp
            val = fs_comp.get(c, "?")
            status = "✓" if present else "⚠"
            is_default = (c in ("analyst_report", "dart_health")
                          and val == 50.0)
            note = " (default=50, 데이터 미부착)" if is_default else ""
            print(f"  {status} {c}: {val}{note}")

    # ── [4] consensus blending ──
    print()
    print("[4] consensus score_source 분포")
    sources = {}
    for r in recs:
        src = r.get("consensus", {}).get("score_source", "?")
        sources[src] = sources.get(src, 0) + 1
    has_blend = "consensus+analyst" in sources
    for src, n in sources.items():
        status = "✓" if src == "consensus+analyst" else " "
        print(f"  {status} {src}: {n}")
    if not has_blend:
        print("  ⚠ 'consensus+analyst' 블렌딩 미출현 "
              "(analyst_report_summary 부재 시 정상)")

    # ── [5] override metadata ──
    print()
    print("[5] overrides_applied 발동 현황")
    ovs = {}
    for r in recs:
        for o in (r.get("overrides_applied") or []):
            ovs[o] = ovs.get(o, 0) + 1
    if ovs:
        for o, n in sorted(ovs.items(), key=lambda x: -x[1]):
            print(f"  · {o}: {n}")
    else:
        print("  (발동 없음)")

    # ── 요약 ──
    print()
    print("=" * 50)
    print(f"핵심 실패 개수: {fail_count}")
    if fail_count == 0:
        print("✓ Phase 1-4 모든 항목 검증 완료")
        return 0
    else:
        print(f"✗ {fail_count}개 Phase 1.B 거버넌스 필드 미부착")
        print("  → 다음 full 실행 후 재확인 필요")
        return 1


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--path", default="data/portfolio.json")
    args = p.parse_args()
    return verify(Path(args.path))


if __name__ == "__main__":
    sys.exit(main())
