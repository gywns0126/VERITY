/*
 * Local staging hook for the path-free automatic evidence catalog.
 *
 * This module does not upload, read environment variables, or select tickers.
 * It validates one fixed public filename, atomically stages it into an existing
 * publish directory, and verifies the staged bytes before returning success.
 */

const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { randomUUID } = require('node:crypto');
const {
  PUBLIC_FILENAME,
  PUBLIC_SCOPE_MODE,
  MAX_PUBLIC_BYTES,
  CAPTURE_FIELDS,
  validateDeliveryCatalog,
  validateStrictJson,
} = require('./build-public-source-filter.cjs');

function sha256(body) {
  return crypto.createHash('sha256').update(body).digest('hex');
}

function parseAndValidate(body) {
  if (!Buffer.isBuffer(body) || body.length === 0 || body.length > MAX_PUBLIC_BYTES) {
    throw Error('Public catalog staging rejected: byte limit');
  }
  let catalog;
  try { catalog = JSON.parse(body.toString('utf8')); }
  catch { throw Error('Public catalog staging rejected: invalid JSON'); }
  if (CAPTURE_FIELDS.some(field => Object.prototype.hasOwnProperty.call(catalog, field))) {
    validateStrictJson(body);
  }
  validateDeliveryCatalog(catalog);
  if (catalog.scope.mode !== PUBLIC_SCOPE_MODE) {
    throw Error('Public catalog staging rejected: public scope required');
  }
  return catalog;
}

function publishSourceFilter({ source, publishDirectory } = {}) {
  if (typeof source !== 'string' || path.basename(source) !== PUBLIC_FILENAME) {
    throw Error(`Public catalog staging rejected: source must be ${PUBLIC_FILENAME}`);
  }
  if (typeof publishDirectory !== 'string' || !publishDirectory.trim()) {
    throw Error('Public catalog staging rejected: explicit publish directory required');
  }
  const destinationDirectory = path.resolve(publishDirectory);
  if (!fs.existsSync(destinationDirectory) || !fs.statSync(destinationDirectory).isDirectory()) {
    throw Error('Public catalog staging rejected: publish directory missing');
  }

  const sourceBody = fs.readFileSync(path.resolve(source));
  const catalog = parseAndValidate(sourceBody); // reject before touching prior-good bytes
  const sourceHash = sha256(sourceBody);
  const destination = path.join(destinationDirectory, PUBLIC_FILENAME);
  const temporary = path.join(destinationDirectory, `.member-map-publish-${randomUUID()}.tmp`);
  let descriptor;
  let created = false;
  try {
    descriptor = fs.openSync(temporary, 'wx', 0o644); created = true;
    fs.writeFileSync(descriptor, sourceBody);
    fs.fsyncSync(descriptor); fs.closeSync(descriptor); descriptor = undefined;

    const temporaryBody = fs.readFileSync(temporary);
    parseAndValidate(temporaryBody);
    if (temporaryBody.length !== sourceBody.length || sha256(temporaryBody) !== sourceHash) {
      throw Error('Public catalog staging rejected: temporary readback mismatch');
    }

    fs.renameSync(temporary, destination); created = false;
  } finally {
    try { if (descriptor !== undefined) fs.closeSync(descriptor); }
    finally { if (created) fs.unlinkSync(temporary); }
  }

  const stagedBody = fs.readFileSync(destination);
  parseAndValidate(stagedBody);
  if (stagedBody.length !== sourceBody.length || sha256(stagedBody) !== sourceHash) {
    throw Error('Public catalog staging rejected: destination readback mismatch');
  }
  return {
    filename: PUBLIC_FILENAME,
    destination,
    bytes: stagedBody.length,
    sha256: sourceHash,
    generatedAt: catalog.generatedAt,
    runtimeFreshness: catalog.scope.runtimeFreshness,
    artifactTimestamps: catalog.artifactTimestamps,
    sourceDateCoverage: catalog.sourceDateCoverage,
    denominators: catalog.denominators,
  };
}

function parseArgs(args) {
  const options = {};
  const allowed = new Map([['--source', 'source'], ['--publish-dir', 'publishDirectory']]);
  for (let index = 0; index < args.length; index += 2) {
    const key = allowed.get(args[index]);
    const value = args[index + 1];
    if (!key || !value || value.startsWith('--') || options[key]) {
      throw Error(`Usage: --source */${PUBLIC_FILENAME} --publish-dir DIRECTORY`);
    }
    options[key] = value;
  }
  if (!options.source || !options.publishDirectory) {
    throw Error(`Usage: --source */${PUBLIC_FILENAME} --publish-dir DIRECTORY`);
  }
  return options;
}

function main(args) {
  process.stdout.write(JSON.stringify(publishSourceFilter(parseArgs(args)), null, 2) + '\n');
}

module.exports = { MAX_PUBLIC_BYTES, publishSourceFilter };

if (require.main === module) {
  try { main(process.argv.slice(2)); }
  catch (error) { console.error(error.message); process.exitCode = 1; }
}
