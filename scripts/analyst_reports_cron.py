#!/usr/bin/env python3
"""증권사 리포트 수집 + AI 요약 — daily_analysis_full 에서 분리한 전용 러너.

🚨 왜 분리했나 (2026-08-14 실측)
  daily_analysis_full 이 4회 연속 실패했다(fail 2 / cancel 2). 원인은 run 117분 vs
  런타임 워치독 110분 초과이고, **그 117분 중 51.4분이 STEP 5.87 한 구간**이었다
  (구간 프로파일: 5.87 리포트 51.4분 / STEP 3 기술적분석 33.5분 / 5.75 NAV 14.2분).

  5.87 은 두 일을 한 덩어리로 하고 있었다.
    ① 네이버 리포트 메타 수집 + PDF → Gemini 요약 → 종목별 집계   ← 51분, 느림
    ② 집계 결과를 candidates 에 attach                          ← 밀리초
  Brain 이 쓰는 것은 ②의 산물(`analyst_report_summary`)뿐이고, ①은 이미
  `data/report_summaries.json` 에 원자적으로 저장된다. 즉 ①을 앞선 시각의 별도 cron 으로
  옮기면 본 파이프라인은 파일을 읽어 attach 만 하면 된다. 산식·입력 무변경, 시점만 이동한다.

  효과: 본 파이프라인 117분 → 약 66분 (워치독 110분 대비 여유 44분).

우선순위 티커: main.py 는 candidates + portfolio.recommendations 의 KR 종목을 넘겼다.
  단독 실행에서는 같은 정보를 디스크에서 읽는다 —
  `data/universe_candidates.json`(운영 후보) + `data/recommendations.json`(운영 풀).
  순서·dedupe 규칙은 main.py 원본과 동일하게 유지한다(선정 로직 변경 아님).

전량 실패 시 exit 1 — 건수 0인데 성공 종료하면 신선도 보드가 초록불로 통과해 버린다
([[feedback_silent_total_failure_guard]]).
"""
from __future__ import annotations

import json
import os
import sys
import time
from typing import Any, Dict, List

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from api.analyzers.report_summarizer import run_report_summarizer  # noqa: E402
from api.collectors.ReportScout import scout_reports  # noqa: E402
from api.config import VERITY_MODE, now_kst  # noqa: E402

RECOMMENDATIONS = os.path.join(_ROOT, "data", "recommendations.json")

# universe_candidates 는 평일 15:30 KST cron 산출물이고 이 러너는 그보다 앞서 돈다.
# 즉 여기서 읽는 스냅샷은 통상 '전일자' 다 — 우선순위 힌트 용도라 그것으로 충분하다.
# 없으면 recommendations(운영 풀)만으로 진행한다. abort 하지 않는다.
_UNIVERSE_MAX_STALE_H = 96

# 러너 IP 간헐 드롭 대비 — 총 3회, 30s/60s 백오프. 51분 작업 대비 무시할 비용이다.
_SCOUT_ATTEMPTS = 3
_SCOUT_BACKOFF_S = 30


def _kr6(v: Any) -> str:
    """KR 6자리 정규화. 비-KR·비숫자는 빈 문자열."""
    s = str(v or "").split(".")[0].strip()
    return s.zfill(6) if s.isdigit() and len(s) <= 6 else ""


def _priority_tickers() -> List[str]:
    """운영 후보 + 운영 풀의 KR ticker6 (순서 유지 dedupe) — main.py 규칙과 동일."""
    out: List[str] = []

    try:
        from api.utils.universe_candidates import load_universe_candidates
        snap = load_universe_candidates(max_stale_hours=_UNIVERSE_MAX_STALE_H)
        for s in (snap or {}).get("candidates") or []:
            if s.get("currency") == "USD":
                continue
            t = _kr6(s.get("ticker"))
            if t:
                out.append(t)
        print(f"  우선순위 · universe_candidates 에서 {len(out)}개")
    except Exception as e:  # noqa: BLE001
        print(f"  우선순위 · universe_candidates 로드 실패 (무해, 계속): {e}")

    before = len(out)
    try:
        with open(RECOMMENDATIONS, encoding="utf-8") as f:
            recs = json.load(f)
        rows = recs if isinstance(recs, list) else (recs.get("recommendations") or [])
        for r in rows:
            if r.get("currency") == "USD":
                continue
            t = _kr6(r.get("ticker"))
            if t:
                out.append(t)
        print(f"  우선순위 · recommendations 에서 {len(out) - before}개")
    except Exception as e:  # noqa: BLE001
        print(f"  우선순위 · recommendations 로드 실패 (무해, 계속): {e}")

    return list(dict.fromkeys(out))


def _collect_with_retry(attempts: int = _SCOUT_ATTEMPTS):
    """리포트 메타 수집 — 러너 IP 드롭 대비 백오프 재시도.

    🚨 정정 (2026-08-14): 이 재시도를 처음 넣을 때 근거로 적은 "러너 IP 차단" 은 오진이었다.
      N=1 실패(run 31808986654)의 진짜 원인은 워크플로에 VERITY_MODE 를 안 넘겨
      config 기본값 dev 로 떨어져 @mockable 이 전량 mock 을 돌린 것이다
      (로그에 [MOCK CENSUS] VERITY_MODE=dev 가 찍혀 있었다). 러너 0건 vs 로컬 162건 비교는
      내가 로컬에만 prod 를 덮어쓴 상태라 조건이 달랐다 — 대조군이 성립하지 않았다.

      그럼에도 재시도는 남긴다. 근거는 이번 사건이 아니라 이 프로젝트의 축적된 기록이다 —
      공공데이터 게이트웨이가 러너 IP 를 드롭했고, 야후 성공률이 로컬 97% vs CI 45% 였다
      ([[feedback_public_data_gateway_runner_ip_retry]] · [[feedback_ci_runner_ip_throttle_and_gate_order]]).
      외부 공개 소스에 의존하는 수집기라 간헐 실패는 실재하고, 3회 백오프는 51분 작업 대비
      무시할 비용이다. 다만 재시도가 mock 오설정 같은 **설정 결함을 가리지 않도록**
      전량실패 가드를 그대로 둔다.
    """
    meta = {}
    st = {}
    total = 0
    for i in range(1, attempts + 1):
        try:
            meta = scout_reports() or {}
        except Exception as e:  # noqa: BLE001
            print(f"  수집 시도 {i}/{attempts} 예외: {e}")
            meta = {}
        st = meta.get("stats", {}) or {}
        total = int(st.get("company_total", 0) or 0)
        print(f"  수집 시도 {i}/{attempts} · 기업 {total}건 "
              f"(네이버 {st.get('company_naver', 0)} / KIRS "
              f"{int(st.get('company_kirs_outsourcing', 0) or 0) + int(st.get('company_kirs_insourcing', 0) or 0)}) "
              f"· with_pdf {st.get('with_pdf', 0)} · 산업 {st.get('industry_total', 0)}")
        if total > 0:
            return meta, st, total
        if i < attempts:
            wait = _SCOUT_BACKOFF_S * i
            print(f"  0건 — {wait}s 후 재시도 (러너 IP 드롭 가능성)")
            time.sleep(wait)
    return meta, st, total


def main() -> int:
    print(f"[analyst_reports] 시작 {now_kst().isoformat(timespec='seconds')}")

    # ── ① 리포트 메타 수집 (네이버·KIRS 공개) ──
    meta, st, company_total = _collect_with_retry()

    # ── ② 요약 + 종목별 집계 ──
    pri = _priority_tickers()
    print(f"  우선순위 티커 {len(pri)}개")
    try:
        result = run_report_summarizer(priority_tickers=pri)
    except Exception as e:  # noqa: BLE001
        print(f"❌ run_report_summarizer 실패: {e}")
        return 1

    status = result.get("status")
    ss: Dict[str, Any] = result.get("stats", {}) or {}
    aggregated = int(ss.get("tickers_aggregated", 0) or 0)
    print(f"  요약 · 신규 {ss.get('new_summaries_this_run', 0)} "
          f"(skip {ss.get('skipped_this_run', 0)}) "
          f"| 종목 집계 {aggregated} "
          f"| 누적 {ss.get('total_processed_lifetime', 0)}")

    # 🚨 전량 실패 판정 — 수집도 0이고 집계도 0이면 산출물이 없는 것이다.
    #   '성공 종료 + mtime 갱신' 은 신선도 보드를 초록불로 통과시켜 없는 것보다 나쁘다.
    #   단 dev/staging 은 @mockable 이 0을 돌려주는 게 정상이라 가드 대상이 아니다
    #   (여기서 exit 1 을 내면 로컬 검증마다 거짓 경보가 난다).
    #
    # 🚨 2026-08-14 N=1 fix — 모드 판정은 반드시 api.config 를 거친다.
    #   옛: os.environ.get("VERITY_MODE") → 미설정 시 None. mock 레이어는 같은 미설정을
    #       config 기본값 "dev" 로 읽어 mock 을 돌리는데, 이 가드만 None 을 prod 취급해
    #       "mock 이 0을 돌려줬다 → 전량 실패 exit 1" 이라는 거짓 경보를 냈다.
    #       같은 변수의 미설정을 두 곳이 다르게 해석한 것이 진범이다 (N=1 run 31808986654).
    #   신: config.VERITY_MODE 단일 해석 — 미설정=dev 로 양쪽이 일치한다.
    if VERITY_MODE in ("dev", "staging"):
        print(f"  (VERITY_MODE={VERITY_MODE} — mock 구간, 전량실패 가드 미적용)")
    elif status in ("no_reports", "empty_input") and aggregated == 0:
        print(f"❌ 산출물 0 (status={status}) — 전량 실패로 신고 (exit 1)")
        return 1
    elif company_total == 0 and aggregated == 0:
        print("❌ 수집 0건 + 집계 0건 — 전량 실패로 신고 (exit 1)")
        return 1

    print(f"[analyst_reports] 완료 {now_kst().isoformat(timespec='seconds')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
