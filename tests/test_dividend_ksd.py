"""KSD 배당기준일 원장 계약 (2026-08-22).

왜 이 파일이 있나 — 배당은 **날짜 의미가 섞이면 조용히 틀리는** 영역이다.
· `dividends_kr.json`(DART) = 사업보고서 **연간 합계** + `ex_date` 는 **추정치**
· `dividends_kr_ksd.json`(예탁결제원) = **회차별 배당기준일 실날짜**, 배당락일은 **없음**

두 축을 한 칸에 넣는 것이 067900 단위오류(제출인이 총액을 주당 칸에 기입)와 같은 형태의
사고다. 아래 계약은 그 혼입을 기계로 막는다.

실측 근거 (2026-08-22, basDt=20260821):
  전량 71,669행 → 정규화 71,600 · 티커 5,453 · 기준일 빈값 0 · 지급일 58.6%
  FY2025 결산배당 기준일이 **29.4% 는 이듬해로 이동**(2025-12 751 / 2026-01~04 314),
  우리 추정 `2025-12-30` 과 정확히 일치한 건 **0건**, 90일 이상 오차 187건.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
COL = ROOT / "api" / "collectors" / "dividend_ksd.py"
LEDGER = ROOT / "data" / "dividends_kr_ksd.json"


def _src() -> str:
    return COL.read_text(encoding="utf-8")


def _ledger() -> dict:
    if not LEDGER.exists():
        pytest.skip("KSD 원장 미생성 — 수집 전 환경")
    return json.loads(LEDGER.read_text(encoding="utf-8"))


# ── 수집기 계약 ────────────────────────────────────────────────

def test_collector_never_writes_ex_date():
    """🚨 이 수집기는 배당락일을 **만들지** 않는다.

    KSD 가 주는 건 배당기준일뿐이고, 기준일→락일 파생 규칙은 미검증이다.
    `ex_date` 를 쓰기 시작하면 추정치가 확정 사실로 둔갑한다.

    🚨 문자열 검색으로 잡으면 안 된다 — DART 원장을 **읽는** `rec.get("ex_date")` 까지
    걸려 정상 코드가 실패한다(첫 판본이 그랬다). 쓰기(dict 키·대입)만 AST 로 본다.
    """
    import ast

    tree = ast.parse(_src())
    writes = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for k in node.keys:
                if isinstance(k, ast.Constant) and k.value == "ex_date":
                    writes.append(f"dict key @L{getattr(k, 'lineno', '?')}")
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Subscript) and isinstance(t.slice, ast.Constant) \
                        and t.slice.value == "ex_date":
                    writes.append(f"subscript 대입 @L{node.lineno}")
    assert not writes, f"KSD 수집기가 ex_date 를 쓴다 — 배당락일 아님: {writes}"


def test_bas_dt_is_discovered_not_hardcoded():
    """🚨 basDt 는 특정 적재일 하나만 유효하고 그 날짜가 이동한다.

    실측 — 20260821 은 71,669행인데 20260822·20260820·20260819·20260815 는 전부 0.
    날짜를 고정하면 어느 날 조용히 0건이 된다.
    """
    s = _src()
    assert "def discover_bas_dt" in s, "적재일 탐색 함수가 사라졌다"
    assert "discover_bas_dt()" in s, "collect() 가 탐색을 안 거친다"


def test_zero_rows_raises_not_saves():
    """건수 0 + 성공 종료 = 다음 소비처가 '배당이 원래 없다' 로 읽는다."""
    s = _src()
    for needle in ("응답 0건", "정규화 후 0건", "유효 적재일 미발견"):
        assert needle in s, f"0건 방어 문구 소실: {needle}"
    assert s.count("raise RuntimeError") >= 4, "0건·실패 경로가 예외를 안 던진다"


def test_partial_paging_does_not_persist():
    """페이징 중간 실패 시 부분 원장을 남기면 커버리지가 조용히 준다."""
    s = _src()
    assert "KSD 페이징 중단" in s, "중간 실패가 예외로 안 올라간다"


# ── 산출물 자기신고 (RULE 12) ──────────────────────────────────

def test_meta_self_reports_semantics():
    meta = _ledger().get("_meta") or {}
    assert meta, "_meta 부재 — 산출물이 자기 신고를 안 한다"
    assert meta.get("ex_date_provided") is False, (
        "배당락일 미보유 사실을 신고해야 한다"
    )
    assert "배당락일 아님" in str(meta.get("date_semantics", "")), (
        "날짜 의미 신고가 사라졌다"
    )
    for k in ("bas_dt", "row_count", "ticker_count", "axis", "market",
              "payment_date_filled_pct", "cross_check_dart"):
        assert k in meta, f"_meta 필드 소실: {k}"


def test_meta_counts_match_body():
    d = _ledger()
    meta = d["_meta"]
    body = {k: v for k, v in d.items() if not k.startswith("_")}
    rows = sum(len(v.get("rows") or []) for v in body.values())
    assert meta["ticker_count"] == len(body), "티커 수 자기신고 불일치"
    assert meta["row_count"] == rows, "행 수 자기신고 불일치"


def test_cross_check_separates_known_flags(monkeypatch):
    """🚨 이미 원장이 신고한 건(067900)을 신규 발견으로 세면 안 된다."""
    from api.collectors import dividend_ksd as collector

    ledger = _ledger()
    body = {k: v for k, v in ledger.items() if not k.startswith("_")}
    monkeypatch.setattr(collector, "DATA_DIR", str(ROOT / "data"))
    cc = collector.cross_check_dart(body)
    assert "unit_error_new" in cc and "unit_error_already_flagged" in cc, (
        "신규/기신고 구분이 사라졌다 — 작동 중인 가드가 매번 새 사고로 보인다"
    )


# ── 원장 본문 계약 ─────────────────────────────────────────────

def test_every_row_has_record_date_and_no_ex_date():
    body = {k: v for k, v in _ledger().items() if not k.startswith("_")}
    assert body, "원장이 비었다"
    bad_date = bad_key = 0
    for ent in body.values():
        for r in ent.get("rows") or []:
            if not r.get("date"):
                bad_date += 1
            if "ex_date" in r:
                bad_key += 1
    assert bad_date == 0, f"기준일 없는 행 {bad_date}건"
    assert bad_key == 0, f"행에 ex_date 가 실렸다 {bad_key}건 — 락일 아님"


def test_ticker_shape_is_six_alnum():
    """🚨 KR 종목코드가 전부 숫자라는 전제는 틀렸다.

    실측 — 569개가 `0001A0`·`00088K` 형태다(신형우선주·예탁 대상 비상장 등).
    이들은 우리 검색 유니버스에 **0/569** 로 없다. KSD 가 KRX 상장분만 담지 않기 때문이고,
    걸러내지 않고 두되 **분모를 메타에 신고**한다.
    """
    body = {k: v for k, v in _ledger().items() if not k.startswith("_")}
    bad = [k for k in body if not (len(k) == 6 and k.isalnum() and k.isupper() or
                                   len(k) == 6 and k.isdigit())]
    assert not bad, f"티커 형식 위반 {len(bad)}건: {bad[:5]}"


def test_meta_reports_non_numeric_ticker_share():
    meta = _ledger().get("_meta") or {}
    assert "ticker_non_numeric" in meta, (
        "숫자 아닌 티커 분모 신고가 없다 — 유니버스 밖 종목이 조용히 섞인다"
    )


def test_rows_sorted_and_dated_iso():
    body = {k: v for k, v in _ledger().items() if not k.startswith("_")}
    for tk, ent in list(body.items())[:400]:
        dates = [r["date"] for r in ent.get("rows") or []]
        assert dates == sorted(dates), f"{tk} 회차 정렬 깨짐"
        for d in dates:
            assert len(d) == 10 and d[4] == "-" and d[7] == "-", f"{tk} 날짜 형식 {d}"


def test_derivable_fields_not_stored():
    """액면 대비 배당률 = dps ÷ par × 100 이라 저장하면 29MB 가 된다(실측)."""
    body = {k: v for k, v in _ledger().items() if not k.startswith("_")}
    for ent in list(body.values())[:200]:
        for r in ent.get("rows") or []:
            assert "cash_dividend_rate_pct" not in r, "파생 가능한 값이 행에 저장됐다"


def test_meta_carries_license_and_caveats():
    """🚨 공개 배선하는 세션이 메타만 봐도 제약을 알아야 한다.

    이용허락범위 = 공공저작물 **제2유형(출처표시 + 상업적 이용금지)** 이고,
    상업적 활용에는 한국예탁결제원 정보이용계약이 선행돼야 한다(유료화 시점 직결).
    문서에만 적으면 3일이면 샌다(RULE 12) — 산출물이 스스로 신고한다.
    """
    meta = _ledger().get("_meta") or {}
    assert "제2유형" in str(meta.get("license", "")), "라이선스 유형 신고 소실"
    assert meta.get("attribution_required") == "한국예탁결제원", (
        "출처표시 대상이 사라졌다 — 금융위가 아니라 예탁결제원이다"
    )
    assert "정보이용계약" in str(meta.get("commercial_use", "")), (
        "상업적 이용 제약 신고 소실 — 유료화 시점에 걸린다"
    )
    caveats = meta.get("public_exposure_caveats") or []
    assert len(caveats) >= 3, "공개 노출 함정 신고가 줄었다"
    assert any("기준일 당일" in c for c in caveats), (
        "기준일 당일 매수로는 못 받는다는 경고가 사라졌다"
    )


# ── 공개 리포트 섹션 계약 ──────────────────────────────────────

def _section(ticker: str):
    """🚨 `load_ledger()` 를 쓰지 않는다 — conftest 가 테스트마다 DATA_DIR 을 tmp 로
    격리해서(실 data/ 보호) 로더가 빈 맵을 준다. 다른 계약 테스트와 같이 파일을 직독한다.
    """
    from api.collectors.dividend_ksd import build_report_section
    ent = _ledger().get(ticker)
    if not ent:
        pytest.skip(f"{ticker} 원장 미보유")
    return build_report_section(ent, today="2026-08-23")


def test_report_section_carries_attribution():
    """🚨 라이선스 제2유형 = 출처표시 의무. 이 문구가 화면에 닿는 유일한 경로다."""
    sec = _section("005930")
    assert "한국예탁결제원" in sec["source"], "출처표시가 사라졌다 — 라이선스 위반"
    assert "한국예탁결제원" in sec["note"]


def test_report_section_warns_record_date_is_not_ex_date():
    """기준일 당일에 사면 못 받는다 — 이 경고가 빠지면 사용자가 틀린 날에 산다."""
    sec = _section("005930")
    assert "당일 매수로는 받지 못" in sec["note"], "기준일 오도 경고 소실"
    assert "배당락일 아님" in sec["note"]


def test_report_section_excludes_zero_dps_rows():
    """무배당 28,690건(전체 57.8%)을 그대로 실으면 화면이 0원으로 도배된다."""
    for tk in ("005930", "033780", "000270"):
        sec = _section(tk)
        if not sec:
            continue
        assert all(r["dps"] > 0 for r in sec["recent"]), f"{tk} 0원 행이 이력에 실렸다"


def test_paid_years_window_is_year_bounded():
    """🚨 '오늘-10년' 으로 자르면 경계 연도가 둘 걸려 11 이 나온다(실측).

    화면에서 "10년 중 11년" 으로 읽히므로 창을 연도 단위로 자른다.
    """
    for tk in ("005930", "033780", "000270", "035420"):
        sec = _section(tk)
        if not sec:
            continue
        assert 0 <= sec["paid_years_10y"] <= 10, (
            f"{tk} paid_years_10y={sec['paid_years_10y']} — 10 을 넘을 수 없다"
        )


def test_ttm_sums_quarterly_rounds():
    """분기·중간배당을 합쳐야 연 배당이 된다 — 삼성전자 4회차 합."""
    sec = _section("005930")
    got = sum(r["dps"] for r in sec["recent"]
              if "2025-08-23" < r["record_date"] <= "2026-08-23")
    assert sec["ttm_dps"] == pytest.approx(got), "TTM 합이 회차 합과 다르다"


def test_builder_wires_dividends():
    """빌더가 배당 파트를 실제로 부착하는가 (배선 소실 감시)."""
    b = (ROOT / "api" / "builders" / "stock_report_public_builder.py").read_text(
        encoding="utf-8")
    assert "load_dividends_ledger_for_report" in b, "빌더 배선이 사라졌다"
    assert 's["dividends"]' in b, "리포트에 배당 키를 안 넣는다"


def test_workflow_uses_isolated_collector_entrypoint():
    """패키지 __init__의 무관한 yfinance import가 KSD 실행을 막지 않아야 한다."""
    wf = (ROOT / ".github" / "workflows" / "dividend_ksd.yml").read_text(encoding="utf-8")
    assert "PYTHONPATH=. python api/collectors/dividend_ksd.py" in wf
    assert "python -m api.collectors.dividend_ksd" not in wf


# ── 8/23 N=2 실패에서 나온 계약 ──────────────────────────────

def test_timeouts_fit_inside_job_budget():
    """🚨 N=2 가 여기서 죽었다 — 내부 타임아웃 합이 워크플로 timeout-minutes 를 넘었다.

    첫 판본: 탐색 15회 × 90s + 페이징 8회 × 90s = **34.5분** vs `timeout-minutes: 15`.
    8/23 15:15 정기 run 이 탐색 구간에서 13분 40초를 태우다 cancelled.
    admin.py 에서 같은 날 고친 것과 **같은 형태**(내부 합 > 바깥 예산)다.
    """
    import re
    from api.collectors import dividend_ksd as m

    wf = (ROOT / ".github" / "workflows" / "dividend_ksd.yml").read_text(encoding="utf-8")
    mm = re.search(r"timeout-minutes:\s*(\d+)", wf)
    assert mm, "워크플로 timeout-minutes 가 없다"
    job_budget = int(mm.group(1)) * 60
    assert m._BUDGET_SEC < job_budget, (
        f"수집 예산 {m._BUDGET_SEC}s 가 job 예산 {job_budget}s 이상 — 또 잘린다"
    )
    worst_discover = (m._DISCOVER_LOOKBACK + 1) * m._DISCOVER_TIMEOUT
    assert worst_discover < m._BUDGET_SEC, (
        f"탐색 최악 {worst_discover}s 가 수집 예산을 다 먹는다"
    )


def test_budget_guards_present():
    s = COL.read_text(encoding="utf-8")
    assert "_BUDGET_SEC" in s, "수집 예산 상수가 사라졌다"
    assert "탐색 예산 초과" in s, "탐색 예산 감시가 사라졌다"
    assert "페이징 예산 초과" in s, "페이징 예산 감시가 사라졌다"


def test_discovery_stops_after_transport_outage(monkeypatch):
    """연결 장애를 14일 데이터 0건으로 오인하거나 15일 연속 호출하지 않는다."""
    from api.collectors import dividend_ksd as m
    calls = []

    def fail(*args, **kwargs):
        calls.append(args[0])
        m._LAST_CALL_STATE = "transport_error"
        return None, []

    monkeypatch.setattr(m, "_call", fail)
    monkeypatch.setattr(m.time, "sleep", lambda _: None)
    assert m.discover_bas_dt() is None
    assert len(calls) == m._DISCOVER_ATTEMPTS
    assert len(set(calls)) == 1
    assert m._LAST_DISCOVERY["status"] == "source_unavailable"
    assert m._LAST_DISCOVERY["calls_succeeded"] == 0


def test_discovery_continues_only_after_valid_empty(monkeypatch):
    """정상 0건이면 과거 날짜를 찾고, 연결 실패와 구분한다."""
    from api.collectors import dividend_ksd as m
    seq = iter([(0, []), (123, [{}])])

    def probe(*args, **kwargs):
        out = next(seq)
        m._LAST_CALL_STATE = "valid_with_data" if out[0] else "valid_but_empty"
        return out

    monkeypatch.setattr(m, "_call", probe)
    monkeypatch.setattr(m, "_cached_bas_dt", lambda: None)
    got = m.discover_bas_dt(lookback_days=1)
    assert got is not None
    assert m._LAST_DISCOVERY["status"] == "found"
    assert m._LAST_DISCOVERY["calls_succeeded"] == 2
    assert m._LAST_DISCOVERY["empty_dates"] == 1


def test_report_section_carries_ledger_freshness():
    from api.collectors.dividend_ksd import build_report_section
    ent = {"rows": [{"date": "2025-12-31", "pay_date": "2026-04-01", "dps": 100}]}
    sec = build_report_section(
        ent, "2026-08-27",
        {"bas_dt": "20260823", "generated_at": "2026-08-24T15:28:35+09:00"},
    )
    assert sec["source_bas_dt"] == "20260823"
    assert sec["source_generated_at"].startswith("2026-08-24")


def test_ticker_collision_is_deterministic_and_reported():
    """🚨 같은 6자 티커에 ISIN 이 여럿이다(신형우선주). 순서 운에 맡기면 매일 뒤바뀐다.

    첫 판본은 `setdefault` 라 먼저 온 쪽이 이겼고, 원천 응답 순서가 적재일마다 달라
    내용이 같은데도 파일이 매일 갱신됐다(23종목 뒤바뀜 실측).
    """
    s = COL.read_text(encoding="utf-8")
    assert "rows = sorted(rows" in s, "결정적 정렬이 사라졌다 — 충돌 승자가 순서에 좌우된다"
    meta = _ledger().get("_meta") or {}
    assert "ticker_isin_collisions" in meta, "충돌을 조용히 합치고 있다"


def test_collisions_do_not_touch_numeric_universe():
    """충돌은 신형우선주 계열이고 우리 유니버스(6자리 숫자)와 겹치지 않아야 한다."""
    meta = _ledger().get("_meta") or {}
    sample = meta.get("ticker_isin_collision_sample") or {}
    numeric = [t for t in sample if str(t).isdigit()]
    assert not numeric, f"6자리 숫자 티커가 충돌에 섞였다 — 실데이터 손실: {numeric}"


def test_noop_guard_ignores_bas_dt_when_body_same():
    """🚨 적재일은 매일 바뀐다 — 그걸 비교에 넣으면 내용이 같아도 매일 5.45MB 를 커밋한다."""
    s = COL.read_text(encoding="utf-8")
    assert 'old_meta.get("bas_dt") == bas_dt' not in s, (
        "무변경 판정에 적재일이 다시 들어갔다 — 가드가 무력화된다"
    )
    assert "if same_body and same_cross_check:" in s, (
        "본문 기준 무변경 판정 또는 교차검증 메타 복구 경로가 사라졌다"
    )
