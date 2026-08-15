

def test_filer_typo_does_not_become_our_number():
    """🚨 제출인 기입 오류를 종목 내부 일관성으로 잡는다 — SYF 2026-08-15 실측.

    동일 인물의 동일 4,000주가 5/1 신고 $305,788, 8/3 신고 $25,240,000,000.
    주당 631만 달러 = 불가능(SYF 는 $70 대). 총액 $25.3B(시총과 맞먹음)가 공개
    발행물에 실려 있었다. 원인은 제출인 오기지만 그대로 실으면 우리 숫자가 된다.
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "f144", "api/builders/us_form144_public_builder.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)

    notices = [
        {"units": 4000, "value_usd": 25_240_000_000.0},   # 오기
        {"units": 4000, "value_usd": 305_788.0},
        {"units": 610, "value_usd": 46_805.0},
        {"units": 721, "value_usd": 55_322.0},
    ]
    m._flag_implied_price_outliers(notices)
    assert notices[0].get("value_suspect") and "기입 오류 의심" in notices[0]["value_suspect"]
    assert not any(n.get("value_suspect") for n in notices[1:])

    # 표본이 얇으면 판정하지 않는다 — 근거 없이 지우느니 남긴다.
    thin = [{"units": 10, "value_usd": 1e9}, {"units": 10, "value_usd": 100.0}]
    m._flag_implied_price_outliers(thin)
    assert not any(n.get("value_suspect") for n in thin)

    # 초고가주라도 자기 중앙값과 비교하므로 오탐이 없다 (BRK.A 류).
    high = [{"units": 1, "value_usd": 700_000.0} for _ in range(4)]
    m._flag_implied_price_outliers(high)
    assert not any(n.get("value_suspect") for n in high)


def test_issuer_cik_extracted_for_attribution():
    """🚨 Form 144 도 발행사를 뽑아 귀속 대조한다 — Form 4 VWAV→SVRE 계열 예방.

    판매자 CIK 색인은 아직 관측되지 않았지만 `issuerCik` 이 원문에 그대로 있어
    대조 비용이 0 이다. 한 번 물린 계열은 공짜면 막아 둔다.
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "f144", "api/builders/us_form144_public_builder.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)

    xml = """<?xml version="1.0"?>
<edgarSubmission>
  <issuerInfo><issuerCik>0001824920</issuerCik><issuerName>IONQ INC</issuerName></issuerInfo>
  <securitiesInformation>
    <noOfUnitsSold>6222</noOfUnitsSold>
    <aggregateMarketValue>340281.18</aggregateMarketValue>
  </securitiesInformation>
  <nameOfPersonForWhoseAccountTheSecuritiesAreToBeSold>JOHN W RAYMOND</nameOfPersonForWhoseAccountTheSecuritiesAreToBeSold>
</edgarSubmission>"""
    p = m._parse_144(xml)
    assert p["_issuer_cik"] == "1824920"      # 선행 0 제거 — int(cik) 비교와 맞춘다
    assert p["units"] == 6222
