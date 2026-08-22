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


def test_cross_check_separates_known_flags():
    """🚨 이미 원장이 신고한 건(067900)을 신규 발견으로 세면 안 된다."""
    cc = _ledger()["_meta"]["cross_check_dart"]
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
