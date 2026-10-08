#!/usr/bin/env python3
"""Bounded public DART HTML capture from the existing feed, local output only.

No API key, member input, upload or publication. Select newest uncaptured
contracts from the source catalog, never handpicked ticker allowlists.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time
import uuid
import urllib.error
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from api.intelligence.portfolio_public_sources import load_public_sources, project_public_sources, PUBLIC_SOURCE_MAX_BYTES
from api.intelligence.portfolio_contract_facts import extract_viewer_url, parse_contract_facts, validate_contract_fact
from api.intelligence.portfolio_event_lineage import _contract_title, parse_dart_family, validate_family, DART
from api.intelligence.portfolio_evidence import _validate_artifact
from api.intelligence.portfolio_company_names import add_public_company_names
from api.intelligence.portfolio_contract_termination import parse_contract_termination, validate_contract_termination
from api.intelligence.portfolio_filing_excerpts import validate_filing_excerpts
from api.intelligence.portfolio_annual_customer_tables import validate_annual_customer_capture


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('public-redirect-refused')


_CAPTURE_FIELDS = ('contract_facts', 'documentFamilies', 'contract_terminations', 'filing_excerpts', 'annual_customer_tables')
_JSON_LIMIT = 8 * 1024 * 1024


def _strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate-json-key')
        result[key] = value
    return result


def _read_regular_json(path, maximum=_JSON_LIMIT):
    """Read one bounded regular file without following its final symlink."""
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError('invalid-json-input-path')
        chunks, size = [], 0
        while True:
            chunk = os.read(descriptor, min(65536, maximum + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
            if size > maximum:
                raise ValueError('json-input-too-large')
    finally:
        os.close(descriptor)
    try:
        value = json.loads(b''.join(chunks).decode('utf-8'), object_pairs_hook=_strict_object)
    except (UnicodeError, json.JSONDecodeError):
        raise ValueError('invalid-json-input') from None
    if not isinstance(value, dict):
        raise ValueError('invalid-json-input')
    return value


def _validate_base_catalog(path):
    """Delegate the closed base schema check to the existing Node validator."""
    raw_value = _read_regular_json(path)
    raw = json.dumps(raw_value, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    builder = Path(__file__).with_name('build-public-source-filter.cjs').resolve()
    script = (
        'const fs=require("node:fs"); '
        'const {validatePublicCatalog}=require(' + json.dumps(str(builder)) + '); '
        'validatePublicCatalog(JSON.parse(fs.readFileSync(0,"utf8")));'
    )
    try:
        result = subprocess.run(['node', '-e', script], input=raw, capture_output=True,
                                timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise ValueError('base-catalog-validator-unavailable') from None
    if result.returncode != 0:
        raise ValueError('invalid-base-catalog')
    return raw_value


def _validate_capture_fields(baseline, evidence):
    """Validate only the explicit, receipt-unique local source arrays."""
    _validate_artifact(evidence)
    baseline = baseline if isinstance(baseline, dict) else {}
    for field, validator in zip(_CAPTURE_FIELDS,
                                (validate_contract_fact, validate_family, validate_contract_termination, validate_filing_excerpts, validate_annual_customer_capture)):
        rows = evidence.get(field, [])
        prior = baseline.get(field, [])
        if not isinstance(rows, list) or not isinstance(prior, list):
            raise ValueError('invalid-contract-history')
        receipts = [validator(row)['receipt_no'] for row in rows]
        prior_receipts = [validator(row)['receipt_no'] for row in prior]
        if len(receipts) != len(set(receipts)):
            raise ValueError('duplicate-contract-receipt')
        if not set(prior_receipts).issubset(receipts):
            raise ValueError('contract-history-loss')


def refresh_base(previous, base_path):
    """Build a review copy from a strict fresh base plus only validated captures."""
    if not isinstance(previous, dict):
        raise ValueError('invalid-prior-evidence')
    _validate_capture_fields(previous, previous)
    base = _validate_base_catalog(base_path)
    # A valid but older/default producer is not a replacement for the reviewed
    # receipt-bearing structured source. Preserve the current file on a source-
    # family downgrade; a later same-family refresh may still change its rows.
    def has_structured(value):
        return any(isinstance(row, dict) and row.get('kind') == 'dart-structured-relation'
                   for row in value.get('sources', {}).values())
    if has_structured(previous) and not has_structured(base):
        raise ValueError('structured-source-family-regression')
    refreshed = deepcopy(base)
    for field in _CAPTURE_FIELDS:
        if field in previous:
            refreshed[field] = deepcopy(previous[field])
    _validate_capture_fields(previous, refreshed)
    if len(json.dumps(refreshed, ensure_ascii=False, indent=2).encode('utf-8')) > _JSON_LIMIT:
        raise ValueError('local-evidence-too-large')
    return refreshed


def write_result(path, value):
    """A replay may reuse identical output, never overwrite different evidence."""
    raw = json.dumps(value, ensure_ascii=False, indent=2).encode('utf-8')
    try:
        with path.open('xb') as handle:
            handle.write(raw)
    except FileExistsError:
        if path.is_symlink() or path.read_bytes() != raw:
            raise ValueError('existing-capture-output-differs') from None


def _replace_local(source_dir, baseline, evidence, output_dir, *, contract_only):
    filename = 'member_map_auto_evidence.json'
    if contract_only and ({key: value for key, value in baseline.items() if key not in _CAPTURE_FIELDS}
                          != {key: value for key, value in evidence.items() if key not in _CAPTURE_FIELDS}):
        raise ValueError('non-contract-evidence-change')
    _validate_capture_fields(baseline, evidence)
    raw = json.dumps(evidence, ensure_ascii=False, indent=2).encode('utf-8')
    if len(raw) > min(_JSON_LIMIT, PUBLIC_SOURCE_MAX_BYTES[filename]):
        raise ValueError('local-evidence-too-large')
    directory = os.open(source_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    lock_fd, temporary = None, None
    try:
        lock_fd = os.open('.member-map-contract-update.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600, dir_fd=directory)
        if not stat.S_ISREG(os.fstat(lock_fd).st_mode):
            raise ValueError('invalid-local-lock')
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        def read_current():
            descriptor = os.open(filename, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            with os.fdopen(descriptor, 'rb') as handle:
                if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                    raise ValueError('invalid-local-target')
                value = handle.read(PUBLIC_SOURCE_MAX_BYTES[filename] + 1)
                if len(value) > PUBLIC_SOURCE_MAX_BYTES[filename]:
                    raise ValueError('local-evidence-too-large')
                return value
        previous = read_current()
        try:
            current = json.loads(previous.decode('utf-8'), object_pairs_hook=_strict_object)
        except (UnicodeError, json.JSONDecodeError):
            raise ValueError('invalid-local-evidence') from None
        if current != baseline:
            raise ValueError('local-evidence-changed-during-capture')
        if baseline == evidence:
            return {'applied': False, 'reason': 'unchanged', 'sha256': hashlib.sha256(previous).hexdigest()}
        # Capture directory is new per run; a pre-existing backup is never replaced.
        backup = output_dir / 'member_map_auto_evidence.before-apply.json'
        with backup.open('xb') as handle:
            handle.write(previous)
            handle.flush()
            os.fsync(handle.fileno())
        temporary = '.member-map-contract-' + uuid.uuid4().hex + '.tmp'
        descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600, dir_fd=directory)
        with os.fdopen(descriptor, 'wb') as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        if read_current() != previous:
            raise ValueError('local-evidence-changed-during-capture')
        os.replace(temporary, filename, src_dir_fd=directory, dst_dir_fd=directory)
        temporary = None
        os.fsync(directory)
        return {'applied': True, 'sha256': hashlib.sha256(raw).hexdigest(),
                'previous_sha256': hashlib.sha256(previous).hexdigest(),
                'contract_facts': len(evidence.get('contract_facts', [])),
                'document_families': len(evidence.get('documentFamilies', [])),
                'contract_terminations': len(evidence.get('contract_terminations', []))}
    finally:
        if temporary is not None:
            os.unlink(temporary, dir_fd=directory)
        if lock_fd is not None:
            os.close(lock_fd)
        os.close(directory)


def apply_local(source_dir, baseline, evidence, output_dir):
    """Apply capture-only changes; base catalog fields must remain identical."""
    return _replace_local(source_dir, baseline, evidence, output_dir, contract_only=True)


def apply_refreshed_local(source_dir, baseline, evidence, output_dir):
    """Apply a validated refreshed base while preserving prior capture history."""
    return _replace_local(source_dir, baseline, evidence, output_dir, contract_only=False)


def capture_kind(filing_type):
    if filing_type == 'contract':
        return 'contract_facts', '단일판매·공급계약체결'
    if filing_type == 'termination':
        return 'contract_terminations', '단일판매·공급계약해지'
    raise ValueError('unsupported-filing-type')


def candidates(sources, *, include_captured=False, filing_type='contract'):
    field, title = capture_kind(filing_type)
    already = set() if include_captured else {row['receipt_no'] for row in sources.get('member_map_auto_evidence.json', {}).get(field, [])}
    documents = {}
    for company in add_public_company_names(sources, project_public_sources(sources)['companies']):
        if not company['id'].startswith('KR:'):
            continue
        for doc in company.get('documents', []):
            if (doc['source'] == 'DART' and _contract_title(doc['title']).replace(' ', '') == title
                    and doc['id'].removeprefix('DART:') not in already):
                documents.setdefault(doc['id'], []).append((company, doc))
    return sorted((rows[0] for rows in documents.values() if len(rows) == 1),
                  key=lambda pair: (pair[1]['as_of'], pair[1]['id']), reverse=True)


def with_issuer_names(company, parser):
    """Only explicit names from the same public security identity may match."""
    for name in company.get('source_names', [company['name']]):
        try:
            return parser(name)
        except ValueError:
            continue
    raise ValueError('source-parser-rejected')


def parse_body(raw, company, doc, viewer, observed, filing_type):
    args = dict(receipt_no=doc['id'][5:], issuer_id=company['id'], filed_on=doc['as_of'],
                main_url=doc['url'], viewer_url=viewer, observed_at=observed)
    if filing_type == 'termination':
        fact = with_issuer_names(company, lambda name: parse_contract_termination(raw,
            issuer_name=company['name'], expected_source_issuer_name=name, **args))
        fact['filing_title'] = doc['title']
        return validate_contract_termination(fact)
    return with_issuer_names(company, lambda name: parse_contract_facts(raw, issuer_name=name, **args))


def preserve_source_titles(evidence, sources):
    """Keep exact already-received feed titles, bound to the captured body.

    No source request or change to quoted body fields. This also backfills old
    captures while their matching header is still present in the current feed.
    """
    bound = {doc['id'][5:]: (company, doc) for company, doc in candidates(sources, include_captured=True)}
    for index, raw in enumerate(evidence.get('contract_facts', [])):
        try:
            fact = validate_contract_fact(raw)
            if 'source_title' in fact['filing']:
                continue
            company, doc = bound[fact['receipt_no']]
            if (company['id'] != fact['issuer']['id'] or fact['issuer']['name'] not in company.get('source_names', [company['name']])
                    or doc['url'] != fact['source']['main_url'] or doc['as_of'] != fact['filing']['filed_on']):
                continue
            fact['filing']['source_title'] = doc['title']
            evidence['contract_facts'][index] = validate_contract_fact(fact)
        except (KeyError, TypeError, ValueError):
            continue


def reparse(sources, directory):
    """Replay captured bytes after a parser fix, with no repeated network read."""
    manifest = json.loads((directory / 'manifest.json').read_text())
    if manifest.get('schema') != 'local-public-contract-capture-v1':
        raise ValueError('invalid-capture-manifest')
    filing_type = manifest.get('filing_type', 'contract')
    field, _ = capture_kind(filing_type)
    bound = {doc['id'][5:]: (company, doc) for company, doc in candidates(sources, include_captured=True, filing_type=filing_type)}
    evidence = sources['member_map_auto_evidence.json']
    facts = {f['receipt_no']: f for f in evidence.get(field, [])}
    families = {f['receipt_no']: f for f in evidence.get('documentFamilies', [])}
    accepted, rejected = 0, []
    for capture in manifest['documents']:
        receipt = capture['receipt_no']
        company, doc = bound[receipt]
        if capture['issuer_id'] != company['id'] or capture['as_of'] != doc['as_of']:
            raise ValueError('capture-binding-mismatch')
        if not all(suffix in capture for suffix in ('.html', '.viewer.html')):
            rejected.append({'receipt_no': receipt, 'reason': 'capture-incomplete'})
            continue
        blobs = {}
        for suffix in ('.html', '.viewer.html'):
            proof = capture[suffix]
            if proof['file'] != receipt + suffix:
                raise ValueError('invalid-capture-path')
            path = directory / proof['file']
            if path.is_symlink():
                raise ValueError('invalid-capture-path')
            raw = path.read_bytes()
            if len(raw) != proof['bytes'] or hashlib.sha256(raw).hexdigest() != proof['sha256']:
                raise ValueError('capture-proof-mismatch')
            blobs[suffix] = raw
        html = blobs['.html'].decode('utf-8')
        viewer = extract_viewer_url(html, receipt)
        if capture['.html']['url'] != doc['url'] or viewer != capture['.viewer.html']['url']:
            raise ValueError('capture-url-mismatch')
        if filing_type == 'contract':
            try:
                families[receipt] = with_issuer_names(company, lambda name: parse_dart_family(html, receipt, company['id'], name, manifest['created_at']))
            except ValueError:
                pass
        try:
            facts[receipt] = parse_body(blobs['.viewer.html'], company, doc, viewer, manifest['created_at'], filing_type)
            accepted += 1
        except ValueError:
            rejected.append({'receipt_no': receipt, 'reason': 'source-parser-rejected'})
    evidence[field], evidence['documentFamilies'] = list(facts.values()), list(families.values())
    preserve_source_titles(evidence, sources)
    output = directory / 'member_map_auto_evidence.reparsed.json'
    write_result(output, evidence)
    summary = {'reparsed': accepted, 'total': len(manifest['documents']), 'rejected': rejected,
               'new_public_gets': 0, 'output': str(output)}
    write_result(directory / 'reparse-summary.json', summary)
    print(json.dumps(summary))
    return evidence


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--source-dir', type=Path, required=True)
    cli.add_argument('--output-dir', type=Path, required=True)
    cli.add_argument('--limit', type=int, choices=range(1, 21))
    cli.add_argument('--fetch-public', action='store_true')
    cli.add_argument('--reparse', action='store_true')
    cli.add_argument('--filing-type', choices=('contract', 'termination'), help='Type of new public filings to capture; replay uses its manifest')
    cli.add_argument('--refresh-base', type=Path, help='Merge validated prior captures into a strict fresh base catalog; local only')
    cli.add_argument('--apply-local', action='store_true', help='Atomically update this local source directory after validation; never uploads')
    args = cli.parse_args()
    if args.refresh_base is not None:
        if args.fetch_public or args.reparse or args.filing_type is not None or args.limit is not None:
            cli.error('--refresh-base conflicts with fetch, reparse, filing-type, and limit options')
        if args.output_dir.exists() or args.output_dir.is_symlink():
            cli.error('--refresh-base requires a new output directory')
        try:
            if args.source_dir.is_symlink() or not args.source_dir.is_dir():
                raise ValueError('invalid-local-source-directory')
            baseline = _read_regular_json(args.source_dir / 'member_map_auto_evidence.json')
            _validate_capture_fields(baseline, baseline)
            evidence = refresh_base(baseline, args.refresh_base)
            args.output_dir.mkdir(parents=True, exist_ok=False)
            write_result(args.output_dir / 'member_map_auto_evidence.refreshed.json', evidence)
            local_update = None
            if args.apply_local:
                local_update = apply_refreshed_local(args.source_dir, baseline, evidence, args.output_dir)
                if local_update['applied']:
                    write_result(args.output_dir / 'local-apply.json', local_update)
            counts = {field: len(evidence.get(field, [])) for field in _CAPTURE_FIELDS}
            print(json.dumps({'refresh': 'review-ready', 'applied': bool(local_update and local_update['applied']),
                              'counts': counts,
                              'review_artifact': str(args.output_dir / 'member_map_auto_evidence.refreshed.json'),
                              'local_update': local_update}, ensure_ascii=False))
        except (OSError, UnicodeError, TypeError, ValueError):
            # A journal/fsync failure can occur after atomic replacement. Do
            # not falsely promise that the prior bytes are still active.
            cli.error('Local base refresh failed; inspect current source and backup before retry')
        return
    if args.apply_local and not (args.reparse or args.fetch_public):
        cli.error('--apply-local requires --reparse or --fetch-public')
    sources = load_public_sources(args.source_dir)
    baseline = deepcopy(sources['member_map_auto_evidence.json'])
    def apply_if_requested(evidence):
        if args.apply_local:
            result = apply_local(args.source_dir, baseline, evidence, args.output_dir)
            if result['applied']:
                write_result(args.output_dir / 'local-apply.json', result)
            print(json.dumps({'local_update': result}))
    if args.reparse:
        if args.fetch_public:
            cli.error('Reparse cannot fetch')
        evidence = reparse(sources, args.output_dir)
        return apply_if_requested(evidence)
    filing_type = args.filing_type or 'contract'
    limit = args.limit or 6
    field, _ = capture_kind(filing_type)
    selected = candidates(sources, filing_type=filing_type)
    if not args.fetch_public:
        print(json.dumps({'available': len(selected), 'selected': min(limit, len(selected)),
                          'max_public_gets': 2 * min(limit, len(selected)), 'network': False}))
        return
    args.output_dir.mkdir(parents=True, exist_ok=False)
    observed = datetime.now(timezone.utc).isoformat()
    result = {'schema': 'local-public-contract-capture-v1', 'created_at': observed, 'filing_type': filing_type,
              'available': len(selected), 'selected': min(limit, len(selected)), 'public_gets': 0, 'documents': []}
    opener = urllib.request.build_opener(NoRedirect())
    evidence = sources['member_map_auto_evidence.json']
    families = {row['receipt_no']: row for row in evidence.get('documentFamilies', [])}
    facts = {row['receipt_no']: row for row in evidence.get(field, [])}
    for company, doc in selected[:limit]:
        receipt = doc['id'][5:]
        record = {'receipt_no': receipt, 'issuer_id': company['id'], 'as_of': doc['as_of'], 'status': 'pending'}
        result['documents'].append(record)
        def capture(url, suffix):
            if result['public_gets'] >= 2 * limit:
                raise ValueError('capture-budget-exhausted')
            time.sleep(1)
            result['public_gets'] += 1
            request = urllib.request.Request(url, headers={'User-Agent': 'AlphaNest-Public-Source-Review/1.0'})
            with opener.open(request, timeout=15) as response:
                if response.status != 200 or response.geturl() != url:
                    raise ValueError('unexpected-source-response')
                raw = response.read(1024 * 1024 + 1)
            if not raw or len(raw) > 1024 * 1024:
                raise ValueError('invalid-source-size')
            filename = receipt + suffix
            (args.output_dir / filename).write_bytes(raw)
            record[suffix] = {'url': url, 'file': filename, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
            return raw
        try:
            if doc['url'] != DART + receipt:
                raise ValueError('invalid-document-binding')
            html = capture(doc['url'], '.html').decode('utf-8')
            # A missing family must not discard an otherwise usable original body.
            if filing_type == 'contract':
                try:
                    families[receipt] = with_issuer_names(company, lambda name: parse_dart_family(html, receipt, company['id'], name, observed))
                except ValueError:
                    record['lineage'] = 'unparsed'
            viewer = extract_viewer_url(html, receipt)
            raw = capture(viewer, '.viewer.html')
            facts[receipt] = parse_body(raw, company, doc, viewer, observed, filing_type)
            record['status'] = 'parsed'
        except urllib.error.HTTPError as error:
            record['status'], record['reason'], record['http_status'] = 'unparsed', 'HTTPError', error.code
            if error.code in (401, 403, 429):
                result['stopped'] = 'source-access-or-rate-limit'
                break
        except Exception as error:
            record['status'] = 'unparsed'
            record['reason'] = type(error).__name__
        print(json.dumps({'receipt': receipt, 'status': record['status']}, ensure_ascii=False), flush=True)
    evidence['documentFamilies'] = list(families.values())
    evidence[field] = list(facts.values())
    preserve_source_titles(evidence, sources)
    result['parsed'] = sum(row['status'] == 'parsed' for row in result['documents'])
    result['attempted'] = len(result['documents'])
    result['not_attempted'] = result['selected'] - result['attempted']
    for filename, content in [('manifest.json', result), ('member_map_auto_evidence.json', evidence)]:
        (args.output_dir / filename).write_text(json.dumps(content, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'selected': result['selected'], 'parsed': result['parsed'], 'public_gets': result['public_gets']}))
    apply_if_requested(evidence)


if __name__ == '__main__':
    main()
