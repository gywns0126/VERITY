/*
 * Path-free public packaging for the automatic member-map evidence catalog.
 *
 * This deliberately rebuilds through buildAutomaticFilter instead of copying
 * the local audit artifact.  It performs no network access or publication.
 */

const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const childProcess = require('node:child_process');
const { randomUUID } = require('node:crypto');
const { buildAutomaticFilter } = require('./build-source-filter.cjs');

const PUBLIC_FILENAME = 'member_map_auto_evidence.json';
const DEFAULT_OUTPUT = `output/member-map-integration-20260927/${PUBLIC_FILENAME}`;
const PUBLIC_SCOPE_MODE = 'published-automatic-evidence-catalog';
const PUBLIC_SCOPE_NOTE = 'Generated from declared received source snapshots; source timestamps are reported separately and are not automatically reverified.';
const MAX_PUBLIC_BYTES = 8 * 1024 * 1024;
const CAPTURE_FIELDS = ['contract_facts', 'documentFamilies', 'contract_terminations', 'filing_excerpts'];
const CAPTURE_VALIDATOR = path.join(__dirname, 'validate-capture-delivery.py');
const INPUT_PATHS = {
  universe: 'data/universe_search.json',
  chainSnippets: 'data/chain_snippets.json',
  groupStructure: 'data/group_structure.json',
};
const TOP_LEVEL_FIELDS = [
  'schemaVersion', 'generatedAt', 'scope', 'artifactTimestamps', 'sourceDateCoverage',
  'inputs', 'identityCatalog', 'denominators', 'rejectionReasons', 'tickerIndex',
  'sources', 'events', 'relations', 'corrections',
];

function exactKeys(value, expected) {
  return value && typeof value === 'object' && !Array.isArray(value)
    && JSON.stringify(Object.keys(value).sort()) === JSON.stringify([...expected].sort());
}

function validatePublicCatalog(catalog) {
  if (!exactKeys(catalog, TOP_LEVEL_FIELDS) || catalog.schemaVersion !== 1) {
    throw Error('Invalid public catalog: top-level contract');
  }
  if (!exactKeys(catalog.scope, ['mode', 'runtimeFreshness', 'note'])
      || catalog.scope.mode !== PUBLIC_SCOPE_MODE
      || catalog.scope.runtimeFreshness !== 'not-automatically-reverified'
      || catalog.scope.note !== PUBLIC_SCOPE_NOTE) {
    throw Error('Invalid public catalog: scope');
  }
  if (!exactKeys(catalog.inputs, ['universe', 'chainSnippets', 'groupStructure'])) {
    throw Error('Invalid public catalog: source inputs');
  }
  for (const input of Object.values(catalog.inputs)) {
    if (!exactKeys(input, ['bytes', 'sha256']) || !Number.isInteger(input.bytes) || input.bytes < 0
        || typeof input.sha256 !== 'string' || !/^[0-9a-f]{64}$/.test(input.sha256)) {
      throw Error('Invalid public catalog: source input metadata');
    }
  }
  if (!exactKeys(catalog.identityCatalog, ['identities', 'textMatchMarkets'])
      || catalog.identityCatalog.identities !== catalog.denominators.issuersIndexed
      || !Array.isArray(catalog.identityCatalog.textMatchMarkets)
      || catalog.identityCatalog.textMatchMarkets.join(',') !== 'KR,KONEX,US') {
    throw Error('Invalid public catalog: identity denominator');
  }
  if (Object.keys(catalog.tickerIndex).length !== catalog.denominators.issuersIndexed) {
    throw Error('Invalid public catalog: full ticker index required');
  }
  const serialized = JSON.stringify(catalog);
  for (const forbidden of ['/Users/', 'registryGroup', 'registryId', 'LOCAL_FILES', 'PRIVATE_FILES', 'data/chain_snippets.json', 'data/group_structure.json', 'data/universe_search.json']) {
    if (serialized.includes(forbidden)) throw Error('Invalid public catalog: private or local metadata');
  }
  return catalog;
}

function runCaptureValidator(raw, args = []) {
  let validator;
  try { validator = fs.lstatSync(CAPTURE_VALIDATOR); }
  catch { throw Error('Invalid enriched public catalog: capture validator unavailable'); }
  if (!validator.isFile() || validator.isSymbolicLink()) {
    throw Error('Invalid enriched public catalog: capture validator unavailable');
  }
  if (!raw.length || raw.length > MAX_PUBLIC_BYTES) {
    throw Error('Invalid enriched public catalog: byte limit');
  }
  const result = childProcess.spawnSync('python3', [CAPTURE_VALIDATOR, ...args], {
    input: raw, encoding: 'utf8', maxBuffer: 1024 * 1024, timeout: 15000,
  });
  if (result.error || result.status !== 0) {
    throw Error('Invalid enriched public catalog: capture validation failed');
  }
}

function validateCapturePayload(payload) {
  runCaptureValidator(Buffer.from(JSON.stringify(payload)));
}

function validateStrictJson(raw) {
  if (!Buffer.isBuffer(raw)) throw Error('Invalid enriched public catalog: strict JSON input');
  runCaptureValidator(raw, ['--strict-json']);
}

function validateDeliveryCatalog(catalog) {
  if (!catalog || typeof catalog !== 'object' || Array.isArray(catalog)) {
    throw Error('Invalid enriched public catalog: top-level contract');
  }
  const extras = Object.keys(catalog).filter(key => !TOP_LEVEL_FIELDS.includes(key));
  if (extras.some(key => !CAPTURE_FIELDS.includes(key))) {
    throw Error('Invalid enriched public catalog: unknown top-level field');
  }
  if (extras.length === 0) return validatePublicCatalog(catalog);
  const base = Object.fromEntries(TOP_LEVEL_FIELDS.filter(key => key in catalog).map(key => [key, catalog[key]]));
  validatePublicCatalog(base);
  const raw = Buffer.from(JSON.stringify(catalog));
  if (raw.length > MAX_PUBLIC_BYTES) throw Error('Invalid enriched public catalog: byte limit');
  const payload = Object.fromEntries(extras.map(key => [key, catalog[key]]));
  validateCapturePayload(payload);
  return catalog;
}

function hasReceiptBearingStructuredSource(catalog) {
  return Object.values(catalog && catalog.sources || {}).some(row => row && row.kind === 'dart-structured-relation'
    && typeof row.receiptNo === 'string' && /^[0-9]{14}$/.test(row.receiptNo));
}

function mergePriorCaptures(base, priorCaptures) {
  validatePublicCatalog(base);
  validateDeliveryCatalog(priorCaptures);
  const present = CAPTURE_FIELDS.filter(field => Object.prototype.hasOwnProperty.call(priorCaptures, field));
  if (present.length === 0) throw Error('Invalid enriched public catalog: prior captures missing');
  if (hasReceiptBearingStructuredSource(priorCaptures) && !hasReceiptBearingStructuredSource(base)) {
    throw Error('Invalid enriched public catalog: structured source family downgrade');
  }
  const enriched = { ...base };
  for (const field of present) enriched[field] = JSON.parse(JSON.stringify(priorCaptures[field]));
  return validateDeliveryCatalog(enriched);
}

function buildPublicCatalog({ priorCaptures, ...options } = {}) {
  const catalog = buildAutomaticFilter(options);
  catalog.scope = {
    mode: PUBLIC_SCOPE_MODE,
    runtimeFreshness: 'not-automatically-reverified',
    note: PUBLIC_SCOPE_NOTE,
  };
  catalog.identityCatalog = {
    identities: catalog.identityCatalog.identities,
    textMatchMarkets: catalog.identityCatalog.textMatchMarkets,
  };
  validatePublicCatalog(catalog);
  return priorCaptures === undefined ? catalog : mergePriorCaptures(catalog, priorCaptures);
}

function writePublicCatalog({ output, ...options } = {}) {
  if (typeof output !== 'string' || !output.trim()) throw Error('Explicit output path required');
  const catalog = buildPublicCatalog(options); // validate before touching prior-good bytes
  const body = Buffer.from(JSON.stringify(catalog, null, 2) + '\n');
  if (body.length > MAX_PUBLIC_BYTES) throw Error('Invalid enriched public catalog: byte limit');
  const destination = path.resolve(output);
  const directory = path.dirname(destination);
  if (!fs.existsSync(directory)) throw Error(`Output directory does not exist: ${directory}`);
  const temporary = path.join(directory, `.member-map-auto-evidence-${randomUUID()}.tmp`);
  let descriptor;
  let created = false;
  try {
    descriptor = fs.openSync(temporary, 'wx', 0o644); created = true;
    fs.writeFileSync(descriptor, body);
    fs.fsyncSync(descriptor); fs.closeSync(descriptor); descriptor = undefined;
    fs.renameSync(temporary, destination); created = false;
  } finally {
    try { if (descriptor !== undefined) fs.closeSync(descriptor); }
    finally { if (created) fs.unlinkSync(temporary); }
  }
  return catalog;
}

function parseArgs(args) {
  const options = { ...INPUT_PATHS, output: DEFAULT_OUTPUT };
  const allowed = new Map([
    ['--generated-at', 'generatedAt'], ['--universe', 'universe'], ['--chain', 'chainSnippets'],
    ['--group', 'groupStructure'], ['--output', 'output'], ['--prior-captures', 'priorCapturePath'],
  ]);
  for (let index = 0; index < args.length; index += 2) {
    const key = allowed.get(args[index]);
    const value = args[index + 1];
    if (!key || !value || value.startsWith('--') || (key === 'generatedAt' && options.generatedAt)) {
      throw Error('Usage: --generated-at UTC_ISO [--universe path --chain path --group path --output path --prior-captures path]');
    }
    options[key] = value;
  }
  if (!options.generatedAt) throw Error('Usage: --generated-at UTC_ISO [--universe path --chain path --group path --output path --prior-captures path]');
  return options;
}

function readBoundedRegularJson(file) {
  let descriptor;
  try {
    descriptor = fs.openSync(file, fs.constants.O_RDONLY | fs.constants.O_NOFOLLOW | fs.constants.O_NONBLOCK);
    const info = fs.fstatSync(descriptor);
    if (!info.isFile() || info.size <= 0 || info.size > MAX_PUBLIC_BYTES) {
      throw Error('Invalid enriched public catalog: prior capture path');
    }
    const chunks = [];
    let size = 0;
    while (true) {
      const chunk = Buffer.alloc(Math.min(65536, MAX_PUBLIC_BYTES + 1 - size));
      const read = fs.readSync(descriptor, chunk, 0, chunk.length, null);
      if (read === 0) break;
      size += read;
      if (size > MAX_PUBLIC_BYTES) throw Error('Invalid enriched public catalog: prior capture path');
      chunks.push(chunk.subarray(0, read));
    }
    const raw = Buffer.concat(chunks, size);
    validateStrictJson(raw);
    return JSON.parse(raw.toString('utf8'));
  } catch (error) {
    if (error && /^Invalid enriched public catalog:/.test(error.message)) throw error;
    throw Error('Invalid enriched public catalog: prior capture path');
  } finally {
    if (descriptor !== undefined) fs.closeSync(descriptor);
  }
}

function loadInputs(options) {
  const root = path.resolve(__dirname, '../..');
  const loaded = {};
  const inputMetadata = {};
  for (const key of Object.keys(INPUT_PATHS)) {
    const body = fs.readFileSync(path.resolve(root, options[key]));
    loaded[key] = JSON.parse(body.toString('utf8'));
    inputMetadata[key] = {
      bytes: body.length,
      sha256: crypto.createHash('sha256').update(body).digest('hex'),
    };
  }
  const priorCaptures = options.priorCapturePath === undefined ? undefined
    : readBoundedRegularJson(path.resolve(root, options.priorCapturePath));
  if (priorCaptures !== undefined) validateDeliveryCatalog(priorCaptures);
  return { ...loaded, inputMetadata, generatedAt: options.generatedAt, priorCaptures,
    output: path.resolve(root, options.output) };
}

function main(args) {
  const options = parseArgs(args);
  const catalog = writePublicCatalog(loadInputs(options));
  process.stdout.write(JSON.stringify({
    output: options.output,
    filename: PUBLIC_FILENAME,
    scope: catalog.scope,
    denominators: catalog.denominators,
    sourceDateCoverage: catalog.sourceDateCoverage,
  }, null, 2) + '\n');
}

module.exports = {
  PUBLIC_FILENAME, PUBLIC_SCOPE_MODE, MAX_PUBLIC_BYTES, CAPTURE_FIELDS,
  buildPublicCatalog, mergePriorCaptures, validateDeliveryCatalog, validatePublicCatalog,
  validateStrictJson, writePublicCatalog,
};

if (require.main === module) {
  try { main(process.argv.slice(2)); }
  catch (error) { console.error(`Public automatic source filter failed: ${error.message}`); process.exitCode = 1; }
}
