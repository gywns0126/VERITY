/*
 * Pure, deterministic member-map source filtering over existing local data.
 *
 * The matching exports below do not read files, use a clock, or use a network.
 * Main may reuse compileIdentityCatalog/matchCompanyMentions/filterStructuredRelations
 * with a ticker-scoped identity map and an already-fetched stock_slice payload.
 * The CLI is only a local denominator audit/artifact builder; it is not a live feed.
 */

const CONTRACT_VERSION = 1;
const DART_URL = 'https://dart.fss.or.kr/dsaf001/main.do?rcpNo=';
const DEFAULT_OUTPUT = 'output/member-map-integration-20260927/automatic-filter.local.json';
const INPUT_PATHS = {
  universe: 'data/universe_search.json',
  chainSnippets: 'data/chain_snippets.json',
  groupStructure: 'data/group_structure.json',
};

function normalize(value) {
  return String(value ?? '').normalize('NFKC').toLocaleLowerCase('en-US')
    .replace(/\s+/gu, ' ').trim();
}

function codePointLength(value) {
  return [...String(value ?? '')].length;
}

function entityKey(row) {
  return `${String(row.market).toUpperCase()}:${String(row.ticker).toUpperCase()}`;
}

function validGeneratedAt(value) {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?Z$/.test(value)) return false;
  const epoch = Date.parse(value);
  const expected = value.includes('.') ? value : value.replace('Z', '.000Z');
  return Number.isFinite(epoch) && new Date(epoch).toISOString() === expected;
}

function sourceDate(value) {
  const text = String(value ?? '');
  const match = /^(\d{4})(?:-?)(\d{2})(?:-?)(\d{2})/.exec(text);
  if (!match || (/^\d{8}$/.test(text) === false && /^\d{4}-\d{2}-\d{2}/.test(text) === false)) return null;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const daysInMonth = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  if (month < 1 || month > 12 || day < 1 || day > daysInMonth[month - 1]) return null;
  const iso = `${match[1]}-${match[2]}-${match[3]}`;
  if (/^\d{8}$/.test(text)) return iso;
  if (Number.isFinite(Date.parse(text))) return iso;
  return null;
}

function stableHash(value) {
  // FNV-1a 32-bit: portable identity suffix, not a security checksum.
  let hash = 0x811c9dc5;
  for (const byte of new TextEncoder().encode(String(value))) {
    hash ^= byte;
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return hash.toString(16).padStart(8, '0');
}

function addTrie(root, alias, entry) {
  let node = root;
  for (const char of alias) {
    if (!node.next.has(char)) node.next.set(char, { next: new Map(), entry: null });
    node = node.next.get(char);
  }
  node.entry = entry;
}

function isWordCharacter(char) {
  return Boolean(char && /[\p{L}\p{N}]/u.test(char));
}

const KOREAN_PARTICLE = /^(?:에서|에게|으로|은|는|이|가|을|를|의|와|과|에|께|로|도|만|측)(?=$|[\s,.;:!?()[\]{}'"·/])/u;

function hasExactBoundary(text, start, end) {
  const chars = [...text];
  if (isWordCharacter(chars[start - 1])) return false;
  if (!isWordCharacter(chars[end])) return true;
  return KOREAN_PARTICLE.test(chars.slice(end).join(''));
}

function universeRows(input) {
  if (Array.isArray(input)) return input;
  if (input && typeof input === 'object' && Array.isArray(input.stocks)) return input.stocks;
  throw Error('Invalid universe: expected stocks array');
}

function validateUniverse(input) {
  const rows = universeRows(input);
  if (!rows.length) throw Error('Invalid universe: empty stocks array');
  if (input && input._meta && Number.isInteger(input._meta.count) && input._meta.count !== rows.length) {
    throw Error('Invalid universe: _meta.count mismatch');
  }
  const seen = new Set();
  for (const row of rows) {
    if (!row || typeof row !== 'object' || typeof row.ticker !== 'string' || !row.ticker.trim()
        || typeof row.market !== 'string' || !row.market.trim() || typeof row.name !== 'string' || !row.name.trim()) {
      throw Error('Invalid universe: malformed identity row');
    }
    const key = entityKey(row);
    if (seen.has(key)) throw Error(`Invalid universe: duplicate entity ${key}`);
    seen.add(key);
  }
  return rows;
}

function compileIdentityCatalog(input) {
  const rows = validateUniverse(input);
  const entities = new Map();
  const tickerKeys = new Map();
  const aliasKeys = new Map();
  for (const row of rows) {
    const key = entityKey(row);
    const identity = {
      key, ticker: String(row.ticker).toUpperCase(), market: String(row.market).toUpperCase(), name: row.name,
      ...(typeof row.name_ko === 'string' && row.name_ko.trim() ? { nameKo: row.name_ko.trim() } : {}),
    };
    entities.set(key, identity);
    const ticker = identity.ticker;
    if (!tickerKeys.has(ticker)) tickerKeys.set(ticker, new Set());
    tickerKeys.get(ticker).add(key);
    for (const raw of [row.name, row.name_ko]) {
      const alias = normalize(raw);
      // Symbols and very short names are not prose aliases. `kw` is intentionally excluded:
      // it is an unstructured search string, not an alias list. Funds, notes, indices,
      // bonds and commodities remain in the full ticker index but are not company mentions.
      if (!['KR', 'KONEX', 'US'].includes(identity.market)
          || !alias || codePointLength(alias) < 3 || !/\p{L}/u.test(alias)) continue;
      if (!aliasKeys.has(alias)) aliasKeys.set(alias, new Set());
      aliasKeys.get(alias).add(key);
    }
  }
  const trie = { next: new Map(), entry: null };
  let uniqueAliases = 0;
  let ambiguousAliases = 0;
  for (const [alias, keys] of aliasKeys) {
    const entry = { alias, keys: [...keys].sort() };
    if (entry.keys.length === 1) uniqueAliases += 1;
    else ambiguousAliases += 1;
    addTrie(trie, alias, entry);
  }
  return { entities, tickerKeys, aliasKeys, trie, stats: {
    identities: rows.length, textMatchMarkets: ['KR', 'KONEX', 'US'], uniqueAliases, ambiguousAliases,
  } };
}

function resolveTicker(catalog, ticker, market) {
  const code = String(ticker ?? '').toUpperCase().trim();
  if (!code) return { status: 'missing' };
  if (market) {
    const key = `${String(market).toUpperCase()}:${code}`;
    return catalog.entities.has(key) ? { status: 'unique', key } : { status: 'missing' };
  }
  const keys = [...(catalog.tickerKeys.get(code) || [])].sort();
  return keys.length === 1 ? { status: 'unique', key: keys[0] }
    : keys.length > 1 ? { status: 'ambiguous', keys } : { status: 'missing' };
}

function matchCompanyMentions(text, catalog, { excludeKeys = [] } = {}) {
  if (typeof text !== 'string') throw Error('matchCompanyMentions text must be a string');
  if (!catalog || !catalog.trie || !catalog.entities) throw Error('matchCompanyMentions requires a compiled catalog');
  const normalized = normalize(text);
  const chars = [...normalized];
  const excluded = new Set(excludeKeys);
  const matches = new Map();
  const ambiguous = new Map();
  for (let start = 0; start < chars.length; start += 1) {
    let node = catalog.trie;
    for (let end = start; end < chars.length; end += 1) {
      node = node.next.get(chars[end]);
      if (!node) break;
      if (!node.entry || !hasExactBoundary(normalized, start, end + 1)) continue;
      const { alias, keys } = node.entry;
      if (keys.length !== 1) {
        ambiguous.set(alias, { alias, entityKeys: keys });
        continue;
      }
      const key = keys[0];
      if (excluded.has(key)) continue;
      const prior = matches.get(key);
      if (!prior || codePointLength(alias) > codePointLength(prior.alias)) matches.set(key, { key, alias });
    }
  }
  return {
    matches: [...matches.values()].sort((a, b) => a.key.localeCompare(b.key)),
    ambiguous: [...ambiguous.values()].sort((a, b) => a.alias.localeCompare(b.alias)),
  };
}

function chainDocuments(input) {
  if (!input || typeof input !== 'object') throw Error('Invalid chain snippets: expected object');
  let rows;
  if (input.by_ticker && typeof input.by_ticker === 'object' && !Array.isArray(input.by_ticker)) rows = Object.values(input.by_ticker);
  else if (Array.isArray(input.documents)) rows = input.documents;
  else throw Error('Invalid chain snippets: expected by_ticker map or documents array');
  for (const row of rows) {
    if (!row || typeof row !== 'object' || typeof row.ticker !== 'string'
        || typeof row.rcept_no !== 'string' || !/^\d{14}$/.test(row.rcept_no)
        || !sourceDate(row.rcept_dt) || typeof row.report_nm !== 'string' || !Array.isArray(row.snippets)) {
      throw Error('Invalid chain snippets: malformed document provenance');
    }
    for (const snippet of row.snippets) {
      if (!snippet || typeof snippet !== 'object' || typeof snippet.snippet !== 'string'
          || typeof snippet.anchor !== 'string' || !Number.isInteger(snippet.char_start)
          || !Number.isInteger(snippet.char_end) || snippet.char_start < 0 || snippet.char_end < snippet.char_start) {
        throw Error('Invalid chain snippets: malformed excerpt');
      }
    }
  }
  return rows;
}

function validateGroupStructure(input) {
  if (!input || typeof input !== 'object' || !input.structures || typeof input.structures !== 'object'
      || Array.isArray(input.structures) || !sourceDate(input.updated_at)) {
    throw Error('Invalid group structure: expected dated structures map');
  }
  const rows = Object.values(input.structures);
  if (Number.isInteger(input.count) && input.count !== rows.length) throw Error('Invalid group structure: count mismatch');
  for (const row of rows) {
    if (!row || typeof row !== 'object' || typeof row.ticker !== 'string'
        || !Array.isArray(row.major_shareholders) || !Array.isArray(row.subsidiaries)) {
      throw Error('Invalid group structure: malformed issuer record');
    }
  }
  return rows;
}

function receivedStructuredGroups(input, catalog) {
  if (input?.schema !== 'alphaconsole-dart-structured-provenance-source-v1') return input;
  if (!Array.isArray(input.issuers) || input.issuers.length !== input._meta?.target_count
      || !sourceDate(input._meta.generated_at)) throw Error('Invalid received structured snapshot');
  const legalName = value => normalize(value).replace(/\s/gu, '').replace(/^(?:주식회사|\(주\))|(?:주식회사|\(주\))$/gu, '');
  const names = new Map();
  for (const company of catalog.entities.values()) {
    if (!['KR', 'KONEX'].includes(company.market)) continue;
    const key = legalName(company.name);
    if (!names.has(key)) names.set(key, []);
    names.get(key).push(company.ticker);
  }
  const structures = {};
  for (const issuer of input.issuers) {
    if (!/^[0-9]{6}$/.test(issuer.ticker) || Object.hasOwn(structures, issuer.ticker)) throw Error('Invalid received issuer');
    const groups = {};
    for (const [endpoint, family] of [['hyslrSttus', 'major_shareholders'], ['otrCprInvstmntSttus', 'subsidiaries']]) {
      const block = issuer.endpoints?.[endpoint];
      if (block?.status !== '000' || !Array.isArray(block.rows)) throw Error('Incomplete received structured endpoint');
      groups[family] = block.rows.map(row => {
        const f = row.sourceRow?.fields, major = family === 'major_shareholders';
        if (!f || f.corp_code !== issuer.corp_code) throw Error('Received source issuer mismatch');
        const matches = names.get(legalName(f[major ? 'nm' : 'inv_prm'])) || [];
        const raw = (f[major ? 'trmend_posesn_stock_qota_rt' : 'trmend_blce_qota_rt'] || '').trim();
        const pct = /^(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)(?:\.[0-9]+)?$/.test(raw) ? Number(raw.replaceAll(',', '')) : null;
        return { symbol: matches.length === 1 ? matches[0] : null,
          name: f[major ? 'nm' : 'inv_prm'], relate: f.relate, ownership_pct: pct,
          provenance: row.provenance, sourceRow: row.sourceRow };
      });
    }
    structures[issuer.ticker] = { ticker: issuer.ticker, collected_at: issuer.collected_at, parent: null, ...groups };
  }
  return { updated_at: input._meta.generated_at, count: input.issuers.length, structures };
}

function emptyIndex(identity) {
  return { issuer: { ticker: identity.ticker, market: identity.market, name: identity.name }, sourceCandidates: [], eventCandidates: [], relationCandidates: [] };
}

function addUnique(list, value) {
  if (!list.includes(value)) list.push(value);
}

function increment(map, reason, by = 1) {
  map[reason] = (map[reason] || 0) + by;
}

function processChain({ documents, catalog, tickerIndex, sources, events, corrections, rejectionReasons, denominators }) {
  const seenSources = new Set();
  const seenEvents = new Set();
  const seenCorrections = new Set();
  for (const doc of documents) {
    denominators.documentsInput += 1;
    denominators.excerptsInput += doc.snippets.length;
    const issuer = resolveTicker(catalog, doc.ticker, /^\d{6}$/.test(doc.ticker) ? 'KR' : undefined);
    if (issuer.status !== 'unique') {
      increment(rejectionReasons, issuer.status === 'ambiguous' ? 'ambiguous_document_issuer' : 'unknown_document_issuer', doc.snippets.length || 1);
      denominators.excerptsRejected += doc.snippets.length;
      continue;
    }
    const date = sourceDate(doc.rcept_dt);
    const sourceId = `source:dart:${doc.rcept_no}`;
    if (!seenSources.has(sourceId)) {
      sources[sourceId] = {
        id: sourceId, kind: 'dart-filing-excerpt', receiptNo: doc.rcept_no, sourceDate: date,
        reportName: doc.report_nm, documentIssuer: issuer.key, url: DART_URL + doc.rcept_no,
      };
      seenSources.add(sourceId);
      denominators.documentsAccepted += 1;
    } else {
      increment(rejectionReasons, 'duplicate_document_receipt');
    }
    addUnique(tickerIndex[issuer.key].sourceCandidates, sourceId);
    // A correction title proves only that this receipt is a correction filing. The input
    // does not carry the original receipt identifier, so no supersession lineage is inferred.
    if (/정정/u.test(doc.report_nm)) {
      const correctionId = `correction:${doc.rcept_no}`;
      if (!seenCorrections.has(correctionId)) {
        seenCorrections.add(correctionId);
        corrections.push({
          stableId: correctionId,
          sourceId,
          issuer: issuer.key,
          disposition: 'kept-distinct',
          reason: 'explicit-correction-title-distinct-receipt',
          lineage: 'not-provided-by-source',
        });
      }
    }

    for (const snippet of doc.snippets) {
      const found = matchCompanyMentions(snippet.snippet, catalog, { excludeKeys: [issuer.key] });
      if (!found.matches.length) {
        denominators.excerptsRejected += 1;
        increment(rejectionReasons, found.ambiguous.length ? 'ambiguous_alias_only' : 'no_unique_other_company_mention');
        continue;
      }
      const mentioned = found.matches.map(match => match.key);
      const suffix = stableHash(`${issuer.key}|${mentioned.join('|')}|${snippet.char_start}|${snippet.char_end}|${snippet.anchor}`);
      const eventId = `event:dart:${doc.rcept_no}:${snippet.char_start}-${snippet.char_end}:${suffix}`;
      if (seenEvents.has(eventId)) {
        denominators.excerptsRejected += 1;
        increment(rejectionReasons, 'duplicate_excerpt_event');
        continue;
      }
      seenEvents.add(eventId);
      events[eventId] = {
        id: eventId, type: 'co-mention', explicitRole: false, sourceId, sourceDate: date,
        documentIssuer: issuer.key, mentionedCompanies: mentioned,
        evidence: { anchor: snippet.anchor, charStart: snippet.char_start, charEnd: snippet.char_end, excerpt: snippet.snippet },
        ...(found.ambiguous.length ? { ignoredAmbiguousAliases: found.ambiguous } : {}),
      };
      denominators.excerptsAccepted += 1;
      addUnique(tickerIndex[issuer.key].eventCandidates, eventId);
      for (const key of mentioned) {
        addUnique(tickerIndex[key].sourceCandidates, sourceId);
        addUnique(tickerIndex[key].eventCandidates, eventId);
      }
    }
  }
}

function structuredSource(row, family, issuerKey, artifactObservedAt) {
  if (!Object.hasOwn(row, 'provenance')) return null;
  const p = row.provenance;
  const fields = ['rcept_no', 'stlm_dt', 'bsns_year', 'reprt_code', 'corp_code', 'endpoint'];
  const endpoint = family === 'major_shareholder' ? 'hyslrSttus' : 'otrCprInvstmntSttus';
  if (!p || typeof p !== 'object' || Array.isArray(p) || Object.keys(p).length !== fields.length
      || !fields.every(key => Object.hasOwn(p, key)) || !/^(?:KR|KONEX):[0-9]{6}$/.test(issuerKey)
      || typeof p.rcept_no !== 'string' || !/^[0-9]{14}$/.test(p.rcept_no)
      || typeof p.corp_code !== 'string' || !/^[0-9]{8}$/.test(p.corp_code)
      || typeof p.bsns_year !== 'string' || !/^[0-9]{4}$/.test(p.bsns_year)
      || p.reprt_code !== '11011' || p.endpoint !== endpoint
      || (p.stlm_dt !== null && (typeof p.stlm_dt !== 'string'
        || !/^[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(p.stlm_dt) || p.stlm_dt.startsWith('0000-') || sourceDate(p.stlm_dt) !== p.stlm_dt))) {
    throw Error('invalid_structured_provenance');
  }
  // A receipt identifies the original document, not its filing date. stlm_dt
  // is a settlement date and must never replace a missing filing date.
  const id = `source:dart-structured:${p.rcept_no}:${p.endpoint}:${issuerKey}:${p.corp_code}:${p.bsns_year}:${p.reprt_code}:${p.stlm_dt ?? 'unknown'}`;
  return { id, kind: 'dart-structured-relation', receiptNo: p.rcept_no, sourceDate: null,
    settlementDate: p.stlm_dt, businessYear: p.bsns_year, reportCode: p.reprt_code,
    corpCode: p.corp_code, endpoint: p.endpoint, documentIssuer: issuerKey,
    artifactObservedAt, url: DART_URL + p.rcept_no };
}

function closedSourceRow(row, majorHolder) {
  if (!Object.hasOwn(row, 'sourceRow')) return undefined;
  const value = row.sourceRow;
  const fields = ['rcept_no', 'corp_code', 'corp_name', 'stlm_dt', ...(majorHolder
    ? ['nm', 'relate', 'stock_knd', 'trmend_posesn_stock_qota_rt'] : ['inv_prm', 'trmend_blce_qota_rt'])];
  if (!value || Object.keys(value).sort().join() !== 'fields,index' || !Number.isInteger(value.index) || value.index < 0
      || !value.fields || Array.isArray(value.fields) || Object.keys(value.fields).length !== fields.length
      || fields.some(key => !Object.hasOwn(value.fields, key) || (value.fields[key] !== null
        && (typeof value.fields[key] !== 'string' || value.fields[key].length > 300 || /[\u0000-\u001f\u007f]/.test(value.fields[key]))))) {
    throw Error('invalid_structured_source_row');
  }
  return { index: value.index, fields: Object.fromEntries(fields.map(key => [key, value.fields[key]])) };
}

function relationCandidate({ issuerKey, counterpartyKey, relationType, role, ownershipPct, sourceId, artifactObservedAt, hasReceipt = false, sourceRow }) {
  const basis = [sourceId, issuerKey, counterpartyKey, relationType,
    ...(sourceRow ? [sourceRow.fields.stock_knd || ''] : [normalize(role), ownershipPct ?? ''])].join('|');
  return {
    id: `relation:group-structure:${stableHash(basis)}`,
    type: relationType,
    explicitRole: true,
    verification: hasReceipt ? 'candidate-source-row-receipt' : 'candidate-unverified-no-document-receipt',
    from: relationType === 'reported-major-shareholder-entry' ? counterpartyKey : issuerKey,
    to: relationType === 'reported-major-shareholder-entry' ? issuerKey : counterpartyKey,
    sourceId, sourceDate: null, artifactObservedAt,
    role: String(role || ''),
    ...(ownershipPct !== null && ownershipPct !== undefined && ownershipPct !== '' && Number.isFinite(Number(ownershipPct)) ? { reportedOwnershipPct: Number(ownershipPct) } : {}),
    ...(sourceRow ? { sourceRow } : {}),
  };
}

function filterStructuredRelations({ issuerKey, groupRecord, catalog, sourceId, artifactObservedAt }) {
  if (!catalog || !catalog.entities.has(issuerKey)) throw Error('Unknown structured-relation issuer');
  if (!groupRecord || typeof groupRecord !== 'object') throw Error('Invalid structured-relation record');
  const accepted = [];
  const rejected = [];
  const sources = {};
  const rows = [
    ...(groupRecord.parent ? [{ family: 'parent', row: groupRecord.parent }] : []),
    ...(groupRecord.major_shareholders || []).map(row => ({ family: 'major_shareholder', row })),
    ...(groupRecord.subsidiaries || []).map(row => ({ family: 'subsidiary', row })),
  ];
  for (const item of rows) {
    if (item.family === 'parent') {
      rejected.push({ reason: 'derived_parent_not_explicit_role' });
      continue;
    }
    const resolved = resolveTicker(catalog, item.row && item.row.symbol, 'KR');
    if (resolved.status !== 'unique') {
      rejected.push({ reason: resolved.status === 'ambiguous' ? 'ambiguous_exact_symbol' : 'missing_exact_symbol' });
      continue;
    }
    if (resolved.key === issuerKey) {
      rejected.push({ reason: 'self_relation' });
      continue;
    }
    const relationType = item.family === 'major_shareholder'
      ? 'reported-major-shareholder-entry' : 'reported-equity-investment';
    const role = item.family === 'major_shareholder' ? item.row.relate : 'DART 타법인 출자현황 행';
    if (item.family === 'major_shareholder' && (typeof role !== 'string' || !role.trim())) {
      rejected.push({ reason: 'missing_explicit_role' });
      continue;
    }
    if (item.family === 'major_shareholder'
        && (new Set(['발행회사 본인', '자사주']).has(normalize(role))
          || (normalize(role) === '본인' && !Object.hasOwn(item.row, 'sourceRow')))) {
      rejected.push({ reason: 'self_descriptive_ownership_role' });
      continue;
    }
    let source, sourceRow;
    try { source = structuredSource(item.row, item.family, issuerKey, artifactObservedAt); }
    catch { rejected.push({ reason: 'invalid_structured_provenance' }); continue; }
    try { sourceRow = closedSourceRow(item.row, item.family === 'major_shareholder'); }
    catch { rejected.push({ reason: 'invalid_structured_source_row' }); continue; }
    if (source) sources[source.id] = source;
    accepted.push(relationCandidate({ issuerKey, counterpartyKey: resolved.key, relationType, role,
      ownershipPct: item.row.ownership_pct, sourceId: source?.id || sourceId, artifactObservedAt,
      hasReceipt: Boolean(source), sourceRow }));
  }
  return { input: rows.length, accepted, rejected, sources };
}

function processGroup({ input, rows, catalog, tickerIndex, sources, relations, rejectionReasons, denominators }) {
  const topDate = sourceDate(input.updated_at);
  const seenRelations = new Set();
  for (const row of rows) {
    const issuer = resolveTicker(catalog, row.ticker, 'KR');
    const rowCount = (row.parent ? 1 : 0) + row.major_shareholders.length + row.subsidiaries.length;
    denominators.relationsInput += rowCount;
    if (issuer.status !== 'unique') {
      denominators.relationsRejected += rowCount;
      increment(rejectionReasons, issuer.status === 'ambiguous' ? 'ambiguous_relation_issuer' : 'unknown_relation_issuer', rowCount);
      continue;
    }
    const date = sourceDate(row.collected_at) || topDate;
    const observedAt = typeof row.collected_at === 'string' ? row.collected_at : input.updated_at;
    const sourceId = `source:group-structure:${date}:${issuer.key}`;
    sources[sourceId] = {
      id: sourceId, kind: 'local-structured-relation-candidate', sourceDate: null,
      artifactObservedAt: observedAt,
      documentIssuer: issuer.key, receiptNo: null,
      note: 'Existing structured rows; no per-document DART receipt in source artifact.',
    };
    addUnique(tickerIndex[issuer.key].sourceCandidates, sourceId);
    const filtered = filterStructuredRelations({ issuerKey: issuer.key, groupRecord: row, catalog, sourceId, artifactObservedAt: observedAt });
    Object.assign(sources, filtered.sources);
    for (const rejection of filtered.rejected) {
      denominators.relationsRejected += 1;
      increment(rejectionReasons, rejection.reason);
    }
    for (const relation of filtered.accepted) {
      if (seenRelations.has(relation.id)) {
        denominators.relationsRejected += 1;
        increment(rejectionReasons, 'duplicate_structured_relation');
        continue;
      }
      seenRelations.add(relation.id);
      relations[relation.id] = relation;
      denominators.relationsAccepted += 1;
      for (const key of [relation.from, relation.to]) {
        addUnique(tickerIndex[key].sourceCandidates, relation.sourceId);
        addUnique(tickerIndex[key].relationCandidates, relation.id);
      }
    }
  }
}

function buildAutomaticFilter({ generatedAt, universe, chainSnippets, groupStructure, inputMetadata = {} } = {}) {
  if (!validGeneratedAt(generatedAt)) throw Error('generatedAt must be an explicit valid UTC ISO timestamp');
  const catalog = compileIdentityCatalog(universe);
  const documents = chainDocuments(chainSnippets);
  groupStructure = receivedStructuredGroups(groupStructure, catalog);
  const groupRows = validateGroupStructure(groupStructure);
  const tickerIndex = {};
  for (const [key, identity] of [...catalog.entities].sort(([a], [b]) => a.localeCompare(b))) tickerIndex[key] = emptyIndex(identity);
  const sources = {}, events = {}, relations = {}, corrections = [], rejectionReasons = {};
  const denominators = {
    issuersInput: catalog.entities.size, issuersIndexed: Object.keys(tickerIndex).length,
    documentsInput: 0, documentsAccepted: 0,
    excerptsInput: 0, excerptsAccepted: 0, excerptsRejected: 0,
    relationsInput: 0, relationsAccepted: 0, relationsRejected: 0,
  };
  processChain({ documents, catalog, tickerIndex, sources, events, corrections, rejectionReasons, denominators });
  processGroup({ input: groupStructure, rows: groupRows, catalog, tickerIndex, sources, relations, rejectionReasons, denominators });
  if (denominators.excerptsAccepted + denominators.excerptsRejected !== denominators.excerptsInput) {
    throw Error('Internal denominator mismatch: excerpts');
  }
  if (denominators.relationsAccepted + denominators.relationsRejected !== denominators.relationsInput) {
    throw Error('Internal denominator mismatch: relations');
  }
  for (const row of Object.values(tickerIndex)) {
    row.sourceCandidates.sort(); row.eventCandidates.sort(); row.relationCandidates.sort();
  }
  const dartSourceDates = Object.values(sources).filter(row => row.kind === 'dart-filing-excerpt')
    .map(row => row.sourceDate).filter(Boolean).sort();
  return {
    schemaVersion: CONTRACT_VERSION,
    generatedAt,
    scope: {
      mode: 'local-existing-data-builder-and-pure-runtime-filter',
      runtimeFreshness: 'not-automatically-reverified',
      note: 'The artifact is a denominator audit/build result. Runtime automation requires fresh received source maps and the exported pure matcher.',
    },
    artifactTimestamps: {
      universeGeneratedAt: universe && universe._meta && (universe._meta.generated_at || universe._meta.base_generated_at) || null,
      chainSnippetsUpdatedAt: chainSnippets && chainSnippets.updated_at || null,
      groupStructureUpdatedAt: groupStructure && groupStructure.updated_at || null,
    },
    sourceDateCoverage: {
      dartDocumentsWithReceiptDate: dartSourceDates.length,
      earliestDartReceiptDate: dartSourceDates[0] || null,
      latestDartReceiptDate: dartSourceDates.at(-1) || null,
      groupStructurePerDocumentSourceDate: null,
    },
    inputs: inputMetadata,
    identityCatalog: catalog.stats,
    denominators,
    rejectionReasons: Object.fromEntries(Object.entries(rejectionReasons).sort(([a], [b]) => a.localeCompare(b))),
    tickerIndex, sources, events, relations,
    corrections: corrections.sort((a, b) => a.stableId.localeCompare(b.stableId)),
  };
}

function writeAutomaticFilter({ output, ...options } = {}) {
  if (typeof output !== 'string' || !output.trim()) throw Error('Explicit output path required');
  const manifest = buildAutomaticFilter(options); // validate everything before touching last-good bytes
  const fs = require('node:fs');
  const path = require('node:path');
  const { randomUUID } = require('node:crypto');
  const destination = path.resolve(output);
  const directory = path.dirname(destination);
  if (!fs.existsSync(directory)) throw Error(`Output directory does not exist: ${directory}`);
  const temporary = path.join(directory, `.automatic-filter-${randomUUID()}.tmp`);
  let fd;
  let created = false;
  try {
    fd = fs.openSync(temporary, 'wx', 0o644); created = true;
    fs.writeFileSync(fd, JSON.stringify(manifest, null, 2) + '\n', 'utf8');
    fs.fsyncSync(fd); fs.closeSync(fd); fd = undefined;
    fs.renameSync(temporary, destination); created = false;
  } finally {
    try { if (fd !== undefined) fs.closeSync(fd); }
    finally { if (created) fs.unlinkSync(temporary); }
  }
  return manifest;
}

function parseArgs(args) {
  const options = { ...INPUT_PATHS, output: DEFAULT_OUTPUT };
  const allowed = new Map([
    ['--generated-at', 'generatedAt'], ['--universe', 'universe'], ['--chain', 'chainSnippets'],
    ['--group', 'groupStructure'], ['--output', 'output'],
  ]);
  for (let index = 0; index < args.length; index += 2) {
    const key = allowed.get(args[index]);
    const value = args[index + 1];
    if (!key || !value || value.startsWith('--') || Object.prototype.hasOwnProperty.call(options, key) && key === 'generatedAt') {
      throw Error('Usage: --generated-at UTC_ISO [--universe path --chain path --group path --output path]');
    }
    options[key] = value;
  }
  return options;
}

function loadLocalInputs(options) {
  const fs = require('node:fs');
  const path = require('node:path');
  const crypto = require('node:crypto');
  const root = path.resolve(__dirname, '../..');
  const loaded = {};
  const metadata = {};
  const registry = {
    universe: { registryId: null, registryGroup: null,
      note: 'Existing public identity catalog used by ticker_facts resolver; not declared in its four source lists.' },
    chainSnippets: { registryId: 'source:LOCAL_FILES:data/chain_snippets.json', registryGroup: 'LOCAL_FILES' },
    groupStructure: { registryId: 'source:LOCAL_FILES:data/group_structure.json', registryGroup: 'LOCAL_FILES' },
  };
  for (const key of ['universe', 'chainSnippets', 'groupStructure']) {
    const file = path.resolve(root, options[key]);
    const body = fs.readFileSync(file);
    loaded[key] = JSON.parse(body.toString('utf8'));
    metadata[key] = { path: path.relative(root, file), ...registry[key], bytes: body.length,
      sha256: crypto.createHash('sha256').update(body).digest('hex') };
  }
  return { ...loaded, inputMetadata: metadata, output: path.resolve(root, options.output), generatedAt: options.generatedAt };
}

function main(args) {
  const options = parseArgs(args);
  const manifest = writeAutomaticFilter(loadLocalInputs(options));
  process.stdout.write(JSON.stringify({ output: options.output, denominators: manifest.denominators,
    rejectionReasons: manifest.rejectionReasons }, null, 2) + '\n');
}

module.exports = {
  buildAutomaticFilter, compileIdentityCatalog, filterStructuredRelations,
  matchCompanyMentions, resolveTicker, writeAutomaticFilter,
};

if (require.main === module) {
  try { main(process.argv.slice(2)); }
  catch (error) { console.error(`Automatic source filter failed: ${error.message}`); process.exitCode = 1; }
}
