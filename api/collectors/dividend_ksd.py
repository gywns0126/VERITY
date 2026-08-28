"""
dividend_ksd — KR 배당 **기준일** 원장 (금융위/한국예탁결제원 공개 API)

왜 별도 수집기인가:
  기존 `dividend_kr.py` 원장은 **사업보고서 기준 연간 합계**이고 날짜 필드(`ex_date`)가
  `_estimate_ex_date()` 산출값 = **추정치**다. 실측(2026-08-22) — `dividends_kr.json`
  1,322행의 ex_date 가 100% 정확히 `{연도}-12-30`.

  이 수집기가 받는 KSD 원장은 **회차별(배당기준일별) 실날짜**다. 두 원장은 축이 달라서
  🚨 **같은 파일에 섞지 않는다.** 섞으면 "연간 합계" 와 "회차 금액" 이 한 칸에 들어가
  067900 단위오류와 같은 형태의 사고가 난다([[project_dividend_ledger_unit_error_2026_08_15]]).

🚨 **`ex_date`(배당락일) 를 이 파일은 절대 쓰지 않는다.**
  KSD 가 주는 건 `dvdnBasDt` = **배당기준일**이고 배당락일이 아니다. 둘은 다른 날짜이고,
  기준일에서 락일을 파생하려면 거래일 달력 + 결제주기 규칙이 필요한데 그 규칙은 **미검증**이다.
  검증 전까지 이 원장은 `record_date` 만 신고한다. 표기도 "배당기준일" 로만 쓴다.

실측 근거 (2026-08-22, basDt=20260821 전량 71,669행):
  · 배당기준일 빈값 **0건** · 지급일 보유 58.6% · KR7 티커 5,453(보통주 4,421)
  · 우리 KR 리포트 1,790 중 **1,781(99.5%)** 커버
  · 🚨 FY2025 결산배당의 실제 기준일이 **29.4% 는 이듬해(2026-01~04)로 이동**했다.
    (2025-12 751건 / 2026-03 218 · 2026-02 52 · 2026-04 39 · 2026-01 5)
    우리 추정 `2025-12-30` 과 **정확히 일치한 건은 0건**, 90일 이상 오차 187건(17.5%).
    배당절차 개선으로 기준일이 배당액 결정 이후로 이동 중인 그 현상이다.

산출: data/dividends_kr_ksd.json
  { "_meta": {...}, "005930": [ {record_date, payment_date, amount_per_share, ...}, ... ] }

API: apis.data.go.kr/1160100/GetStocDiviInfoService_V2/getDiviInfo_V2
  · 키 = PUBLIC_DATA_API_KEY (이 서비스 활용신청 2026-08-22 완료)
  · 🚨 `basDt` 는 **특정 적재일 하나만 유효**하다. 20260821 은 71,669행인데 20260822·
    20260820·20260819·20260815·20260808·20260801 은 전부 0. 날짜 고정 금지 —
    `discover_bas_dt()` 로 최신 적재일을 찾는다.
  · numOfRows 10,000 허용 → 전량 8 호출.
"""
from __future__ import annotations

import json
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

from api.config import DATA_DIR, PUBLIC_DATA_API_KEY, now_kst

_LEDGER_PATH = os.path.join(DATA_DIR, "dividends_kr_ksd.json")
_ENDPOINT = (
    "https://apis.data.go.kr/1160100/GetStocDiviInfoService_V2/getDiviInfo_V2"
)
_PAGE_SIZE = 10000
_MAX_PAGES = 30          # 71,669행 기준 8 페이지. 상한은 폭주 방지용 여유.

# 🚨 타임아웃은 **바깥 예산 안에** 들어와야 한다 (2026-08-23 실사고).
#   첫 판본은 탐색·페이징 모두 90s 였다 — 최악 (15탐색 + 8페이징) × 90s = **34.5분** 인데
#   워크플로 `timeout-minutes` 는 **15분**이었다. 개별 호출은 각자 넉넉한데 **합이 넘는다.**
#   결과: 8/23 15:15 정기 run 이 탐색 구간에서 13분 40초를 태우다 **cancelled**(N=2 실패).
#   같은 형태를 같은 날 `vercel-api/api/admin.py` 에서도 고쳤다(내부 합 27s vs maxDuration 15s).
#   → 탐색은 `numOfRows=1` 짜리 가벼운 호출이라 짧게, 전량 페이징만 넉넉히.
_TIMEOUT = 60            # 전량 페이징(10,000행/호출)
_DISCOVER_TIMEOUT = 12   # 적재일 탐색 — 1행짜리 프로브라 길 이유가 없다
_DISCOVER_LOOKBACK = 14  # 최신 적재일 역순 탐색 창(일)
_DISCOVER_ATTEMPTS = 3   # 연결 장애 시 같은 날짜를 재시도한 뒤 과거 날짜 탐색을 중단
_DISCOVER_BACKOFF_SEC = (1, 3)
# 수집 전체 예산 — 넘으면 다음 스케줄에 맡긴다(job 이 잘려 로그도 안 남는 것보다 낫다).
_BUDGET_SEC = int(os.environ.get("KSD_BUDGET_SEC", "540") or "540")   # 9분 < timeout-minutes
# 티커 6자 충돌 기록(정규화 1회분) — _meta 자기신고용
_LAST_COLLISIONS: Dict[str, Any] = {}
_LAST_CALL_STATE = "not_called"
_LAST_DISCOVERY: Dict[str, Any] = {}


# ──────────────────────────────────────────────────────────────
# 원천 호출
# ──────────────────────────────────────────────────────────────

def _call(bas_dt: str, page: int, rows: int,
          tmo: Optional[float] = None) -> Tuple[Optional[int], List[dict]]:
    """1회 호출 → (totalCount, items). 실패는 (None, []).

    🚨 실패를 0 으로 흡수하지 않는다 — totalCount=None(호출 실패) 과 0(데이터 없음)은
    다른 사건이다([[feedback_silent_zero_fallback_looks_plausible]]).
    """
    global _LAST_CALL_STATE
    _LAST_CALL_STATE = "transport_error"
    try:
        r = requests.get(
            _ENDPOINT,
            params={
                "serviceKey": PUBLIC_DATA_API_KEY,
                "resultType": "json",
                "numOfRows": rows,
                "pageNo": page,
                "basDt": bas_dt,
            },
            timeout=tmo or _TIMEOUT,
        )
    except requests.RequestException as e:
        print(f"[dividend_ksd] {bas_dt} p{page} 호출 실패: {type(e).__name__}")
        return None, []
    if r.status_code != 200:
        _LAST_CALL_STATE = "http_error"
        print(f"[dividend_ksd] {bas_dt} p{page} HTTP {r.status_code}: {r.text[:160]}")
        return None, []
    try:
        body = r.json()["response"]["body"]
    except Exception:
        # 인증 오류는 OpenAPI_ServiceResponse 로 온다 — 200 이어도 본문이 다르다.
        print(f"[dividend_ksd] {bas_dt} p{page} 본문 파싱 실패: {r.text[:200]}")
        _LAST_CALL_STATE = "auth_or_parse_error"
        return None, []
    items = body.get("items") or {}
    arr = items.get("item") if isinstance(items, dict) else None
    if arr is None:
        arr = []
    elif isinstance(arr, dict):
        arr = [arr]
    total = body.get("totalCount")
    _LAST_CALL_STATE = "valid_with_data" if total else "valid_but_empty"
    return total, arr


def _probe_with_retry(bas_dt: str) -> Tuple[Optional[int], List[dict], int]:
    """적재일 프로브. 연결 실패만 짧게 재시도하고 호출 횟수를 신고한다."""
    for attempt in range(1, _DISCOVER_ATTEMPTS + 1):
        total, items = _call(bas_dt, page=1, rows=1, tmo=_DISCOVER_TIMEOUT)
        if total is not None:
            return total, items, attempt
        if attempt < _DISCOVER_ATTEMPTS:
            time.sleep(_DISCOVER_BACKOFF_SEC[attempt - 1])
    return None, [], _DISCOVER_ATTEMPTS


def _cached_bas_dt() -> Optional[str]:
    """마지막 정상 원장의 적재일. 최신일 0건일 때 두 번째 후보로만 사용한다."""
    try:
        with open(_LEDGER_PATH, encoding="utf-8") as f:
            bas_dt = str((json.load(f).get("_meta") or {}).get("bas_dt") or "")
        return bas_dt if len(bas_dt) == 8 and bas_dt.isdigit() else None
    except Exception:
        return None


def discover_bas_dt(lookback_days: int = _DISCOVER_LOOKBACK) -> Optional[str]:
    """유효한 최신 적재일(basDt) 탐색.

    🚨 날짜를 고정하면 안 된다 — 적재일 하나에만 데이터가 있고 그 날짜가 이동한다.
    오늘부터 역순으로 훑어 totalCount>0 인 첫 날짜를 쓴다.
    """
    from datetime import timedelta

    global _LAST_DISCOVERY
    _LAST_DISCOVERY = {
        "status": "running", "dates_checked": 0, "calls_attempted": 0,
        "calls_succeeded": 0, "empty_dates": 0, "last_call_state": None,
    }
    today = now_kst().date()
    t0 = time.monotonic()
    dates = [(today - timedelta(days=back)).strftime("%Y%m%d")
             for back in range(lookback_days + 1)]
    cached = _cached_bas_dt()
    if cached and cached in dates[1:]:
        dates.remove(cached)
        dates.insert(1, cached)
    for d in dates:
        # 🚨 탐색이 전체 예산의 절반을 넘게 먹으면 멈춘다 — 여기서 다 태우면
        #   정작 수집을 못 하고 job 이 잘린다(8/23 실사고).
        if time.monotonic() - t0 > _BUDGET_SEC * 0.5:
            checked = _LAST_DISCOVERY["dates_checked"]
            _LAST_DISCOVERY["status"] = "budget_exhausted"
            print(f"[dividend_ksd] 적재일 탐색 예산 초과 ({checked}일 훑음) — 이번 run 포기",
                  file=sys.stderr)
            return None
        total, _, attempts = _probe_with_retry(d)
        _LAST_DISCOVERY["dates_checked"] += 1
        _LAST_DISCOVERY["calls_attempted"] += attempts
        _LAST_DISCOVERY["last_call_state"] = _LAST_CALL_STATE
        if total is None:
            # 같은 날짜가 3회 연속 실패하면 날짜 문제가 아니라 원천 연결 장애다.
            _LAST_DISCOVERY["status"] = "source_unavailable"
            return None
        _LAST_DISCOVERY["calls_succeeded"] += 1
        if total:
            _LAST_DISCOVERY["status"] = "found"
            _LAST_DISCOVERY["bas_dt"] = d
            return d
        _LAST_DISCOVERY["empty_dates"] += 1
    _LAST_DISCOVERY["status"] = "no_data_in_window"
    return None


def fetch_all(bas_dt: str) -> List[dict]:
    """해당 적재일 전량 페이징."""
    out: List[dict] = []
    t0 = time.monotonic()
    for page in range(1, _MAX_PAGES + 1):
        if time.monotonic() - t0 > _BUDGET_SEC:
            raise RuntimeError(
                f"KSD 페이징 예산 초과 (basDt={bas_dt}, {page-1}페이지 수집, "
                f"{_BUDGET_SEC}s) — 부분 원장을 남기지 않는다")
        total, items = _call(bas_dt, page=page, rows=_PAGE_SIZE)
        if total is None:
            # 중간 실패 = 부분 원장을 만들지 않는다. 통째로 포기.
            raise RuntimeError(f"KSD 페이징 중단 (basDt={bas_dt}, page={page})")
        out += items
        if len(items) < _PAGE_SIZE:
            break
    return out


# ──────────────────────────────────────────────────────────────
# 정규화
# ──────────────────────────────────────────────────────────────

def _ticker_of(row: dict) -> Optional[str]:
    """ISIN → 6자리 티커. KR7xxxxxx0 형태만 취한다.

    우선주는 자기 ISIN·자기 티커로 오므로(실측 보통주↔우선주 티커 겹침 0)
    종류 구분은 `stock_kind` 로만 하고 티커를 합치지 않는다.
    """
    isin = str(row.get("isinCd") or "")
    if not isin.startswith("KR7") or len(isin) < 9:
        return None
    return isin[3:9]


def _iso(yyyymmdd: Any) -> Optional[str]:
    s = str(yyyymmdd or "").strip()
    if len(s) != 8 or not s.isdigit():
        return None
    return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"


def _num(v: Any) -> Optional[float]:
    s = str(v if v is not None else "").strip().replace(",", "")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def normalize(rows: List[dict]) -> Dict[str, Dict[str, Any]]:
    """원천 행 → 티커별 {종목 상수 + rows[회차]}.

    🚨 스키마를 납작하게 두면 파일이 29MB 가 된다(실측 — 행 437B × 71,600).
    티커마다 불변인 값(주식종류·액면가·결산월·법인등록번호·명의개서대리인)은 **위로 올리고**,
    회차 행에는 변하는 것만 남긴다. 파생 가능한 값은 저장하지 않는다 —
    `stckGenrCashDvdnRt`(액면 대비 배당률) = dps ÷ par × 100 이라 재계산된다.
    """
    # 🚨 **티커 충돌을 순서 운에 맡기지 않는다** (2026-08-23 실측 사고).
    #   `_ticker_of()` 는 ISIN 을 6자로 자르는데, 신형우선주는 서로 다른 종목이 같은 6자로
    #   겹친다 — `KR714276K044`(8우선주) 와 `KR714276K010`(5우선주) 가 둘 다 `14276K`.
    #   첫 판본은 `setdefault` 라 **먼저 온 쪽**이 이겼고, 원천 응답 순서가 적재일마다
    #   달라져 **23종목이 매일 뒤바뀌었다**(→ 내용 무변경인데 파일이 매일 갱신).
    #   ISIN 오름차순으로 **결정적으로** 고정한다. 충돌 자체는 `_meta` 에 신고한다.
    rows = sorted(rows, key=lambda r: (str(r.get("isinCd") or ""),
                                       str(r.get("dvdnBasDt") or "")))
    db: Dict[str, Dict[str, Any]] = {}
    seen_isin: Dict[str, str] = {}
    collisions: Dict[str, set] = {}
    for r in rows:
        tk = _ticker_of(r)
        rec_dt = _iso(r.get("dvdnBasDt"))
        if not tk or not rec_dt:
            continue
        isin = str(r.get("isinCd") or "")
        if tk in seen_isin and seen_isin[tk] != isin:
            # 같은 6자 티커에 다른 ISIN — 채택본(먼저 정렬된 것)만 쓰고 나머지는 버린다.
            collisions.setdefault(tk, {seen_isin[tk]}).add(isin)
            continue
        seen_isin[tk] = isin
        ent = db.setdefault(tk, {
            "stock_kind": (r.get("scrsItmsKcdNm") or "").strip() or None,
            "par_value": _num(r.get("stckParPrc")),
            "settlement_month": (r.get("stckStacMd") or "").strip() or None,
            "corp_reg_no": (r.get("crno") or "").strip() or None,
            "transfer_agent": (r.get("trsnmDptyDcdNm") or "").strip() or None,
            "isin": (r.get("isinCd") or "").strip() or None,
            "rows": [],
        })
        # 🚨 date = 배당**기준일**. 배당락일이 아니다. ex_date 로 쓰지 말 것.
        row: Dict[str, Any] = {
            "date": rec_dt,
            "pay_date": _iso(r.get("cashDvdnPayDt")),
            "dps": _num(r.get("stckGenrDvdnAmt")),
        }
        # 아래 3개는 대부분 비어 있거나 기본값이라 있을 때만 싣는다.
        diff = _num(r.get("stckGrdnDvdnAmt"))
        if diff:
            row["diff_dps"] = diff
        hand = _iso(r.get("stckHndvDt"))
        if hand:
            row["handover_date"] = hand
        kind = (r.get("stckDvdnRcdNm") or "").strip()
        if kind and kind != "현금배당":
            row["dividend_kind"] = kind
        ent["rows"].append(row)
    for tk in db:
        db[tk]["rows"].sort(key=lambda x: x["date"])
    if collisions:
        # 🚨 조용히 합치지 않는다 — 몇 종목이 겹쳤고 어떤 ISIN 이 버려졌는지 남긴다.
        _LAST_COLLISIONS.clear()
        _LAST_COLLISIONS.update({k: sorted(v) for k, v in collisions.items()})
        print(f"[dividend_ksd] 티커 6자 충돌 {len(collisions)}종목 — ISIN 오름차순 채택",
              file=sys.stderr)
    else:
        _LAST_COLLISIONS.clear()
    return db


# ──────────────────────────────────────────────────────────────
# 교차검증 — DART 연간 원장과 대조
# ──────────────────────────────────────────────────────────────

def cross_check_dart(db: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """DART `dividends_kr.json`(연간 합계) 와 KSD(회차) 대조 신고.

    🚨 축이 다르므로 **불일치를 오류로 단정하지 않는다** — 연간 합계 vs 회차 금액,
    사업연도 라벨 vs 기준일 연도가 섞인다. 여기서는 **신고만** 한다.

    🚨 이미 원장이 스스로 신고한 건(`implausible`)은 **따로 센다.** 8/15 #369 가드가
    067900 을 `implausible_reason` 까지 달아 잡아둔 상태라, 그걸 신규 발견으로 세면
    가드가 작동 중인데도 매번 새 사고처럼 보인다.
    """
    # 이 워크플로는 수집기를 파일 경로로 직접 실행한다. 그 환경에서 다른 collector
    # import 가 실패해 교차검증 필드 전체가 사라진 실측이 있어, 필요한 정본 JSON을
    # 직접 읽는다. 읽기 실패는 원인까지 신고하며 본 KSD 수집은 유지한다.
    try:
        with open(os.path.join(DATA_DIR, "dividends_kr.json"), encoding="utf-8") as f:
            dart = json.load(f)
        if not isinstance(dart, dict):
            raise TypeError("dividends_kr root is not object")
    except Exception as e:
        return {"status": "skip",
                "reason": f"DART 원장 로드 실패: {type(e).__name__}: {e}"[:160]}

    checked = matched = ratio_flag = known_flag = 0
    flags: List[dict] = []
    for tk, arr in dart.items():
        if tk.startswith("_"):
            continue
        ent = db.get(tk) or {}
        rows = ent.get("rows") or []
        if not rows:
            continue
        for rec in arr:
            if rec.get("_meta"):
                continue
            ours = rec.get("confirmed_amount_per_share") or rec.get(
                "announced_amount_per_share")
            if ours is None:
                continue
            checked += 1
            # 사업연도 결산배당의 기준일은 당해 12월 ~ 이듬해 상반기에 걸친다.
            fy = str(rec.get("ex_date") or "")[:4]
            if not fy.isdigit():
                continue
            lo, hi = f"{fy}-10-01", f"{int(fy) + 1}-06-30"
            amts = [x["dps"] for x in rows
                    if lo <= x["date"] <= hi and x.get("dps") is not None]
            if not amts:
                continue
            if any(abs(float(ours) - a) < 0.51 for a in amts):
                matched += 1
                continue
            biggest = max(amts)
            # 배율 100배 이상 = 단위/총액 혼입 의심 (067900 형태)
            if biggest > 0 and float(ours) / biggest >= 100:
                if rec.get("implausible"):
                    known_flag += 1
                    continue
                ratio_flag += 1
                if len(flags) < 30:
                    flags.append({
                        "ticker": tk, "fy": fy,
                        "dart_amount": float(ours), "ksd_max": biggest,
                        "ratio": round(float(ours) / biggest, 1),
                    })
    return {
        "status": "ok",
        "dart_rows_checked": checked,
        "amount_matched": matched,
        "unit_error_new": ratio_flag,
        "unit_error_already_flagged": known_flag,
        "suspects": flags,
    }


# ──────────────────────────────────────────────────────────────
# 산출
# ──────────────────────────────────────────────────────────────

def build_meta(db: Dict[str, Dict[str, Any]], bas_dt: str, raw_n: int,
               cross: Dict[str, Any]) -> Dict[str, Any]:
    """🚨 산출물이 자기 입으로 말하게 한다 (RULE 12)."""
    rows = [r for ent in db.values() for r in ent["rows"]]
    n = len(rows) or 1
    pay = sum(1 for r in rows if r.get("pay_date"))
    kinds: Dict[str, int] = {}
    years: Dict[str, int] = {}
    for tk, ent in db.items():
        k = ent.get("stock_kind") or "미상"
        kinds[k] = kinds.get(k, 0) + len(ent["rows"])
    for r in rows:
        y = r["date"][:4]
        years[y] = years.get(y, 0) + 1
    return {
        "generated_at": now_kst().isoformat(),
        "source": "금융위원회_주식배당정보(한국예탁결제원) getDiviInfo_V2",
        "bas_dt": bas_dt,
        "raw_row_count": raw_n,
        "row_count": len(rows),
        "ticker_count": len(db),
        "record_date_filled_pct": 100.0,   # 기준일 없는 행은 normalize 에서 탈락
        "payment_date_filled_pct": round(pay / n * 100, 1),
        "record_year_min": min(years) if years else None,
        "record_year_max": max(years) if years else None,
        # 🚨 KR 종목코드가 전부 숫자라는 전제는 틀렸다 — `0001A0` 형태 569건 실측.
        #   이들은 우리 검색 유니버스에 0/569 로 없다(KSD 는 예탁 대상 전체라 KRX
        #   상장분만 담지 않는다). 거르지 않고 두되 분모를 신고한다.
        "ticker_non_numeric": sum(1 for t in db if not t.isdigit()),
        # 🚨 같은 6자 티커에 ISIN 이 둘 이상 — 신형우선주 계열. 채택 규칙 = ISIN 오름차순.
        "ticker_isin_collisions": len(_LAST_COLLISIONS),
        "ticker_isin_collision_sample": dict(list(_LAST_COLLISIONS.items())[:5]),
        "stock_kind_counts": dict(sorted(kinds.items(), key=lambda x: -x[1])[:8]),
        "record_year_counts": dict(sorted(years.items(), reverse=True)[:10]),
        "cross_check_dart": cross,
        # 🚨 이 원장이 무엇이고 무엇이 아닌지 스스로 신고한다.
        "date_semantics": "rows[].date = 배당기준일(dvdnBasDt). 배당락일 아님.",
        "ex_date_provided": False,
        "axis": "회차별(기준일 단위). DART dividends_kr.json 은 연간 합계라 축이 다름.",
        "market": "KR only (ISIN KR 99.99% · 해외법인 국내상장분 소수 포함)",
        # 🚨 공개 노출 전에 반드시 읽을 것 — 이 원장은 라이선스가 걸려 있다.
        "license": "공공저작물 제2유형 — 출처표시 + 상업적 이용금지",
        "attribution_required": "한국예탁결제원",
        "commercial_use": (
            "금지. 상업적 활용 시 한국예탁결제원과 정보이용계약 필요"
            " (portal@ksd.or.kr). 현재 AlphaNest 는 무료·광고 0 이라 제2유형 안."
            " 🚨 유료화 시점에 계약이 선행돼야 한다."
        ),
        "public_exposure_caveats": [
            "배당기준일 당일 매수로는 배당을 못 받는다 — 화면에 기준일만 띄우면 오도된다",
            f"dps 0 행이 {sum(1 for r in rows if not r.get('dps'))}건 "
            f"({sum(1 for r in rows if not r.get('dps')) / n * 100:.1f}%, 무배당 포함) — 필터 필요",
            "우리 검색 유니버스 밖 종목이 섞여 있다 (ticker_non_numeric 참조)",
        ],
    }


def collect(save: bool = True) -> Dict[str, Any]:
    """전량 수집 → 원장 저장. 반환 = _meta.

    🚨 0건이면 저장하지 않고 예외를 던진다 — 빈 원장을 성공으로 남기면
    다음 소비처가 "배당이 원래 없다" 로 읽는다([[feedback_cluster_silent_defect]]).
    """
    if not PUBLIC_DATA_API_KEY:
        raise RuntimeError("PUBLIC_DATA_API_KEY 미설정")
    bas_dt = discover_bas_dt()
    if not bas_dt:
        st = _LAST_DISCOVERY.get("status")
        done = _LAST_DISCOVERY.get("calls_succeeded", 0)
        total = _LAST_DISCOVERY.get("calls_attempted", 0)
        if st == "source_unavailable":
            raise RuntimeError(
                f"KSD 원천 연결 불가 (성공 호출 {done}/{total}, "
                f"last={_LAST_DISCOVERY.get('last_call_state')}) — 기존 원장 보존")
        raise RuntimeError(
            f"유효 적재일 미발견 (정상 응답 {_LAST_DISCOVERY.get('empty_dates', 0)}일, "
            f"성공 호출 {done}/{total})")
    raw = fetch_all(bas_dt)
    if not raw:
        raise RuntimeError(f"KSD 응답 0건 (basDt={bas_dt})")
    db = normalize(raw)
    if not db:
        raise RuntimeError(f"정규화 후 0건 (원천 {len(raw)}행, basDt={bas_dt})")
    cross = cross_check_dart(db)
    meta = build_meta(db, bas_dt, len(raw), cross)
    if not save:
        return meta

    # 🚨 무변경이면 파일을 건드리지 않는다. `generated_at` 만 바뀌어도 5.45MB 가 매 실행
    #   커밋되고, 하루 292개 봇 커밋이 도는 repo 에서 그건 순수 낭비다.
    #   비교는 **본문만** — 휘발 필드(generated_at)를 뺀 나머지가 같으면 no-op.
    body_new = json.dumps(db, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"))
    if os.path.exists(_LEDGER_PATH):
        try:
            with open(_LEDGER_PATH, encoding="utf-8") as f:
                old = json.load(f)
            old_meta = old.get("_meta") or {}
            old_body = {k: v for k, v in old.items() if not k.startswith("_")}
            same_body = json.dumps(old_body, ensure_ascii=False, sort_keys=True,
                                   separators=(",", ":")) == body_new
            same_cross_check = old_meta.get("cross_check_dart") == meta.get("cross_check_dart")
            # 🚨 적재일이 바뀌어도 **본문이 같으면 쓰지 않는다** (2026-08-23 실측 정정).
            #   data.go.kr 은 같은 데이터를 매일 새 `basDt` 로 다시 올린다 —
            #   `bas_dt` 까지 비교 조건에 넣으면 내용이 같아도 **매일 5.45MB 를 커밋**하게 되어
            #   무변경 가드를 넣은 이유가 통째로 무력화된다(첫 판본이 그랬다).
            #   `_meta.bas_dt` 는 "현재 본문이 어느 적재분에서 왔는가" 이므로 옛 날짜가 맞다.
            #   관측한 최신 적재일은 로그로만 남긴다.
            # 본문이 같아도 교차검증 계약이 복구·변경되면 메타를 갱신해야 한다.
            # 이를 무시하면 결함 상태가 원장에 영구 고정되고 CI도 계속 실패한다.
            if same_body and same_cross_check:
                old_bd = old_meta.get("bas_dt")
                note = "무변경 (본문 동일)"
                if old_bd != bas_dt:
                    note += f" · 적재일 {old_bd}→{bas_dt} 이동했으나 내용 동일"
                    print(f"[dividend_ksd] {note}", file=sys.stderr)
                meta["write_skipped"] = note
                meta["observed_bas_dt"] = bas_dt
                meta["bas_dt"] = old_bd or bas_dt
                return meta
        except Exception:
            pass  # 손상된 기존 파일 = 그냥 새로 쓴다

    payload: Dict[str, Any] = {"_meta": meta}
    payload.update(db)
    tmp = _LEDGER_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, _LEDGER_PATH)
    return meta


def load_ledger() -> Dict[str, Dict[str, Any]]:
    """소비처용 로더 — `_meta` 제외한 티커 맵."""
    if not os.path.exists(_LEDGER_PATH):
        return {}
    try:
        with open(_LEDGER_PATH, encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        return {}
    return {k: v for k, v in d.items() if not k.startswith("_")}


def get_history(ticker: str, limit: Optional[int] = None) -> List[dict]:
    """종목 배당 이력 — 최근순. 리포트 노출용."""
    ent = load_ledger().get(str(ticker).zfill(6)) or {}
    rows = list(reversed(ent.get("rows") or []))
    return rows[:limit] if limit else rows


def get_by_record_date(lo: str, hi: str) -> List[dict]:
    """기간 내 배당기준일 — 캘린더용. lo/hi = 'YYYY-MM-DD' 포함 구간.

    🚨 "배당락일" 이 아니라 **"배당기준일"** 로 표기해야 한다. 이 원장은 락일을 모른다.
    """
    out: List[dict] = []
    for tk, ent in load_ledger().items():
        for r in ent.get("rows") or []:
            if lo <= r["date"] <= hi:
                out.append({
                    "ticker": tk,
                    "stock_kind": ent.get("stock_kind"),
                    **r,
                })
    out.sort(key=lambda x: x["date"])
    return out


def get_upcoming(days_ahead: int = 90) -> List[dict]:
    """오늘 이후 배당기준일 — 캘린더용."""
    from datetime import timedelta

    today = now_kst().date()
    return get_by_record_date(
        today.strftime("%Y-%m-%d"),
        (today + timedelta(days=days_ahead)).strftime("%Y-%m-%d"),
    )


# ──────────────────────────────────────────────────────────────
# 공개 리포트용 섹션
# ──────────────────────────────────────────────────────────────

# 🚨 라이선스 제2유형 = **출처표시 의무**. 이 문구가 화면에 닿는 경로다 — 지우지 말 것.
#   그리고 배당기준일은 배당락일이 아니다. 기준일 당일에 사면 받지 못한다.
_REPORT_NOTE = (
    "배당기준일 기준 · 한국예탁결제원 · 기준일 당일 매수로는 받지 못하며 "
    "그 전에 보유해야 함 (배당락일 아님)"
)
_REPORT_RECENT_N = 8


def build_report_section(entry: Dict[str, Any],
                         today: Optional[str] = None,
                         ledger_meta: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """티커 1건 → 공개 리포트에 실을 배당 파트. 배당 이력이 없으면 None.

    🚨 dps 0 행은 **이력에서 빼되 세는 데는 쓴다** — 무배당 28,690건(전체 57.8%)을
    그대로 뿌리면 화면이 0원으로 도배되지만, 그 행이 있어야 "몇 해나 배당했나" 가 나온다.
    🚨 배당수익률은 여기서 계산하지 않는다 — 리포트 가격은 클라이언트 라이브 조회라
    빌더가 시점 다른 가격으로 나누면 조용히 틀린다.
    """
    rows = (entry or {}).get("rows") or []
    if not rows:
        return None
    today = today or now_kst().strftime("%Y-%m-%d")
    paid = [r for r in rows if (r.get("dps") or 0) > 0]
    if not paid:
        return None

    # 최근 12개월(기준일 기준) 합 — 분기·중간배당을 합쳐야 연 배당이 된다.
    y1 = f"{int(today[:4]) - 1}{today[4:]}"
    ttm = sum(r["dps"] for r in paid if y1 < r["date"] <= today)
    # 🚨 창을 "오늘 - 10년" 으로 자르면 경계 연도가 **둘** 걸려 11 이 나온다
    #   (실측 삼성전자 paid_years_10y=11). 화면에서 "10년 중 11년" 으로 읽힌다.
    #   연도 단위 질문이므로 창도 **연도 단위**로 자른다 — 올해 포함 최근 10개 연도.
    y_from = int(today[:4]) - 9
    years_paid = {r["date"][:4] for r in paid if int(r["date"][:4]) >= y_from}

    upcoming = [r for r in rows if r["date"] > today and (r.get("dps") or 0) > 0]
    recent = list(reversed(paid))[:_REPORT_RECENT_N]
    ledger_meta = ledger_meta or {}
    return {
        "recent": [{"record_date": r["date"], "pay_date": r.get("pay_date"),
                    "dps": r["dps"]} for r in recent],
        "ttm_dps": round(ttm, 2) if ttm else None,
        "latest_record_date": recent[0]["date"] if recent else None,
        "latest_pay_date": recent[0].get("pay_date") if recent else None,
        "paid_years_10y": len(years_paid),
        "upcoming_record_date": upcoming[0]["date"] if upcoming else None,
        "stock_kind": (entry or {}).get("stock_kind"),
        "source": "한국예탁결제원(KSD) · 금융위 공공데이터",
        "source_bas_dt": ledger_meta.get("bas_dt"),
        "source_generated_at": ledger_meta.get("generated_at"),
        "note": _REPORT_NOTE,
    }


def load_dividends_ledger_for_report() -> Dict[str, Dict[str, Any]]:
    """티커 → 리포트 섹션 맵. 빌더가 이것만 호출한다."""
    today = now_kst().strftime("%Y-%m-%d")
    out: Dict[str, Dict[str, Any]] = {}
    try:
        with open(_LEDGER_PATH, encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        raw = {}
    ledger_meta = raw.get("_meta") or {}
    for tk, ent in raw.items():
        if tk.startswith("_"):
            continue
        sec = build_report_section(ent, today, ledger_meta)
        if sec:
            out[tk] = sec
    return out


if __name__ == "__main__":
    m = collect()
    print(json.dumps(m, ensure_ascii=False, indent=1))
