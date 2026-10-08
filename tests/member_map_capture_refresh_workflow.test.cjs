const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const workflow = fs.readFileSync(path.resolve(__dirname, '../.github/workflows/kr_company_facts_backfill.yml'), 'utf8');

function step(name) {
    const start = workflow.indexOf(`      - name: ${name}\n`);
    assert.notEqual(start, -1, `missing workflow step: ${name}`);
    const next = workflow.indexOf('\n      - name:', start + 1);
    return workflow.slice(start, next < 0 ? workflow.length : next);
}

test('daily public catalog refresh preserves validated captures and reports bounded public capture outcomes', () => {
    const build = step('Build path-free automatic evidence catalog');
    const commit = step('Commit');
    const failure = step('Fail stopped public capture after preserving successful source rows');
    const publish = step('Publish verified public evidence catalog');
    const manifests = step('Upload public capture manifests');
    const annual = step('Capture bounded annual customer tables');

    const detect = build.indexOf('CAPTURE_FIELDS_PRESENT=');
    const buildCatalog = build.indexOf('node scripts/member-map/build-public-source-filter.cjs');
    const contractCapture = build.indexOf('--filing-type contract');
    const terminationCapture = build.indexOf('--filing-type termination');
    const manifestReport = build.lastIndexOf('manifest.json');
    assert.ok(detect >= 0 && detect < buildCatalog);
    assert.ok(buildCatalog < contractCapture && contractCapture < terminationCapture && terminationCapture < manifestReport);
    assert.match(build, /object_pairs_hook=unique_object/);
    assert.match(build, /if \[ "\$CAPTURE_FIELDS_PRESENT" = yes \]; then[\s\S]*PRIOR_CAPTURE_ARGS=\(\s*--prior-captures data\/member_map_auto_evidence\.json\s*\)/);
    assert.match(build, /"\$\{PRIOR_CAPTURE_ARGS\[@\]\}"/);

    assert.equal((build.match(/python3 scripts\/member-map\/capture-contract-facts\.py/g) || []).length, 2);
    assert.equal((build.match(/--limit 6 --fetch-public --apply-local/g) || []).length, 2);
    assert.match(build, /--source-dir data --output-dir "\$CONTRACT_CAPTURE_DIR"[\s\S]*--filing-type contract/);
    assert.match(build, /--source-dir data --output-dir "\$TERMINATION_CAPTURE_DIR"[\s\S]*--filing-type termination/);
    assert.match(build, /CONTRACT_CAPTURE_ROOT="\$\(mktemp -d "\$RUNNER_TEMP\/member-map-contract\.XXXXXX"\)"[\s\S]*CONTRACT_CAPTURE_DIR="\$CONTRACT_CAPTURE_ROOT\/capture"/);
    assert.match(build, /TERMINATION_CAPTURE_ROOT="\$\(mktemp -d "\$RUNNER_TEMP\/member-map-termination\.XXXXXX"\)"[\s\S]*TERMINATION_CAPTURE_DIR="\$TERMINATION_CAPTURE_ROOT\/capture"/);
    assert.ok(build.indexOf('CONTRACT_SOURCE_ACCESS_STOP=') < terminationCapture);
    assert.match(build, /if \[ "\$CONTRACT_SOURCE_ACCESS_STOP" != true \]; then[\s\S]*--filing-type termination/);
    assert.match(build, /'available', 'selected', 'attempted', 'parsed', 'not_attempted'/);
    assert.match(build, /source-access-or-rate-limit/);
    assert.match(build, /'partial'/);

    assert.ok(workflow.indexOf('      - name: Commit\n') > workflow.indexOf('      - name: Build path-free automatic evidence catalog\n'));
    assert.ok(workflow.indexOf(failure) > workflow.indexOf(commit));
    assert.match(failure, /if: steps\.automatic_evidence\.outputs\.source_access_stop == 'true'/);
    assert.match(failure, /steps\.annual_capture\.outputs\.source_access_stop == 'true'/);
    assert.match(failure, /exit 1/);
    assert.match(commit, /::error::push 실패/);
    assert.match(commit, /exit 1/);
    assert.ok(commit.indexOf('for i in 1 2 3 4 5 6; do') < commit.indexOf('::error::push 실패'));
    assert.match(manifests, /actions\/upload-artifact@v4/);
    assert.match(manifests, /\$\{\{ env\.CONTRACT_CAPTURE_DIR \}\}\/manifest\.json/);
    assert.match(manifests, /\$\{\{ env\.TERMINATION_CAPTURE_DIR \}\}\/manifest\.json/);
    assert.match(manifests, /\$\{\{ env\.ANNUAL_CAPTURE_DIR \}\}\/manifest\.json/);
    assert.doesNotMatch(manifests, /\.html|raw/i);
    assert.ok(workflow.indexOf(manifests) > workflow.indexOf(build));
    assert.ok(workflow.indexOf(manifests) < workflow.indexOf(commit));
    assert.ok(workflow.indexOf(publish) > workflow.indexOf(failure));
    assert.match(publish, /BLOB_READ_WRITE_TOKEN: \$\{\{ secrets\.VERCEL_BLOB_TOKEN \}\}/);
    assert.match(publish, /if \[ -z "\$\{BLOB_READ_WRITE_TOKEN:-\}" \]; then[\s\S]*exit 1/);
    assert.match(publish, /npm install --prefix "\$PUBLISH_DEPS_DIR" --no-save --package-lock=false @vercel\/blob@2\.4\.1/);
    assert.match(publish, /NODE_PATH="\$PUBLISH_DEPS_DIR\/node_modules"[\s\\]*node scripts\/member-map\/upload-public-source-filter\.cjs data\/member_map_auto_evidence\.json/);
    assert.doesNotMatch(publish, /bulk|delete/i);
    assert.doesNotMatch(workflow, /uses: \.\/\.github\/actions\/publish-data/);
    assert.doesNotMatch(build, /--allow-llm|member portfolio|holdings|private ticker/i);
    assert.match(build, /'annual_customer_tables'/);
    assert.ok(workflow.indexOf(annual) > workflow.indexOf(build));
    assert.ok(workflow.indexOf(annual) < workflow.indexOf(manifests));
    assert.match(annual, /if: steps\.automatic_evidence\.outputs\.source_access_stop != 'true'/);
    assert.match(annual, /--limit 3 --fetch-public --apply-local/);
    assert.match(annual, /DART_API_KEY: \$\{\{ secrets\.DART_API_KEY \}\}/);
    assert.match(annual, /counts\['public_gets'\] <= 3/);
    assert.match(commit, /data\/member_map_annual_capture_attempts\.json/);
    assert.doesNotMatch(annual, /--allow-llm|tokenP|oauth2/);
});
