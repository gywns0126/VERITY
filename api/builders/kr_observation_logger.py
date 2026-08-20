"""kr_observation_logger — KR 종목 cross-section 관측 신호 raw 적재 (v0, RULE 7 관측 only).

2026-06-21 신설. audit(2026-06-21) 결과 공개 터미널용으로 전종목 수집된 4개 신호(내부자·수급·희석이력·
총수일가 지분)를 엔진(brain score / observation trail) 어디서도 미사용 확인 — 엔진 insider=Finnhub(US),
flow=market_flow(별개), ownership=DART major_shareholders(FTC cross-check만), forensics=red_flags 미wire.

🚨 v0 = **점수·방향·조합식 0, raw 시점-페어 적재만** (crowding_observation_spec_v0 패턴). 검증 게이트 forward
   IC 검증용 trail 을 *지금부터* 누적 시작. v1(방향 환산 + 점수 사전등록) = Perplexity 방법론 + PM 승인 후
   한 번에 하나씩. brain score·decision 무간섭(가중 0). RULE 7 정합.

입력(공개 빌더 산출, 이미 일별 생성): insider_trades.json / stock_flow_5d.json / disclosure_forensics.json /
   stock_report_public.json(ownership.family_pct). commodity_exposure 제외(산업 멤버십=정적, 종목 시변 신호 아님).
출력: data/observations/kr_cross_section_observations.jsonl (주 1회 Fri, date-dedupe, append-only).

🚨 2026-08-20 두 건 추가:
① insider_net_365d/buy/sell 병기 — 기존 insider_net 은 elestock 이 주는 약 2년 롤링 누적이라
   '최근 내부자 매수'가 아니라 '누적 보유 수준'을 잰다. 기존 컬럼은 trail 연속성 때문에 그대로
   두고 창 컬럼을 나란히 시작한다(창 정의를 나중에 바꾸면 앞뒤가 섞인다, RULE 13 ⑤).
   🚨 같은 날 자기 정정 — 최초 판본은 여기에 "종목별로 사실상 상수다(000660 8주 2.2%)" 라고
   적었다. **틀렸다.** 000660 하나로 횡단면을 말한 것이고(RULE 13), 8주 trail 전수 재측정 결과:
     · 값 변경 종목 = 669 / 1,364 = **49.0%** (주간 9.6~24.2%)
     · 변경 종목의 상대 변동폭 중앙값 **14.3%** · 75%분위 70.9% · 90%분위 182%
     · 🚨 000660 의 2.2% 는 변경 종목 중 **하위 26% 분위** = 작은 쪽 사례였다
   정확한 서술 = "상수" 가 아니라 **높은 지속성**이다 — 주간 순위상관 ρ 0.96~0.99,
   8주 백분위 순위 이동 중앙값 0.79%p(36.7% 는 0.5%p 미만). 값은 움직이나 순위는 잘 안 바뀌므로
   **주 단위로 표본을 늘려도 독립 정보는 그만큼 늘지 않는다.** 이게 창 컬럼을 지금 시작한 이유다.
③ 🚨 컬럼별 주기 정합 (PM 승인 2026-08-20, 옵션 B) — 8주 trail 전수 측정 결과 컬럼마다
   시변 성격이 완전히 달랐다. 전부를 주 1회로 적는 것은 한쪽은 과표집, 한쪽은 낭비였다.

     컬럼              주간 순위상관 ρ   주간 값변경률   판정
     foreign_net            0.240          79.5%     진짜 시변 → 주간 유지
     inst_net               0.273          76.0%     진짜 시변 → 주간 유지
     insider_*              0.986          13.2%     매우 지속적 → 28일
     dilution_count         0.933           5.4%     매우 지속적 → 28일
     family_pct             1.0000          0.0%     🚨 8주간 변경 0 → 시계열 제외

   family_pct 는 공정위 대기업집단 지정 지분이라 **연 1회 갱신**이다. 주 1회 적재는 같은 값을
   8번 복사한 것이었다(정보 증가 0). 현재값은 stock_report_public.json 의 ownership.family_pct
   에 매일 발행되므로 참조처가 이미 있다 — 여기서는 뺀다.
   🚨 주기 판정은 달력이 아니라 **trail 자체**로 한다(`_last_sampled`): 마지막 적재로부터
   28일 경과 또는 **한 번도 적재 안 된 컬럼**이면 적재. 달력 규칙(첫 금요일 등)은 그 주 run 이
   죽으면 한 달을 통째로 건너뛴다 — 2026-08-14 결손이 실제로 그 형태였다.
   🚨 주기 경계는 행마다 `cadence` 필드로 신고한다. **키 부재 = 그 주 미표집**이고
   **null = 표집했으나 입력 stale** 이다. 둘을 섞어 읽으면 안 된다.

② 입력 신선도 자기신고 — 이 step 은 같은 run 의 빌더 3종 산출을 읽는다. 분석이 죽어 그
   빌더가 skip 되면 '어제 값'이 '오늘 date'로 적재된다(as-of 거짓 = forward IC trail 오염).
   → _meta.generated_at 이 오늘이 아닌 입력은 컬럼을 null 로 적고 stale_inputs 로 신고한다.
   실측 사고: 2026-08-14(금) daily_analysis_full 3연속 실패 → 그 주 관측 행 영구 결손.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

KST = timezone(timedelta(hours=9))
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
INSIDER_PATH = os.path.join(_ROOT, "data", "insider_trades.json")
FLOW_PATH = os.path.join(_ROOT, "data", "stock_flow_5d.json")
FORENSICS_PATH = os.path.join(_ROOT, "data", "disclosure_forensics.json")
REPORT_PATH = os.path.join(_ROOT, "data", "stock_report_public.json")
OUT_DIR = os.path.join(_ROOT, "data", "observations")
OUT_PATH = os.path.join(OUT_DIR, "kr_cross_section_observations.jsonl")
META_PATH = os.path.join(OUT_DIR, "kr_cross_section_observations_meta.json")
DILUTIVE = ["유상증자", "전환사채(CB)", "신주인수권부사채(BW)"]

# 컬럼 그룹 = (소스 doc, 주기 일수, 컬럼들). 주기 0 = 매 run(주간).
#   근거 = docstring ③ 의 8주 실측. 임계 28일 = "월 1회" 를 달력 없이 표현한 값.
CADENCE_DAYS = 28
GROUPS = {
    "flow":     {"src": "flow",      "days": 0,
                 "cols": ["foreign_net", "inst_net"]},
    "insider":  {"src": "insider",   "days": CADENCE_DAYS,
                 "cols": ["insider_net", "insider_buy_n", "insider_sell_n",
                          "insider_net_365d", "insider_buy_n_365d", "insider_sell_n_365d"]},
    "dilution": {"src": "forensics", "days": CADENCE_DAYS,
                 "cols": ["dilution_count"]},
}
# 2026-08-20 시계열에서 제외(PM 승인 B). 현재값 참조처 = stock_report_public.json ownership.family_pct
RETIRED_COLS = {"family_pct": "공정위 연 1회 갱신 — 8주 변경 0%. stock_report_public.ownership.family_pct 참조"}


def _now_kst() -> datetime:
    return datetime.now(KST)


def _load_json(path: str, default: Any) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def _asof(doc) -> str:
    """입력 산출물의 _meta.generated_at → 'YYYY-MM-DD'. 부재 시 '' (= stale 취급)."""
    try:
        return str(((doc or {}).get("_meta") or {}).get("generated_at") or "")[:10]
    except AttributeError:
        return ""


def _last_sampled() -> Dict[str, str]:
    """trail 1회 스캔 → {컬럼: 그 컬럼이 마지막으로 실린 날짜}. 미적재 컬럼은 키 자체가 없다.

    🚨 '실렸다' 의 기준은 **키 존재**다(값 null 포함). null 은 그 주에 표집은 했으나 입력이
    stale 이었다는 뜻이라 주기 시계는 정상적으로 돌아야 한다.
    """
    out: Dict[str, str] = {}
    if not os.path.exists(OUT_PATH):
        return out
    try:
        with open(OUT_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                d = str(r.get("date") or "")
                if not d:
                    continue
                for k in r:
                    if k in ("date", "ticker", "cadence", "stale_inputs"):
                        continue
                    if d > out.get(k, ""):
                        out[k] = d
    except OSError:
        pass
    return out


def _due_groups(date_str: str) -> List[str]:
    """오늘 표집할 그룹. days=0 은 항상 · 그 외는 28일 경과 또는 미적재 컬럼 보유 시.

    🚨 '미적재 컬럼 보유' 가 신규 컬럼의 부트스트랩이다 — 새 컬럼은 첫 관측을 먼저 남기고
    거기서부터 주기 시계가 돈다. 없으면 신설 컬럼이 최대 28일 동안 비어 있게 된다.
    """
    last = _last_sampled()
    today = datetime.strptime(date_str, "%Y-%m-%d").date()
    due = []
    for name, g in GROUPS.items():
        if g["days"] <= 0:
            due.append(name)
            continue
        if any(c not in last for c in g["cols"]):
            due.append(name)
            continue
        newest = max(last[c] for c in g["cols"])
        try:
            age = (today - datetime.strptime(newest, "%Y-%m-%d").date()).days
        except ValueError:
            age = g["days"]
        if age >= g["days"]:
            due.append(name)
    return sorted(due)


def _already_logged(date_str: str) -> bool:
    """date-dedupe — 같은 날짜 entry 가 이미 있으면 재적재 skip (idempotent)."""
    if not os.path.exists(OUT_PATH):
        return False
    try:
        with open(OUT_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if f'"date": "{date_str}"' in line or f'"date":"{date_str}"' in line:
                    return True
    except OSError:
        pass
    return False


# 🚨 2026-06-21~2026-08-07 8주 trail 전수 실측(주기 결정 근거). 임의 추정치 아님 —
#    재현 = 인접 주 쌍의 종목 순위 스피어만 ρ 평균 + 값이 바뀐 종목 비율 평균.
COLUMN_NATURE = {
    "foreign_net":    {"group": "flow",     "weekly_rank_rho": 0.240, "weekly_change_rate": 0.795, "n": 1540},
    "inst_net":       {"group": "flow",     "weekly_rank_rho": 0.273, "weekly_change_rate": 0.760, "n": 1540},
    "insider_net":    {"group": "insider",  "weekly_rank_rho": 0.986, "weekly_change_rate": 0.132, "n": 1460},
    "dilution_count": {"group": "dilution", "weekly_rank_rho": 0.933, "weekly_change_rate": 0.054, "n": 1946},
    "family_pct":     {"group": "(제외)",   "weekly_rank_rho": 1.000, "weekly_change_rate": 0.000, "n": 321},
}
CADENCE_CHANGE_DATE = "2026-08-21"


def _write_meta(date_str: str, due: List[str], stale: List[str]) -> None:
    """산출물이 자기 입으로 말하게 한다(RULE 12 ②) — 주기 정책·컬럼 성격·경계 신고.

    jsonl 은 _meta 를 실을 자리가 없어 사이드카로 낸다. 소비자는 행의 `cadence` 로 그 주
    표집 범위를, 여기서 왜 그 주기인지를 읽는다.
    """
    doc = {
        "_meta": {
            "generated_at": _now_kst().isoformat(),
            "for_date": date_str,
            "trail": os.path.basename(OUT_PATH),
            "note": "관측 only · 점수·방향·조합식 0(RULE 7). 이 파일은 trail 의 읽는 법이다.",
        },
        "🚨 등록 상태": (
            "이 trail 의 종전 근거였던 표본 수 게이트는 §7-1(PM 2026-08-15)로 폐기됐다. "
            "대체 관문 §7-3(검출하한 신고)은 PM 승인 대기 → 현재 유효한 등록 근거 없음. "
            "표본을 더 쌓는 것 자체는 결론이 아니다."
        ),
        "cadence_policy": {
            "rule": "달력이 아니라 trail 자체로 판정 — 마지막 적재 후 N일 경과 또는 미적재 컬럼 보유",
            "why_not_calendar": "달력 규칙은 그 주 run 이 죽으면 한 달을 건너뛴다(2026-08-14 결손이 그 형태)",
            "groups": {g: {"days": v["days"], "cols": v["cols"]} for g, v in GROUPS.items()},
        },
        "key_semantics": {
            "키 부재": "미표집 — 그 주 표집 주기가 아니었다",
            "null": "표집했으나 입력 산출물이 stale(같은 run 의 상류 빌더 skip)",
            "stale_inputs": "null 이 난 소스 이름. 정상 주엔 키 자체가 없다",
        },
        "column_nature_measured_2026_06_21__2026_08_07": COLUMN_NATURE,
        "cadence_change": {
            "date": CADENCE_CHANGE_DATE,
            "before": "전 컬럼 주 1회",
            "after": "flow 주간 · insider/dilution 28일 · family_pct 시계열 제외",
            "why": "컬럼별 시변 성격이 완전히 달랐다 — 한쪽은 과표집, 한쪽은 같은 값 복사",
            "🚨 read_across_boundary": (
                "이 날짜 앞뒤로 표집 빈도가 다르다. 행 수를 관측 수로 세면 앞뒤가 섞인다 — "
                "반드시 행의 cadence 필드로 잘라서 볼 것(RULE 13 ⑤)"
            ),
            "pm_approval": "2026-08-20 옵션 B",
        },
        "retired_columns": RETIRED_COLS,
        "last_run": {"due_groups": due, "stale_inputs": stale},
    }
    try:
        os.makedirs(OUT_DIR, exist_ok=True)
        with open(META_PATH, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=1)
    except OSError as e:  # noqa: BLE001
        print(f"[kr_obs] meta 기록 실패(적재는 완료): {e!r}", file=sys.stderr)


def main() -> int:
    ok = False
    try:
        now = _now_kst()
        # 주 1회(금요일)만 적재 — 신호가 느린 이벤트(공시)라 주간 스냅샷 충분 + trail 비대 회피.
        # daily cron 에 배선해도 금요일 외엔 self-skip (crowding 주간 cron 패턴 정합).
        if now.weekday() != 4 and os.environ.get("KR_OBS_FORCE") != "1":
            print(f"[kr_obs] 금요일 아님(weekday={now.weekday()}) — skip (주간 적재)", file=sys.stderr)
            return 0
        date_str = now.date().strftime("%Y-%m-%d")
        if _already_logged(date_str):
            print(f"[kr_obs] {date_str} 이미 적재됨 — skip (date-dedupe)", file=sys.stderr)
            ok = True
            return 0

        # 오늘 표집할 그룹 결정(docstring ③) — 주기 밖 그룹은 키 자체를 안 만든다
        due = _due_groups(date_str)
        if not due:
            print(f"[kr_obs] {date_str} 표집 주기 도래 그룹 0 — skip", file=sys.stderr)
            ok = True
            return 0
        srcs = {GROUPS[g]["src"] for g in due}

        # 입력 로드 + 신선도 자기신고(docstring ②) — 오늘 쓰는 소스만
        docs = {}
        if "insider" in srcs:
            docs["insider"] = _load_json(INSIDER_PATH, {})
        if "flow" in srcs:
            docs["flow"] = _load_json(FLOW_PATH, {})
        if "forensics" in srcs:
            docs["forensics"] = _load_json(FORENSICS_PATH, {})
        stale = sorted(n for n, d in docs.items() if _asof(d) != date_str)
        if len(stale) == len(docs):
            # 전부 어제 것 = 이 run 에서 빌더가 하나도 안 돌았다. 빈 행을 남기는 대신 skip
            #   (같은 날 뒤 run 이 date-dedupe 에 막히지 않고 제대로 적재하도록).
            print(f"[kr_obs] 입력 {len(docs)}종 전부 stale(asof != {date_str}) — 적재 skip", file=sys.stderr)
            return 0
        if stale:
            print(f"[kr_obs] stale 입력 {stale} — 해당 컬럼 null 적재(as-of 거짓 방지)", file=sys.stderr)

        def _ok(name: str):
            return name not in stale

        insider = {str(s.get("ticker")): s for s in (docs.get("insider", {}).get("stocks") or [])}
        flow = (docs.get("flow", {}).get("flows") or {})
        forensics = {str(s.get("ticker")): s for s in (docs.get("forensics", {}).get("stocks") or [])}

        # 신호 보유 종목 합집합 — 오늘 표집 + 신선한 소스만(전 컬럼 null 인 유령 행 방지)
        idx = {"insider": insider, "flow": flow, "dilution": forensics}
        tickers = set()
        for g in due:
            if _ok(GROUPS[g]["src"]):
                tickers |= set(idx[g])
        if not tickers:
            print("[kr_obs] 신호 보유 종목 0 — skip", file=sys.stderr)
            return 0

        def _dil(tk: str):
            if not _ok("forensics"):
                return None   # 표집은 했으나 입력 stale — 키 부재(미표집)와 구분된다
            c = (forensics.get(tk) or {}).get("counts") or {}
            return sum(int(c.get(k) or 0) for k in DILUTIVE)

        def _flow_last(tk: str):
            if not _ok("flow"):
                return {}
            rows = flow.get(tk) or []
            return rows[-1] if rows else {}

        ins_ok = _ok("insider")
        rows: List[Dict[str, Any]] = []
        for tk in sorted(tickers):
            ins = insider.get(tk) or {}
            row: Dict[str, Any] = {"date": date_str, "ticker": tk, "cadence": due}
            if "flow" in due:
                fl = _flow_last(tk)
                # 수급(네이버) — 최근일 외국인/기관 순매매(주). 주간(ρ 0.24 = 진짜 시변)
                row["foreign_net"] = fl.get("foreign_net")
                row["inst_net"] = fl.get("inst_net")
            if "insider" in due:
                # 내부자(DART elestock) — elestock 이 주는 약 2년 롤링 누적. 🚨 창 아님.
                #   2026-06-21~ trail 연속성 때문에 정의 유지. 28일 주기(ρ 0.986)
                row["insider_net"] = ins.get("net_change") if ins_ok else None
                row["insider_buy_n"] = ins.get("buy_n") if ins_ok else None
                row["insider_sell_n"] = ins.get("sell_n") if ins_ok else None
                # 내부자 최근 365일 창 — 2026-08-20 신설(그 이전 행은 키 자체가 없음)
                row["insider_net_365d"] = ins.get("net_change_365d") if ins_ok else None
                row["insider_buy_n_365d"] = ins.get("buy_n_365d") if ins_ok else None
                row["insider_sell_n_365d"] = ins.get("sell_n_365d") if ins_ok else None
            if "dilution" in due:
                # 희석이력(DART) — 유증/CB/BW 누적 빈도. 28일 주기(ρ 0.933)
                row["dilution_count"] = _dil(tk)
            if stale:
                row["stale_inputs"] = stale   # 정상 주엔 키 자체가 없다(파일 비대 회피)
            rows.append(row)

        os.makedirs(OUT_DIR, exist_ok=True)
        with open(OUT_PATH, "a", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        _write_meta(date_str, due, stale)
        print(f"[kr_obs] logged=True · {date_str} · {len(rows)}종목 · 표집 그룹 {due} "
              f"(관측 only, 점수 0) -> {os.path.relpath(OUT_PATH, _ROOT)}", file=sys.stderr)
        ok = True
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[kr_obs] FAILED: {e!r}", file=sys.stderr)
        return 1
    finally:
        if not ok:
            print("[kr_obs] logged=False", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
