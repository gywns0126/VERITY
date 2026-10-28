"""Published name indexes must keep source, catalog and ambiguity boundaries."""
from copy import deepcopy
import base64
import gzip
import importlib
import json
from unittest.mock import Mock

import pytest

from tests.test_portfolio_prepared_projection import engine, documents, _seed, _run, _canonical


def test_published_names_skip_cold_catalog_matching_and_preserve_output(engine, documents, monkeypatch):
    docs = deepcopy(documents)
    docs['us_stock_report_public.json']['stocks']['AAPL']['name_ko'] = '합성시스템'
    helper, _, artifact, receipt, revision = _seed(engine, docs)
    expected = engine.index_public_news_names(engine.public_news_name_catalog(docs,
        engine.add_public_company_names(docs, engine.project_public_sources(docs)['companies'])))
    matcher = Mock(side_effect=AssertionError('published names should skip source rematching'))
    monkeypatch.setattr(engine, 'public_news_name_catalog', matcher)
    index = _run(engine, docs, artifact, receipt, revision)
    assert index['news_names'] == expected
    assert index['news_names']['aliases']['합성시스템'] == frozenset({'US:AAPL'})
    matcher.assert_not_called()
    assert helper.checked_news_index(artifact, receipt, 'f' * 64, index['by_id']) is None
    wrong_catalog = deepcopy(index['by_id'])
    wrong_catalog['US:AAPL']['name'] = 'Changed Public Name'
    assert helper.checked_news_index(artifact, receipt, revision, wrong_catalog) is None


@pytest.mark.parametrize('change', ['missing', 'unknown-field', 'unknown-company', 'duplicate-name',
    'ambiguous-alias', 'unsafe-name', 'normalized-name', 'receipt'])
def test_malformed_prepared_names_use_existing_matcher(engine, documents, change):
    helper, _, artifact, receipt, revision = _seed(engine, documents)
    expected = _run(engine, documents, artifact, receipt, revision)['news_names']
    names = json.loads(gzip.decompress(base64.b64decode(artifact['news_names']['data'])))
    if change == 'missing':
        del artifact['news_names']
    elif change == 'unknown-field':
        names['extra'] = 'rejected'
    elif change == 'unknown-company':
        names['aliases']['합성회사'] = ['US:UNKNOWN']
    elif change == 'duplicate-name':
        names['catalog_names'].append(names['catalog_names'][0])
    elif change == 'ambiguous-alias':
        names['aliases']['합성회사'] = ['KR:000001', 'US:AAPL']
    elif change == 'unsafe-name':
        names['catalog_names'].append('person@example.com')
    elif change == 'normalized-name':
        names['catalog_names'].append(' UNSAFE SPACING ')
    if change not in ('missing', 'receipt'):
        artifact['news_names']['data'] = base64.b64encode(gzip.compress(json.dumps(names).encode())).decode()
    if change != 'receipt':
        receipt = engine.prepared_business_publisher_receipt(artifact)
    else:
        receipt['artifact_sha256'] = '0' * 64
    index = _run(engine, documents, artifact, receipt, revision)
    assert index['news_names'] == expected


def test_public_name_collision_and_added_identity_preserve_existing_rules(engine, documents):
    docs = deepcopy(documents)
    docs['universe_search.json']['stocks'][0]['name_ko'] = '같은이름'
    docs['universe_search.json']['stocks'][1]['name_ko'] = '같은이름'
    helper, _, artifact, receipt, revision = _seed(engine, docs)
    before = _canonical(artifact)
    index = _run(engine, docs, artifact, receipt, revision)
    assert '같은이름' not in index['news_names']['aliases']
    assert '같은이름' in index['news_names']['catalog_names']
    index['news_names']['aliases'].clear()
    assert _canonical(artifact) == before
    engine._reset_projection_cache_for_tests()
    by_id = deepcopy(index['by_id'])
    by_id['US:OTHER'] = {'id':'US:OTHER', 'market':'US', 'name':'Other Company', 'source_names':['Other Company']}
    assert helper.checked_news_index(artifact, receipt, revision, by_id) is None


@pytest.mark.parametrize('payload', [b'{"aliases":{},"aliases":{},"catalog_names":[]}', b'[]', b'{broken'])
def test_packed_names_reject_duplicate_keys_and_invalid_json(engine, documents, payload):
    helper, _, artifact, receipt, revision = _seed(engine, documents)
    index = _run(engine, documents, artifact, receipt, revision)
    artifact['news_names']['data'] = base64.b64encode(gzip.compress(payload)).decode()
    receipt = engine.prepared_business_publisher_receipt(artifact)
    assert helper.checked_news_index(artifact, receipt, revision, index['by_id']) is None


def test_optional_names_leave_room_for_the_existing_prepared_base(engine, documents, monkeypatch):
    artifact = engine.build_prepared_business_index(documents)
    assert artifact['news_names'] is not None
    baseline = deepcopy(artifact)
    baseline['news_names'] = None
    limit = len(json.dumps(baseline, sort_keys=True, ensure_ascii=True, separators=(',', ':')).encode())
    monkeypatch.setattr(engine, '_PREPARED_ARTIFACT_MAX_BYTES', limit)
    bounded = engine.build_prepared_business_index(documents)
    assert bounded['news_names'] is None
    assert len(json.dumps(bounded, sort_keys=True, ensure_ascii=True, separators=(',', ':')).encode()) <= limit


@pytest.mark.parametrize('corruption', ['truncated', 'trailing', 'oversize'])
def test_names_gzip_stream_boundaries(engine, documents, monkeypatch, corruption):
    helper, _, artifact, receipt, revision = _seed(engine, documents)
    index = _run(engine, documents, artifact, receipt, revision)
    packed = base64.b64decode(artifact['news_names']['data'])
    if corruption == 'truncated':
        packed = packed[:-3]
    elif corruption == 'trailing':
        packed += gzip.compress(b'{}')
    else:
        monkeypatch.setattr(helper, 'ARTIFACT_MAX_BYTES', 1000)
        packed = gzip.compress(b' ' * 2000)
    artifact['news_names']['data'] = base64.b64encode(packed).decode()
    receipt = engine.prepared_business_publisher_receipt(artifact)
    assert helper.checked_news_index(artifact, receipt, revision, index['by_id']) is None
