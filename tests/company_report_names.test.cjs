const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const esbuild = require('esbuild');

const source = fs.readFileSync(path.join(__dirname, '../framer-components/public-probe/PublicCompanyReports.tsx'), 'utf8');
const defaults = source.slice(source.indexOf('const DEF_KR'), source.indexOf('const LIGHT'));
const effect = source.match(/useEffect\(\(\) => \{\s*if \(onCanvas\) return\s*let alive = true[\s\S]*?\}, \[krUniverseUrl, usUniverseUrl, onCanvas\]\)/)[0];
const base = 'https://rte5guenhonw9fzn.public.blob.vercel-storage.com/';

function mount({ krUniverseUrl, usUniverseUrl, onCanvas = false, responses = {} } = {}) {
    const calls = [];
    let cleanup, names;
    vm.runInNewContext(esbuild.transformSync(defaults + '\n' + effect, { loader: 'ts' }).code, {
        krUniverseUrl, usUniverseUrl, onCanvas,
        useEffect(fn) { cleanup = fn(); },
        setNameMap(next) { names = next; },
        fetch(url) {
            calls.push(url);
            const value = responses[url];
            if (value instanceof Error) return Promise.reject(value);
            if (value && typeof value.then === 'function') return value;
            return Promise.resolve({ ok: value !== undefined, json: async () => value });
        },
    });
    return { calls, get names() { return names; }, close() { cleanup?.(); } };
}
const flush = () => new Promise(resolve => setImmediate(resolve));

test('new defaults and saved old defaults request a single slim name catalog', async () => {
    for (const props of [
        {},
        { krUniverseUrl: base + 'universe_search.json', usUniverseUrl: base + 'universe_search.json' },
        { krUniverseUrl: base + 'stock_report_public.json', usUniverseUrl: base + 'us_stock_report_public.json' },
    ]) {
        const run = mount({ ...props, responses: { [base + 'universe_search.json']: { stocks: [
            { ticker: '005930', name: '삼성전자' },
            { ticker: 'aapl', name: 'Apple Inc.', name_ko: '애플' },
        ] } } });
        await flush();
        assert.deepEqual(run.calls, [base + 'universe_search.json']);
        assert.equal(run.names['005930'], '삼성전자');
        assert.equal(run.names.AAPL, 'Apple Inc.');
    }
});

test('custom catalogs and explicit empty opt-out are preserved, with duplicate URL deduplication', async () => {
    const custom = 'https://example.test/company-names.json';
    const run = mount({ krUniverseUrl: custom, usUniverseUrl: custom, responses: {
        [custom]: [{ ticker: 'CAT', name: 'Custom name' }],
    } });
    await flush();
    assert.deepEqual(run.calls, [custom]);
    assert.equal(run.names.CAT, 'Custom name');
    assert.deepEqual(mount({ krUniverseUrl: '', usUniverseUrl: '' }).calls, []);
});

test('catalog failure leaves ticker-based links available; successful custom source still resolves', async () => {
    const custom = 'https://example.test/company-names.json';
    const run = mount({ usUniverseUrl: custom, responses: {
        [base + 'universe_search.json']: Error('offline'),
        [custom]: { stocks: [{ ticker: 'CAT', name: 'Caterpillar' }, { ticker: 'BAD' }] },
    } });
    await flush();
    assert.equal(run.names.CAT, 'Caterpillar');
    assert.equal(run.names.BAD, undefined);
    assert.match(source, /const name = nameMap\[String\(tk\)\.toUpperCase\(\)\] \|\| ""/);
    assert.match(source, /const links = useMemo\(\(\) => linksFor\(tk\), \[tk\]\)/);
});

test('canvas does not fetch; detached component ignores an outstanding catalog response', async () => {
    assert.deepEqual(mount({ onCanvas: true }).calls, []);
    let complete;
    const request = new Promise(resolve => { complete = resolve; });
    const run = mount({ responses: { [base + 'universe_search.json']: request } });
    run.close();
    complete({ ok: true, json: async () => ({ stocks: [{ ticker: 'CAT', name: 'Caterpillar' }] }) });
    await flush();
    assert.equal(run.names, undefined);
});

test('component compiles and KR/US source links retain the selected symbol', () => {
    assert.doesNotThrow(() => esbuild.transformSync(source, { loader: 'tsx', format: 'esm' }));
    const linkFunctions = source.slice(source.indexOf('function isKrSecurityCode'), source.indexOf('/**\n * @framerSupportedLayoutWidth'));
    const context = {};
    vm.runInNewContext(esbuild.transformSync(linkFunctions, { loader: 'ts' }).code, context);
    assert(context.linksFor('005930').every(link => link.url.includes('005930')));
    assert(context.linksFor('CAT').every(link => link.url.includes('CAT')));
    assert.equal(context.isKrSecurityCode('0046A0'), true);
});
