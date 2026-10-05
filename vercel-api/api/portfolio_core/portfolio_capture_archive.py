"""Retain previously captured public filings after rolling feeds advance.

Only a validated captured body can supply a missing document header. Family
links alone do not invent bodies. Dates remain filing dates, never refresh time.
No IO, member state, status promotion or external lookup occurs here.
"""
from collections import Counter
from copy import deepcopy

from .portfolio_contract_facts import validate_contract_fact
from .portfolio_contract_termination import validate_contract_termination
from .portfolio_event_lineage import _name
from .portfolio_public_sources import safe_public_text

ARCHIVE = 'retained-public-capture'


def retain_captured_documents(artifact, companies):
    catalog = deepcopy(companies)
    by_id = {company['id']: company for company in catalog}
    current = {}
    for company in catalog:
        for doc in company.get('documents', []):
            current.setdefault(doc['id'], []).append((company['id'], doc))
    coverage = {'input': 0, 'accepted': 0, 'rejected': 0, 'retained': 0,
                'in_current_feed': 0, 'conflicting_feed': 0}
    staged = []
    for key, validator in [('contract_facts', validate_contract_fact),
                           ('contract_terminations', validate_contract_termination)]:
        raw_rows = artifact.get(key, []) if isinstance(artifact, dict) else []
        if not isinstance(raw_rows, list):
            coverage['shape_errors'] = coverage.get('shape_errors', 0) + 1
            continue
        coverage['input'] += len(raw_rows)
        if len(raw_rows) > 1000:
            coverage['rejected'] += len(raw_rows)
            continue
        for raw in raw_rows:
            try:
                fact = validator(raw)
                issuer = fact['issuer']['id']
                company = by_id[issuer]
                names = {_name(n) for n in company.get('source_names', [company['name']])}
                if (_name(fact['issuer']['name']) not in names
                        or (key == 'contract_terminations' and _name(fact['issuer']['source_name']) not in names)):
                    raise ValueError('capture-issuer-mismatch')
                filing = fact['filing'] if key == 'contract_facts' else {'title': fact['filing_title'], 'filed_on': fact['as_of']}
                receipt = fact['receipt_no']
                if (receipt[:8] != filing['filed_on'].replace('-', '')
                        or safe_public_text(filing['title'], 300) is None):
                    raise ValueError('capture-header-mismatch')
                title = filing.get('source_title', filing['title'])
                if (key == 'contract_facts' and fact['correction'] is not None
                        and 'source_title' not in filing and 'DART:' + receipt not in current):
                    # Never synthesize a correction subtype/title: it would
                    # falsely change the member's source-content read revision.
                    coverage['missing_source_title'] = coverage.get('missing_source_title', 0) + 1
                    raise ValueError('captured-correction-title-missing')
                header = {'id': 'DART:' + receipt, 'title': title,
                          'url': fact['source']['main_url'], 'as_of': filing['filed_on'],
                          'kind': 'disclosure', 'source': 'DART'}
                staged.append((issuer, header))
            except (KeyError, TypeError, ValueError):
                coverage['rejected'] += 1
    counts = Counter(doc['id'] for _, doc in staged)
    for issuer, doc in staged:
        if counts[doc['id']] != 1:
            coverage['rejected'] += 1
            continue
        existing = current.get(doc['id'], [])
        # Never replace a newer feed header or resolve contradictory ownership.
        # Cosmetic title spacing is retained by the feed; fact attach still
        # validates normalized title and correction status independently.
        if existing:
            if any(owner != issuer or any(row.get(k) != doc[k] for k in ('url', 'as_of', 'kind', 'source'))
                   for owner, row in existing):
                coverage['conflicting_feed'] += 1
                coverage['rejected'] += 1
                continue
            coverage['accepted'] += 1
            coverage['in_current_feed'] += 1
            continue
        by_id[issuer].setdefault('documents', []).append({**doc, 'capture_archive': ARCHIVE})
        coverage['accepted'] += 1
        coverage['retained'] += 1
    return catalog, coverage
