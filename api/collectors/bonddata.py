"""
국내 채권 수익률·스프레드 수집 (pykrx + ECOS)
  - 국고채 수익률 곡선 (1Y~30Y)
  - 회사채 신용등급별 스프레드 (AA- / BBB-, 3년물, 국고채 3년 대비)
  - 한국은행 ECOS 보조 (국고채 3Y 기준)
"""
import sys
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple

from api.config import ECOS_API_KEY, now_kst

_KR_GOV_BOND_TENORS = {
    "1Y": "국고채권(01년)",
    "2Y": "국고채권(02년)",
    "3Y": "국고채권(03년)",
    "5Y": "국고채권(05년)",
    "10Y": "국고채권(10년)",
    "20Y": "국고채권(20년)",
    "30Y": "국고채권(30년)",
}

# 🚨 2026-08-08 정정 — 옛 _CORP_GRADES/_ECOS_BOND_ITEMS 는 어디에서도 참조되지 않는 죽은 상수였고,
#   담고 있던 회사채 item 코드(010300003 AA- / 010300006 A+ / 010300009 BBB+)는 ECOS 에 존재하지
#   않는 번호였다(실호출 3건 전부 INFO-200 "해당하는 데이터가 없습니다"). 2026-06-03 에 국고채
#   코드만 메타 API 로 정정하고 회사채 코드는 그대로 남겨 둔 잔여물이다. 코드 자체를 제거하고
#   실제 유효 코드는 _ecos_yield_curve() 안 corp_grade_map 한 곳에만 둔다(단일 출처).


def _pykrx_bond_yields() -> Dict[str, Any]:
    """pykrx에서 국고채 수익률 곡선 수집 시도."""
    try:
        from pykrx import bond
    except ImportError:
        return {}

    today = now_kst().date()
    start = today - timedelta(days=14)
    from_s = start.strftime("%Y%m%d")
    to_s = today.strftime("%Y%m%d")

    curve: List[Dict[str, Any]] = []
    for tenor, name in _KR_GOV_BOND_TENORS.items():
        try:
            df = bond.get_otc_treasury_yields(from_s, to_s, name)
            if df is None or df.empty:
                continue
            col = "수익률" if "수익률" in df.columns else (df.columns[0] if len(df.columns) > 0 else None)
            if col is None:
                continue
            vals = df[col].dropna()
            if vals.empty:
                continue
            last_yield = float(vals.iloc[-1])
            curve.append({"tenor": tenor, "yield": round(last_yield, 3)})
        except Exception:
            continue

    return {"curve": curve} if curve else {}


def _ecos_fetch_point(
    stat_code: str, item_code: str, days: int = 30
) -> Optional[Tuple[float, str]]:
    """ECOS 단일 시계열의 최신 관측 = (값, 관측일 YYYYMMDD).

    🚨 관측일을 같이 돌려주는 이유 = ECOS 일별 금리는 수집 시점보다 뒤처진다(2026-08-08 실측:
      회사채 최신 관측 20260723 = 수집일 대비 16일 전). 수집일을 as_of 로 쓰면 실제보다 신선한
      것처럼 보인다 — [[feedback_macro_timestamp_policy]] collected_at 과 as_of 분리 의무.

    🚨 **2026-08-11 결함 정정 — 행 수 절단.** 옛 URL 은 `json/kr/1/10` 이라 ECOS 에
      **10행만** 요청했다. ECOS 는 **오름차순**으로 주므로 30일 창(영업일 약 22관측)에서
      돌아오는 것은 **가장 오래된 10건**이고, `rows[-1]` 은 그중 마지막 = 실제 최신이 아니라
      **약 10영업일 전 값**이었다.

      실측(2026-08-11): 발행 AA- 4.576 / as_of 20260727  ↔  ECOS 실제 4.476 / 20260810.
      국고채 커브도 같은 함수를 타서 전 만기가 함께 낡아 있었다 —
      1Y 3.375↔3.384 · 2Y 3.723↔3.601 · 3Y 3.865↔3.778 · 5Y 4.117↔3.994 · 10Y 4.333↔4.239
      (최대 12bp). 워크플로는 계속 success 였고 값도 그럴듯해서 **초록불로는 못 잡는 결함**이다.
      [[feedback_silent_total_failure_guard]] 의 반대 방향 — 0건이 아니라 '틀린 값이 채워짐'.

      → 행 수를 창 길이에서 파생시키고, **응답이 상한에 닿으면 절단으로 보고 거부**한다.
        상한을 늘려도 닿으면 조용히 옛 값을 쓰는 대신 None 을 돌려 결손으로 드러낸다.
    """
    if not ECOS_API_KEY:
        return None
    try:
        import requests
        from urllib.parse import quote

        today = now_kst().date()
        start = today - timedelta(days=days)
        key_seg = quote(str(ECOS_API_KEY).strip(), safe="")
        # 창 길이에서 파생 + 넉넉한 여유. 달력일보다 관측이 많을 수 없으므로 days+50 이면 안전.
        limit = days + 50
        url = (
            f"https://ecos.bok.or.kr/api/StatisticSearch/{key_seg}/json/kr/1/{limit}"
            f"/{stat_code}/D/{start.strftime('%Y%m%d')}/{today.strftime('%Y%m%d')}/{item_code}"
        )
        r = requests.get(url, timeout=20)
        if r.status_code != 200:
            return None
        data = r.json()
        ss = data.get("StatisticSearch") or {}
        rows = ss.get("row")
        if not rows:
            return None
        if isinstance(rows, dict):
            rows = [rows]
        # 🚨 상한에 닿았다 = 절단 가능 = rows[-1] 이 최신이라는 보장이 깨진다. 옛 값을 조용히
        #   쓰지 말고 결손으로 드러낸다(틀린 값보다 빈 값이 낫다).
        if len(rows) >= limit:
            sys.stderr.write(
                f"[bonddata] 🚨 ECOS 응답이 상한 {limit} 에 닿음 ({stat_code}/{item_code}) — "
                f"절단 의심, 최신값 신뢰 불가로 결손 처리\n"
            )
            return None
        # ECOS 는 오름차순 → 마지막이 최신. 방어적으로 TIME 최대값을 고른다.
        last = max(rows, key=lambda r: str(r.get("TIME") or ""))
        return round(float(last.get("DATA_VALUE", 0)), 4), str(last.get("TIME") or "")
    except Exception:
        return None


def _ecos_fetch_series(stat_code: str, item_code: str, days: int = 30) -> Optional[float]:
    """ECOS 최신값만 (관측일이 필요 없는 경로용 얇은 래퍼)."""
    point = _ecos_fetch_point(stat_code, item_code, days)
    return point[0] if point else None


def _ecos_yield_curve() -> Dict[str, Any]:
    """ECOS에서 국고채 수익률 곡선 + 회사채 스프레드 수집."""
    if not ECOS_API_KEY:
        return {}

    # ECOS stat 817Y002 국고채 item 코드 (2026-06-03 정정 — 메타 API StatisticItemList 확인).
    # 옛 코드는 mislabel/오류: "1Y"=010200000(실제 3년), "3Y"=010210000(실제 10년),
    # 5Y/10Y 코드(010200002/010210001)는 무효 → KR 커브 라벨 오류 + 5Y/10Y/2Y 누락 사고.
    tenor_map = {
        "1Y":  ("817Y002", "010190000"),  # 국고채(1년)
        "2Y":  ("817Y002", "010195000"),  # 국고채(2년)
        "3Y":  ("817Y002", "010200000"),  # 국고채(3년)
        "5Y":  ("817Y002", "010200001"),  # 국고채(5년)
        "10Y": ("817Y002", "010210000"),  # 국고채(10년)
        "20Y": ("817Y002", "010220000"),  # 국고채(20년)
        "30Y": ("817Y002", "010230000"),  # 국고채(30년)
    }

    curve: List[Dict[str, Any]] = []
    curve_as_of = ""
    for tenor, (stat, item) in tenor_map.items():
        # 🚨 커브에도 관측일을 남긴다. 옛 코드는 값만 담아 **커브가 언제 것인지 알 수 없었다**
        #   — 위 행수 절단이 10영업일 낡은 값을 채웠는데도 신선도 보드가 못 잡은 이유다.
        point = _ecos_fetch_point(stat, item, days=30)
        if point is not None:
            val, obs_date = point
            entry: Dict[str, Any] = {"tenor": tenor, "yield": val}
            if obs_date:
                entry["as_of"] = obs_date
                curve_as_of = max(curve_as_of, obs_date)
            curve.append(entry)

    gov_3y = next((c["yield"] for c in curve if c["tenor"] == "3Y"), None)

    # 🚨 2026-08-08 정정 — ECOS 메타 API(StatisticItemList/817Y002) 27행 실조회로 확정한 코드.
    #   옛 코드(010300003 / 010300006 / 010300009)는 셋 다 존재하지 않아 grades 가 항상 비었고,
    #   그 결과 bonds.json 에 kr_corp_spreads 키 자체가 없었다 = KR 신용 스프레드 축 상시 결손.
    #   niche_intel.build_macro_niche_credit / _build_credit(KR) 이 이 값을 읽으므로 침묵 결손이었다.
    #   817Y002 가 제공하는 회사채 등급은 AA-(3년)와 BBB-(3년) 둘뿐이다 — A+/BBB+ 는 미제공이라 뺀다.
    corp_grade_map = {
        "AA-":  ("817Y002", "010300000"),  # 회사채(3년, AA-)
        "BBB-": ("817Y002", "010320000"),  # 회사채(3년, BBB-)
    }

    grades: Dict[str, Dict[str, Any]] = {}
    grade_as_of = ""
    for grade, (stat, item) in corp_grade_map.items():
        point = _ecos_fetch_point(stat, item, days=30)
        if point is not None:
            val, obs_date = point
            entry: Dict[str, Any] = {"yield": val}
            if gov_3y is not None:
                entry["spread_vs_3y"] = round(val - gov_3y, 3)
            if obs_date:
                entry["as_of"] = obs_date
                grade_as_of = max(grade_as_of, obs_date)
            grades[grade] = entry

    result: Dict[str, Any] = {}
    if curve:
        result["curve"] = curve
        if curve_as_of:
            result["curve_as_of"] = curve_as_of
    if grades:
        result["grades"] = grades
        if grade_as_of:
            result["grades_as_of"] = grade_as_of
    return result


def _classify_curve_shape(curve: List[Dict[str, Any]]) -> str:
    """수익률 곡선 형태 판별."""
    if len(curve) < 3:
        return "insufficient_data"

    yields = [c["yield"] for c in curve]
    short = yields[0]
    long = yields[-1]
    mid = yields[len(yields) // 2]

    if long > short + 0.3:
        return "normal"
    elif short > long + 0.3:
        return "inverted"
    elif mid > short and mid > long:
        return "humped"
    else:
        return "flat"


def get_bond_market_summary() -> Dict[str, Any]:
    """
    국내 채권 시장 요약.
    반환: {curve: [...], curve_shape, kr_corp_spreads: {grades: ...}, updated_at}
    """
    ts = now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00")
    date_str = now_kst().strftime("%Y%m%d")

    result: Dict[str, Any] = {
        "available": False,
        "updated_at": ts,
    }

    pykrx_data = _pykrx_bond_yields()
    ecos_data = _ecos_yield_curve()

    # ECOS(BOK 공식, credential 불요) 우선 + pykrx 보충 — 만기 union (2026-06-03 정정).
    # 옛 'pykrx OR ecos' = pykrx 부분 성공(KRX 로그인 실패에도 일부 반환) 시 ECOS 통째 무시 →
    # KR 커브 결손(5Y/10Y/2Y 누락). 두 소스 병합으로 결손 방지, ECOS 값 우선.
    _by_tenor: Dict[str, Any] = {}
    for _c in (pykrx_data.get("curve") or []):
        if isinstance(_c, dict) and _c.get("tenor"):
            _by_tenor[_c["tenor"]] = _c
    for _c in (ecos_data.get("curve") or []):
        if isinstance(_c, dict) and _c.get("tenor"):
            _by_tenor[_c["tenor"]] = _c
    _kr_order = {t: i for i, t in enumerate(["1Y", "2Y", "3Y", "5Y", "10Y", "20Y", "30Y"])}
    curve = sorted(_by_tenor.values(), key=lambda c: _kr_order.get(c.get("tenor"), 99))

    if curve:
        result["curve"] = curve
        result["curve_shape"] = _classify_curve_shape(curve)
        result["available"] = True
        # 🚨 2026-08-11 — curve_as_of 전파. #348 이 _ecos_yield_curve 에 관측일을 넣었으나
        #   이 함수가 curve/curve_shape 만 옮겨 **집계 관측일이 bonds.json 에 닿지 않았다.**
        #   measurement_audit 검사 I(as_of 노후)가 잡았다. 만기별 as_of 는 curve 항목 안에
        #   살아 있으나, 축 단위 노후 판정에는 집계값이 필요하다.
        #   pykrx 보충분에는 관측일이 없으므로 실제 존재하는 값들의 최대치를 쓴다.
        _as_ofs = [str(c.get("as_of")) for c in curve if c.get("as_of")]
        if _as_ofs:
            result["curve_as_of"] = max(_as_ofs)

    grades = ecos_data.get("grades")
    if grades:
        # date = ECOS 실제 관측일(있으면). 수집일 fallback 은 관측일 부재 시에만.
        result["kr_corp_spreads"] = {
            "date": ecos_data.get("grades_as_of") or date_str,
            "collected_at": ts,
            "grades": grades,
        }

    return result


if __name__ == "__main__":
    import json
    data = get_bond_market_summary()
    print(json.dumps(data, ensure_ascii=False, indent=2))
