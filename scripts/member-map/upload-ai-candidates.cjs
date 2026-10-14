// One public file only: create by default, replace only the explicitly expected
// content using storage ifMatch. Never invoke the bulk uploader or load dotenv.
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { createHash } = require('node:crypto');
const { spawnSync } = require('node:child_process');
const ROOT = path.resolve(__dirname, '../..');
const NAME = 'member_map_ai_candidates.json';
const URL = `https://rte5guenhonw9fzn.public.blob.vercel-storage.com/${NAME}`;
const LIMIT = 2_000_000;
const hash = body => createHash('sha256').update(body).digest('hex');
const READBACK_DELAYS_MS = [0, 10000, 20000, 30000];
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

async function publish({ input, artifact: publicArtifact, artifactSha256, workerState = false, sourceDir, upload = false, replaceSha256,
  judgmentInput, judgmentReviews, judgmentAsOf, judgmentPrevious,
  periodInput, periodSourceDir, issuerRegistryPath }, deps = {}) {
  let stage = 'local-validation';
  try {
    const inputs = input === undefined ? [] : Array.isArray(input) ? input : [input];
    if (!sourceDir || typeof upload !== 'boolean' || typeof workerState !== 'boolean'
        || (publicArtifact !== undefined ? typeof publicArtifact !== 'string' || !publicArtifact
          || input !== undefined || workerState || !/^[a-f0-9]{64}$/.test(artifactSha256 || '')
          || [judgmentInput, judgmentReviews, judgmentAsOf, judgmentPrevious].some(v => v !== undefined)
          : artifactSha256 !== undefined || (workerState ? input !== undefined : inputs.length < 1 || inputs.length > 2))
        || inputs.some(value => typeof value !== 'string' || !value)
        || replaceSha256 !== undefined && (typeof replaceSha256 !== 'string'
          || !/^[a-f0-9]{64}$/.test(replaceSha256))) throw Error();
    const judgmentArgs = [judgmentInput, judgmentReviews, judgmentAsOf];
    if (judgmentArgs.some(v => v !== undefined) && !judgmentArgs.every(v => typeof v === 'string' && v)
        || judgmentPrevious !== undefined && (typeof judgmentPrevious !== 'string' || !judgmentPrevious || !judgmentInput)) throw Error();
    const periodArgs = [periodInput, periodSourceDir, issuerRegistryPath];
    if (periodArgs.some(v => v !== undefined) && (!publicArtifact
        || !periodArgs.every(v => typeof v === 'string' && v))) throw Error();
    let body, artifact;
    function exportBody(retainedBody) {
      const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'ai-candidates-publish-'));
      try {
      const output = path.join(directory, NAME);
      const retained = path.join(directory, 'previous-public.json');
      if (retainedBody) fs.writeFileSync(retained, retainedBody, { flag: 'wx', mode: 0o600 });
      const result = (deps.run || spawnSync)('python3', [path.join(__dirname,
        publicArtifact ? 'validate-public-ai-artifact.py' : 'export-ai-candidates.py'),
        ...(publicArtifact ? ['--artifact', path.resolve(publicArtifact), '--sha256', artifactSha256] : []),
        ...(periodInput ? ['--period-input', path.resolve(periodInput), '--period-source-dir', path.resolve(periodSourceDir),
          '--issuer-registry-path', path.resolve(issuerRegistryPath)] : []),
        ...(workerState ? ['--worker-state'] : inputs.flatMap(value => ['--input', path.resolve(value)])),
        ...(judgmentInput ? ['--judgment-input', path.resolve(judgmentInput), '--judgment-reviews', path.resolve(judgmentReviews),
          '--judgment-as-of', judgmentAsOf, ...(judgmentPrevious ? ['--judgment-previous', path.resolve(judgmentPrevious)] : [])] : []),
        ...(retainedBody ? ['--retained-public-judgments', retained] : []),
        '--source-dir', path.resolve(sourceDir), '--output', output],
      { cwd: ROOT, env: { PATH: process.env.PATH, PYTHONDONTWRITEBYTECODE: '1' },
        encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'], timeout: 30000, maxBuffer: 16384 });
      if (result.status !== 0 || result.error) throw Error();
      const info = fs.lstatSync(output);
      if (!info.isFile() || info.size > LIMIT) throw Error();
      body = fs.readFileSync(output);
      artifact = JSON.parse(body);
      // The exporter validates the closed coverage and removes rejected rows.
      if (body.length > LIMIT || artifact.schema !== 'local-ai-review-v1' || artifact.candidates.length > 400
          || publicArtifact && hash(body) !== artifactSha256) throw Error();
      } finally { fs.rmSync(directory, { recursive: true, force: true }); }
    }
    exportBody();
    let summary = { url: URL, sha256: hash(body), count: artifact.candidates.length };
    if (!upload) return summary; // No credentials, SDK or network in dry-run.
    const get = deps.fetch || globalThis.fetch;
    // The existing file may carry a long CDN TTL. Use a content-specific query
    // for replacement reads; its ETag must still match storage before any write.
    let reads = 0;
    async function read(fresh = Boolean(replaceSha256)) {
      const readUrl = fresh ? `${URL}?verify=${summary.sha256}-${Date.now()}-${++reads}` : URL;
      const response = await get(readUrl, { redirect: 'error', cache: 'no-store', signal: AbortSignal.timeout(30000) });
      if (response.redirected || response.url !== readUrl) throw Error();
      if (response.status === 404) { await response.body?.cancel(); return null; }
      if (response.status !== 200 || Number(response.headers.get('content-length')) > LIMIT) throw Error();
      const chunks = []; let size = 0;
      for await (const chunk of response.body) {
        size += chunk.length; if (size > LIMIT) throw Error(); chunks.push(chunk);
      }
      const bytes = Buffer.concat(chunks);
      return { sha256: hash(bytes), etag: response.headers.get('etag'), body: bytes };
    }
    async function verifyReadback() {
      // Verify the exact consumer URL, not just a cache-busted view of storage.
      for (const wait of READBACK_DELAYS_MS) {
        if (wait) await (deps.sleep || delay)(wait);
        if ((await read(false))?.sha256 === summary.sha256) return;
      }
      throw Error();
    }
    stage = 'public-preflight';
    const prior = await read();
    // Check replacement authority before parsing or reusing any prior fields.
    if (prior?.sha256 !== summary.sha256 && (replaceSha256 ? prior?.sha256 !== replaceSha256 : prior !== null)) {
      stage = 'existing-content';
      throw Error();
    }
    if (prior && !publicArtifact && !judgmentInput && Object.hasOwn(JSON.parse(prior.body), 'company_judgments')) {
      // Preserve only already-public reviewed rows still bound to identical
      // candidate/source bytes. Python revalidates; no receipt/AI reconstruction.
      stage = 'retained-judgment-validation';
      exportBody(prior.body);
      summary = { url: URL, sha256: hash(body), count: artifact.candidates.length };
    }
    if (prior?.sha256 === summary.sha256) {
      if (replaceSha256) { stage = 'readback'; await verifyReadback(); }
      return summary;
    }
    stage = 'existing-content';
    if (replaceSha256 ? prior?.sha256 !== replaceSha256 : prior !== null) throw Error();
    stage = 'credential';
    const env = deps.env || process.env;
    if (Object.keys(env).some(key => /^(?:NEXT_PUBLIC_)?VERCEL_BLOB_(?:API_|PROXY_)/.test(key)
        || key === 'DEBUG' || key === 'VERCEL_DEBUG')) throw Error();
    const token = env.BLOB_READ_WRITE_TOKEN;
    if (!/^vercel_blob_rw_rte5guenhonw9fzn_/i.test(token || '')) throw Error();
    let ifMatch;
    if (replaceSha256) {
      stage = 'storage-precondition';
      const meta = await (deps.head || require('@vercel/blob').head)(URL,
        { token, abortSignal: AbortSignal.timeout(30000) });
      if (meta.url !== URL || meta.pathname !== NAME || typeof meta.etag !== 'string'
          || !meta.etag || meta.etag === '*' || /[\r\n]/.test(meta.etag)
          || meta.etag.startsWith('W/') || !prior.etag
          || prior.etag.replace(/^W\//, '') !== meta.etag) throw Error();
      ifMatch = meta.etag;
    }
    stage = 'upload';
    const retries = env.VERCEL_BLOB_RETRIES;
    let result;
    try {
      // Installed SDK getRetries() reads this env; use its public put only.
      env.VERCEL_BLOB_RETRIES = '0';
      result = await (deps.put || require('@vercel/blob').put)(NAME, body, { token, access: 'public', addRandomSuffix: false,
        allowOverwrite: Boolean(ifMatch), ...(ifMatch ? { ifMatch } : {}),
        multipart: false, contentType: 'application/json', cacheControlMaxAge: 600,
        abortSignal: AbortSignal.timeout(30000) });
    } finally {
      if (retries === undefined) delete env.VERCEL_BLOB_RETRIES;
      else env.VERCEL_BLOB_RETRIES = retries;
    }
    stage = 'destination';
    if (result.url !== URL) throw Error();
    stage = 'readback';
    // Propagation may temporarily return 404 or different bytes. Retry GET only.
    await verifyReadback();
    return summary;
  } catch { throw new Error(`public-ai-publish-${stage}-rejected`); }
}

function parseArgs(args) {
  const options = {};
  while (args.length) {
    const flag = args.shift(), key = { '--input': 'input', '--artifact': 'artifact', '--artifact-sha256': 'artifactSha256', '--source-dir': 'sourceDir',
      '--upload': 'upload', '--worker-state': 'workerState', '--replace-sha256': 'replaceSha256',
      '--judgment-input': 'judgmentInput', '--judgment-reviews': 'judgmentReviews',
      '--judgment-as-of': 'judgmentAsOf', '--judgment-previous': 'judgmentPrevious',
      '--period-input': 'periodInput', '--period-source-dir': 'periodSourceDir', '--issuer-registry-path': 'issuerRegistryPath' }[flag];
    if (!['input', 'artifact', 'artifactSha256', 'sourceDir', 'upload', 'workerState', 'replaceSha256', 'judgmentInput', 'judgmentReviews', 'judgmentAsOf', 'judgmentPrevious', 'periodInput', 'periodSourceDir', 'issuerRegistryPath'].includes(key) || key in options && key !== 'input') throw Error('public-ai-publish-arguments-rejected');
    const value = key === 'upload' || key === 'workerState' ? true : args.shift();
    if (!value || typeof value === 'string' && value.startsWith('--') || Array.isArray(options[key])) throw Error('public-ai-publish-arguments-rejected');
    options[key] = key === 'input' && options.input ? [options.input, value] : value;
  }
  if ([options.input, options.workerState, options.artifact].filter(Boolean).length !== 1 || !options.sourceDir
      || Boolean(options.artifact) !== Boolean(options.artifactSha256)
      || options.artifactSha256 && !/^[a-f0-9]{64}$/.test(options.artifactSha256)
      || options.artifact && [options.judgmentInput, options.judgmentReviews, options.judgmentAsOf, options.judgmentPrevious].some(Boolean)) throw Error('public-ai-publish-arguments-rejected');
  if (options.replaceSha256 !== undefined && !/^[a-f0-9]{64}$/.test(options.replaceSha256)) throw Error('public-ai-publish-arguments-rejected');
  const judgmentArgs = [options.judgmentInput, options.judgmentReviews, options.judgmentAsOf];
  if (judgmentArgs.some(Boolean) && !judgmentArgs.every(Boolean) || options.judgmentPrevious && !options.judgmentInput)
    throw Error('public-ai-publish-arguments-rejected');
  const periodArgs = [options.periodInput, options.periodSourceDir, options.issuerRegistryPath];
  if (periodArgs.some(Boolean) && (!options.artifact || !periodArgs.every(Boolean)))
    throw Error('public-ai-publish-arguments-rejected');
  return options;
}
module.exports = { publish, parseArgs };
if (require.main === module) Promise.resolve().then(() => publish(parseArgs(process.argv.slice(2))))
  .then(result => console.log(JSON.stringify(result)))
  .catch(error => { console.error(/^public-ai-publish-[a-z-]+-rejected$/.test(error.message)
    ? error.message : 'public-ai-publish-rejected'); process.exitCode = 1; });
