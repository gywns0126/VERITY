"""다계좌 라우팅 안전 회귀 테스트 (PM 2026-08-07, 회원 2명 A안).

막으려는 사고는 하나다: **친구가 낸 주문이 오퍼레이터 실계좌로 체결되는 것**,
그리고 그 거울상인 **친구 로그인으로 오퍼레이터 잔고가 보이는 것**.

지키는 불변식:
  1. 슬러그 미지정 → 기본 계좌 폴백 금지. 거절해야 한다.
     (기본값을 두는 순간 "조회 실패 = 남의 계좌" 가 된다.)
  2. allowlist 밖 슬러그 → 해석 거부. 슬러그가 env 키 이름으로 조립되므로
     검증 없이 받으면 임의 env 를 읽어내는 통로가 된다.
  3. 손에 든 토큰의 앱키 ≠ 대상 계좌 앱키 → 발주 차단(BrokerMismatch).
     KIS 토큰은 앱키에 묶여 있다. 이 검사는 앱키별 토큰 발급(RULE 1 2단계)이
     완료되면 자동으로 통과하기 시작한다.
  4. 슬러그 출처는 헤더(서버가 붙인 값)이지 본문이 아니다. 본문은 조작 가능.
"""
import importlib
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load_config(monkeypatch, **env):
    """server.config 를 원하는 env 로 재로드."""
    for k in ("KIS_APP_KEY", "KIS_APP_SECRET", "KIS_ACCOUNT_NO", "BROKER_SLUGS",
              "KIS_APP_KEY__FRIEND", "KIS_APP_SECRET__FRIEND", "KIS_ACCOUNT_NO__FRIEND"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import server.config as cfg
    return importlib.reload(cfg)


# ── 1·2. allowlist 와 fail-closed ────────────────────────────────────
def test_unknown_slug_returns_none(monkeypatch):
    cfg = _load_config(monkeypatch, KIS_APP_KEY="k", KIS_APP_SECRET="s",
                       KIS_ACCOUNT_NO="12345678-01", BROKER_SLUGS="operator")
    assert cfg.broker_credentials("friend") is None
    assert cfg.broker_credentials("") is None
    assert cfg.broker_credentials(None) is None


@pytest.mark.parametrize("evil", [
    "../../etc", "OPERATOR", "operator; rm", "a" * 40, "1operator", "op-erator",
])
def test_malformed_slug_never_resolves(monkeypatch, evil):
    """슬러그는 env 키 이름이 된다 — 형식 이탈은 전부 거부."""
    cfg = _load_config(monkeypatch, KIS_APP_KEY="k", KIS_APP_SECRET="s",
                       KIS_ACCOUNT_NO="12345678-01", BROKER_SLUGS=f"operator,{evil}")
    assert cfg.broker_credentials(evil) is None


def test_allowlisted_slug_without_env_is_none(monkeypatch):
    """allowlist 에 있어도 자격증명 env 가 없으면 None — 반쯤 설정된 상태로 주문 금지."""
    cfg = _load_config(monkeypatch, KIS_APP_KEY="k", KIS_APP_SECRET="s",
                       KIS_ACCOUNT_NO="12345678-01", BROKER_SLUGS="operator,friend")
    assert cfg.broker_credentials("friend") is None


def test_friend_resolves_to_own_credentials(monkeypatch):
    cfg = _load_config(
        monkeypatch, KIS_APP_KEY="opkey", KIS_APP_SECRET="ops", KIS_ACCOUNT_NO="11111111-01",
        BROKER_SLUGS="operator,friend",
        KIS_APP_KEY__FRIEND="frkey", KIS_APP_SECRET__FRIEND="frs",
        KIS_ACCOUNT_NO__FRIEND="22222222-01",
    )
    op = cfg.broker_credentials("operator")
    fr = cfg.broker_credentials("friend")
    assert op["account_no"] == "11111111-01" and op["app_key"] == "opkey"
    assert fr["account_no"] == "22222222-01" and fr["app_key"] == "frkey"
    # 🚨 두 사람의 계좌번호가 절대 같아선 안 된다
    assert op["account_no"] != fr["account_no"]


# ── 3. 토큰-계좌 일치 가드 ───────────────────────────────────────────
def test_mismatched_app_key_blocks_order(monkeypatch):
    """친구 계좌인데 프로세스가 쥔 토큰은 오퍼레이터 것 → 발주 차단."""
    _load_config(
        monkeypatch, KIS_APP_KEY="opkey", KIS_APP_SECRET="ops", KIS_ACCOUNT_NO="11111111-01",
        BROKER_SLUGS="operator,friend",
        KIS_APP_KEY__FRIEND="frkey", KIS_APP_SECRET__FRIEND="frs",
        KIS_ACCOUNT_NO__FRIEND="22222222-01",
    )
    import server.kis_rest_client as krc
    importlib.reload(krc)

    # 오퍼레이터는 통과 (토큰 앱키 == 계좌 앱키)
    assert krc._account_parts_for("operator") == ("11111111", "01")

    # 친구는 차단 — 조용히 오퍼레이터 계좌로 흐르지 않는다
    with pytest.raises(krc.BrokerMismatch):
        krc._account_parts_for("friend")


def test_unknown_slug_raises_not_falls_back(monkeypatch):
    _load_config(monkeypatch, KIS_APP_KEY="opkey", KIS_APP_SECRET="ops",
                 KIS_ACCOUNT_NO="11111111-01", BROKER_SLUGS="operator")
    import server.kis_rest_client as krc
    importlib.reload(krc)
    with pytest.raises(krc.BrokerMismatch):
        krc._account_parts_for("friend")
    with pytest.raises(krc.BrokerMismatch):
        krc._account_parts_for("")


# ── 4. 슬러그 출처 = 헤더, 본문 아님 ─────────────────────────────────
def _src(rel):
    return open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), rel),
                encoding="utf-8").read()


def test_railway_reads_broker_from_header_only():
    s = _src("server/main.py")
    assert 'request.headers.get("X-Verity-Broker")' in s
    # 본문에서 읽으면 클라이언트가 남의 계좌를 지정할 수 있다
    assert 'body.get("broker' not in s
    assert 'body.get("account' not in s


def test_railway_rejects_missing_broker_header():
    s = _src("server/main.py")
    # 주문·잔고 두 엔드포인트 모두 헤더 누락 시 403
    assert s.count("계좌 라우팅 헤더 누락") == 2


def test_vercel_forwards_slug_and_rejects_when_absent():
    s = _src("vercel-api/api/order.py")
    assert 'out["X-Verity-Broker"] = user["limits"]["broker_slug"]' in s
    assert '"Broker account not linked"' in s
    # 기본값 폴백 금지 — defaults 의 broker_slug 는 None 이어야 한다
    assert '"broker_slug": None,' in s


def test_migration_guards_broker_slug_as_service_role_only():
    s = _src("supabase/migrations/029_broker_routing.sql")
    assert "NEW.broker_slug IS DISTINCT FROM OLD.broker_slug" in s
    assert "profiles_broker_slug_uniq" in s          # 한 계좌 = 한 사람
    assert "profiles_broker_slug_format" in s
    assert "seed_krw > 0" in s                        # 배분 분모 0/음수 차단
