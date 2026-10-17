"""Only explicitly reviewed DART HTML may supplement matching KR periods."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "vercel-api" / "api"))
import report_kr_review as review


KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 10, 16, 21, 0, tzinfo=KST)
STOCK = {"ticker": "084010", "name": "대한제강", "corp_code": "00113225"}


def _by_period(rows, year, kind):
    return next(row for row in rows if row["year"] == year and row["period_kind"] == kind)


def test_review_entry_requires_name_ticker_and_supplied_corp_code():
    entry = review.reviewed_entry("084010", STOCK, NOW)
    assert entry and entry["corp_code_match"] == "input_verified"
    assert len(entry["periods"]) == 7
    assert review.reviewed_entry("000000", STOCK, NOW) is None
    assert review.reviewed_entry("084010", {**STOCK, "name": "다른회사"}, NOW) is None
    assert review.reviewed_entry("084010", {**STOCK, "corp_code": "99999999"}, NOW) is None
    assert review.reviewed_entry("084010", {**STOCK, "dart_corp_code": "99999999"}, NOW) is None
    assert review.reviewed_entry("084010", {**STOCK, "financial_evidence": {"corp_code": "99999999"}}, NOW) is None
    assert review.reviewed_entry("084010", {"ticker": "084010", "name": "대한제강"}, NOW)["corp_code_match"] == "registry_only_input_missing"


def test_annual_values_and_sga_components_retain_original_2025_basis():
    rows = review.reviewed_financials("084010", STOCK, [], NOW)
    assert len(rows) == 7
    annual = _by_period(rows, 2025, "annual")
    assert annual["revenue"] == 1247058624052
    assert annual["ocf"] == 39618460129
    assert annual["capex"] == 20703709165
    assert annual["source"].endswith("API 원응답 아님")
    assert annual["metric_sources"]["revenue"]["raw_text"] == "1,247,058,624,052"
    assert annual["metric_sources"]["revenue"]["sha256"]
    assert annual["derived_metrics"]["sga"]["value"] == 73115271001
    assert sum(c["value"] for c in annual["derived_metrics"]["sga"]["components"]) == 73115271001
    assert "sga" not in annual  # Derived source is not a replacement financials operand.
    for year, expected in ((2023, 67071678635), (2024, 66343974431)):
        row = _by_period(rows, year, "annual")
        assert row["derived_metrics"]["sga"]["value"] == expected
        assert sum(c["value"] for c in row["derived_metrics"]["sga"]["components"]) == expected
    entry = review.reviewed_entry("084010", STOCK, NOW)
    assert "1,184,170,129,020" in entry["notes"][0]
    assert "1,247,058,624,052" in entry["notes"][0]
    assert "자동 대체하지 않는다" in entry["notes"][0]


def test_quarter_and_ytd_are_distinct_and_unreported_net_stays_null():
    rows = review.reviewed_financials("084010", STOCK, [], NOW)
    q2 = _by_period(rows, 2026, "quarter")
    h1 = _by_period(rows, 2026, "ytd")
    prior_q2 = _by_period(rows, 2025, "quarter")
    prior_h1 = _by_period(rows, 2025, "ytd")
    assert q2["start"] == "2026-04-01" and "산출" in q2["start_basis"]
    assert prior_q2["start"] == "2025-04-01" and prior_q2["start_basis"]
    assert q2["revenue"] == 387727240066 and q2["op"] == 16292618911
    assert h1["revenue"] == 692069629955 and h1["op"] == 16780631998
    assert h1["net"] == 9033951339 and h1["metric_sources"]["net"]["name"] == "연결 당기순손익"
    assert h1["ocf"] == -6818141298 and h1["capex"] == 5754700573
    assert prior_h1["ocf"] == 48206240793 and prior_h1["capex"] == 11213465993
    assert q2["net"] is q2["ocf"] is q2["capex"] is None
    assert prior_q2["net"] is prior_q2["ocf"] is prior_q2["capex"] is None
    assert prior_h1["net"] is None
    assert q2["metric_sources"]["revenue"]["column"].endswith("3개월")
    assert h1["metric_sources"]["ocf"]["column"] == "제 74 기 반기"


def test_future_review_and_stale_review_fail_closed():
    assert review.reviewed_entry("084010", STOCK, datetime(2026, 10, 15, tzinfo=KST)) is None
    assert review.reviewed_entry("084010", STOCK, datetime(2027, 4, 15, tzinfo=KST)) is None


def test_next_primary_net_keeps_original_history_and_restated_columns_separate():
    now = datetime(2026, 10, 17, tzinfo=KST)
    expected = [('000480', '시알홀딩스', '00148984', -18803450000, 3, 1000),
                ('001130', '대한제분', '00113243', -25137525435, 3, 1),
                ('000680', 'LS네트웍스', '00104698', -19102992842, 2, 1),
                ('241590', '화승엔터프라이즈', '01128613', -27121361108, 3, 1)]
    for ticker, name, corp, net, count, multiplier in expected:
        rows = review.reviewed_financials(ticker, {'ticker':ticker,'name':name,'corp_code':corp}, [], now)
        assert len(rows) == count
        annual = _by_period(rows, 2025, 'annual')
        assert annual['net'] == net and annual['sga'] > 0
        assert annual['revenue'] - annual['cost_of_sales'] - annual['sga'] == annual['op']
        assert annual['metric_sources']['net']['unit_multiplier'] == multiplier
        if ticker == '000480':
            assert _by_period(rows, 2024, 'annual')['net'] == -1278597000
        if ticker == '000680':
            prior = _by_period(rows, 2024, 'annual')
            assert (prior['net'], prior['op']) == (-17593580482,30187565175)
            assert not any(r['year'] == 2023 for r in rows)


def test_next_primary_totals_exclude_discontinued_and_attribution_rows():
    now = datetime(2026, 10, 17, tzinfo=KST)
    expected = [('214270', 'FSN', '01061497', 30518488142, -15863077578),
                ('033640', '네패스', '00227333', 23761125843, 20158821632),
                ('009580', '무림P&P', '00119007', -24460014863, -33085743414),
                ('035080', '그래디언트', '00244561', -29581406856, -24705775927)]
    for ticker, name, corp, op, net in expected:
        stock = {'ticker': ticker, 'name': name, 'corp_code': corp}
        rows = review.reviewed_financials(ticker, stock, [], now)
        assert len(rows) == 3
        annual = _by_period(rows, 2025, 'annual')
        assert (annual['op'], annual['net']) == (op, net)
        for key in ('revenue', 'op', 'net'):
            assert annual['metric_sources'][key]['unit_multiplier'] == 1
            assert annual['metric_sources'][key]['fs_div'] == 'CFS'
            assert annual['accession'] in annual['metric_sources'][key]['source_url']
        if ticker == '214270':
            assert _by_period(rows, 2023, 'annual')['net'] == -24785408918
            assert _by_period(rows, 2024, 'annual')['revenue'] == 185400336138
            assert annual.get('sga') is None
        if ticker == '033640':
            assert _by_period(rows, 2023, 'annual')['op'] == 10069328909
        if ticker == '009580':
            assert _by_period(rows, 2023, 'annual')['net'] == -21635976438
        if ticker == '035080':
            assert _by_period(rows, 2024, 'annual')['net'] == -25955494157


def test_future_filing_is_not_returned_even_if_review_date_is_current(monkeypatch):
    fixture = deepcopy(review._registry())
    entry = fixture["084010"]
    entry["documents"]["half_income"]["filed"] = "2026-10-17"
    monkeypatch.setattr(review, "_registry", lambda: fixture)
    eligible = review.reviewed_entry("084010", STOCK, NOW)
    assert eligible and len(eligible["periods"]) == 3
    assert all(row["period_kind"] == "annual" for row in eligible["periods"])


def test_newer_or_unknown_same_period_source_is_preserved_without_mutation():
    base = _by_period(review.reviewed_financials("084010", STOCK, [], NOW), 2026, "ytd")
    newer = {**base, "filed": "2026-09-01", "accession": "20260901000001", "ocf": 123}
    unknown = {**base, "filed": "", "ocf": 456}
    for existing in (newer, unknown):
        before = deepcopy(existing)
        result = review.reviewed_financials("084010", STOCK, [existing], NOW)
        assert result[0] == before
        assert existing == before
        assert len([r for r in result if r.get("start") == base["start"] and r.get("end") == base["end"] and r.get("period_kind") == "ytd"]) == 1


def test_older_filing_replaced_and_same_filing_only_fills_missing_metrics():
    old = {"year": 2026, "start": "2026-01-01", "end": "2026-06-30", "period_kind": "ytd",
           "currency": "KRW", "fs_div": "CFS", "filed": "2026-07-01", "accession": "20260701000001", "revenue": 1}
    replaced = _by_period(review.reviewed_financials("084010", STOCK, [old], NOW), 2026, "ytd")
    assert replaced["revenue"] == 692069629955 and replaced["accession"] == "20260814003201"
    same = {**old, "filed": "2026-08-14", "accession": "20260814003201", "revenue": 777, "ocf": None}
    filled = _by_period(review.reviewed_financials("084010", STOCK, [same], NOW), 2026, "ytd")
    assert filled["revenue"] == 777 and filled["ocf"] == -6818141298
    assert "revenue" not in filled["metric_sources"]
    assert filled["metric_sources"]["ocf"]["raw_text"] == "(6,818,141,298)"
    assert old["revenue"] == 1 and same["ocf"] is None


def test_separate_statements_require_matching_document_scope(monkeypatch):
    fixture = deepcopy(review._registry())
    entry = fixture['084010']
    for doc in entry['documents'].values():
        if doc.get('fs_div') == 'CFS':
            doc['fs_div'] = 'OFS'
    for row in entry['periods']:
        row['fs_div'] = 'OFS'
    monkeypatch.setattr(review, '_registry', lambda: fixture)
    separate = review.reviewed_financials('084010', STOCK, [], NOW)
    assert len(separate) == 7 and all(r['fs_div'] == 'OFS' for r in separate)
    entry['documents']['half_income']['fs_div'] = 'CFS'
    eligible = review.reviewed_entry('084010', STOCK, NOW)
    assert len(eligible['periods']) == 3
    assert all(r['period_kind'] == 'annual' for r in eligible['periods'])
    for row in entry['periods']:
        row['fs_div'] = 'UNKNOWN'
    assert review.reviewed_entry('084010', STOCK, NOW) is None


def test_latest_peer_reviews_preserve_quarter_ytd_scope_and_source():
    now = datetime(2026, 10, 17, tzinfo=KST)
    expected = [('104700', '한국철강', '00687711', 173809519338, -6284385117, -12691130328),
                ('460860', '동국제강', '01765265', 995514578458, 45563446844, 137488041100)]
    for ticker, name, corp, revenue, op, cash in expected:
        rows = review.reviewed_financials(ticker, {'ticker': ticker, 'name': name, 'corp_code': corp}, [], now)
        assert len(rows) == (6 if ticker == '460860' else 4)
        q2, h1 = _by_period(rows, 2026, 'quarter'), _by_period(rows, 2026, 'ytd')
        assert q2['start'] == '2026-04-01' and h1['start'] == '2026-01-01'
        assert q2['revenue'] == revenue and q2['op'] == op
        assert q2['revenue'] - q2['cost_of_sales'] - q2['sga'] == q2['op']
        assert h1['ocf'] == cash and h1['capex'] > 0
        assert q2['ocf'] is q2['capex'] is None
        assert q2['metric_sources']['sga']['fs_div'] == 'OFS'
        assert all(r['fs_div'] == 'OFS' for r in rows)
        assert all('rcpNo=' + r['accession'] in m['source_url'] for r in rows for m in r['metric_sources'].values())
        if ticker == '460860':
            annual = _by_period(rows, 2025, 'annual')
            assert annual['net'] == 8231853074 and annual['sga'] == 214066943596
            assert annual['revenue'] - annual['cost_of_sales'] - annual['sga'] == annual['op']
            assert not any(r['year'] == 2023 for r in rows)  # First seven-month year is not a full annual.


def test_total_net_review_does_not_reuse_noncontrolling_or_parent_amounts():
    now = datetime(2026, 10, 17, tzinfo=KST)
    for ticker, name, expected in [('018880', '한온시스템', {2024: -358595798106, 2025: -197268294891}),
                                    ('331920', '셀레믹스', {2024: 12266469564, 2025: -4036458382})]:
        rows = review.reviewed_financials(ticker, {'ticker': ticker, 'name': name}, [], now)
        assert len(rows) == 2
        for row in rows:
            assert row['net'] == expected[row['year']] and row['fs_div'] == 'CFS'
            assert row['metric_sources']['net']['name'] == '당기순이익(손실)'
            assert row['metric_sources']['net']['sha256']


def test_table_units_are_converted_once_with_raw_cells_preserved(monkeypatch):
    from datetime import date
    for unit, multiplier in [('천원', 1000), ('백만원', 1000000)]:
        fixture = deepcopy(review._registry())
        entry = fixture['018880']
        entry['documents']['annual_income']['unit'] = unit
        for row in entry['periods']:
            for metric in row['metrics'].values():
                metric['value'] = review._amount(metric['raw']) * multiplier
        monkeypatch.setattr(review, '_registry', lambda: fixture)
        row = review.reviewed_financials('018880', {'ticker':'018880','name':'한온시스템'}, [], date(2026,10,17))[0]
        source = row['metric_sources']['net']
        assert row['net'] == review._amount(source['raw_text']) * multiplier
        assert source['reported_unit'] == unit and source['unit_multiplier'] == multiplier
        entry['periods'][0]['metrics']['net']['value'] //= multiplier
        assert len(review.reviewed_entry('018880', {'ticker':'018880','name':'한온시스템'}, date(2026,10,17))['periods']) == 1
        entry['documents']['annual_income']['unit'] = '단위 미확인'
        assert review.reviewed_entry('018880', {'ticker':'018880','name':'한온시스템'}, date(2026,10,17)) is None


def test_large_issuer_losses_and_rewritten_comparatives_use_reported_totals():
    now = datetime(2026, 10, 17, tzinfo=KST)
    cases = [('051910','LG화학',-977063000000,515011000000,1000000),
             ('011170','롯데케미칼',-2476176326250,-1825555752135,1),
             ('097950','CJ제일제당',-416955408000,345925769000,1000),
             ('000070','삼양홀딩스',-298132876106,89491916474,1)]
    for ticker,name,current,prior,multiplier in cases:
        rows=review.reviewed_financials(ticker,{'ticker':ticker,'name':name},[],now)
        assert len(rows)==2
        assert _by_period(rows,2025,'annual')['net']==current
        assert _by_period(rows,2024,'annual')['net']==prior
        assert all(r['metric_sources']['net']['unit_multiplier']==multiplier for r in rows)
        assert all(r['metric_sources']['net']['name'] in ('당기순이익(손실)','당기순손실') for r in rows)


def test_discontinued_results_are_not_operating_profit_or_total_net():
    now = datetime(2026, 10, 17, tzinfo=KST)
    holdings = review.reviewed_financials('005440', {'ticker':'005440','name':'현대지에프홀딩스'}, [], now)
    assert _by_period(holdings,2025,'annual')['op'] == 274073694000
    assert _by_period(holdings,2024,'annual')['op'] == 198099994000
    assert _by_period(holdings,2023,'annual')['op'] == -11033826000
    assert _by_period(holdings,2025,'annual')['net'] == 518661888000
    wia = review.reviewed_financials('011210', {'ticker':'011210','name':'현대위아'}, [], now)
    current = _by_period(wia,2025,'annual')
    assert current['op'] == 204413000000 and current['op'] != -43559000000
    assert current['net'] == 116932000000 and current['net'] != 160491000000
    assert _by_period(wia,2024,'annual')['op'] == 218810000000
    assert current['metric_sources']['net']['name'] == '당기순이익'
    assert current['metric_sources']['op']['unit_multiplier'] == 1000000


def test_ecopro_and_kakaogames_total_losses_do_not_use_positive_nci_parts():
    now = datetime(2026, 10, 17, tzinfo=KST)
    eco = review.reviewed_financials('086520', {'ticker':'086520','name':'에코프로','corp_code':'00536541'}, [], now)
    current = _by_period(eco,2025,'annual')
    assert current['net'] == -105539603168 and current['net'] != 44234880608
    assert _by_period(eco,2023,'annual')['op'] == 298172334242
    assert _by_period(eco,2024,'annual')['net'] == -295367033134
    assert current['metric_sources']['net']['name'] == '당기순이익(손실)'
    games = review.reviewed_financials('293490', {'ticker':'293490','name':'카카오게임즈','corp_code':'01137383'}, [], now)
    current = _by_period(games,2025,'annual')
    assert current['net'] == -143084637075 and current['net'] != 611118797
    assert current['op'] == -39590701112 and current['revenue'] == 465018566528
    assert {r['year'] for r in games} == {2024,2025}  # Original 2023 history is not silently restated.
    assert 'sga' not in current  # Operating expenses are not reported SG&A.
    assert current['metric_sources']['net']['unit_multiplier'] == 1
    assert review.reviewed_entry('293490', {'ticker':'293490','name':'카카오게임즈','corp_code':'00258801'}, now) is None


def test_next_priority_totals_and_operating_profit_keep_scope_and_versions():
    now = datetime(2026, 10, 17, tzinfo=KST)
    sajo = review.reviewed_financials('003960', {'ticker':'003960','name':'사조대림','corp_code':'00109718'}, [], now)
    assert _by_period(sajo,2025,'annual')['net'] == -73563368883
    assert _by_period(sajo,2025,'annual')['net'] != 5069145678
    sk = review.reviewed_financials('302440', {'ticker':'302440','name':'SK바이오사이언스','corp_code':'01319899'}, [], now)
    assert _by_period(sk,2025,'annual')['net'] == -56173210192
    assert _by_period(sk,2024,'annual')['net'] == -50117070464
    assert _by_period(sk,2023,'annual')['net'] == 22317719237
    sns = review.reviewed_financials('101490', {'ticker':'101490','name':'에스앤에스텍','corp_code':'00411048'}, [], now)
    assert _by_period(sns,2025,'annual')['op'] == 50389752346
    assert _by_period(sns,2024,'annual')['op'] == 29478688017
    assert _by_period(sns,2023,'annual')['op'] == 25039402690
    assert _by_period(sns,2024,'annual')['net'] == 30313647619
    assert 'sga' not in _by_period(sns,2025,'annual')
    lnc = review.reviewed_financials('290650', {'ticker':'290650','name':'엘앤씨바이오','corp_code':'01181515'}, [], now)
    previous = _by_period(lnc,2024,'annual')
    assert _by_period(lnc,2025,'annual')['net'] == -138246706187
    # The report compares the latest filing's complete restated column, while
    # annual history is separately corrected to its original-as-filed total.
    assert previous['net'] == 141496608088 and previous['net'] != 140965124092
    assert previous['revenue'] == 72032432117 and previous['op'] == 3869170258
    assert previous['accession'] == '20260324000006'
    assert 'rcpNo=20260324000006' in previous['metric_sources']['net']['source_url']
    notes = review.reviewed_entry('290650', {'ticker':'290650','name':'엘앤씨바이오'}, now)['notes']
    assert '140,965,124,092' in notes[0] and '141,496,608,088' in notes[0]


def test_owner_discontinued_and_renamed_issuer_sources_keep_exact_annual_scope():
    now = datetime(2026, 10, 17, tzinfo=KST)
    cases = (
        ('200130','콜마비앤에이치','01032404',-22639015475,26645965589),
        ('282880','코윈로보틱스','01211232',-17618390526,-25447396955),
        ('092200','디아이씨','00112165',-4771081140,18550433161),
        ('045660','에이텍','00256502',393882122,8698700770),
    )
    for ticker,name,corp,net,op in cases:
        rows=review.reviewed_financials(ticker,{'ticker':ticker,'name':name,'corp_code':corp},[],now)
        assert len(rows)==3
        current=_by_period(rows,2025,'annual')
        assert (current['net'],current['op'])==(net,op)
        assert current['revenue']-current['cost_of_sales']-current['sga']==op
        assert current['metric_sources']['net']['unit_multiplier']==1
        assert review.reviewed_entry(ticker,{'ticker':ticker,'name':name,'corp_code':'99999999'},now) is None
    atec=review.reviewed_financials('045660',{'ticker':'045660','name':'에이텍'},[],now)
    prior=_by_period(atec,2024,'annual')
    assert (prior['revenue'],prior['op'])==(45526630657,2075095975)
    assert prior['op']!=1462480218  # Historical original is not this recast column.
    assert _by_period(atec,2023,'annual')['op']==-712489950


def test_primary_cohort_totals_preserve_units_scope_and_document_identity():
    now = datetime(2026, 10, 17, tzinfo=KST)
    cases = (
        ('217330','싸이토젠','01046391',-12339826935),
        ('307180','아이엘','01326279',-10831408385),
        ('267320','나인테크','01208849',-17422714499),
        ('047310','파워로직스','00269612',-12318778055),
        ('011280','태림포장','00153524',-9187452000),
        ('304360','에스바이오메딕스','01258020',-7059342697),
        ('095190','신화프리텍','00526951',-6941945613),
        ('172670','에이엘티','00493325',-8866390769),
        ('101360','에코앤드림','00619640',-8596919787),
        ('083310','엘오티베큠','00484682',-7781162151),
    )
    for ticker,name,corp,net in cases:
        stock = {'ticker':ticker,'name':name,'corp_code':corp}
        rows = review.reviewed_financials(ticker,stock,[],now)
        assert len(rows) == (2 if ticker == '095190' else 3)
        current = _by_period(rows,2025,'annual')
        assert current['net'] == net
        assert all(r['fs_div'] == ('OFS' if ticker == '095190' else 'CFS') for r in rows)
        assert review.reviewed_entry(ticker,{**stock,'corp_code':'99999999'},now) is None
        for row in rows:
            for key,source in row['metric_sources'].items():
                assert row[key] == review._amount(source['raw_text']) * source['unit_multiplier']
                assert row['accession'] in source['source_url']
        residual = current['revenue'] - current['cost_of_sales'] - current['sga'] - current['op']
        assert residual == (2072674155 if ticker == '267320' else 0)
        if ticker == '011280':
            assert current['metric_sources']['net']['reported_unit'] == '천원'
            assert current['metric_sources']['net']['unit_multiplier'] == 1000
        if ticker == '095190':
            assert not any(r['year'] == 2023 for r in rows)
            assert current['net'] != 2226144074  # Continuing-only net is not total.


def test_equity_reported_net_and_restated_columns_are_not_ownership_sums():
    now = datetime(2026, 10, 17, tzinfo=KST)
    rows = review.reviewed_financials('304360',{'ticker':'304360','name':'에스바이오메딕스'},[],now)
    current = _by_period(rows,2025,'annual')
    assert current['net'] == -7059342697 and current['net'] != -8122245545
    source = current['metric_sources']['net']
    assert source['column'] == '2025년 자본 합계'
    assert source['sha256'] == '3206dce2f13dfcdff7a23fc0e85d843587cad4455f5e7714fa5df335fee078ec'
    assert 'eleId=22' in source['source_url']
    assert 'eleId=21' in current['metric_sources']['op']['source_url']
    prior = _by_period(rows,2023,'annual')
    assert prior['net'] == -9257682623 and prior['net'] != -6460345203
    power = review.reviewed_financials('047310',{'ticker':'047310','name':'파워로직스'},[],now)
    for year,net in ((2023,16370375160),(2024,12422763198)):
        period = _by_period(power,year,'annual')
        assert period['net'] == net and period['accession'] == '20260602000010'


def test_next_ten_primary_income_totals_keep_exact_scope_and_identity():
    now = datetime(2026, 10, 17, tzinfo=KST)
    cases = (
        ('086960','MDS테크','00445841',6190210178,5813313438),
        ('108860','셀바스AI','00666064',-4343459641,1482121007),
        ('021050','서원','00131197',-34369841,53323111520),
        ('051980','중앙첨단소재','00347716',-5504612917,-4562905485),
        ('065510','휴비츠','00398668',-4940420274,5553331465),
        ('032820','우리기술','00231044',-4104661336,-5486712823),
        ('299170','더블유에스아이','01318261',-3494309836,3915666692),
        ('242040','나무AX','01136348',-1878681541,2251203375),
        ('085310','엔케이','00172228',-3694204031,-647803589),
        ('306620','지아이에스','01325429',-3648033893,1631644343),
    )
    for ticker,name,corp,net,op in cases:
        stock={'ticker':ticker,'name':name,'corp_code':corp}
        rows=review.reviewed_financials(ticker,stock,[],now)
        assert len(rows)==(2 if ticker=='021050' else 3)
        current=_by_period(rows,2025,'annual')
        assert (current['net'],current['op'])==(net,op)
        assert all(r['fs_div']=='CFS' for r in rows)
        assert review.reviewed_entry(ticker,{**stock,'corp_code':'99999999'},now) is None
        for row in rows:
            for key,source in row['metric_sources'].items():
                assert row[key]==review._amount(source['raw_text'])*source['unit_multiplier']
                assert row['accession'] in source['source_url']


def test_operating_expense_is_not_sga_and_original_periods_are_not_blended():
    now = datetime(2026, 10, 17, tzinfo=KST)
    ai=review.reviewed_financials('108860',{'ticker':'108860','name':'셀바스AI'},[],now)
    for row in ai:
        assert 'sga' not in row and 'cost_of_sales' not in row
        assert set(row['metric_sources'])=={'revenue','op','net'}
    hu=_by_period(review.reviewed_financials('065510',{'ticker':'065510','name':'휴비츠'},[],now),2025,'annual')
    assert hu['sga']==48183071752
    assert hu['metric_sources']['sga']['name']=='판매 및 일반관리비'
    central=review.reviewed_financials('051980',{'ticker':'051980','name':'중앙첨단소재'},[],now)
    prior=_by_period(central,2023,'annual')
    assert prior['op']==56864463 and prior['op']!=46944494
    assert prior['accession']=='20260323001194'
    seowon=review.reviewed_financials('021050',{'ticker':'021050','name':'서원'},[],now)
    assert not any(r['year']==2023 for r in seowon)
    assert review.reviewed_entry('242040',{'ticker':'242040','name':'나무기술'},now) is None


def test_equal_same_filing_number_gains_primary_evidence_without_losing_collected_source():
    now = datetime(2026,10,17,tzinfo=KST)
    stock={'ticker':'086960','name':'MDS테크'}
    primary=_by_period(review.reviewed_financials('086960',stock,[],now),2025,'annual')
    collected={k:primary[k] for k in ('year','start','end','period_kind','currency','fs_div','accession','filed','net')}
    original_source={'name':'당기순이익(손실)','account_id':None,'source_url':primary['source_url'],
                     'start':primary['start'],'end':primary['end'],'currency':'KRW'}
    collected['metric_sources']={'net':original_source}
    before=deepcopy(collected)
    result=_by_period(review.reviewed_financials('086960',stock,[collected],now),2025,'annual')
    assert result['net']==before['net']
    source=result['metric_sources']['net']
    assert source['raw_text']=='6,190,210,178'
    assert source['sha256']=='2a63fc29a66a07e05c6e52591300cd0c40e4e2c61de74ade61b0d885e9f0ed26'
    assert source['collected_source']==original_source
    assert 'API 원응답 아님' in source['source_type']
    assert collected==before
    repeated=_by_period(review.reviewed_financials('086960',stock,[result],now),2025,'annual')
    assert repeated==result  # No nested provenance growth on repeated rendering.


def test_same_filing_evidence_never_overwrites_conflicting_or_already_detailed_sources():
    now = datetime(2026,10,17,tzinfo=KST)
    stock={'ticker':'086960','name':'MDS테크'}
    primary=_by_period(review.reviewed_financials('086960',stock,[],now),2025,'annual')
    variants=[{'source_url':'https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260318001051'},
              {'source_url':'https://dart.fss.or.kr/dsaf001/main.do?rcpNo=202603180010500'},
              {'source_url':'https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260318001050&rcpNo=20260318001051'},
              {'source_url':'https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260318001050&rcpNo='},
              {},
              {'source_url':primary['source_url'],'source_type':'unverified'},
              {'source_url':primary['source_url'],'accession':'20260318001051'},
              {'source_url':primary['source_url'],'rcept_no':'20260318001051'},
              {'source_url':primary['source_url'],'filed':'2026-03-19'},
              {'source_url':'https://dart.fss.or.kr/report/viewer.do?rcpNo=20260318001050&dcmNo=99999999'},
              {'source_url':primary['source_url']+'&dcmNo=99999999'},
              {'source_url':primary['source_url'],'document_version':'different'},
              {'source_url':primary['source_url'],'account_id':'ifrs-full_ProfitLossAttributableToOwnersOfParent'},
              {'currency':'USD'},{'fs_div':'OFS'},{'end':'2024-12-31'},
              {'ticker':'000000'},{'stock_code':'000000'},{'corp_code':'99999999'},
              {'issuer_id':'99999999'},
              {'raw_text':'already retained'},{'sha256':'a'*64}]
    for variant in variants:
        source={'source_url':primary['source_url'],**variant} if variant else {}
        row={**primary,'metric_sources':{'net':source}}
        result=_by_period(review.reviewed_financials('086960',stock,[row],now),2025,'annual')
        assert result['metric_sources']['net']==source
    wrong={**primary,'net':777,'metric_sources':{}}
    result=_by_period(review.reviewed_financials('086960',stock,[wrong],now),2025,'annual')
    assert result['net']==777 and 'net' not in result['metric_sources']


def _inception_review_entry(base=None):
    entry = deepcopy(base if base is not None else review._registry()['489790'])
    entry['documents']['inception_income'] = {
        'accession':'20250317000812','filed':'2025-03-17','unit':'원',
        'currency':'KRW','fs_div':'CFS','section':'연결 포괄손익계산서',
        'url':'https://dart.fss.or.kr/report/viewer.do?rcpNo=20250317000812&dcmNo=10415585&eleId=21&offset=273070&length=19363&dtd=dart4.xsd',
        'sha256':'3adf9e10ce84dc053c73264f9721f14d4a306da7ca828cb3f6eaf83846d01bf3',
        'headers':['연결 포괄손익계산서','제 1 기 2024.09.01 부터 2024.12.31 까지','(단위 : 원)'],
    }
    entry['partial_periods'] = [{
        'year':2024,'start':'2024-09-01','end':'2024-12-31','period_kind':'inception_partial',
        'currency':'KRW','fs_div':'CFS','accession':'20250317000812','filed':'2025-03-17',
        'metrics':{
            'revenue':{'value':493322362934,'raw':'493,322,362,934','account':'I.매출 (주25,26,32)','column':'제 1 기','document':'inception_income'},
            'op':{'value':-120362075,'raw':'(120,362,075)','account':'VI.영업이익(손실)','column':'제 1 기','document':'inception_income'},
            'net':{'value':3210792631,'raw':'3,210,792,631','account':'XV.당기순이익','column':'제 1 기','document':'inception_income'},
        },
    }]
    return entry


def test_489790_original_first_close_is_separate_from_annual_and_one_column(monkeypatch):
    base = deepcopy(review._registry()['489790'])
    entry = _inception_review_entry(base)
    monkeypatch.setattr(review, '_registry', lambda: {'489790': entry})
    stock = {'ticker':'489790','name':'한화비전','corp_code':'01867758'}
    now = datetime(2026,10,17,tzinfo=KST)
    before = deepcopy(stock)
    reviewed = review.reviewed_entry('489790',stock,now)
    assert [r['year'] for r in reviewed['periods']] == [2025]
    assert len(reviewed['partial_periods']) == 1
    first = reviewed['partial_periods'][0]
    assert (first['start'],first['end'],first['period_kind']) == ('2024-09-01','2024-12-31','inception_partial')
    assert (first['revenue'],first['op'],first['net']) == (493322362934,-120362075,3210792631)
    assert {m['column'] for m in first['metric_sources'].values()} == {'제 1 기'}
    assert {m['sha256'] for m in first['metric_sources'].values()} == {entry['documents']['inception_income']['sha256']}
    assert [r['year'] for r in review.reviewed_financials('489790',stock,[],now)] == [2025]
    assert stock == before
    for alter in [
        lambda e:e['documents']['inception_income'].update(sha256='a'*64),
        lambda e:e['documents']['inception_income'].update(url=e['documents']['annual_income']['url']),
        lambda e:e['partial_periods'][0].update(start='2024-01-01'),
        lambda e:e['partial_periods'][0].update(period_kind='annual'),
        lambda e:e['partial_periods'][0].update(currency='USD'),
        lambda e:e['partial_periods'][0].update(fs_div='OFS'),
        lambda e:e['partial_periods'][0].update(accession='20260316001204'),
        lambda e:e['partial_periods'][0].update(filed='2026-03-16'),
        lambda e:e['partial_periods'][0]['metrics']['revenue'].update(column='제 2 기'),
        lambda e:e['partial_periods'][0]['metrics']['op'].update(value=5466174056,raw='5,466,174,056'),
        lambda e:e['partial_periods'][0]['metrics']['net'].update(value=31701255717,raw='31,701,255,717'),
    ]:
        bad = _inception_review_entry(base)
        alter(bad)
        monkeypatch.setattr(review,'_registry',lambda bad=bad:{'489790':bad})
        assert review.reviewed_entry('489790',stock,now)['partial_periods'] == []
    assert review.reviewed_entry('489790',{**stock,'corp_code':'00000000'},now) is None
