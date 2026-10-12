// Reuses the AST/VM synthetic harness pattern from tests/public_auth_navigation.test.cjs.
// Fixtures only: no browser, real storage, credentials, provider or member requests.
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const assert = require('node:assert/strict');
const test = require('node:test');
const { createRequire } = require('node:module');
// Installed under tests/: resolve sources from that checkout. A temporary copy
// may be run from the checkout root without copying fixtures or changing it.
const adjacentRoot = path.resolve(__dirname, '..');
const root = fs.existsSync(path.join(adjacentRoot, 'review/member-map/entry.tsx'))
    ? adjacentRoot : process.cwd();
// Uses existing packages only. Node also honors NODE_PATH; nothing is installed.
const dependencyRoot = path.resolve(process.env.MEMBER_MAP_TEST_DEPENDENCY_ROOT || root);
const req = createRequire(path.join(dependencyRoot, 'package.json'));
const appRequire = createRequire(path.join(dependencyRoot, 'operator-web/package.json'));
const { parse } = appRequire('@babel/parser');
const { transformSync } = req('esbuild');
const source = fs.readFileSync(path.join(root, 'review/member-map/Auth.snapshot.tsx'), 'utf8');
const entry = fs.readFileSync(path.join(root, 'review/member-map/entry.tsx'), 'utf8');
function find(node, predicate) {
    if (!node || typeof node !== 'object') return null;
    if (predicate(node)) return node;
    for (const v of Object.values(node)) {
        if (!v || typeof v !== 'object') continue;
        for (const item of Array.isArray(v) ? v : [v]) {
            const result = find(item, predicate);
            if (result) return result;
        }
    }
    return null;
}
const astOf = s => parse(s, { sourceType: 'module', plugins: ['typescript', 'jsx'] });
function named(s, name) {
    const n = find(astOf(s), n => ['FunctionDeclaration', 'VariableDeclarator'].includes(n.type) && n.id?.name === name);
    assert(n, name); return s.slice(n.start, n.end);
}
function authEffect(s) {
    return find(astOf(s), n => n.type === 'CallExpression' && n.callee.name === 'useEffect' && s.slice(n.start, n.end).includes('const consumeHash'));
}
const effect = authEffect(source);
const entryEffect = find(astOf(entry), n => n.type === 'CallExpression' && n.callee?.property?.name === 'useEffect');
const code = transformSync([
    ...['SESSION_KEY', 'AUTH_EVENT', 'FETCH_TIMEOUT_MS'].map(n => 'const ' + named(source, n) + ';'),
    'let ' + named(source, 'sessionRevision') + ';',
    ...['saveSession', 'clearSession', 'isStoredSession', 'loadStoredSession', 'loadSession', 'getVeritySession', 'emitAuthChange', 'refreshSession'].map(n => named(source, n)),
    'this.getSession=getVeritySession; this.save=saveSession; this.clear=clearSession; this.emitAuth=emitAuthChange;',
    'this.start=()=>(' + source.slice(effect.arguments[0].start, effect.arguments[0].end) + ')();',
    'this.startEntry=()=>(' + entry.slice(entryEffect.arguments[0].start, entryEffect.arguments[0].end) + ')();',
    'const ' + named(source, 'logout') + '; this.logout=logout;',
].join('\n'), { loader: 'ts' }).code;
const KEY = 'verity_supabase_session';
const flush = () => new Promise(setImmediate);
function deferred() { let resolve, reject; const promise = new Promise((r, j) => { resolve = r; reject = j; }); return { promise, resolve, reject }; }
function fixture(overrides = {}) {
    return { access_token: 'fixture-old', refresh_token: 'fixture-refresh', expires_at: 1999940, user: { id: 'fixture-user', email: 'fixture@example.invalid' }, ...overrides };
}
const validResponse = () => fixture({ access_token: 'fixture-new', refresh_token: 'fixture-rotated', expires_at: 2003600 });
const response = body => ({ ok: true, json: async () => body });
function harness(options = {}) {
    let now = 2000000000;
    const initial = Object.hasOwn(options, 'stored') ? options.stored : fixture();
    const store = new Map(initial === null ? [] : [[KEY, typeof initial === 'string' ? initial : JSON.stringify(initial)]]);
    const requests = [], writes = [], events = [], timers = new Map(), intervals = new Map(), listeners = new Map();
    const env = {
        onCanvas: false, url: 'https://auth.invalid', anonKey: 'fixture-anon', loginReturnRef: { current: false },
        navigateAfterLogin() {}, setErr() {}, setSession(s) { env.session = s; }, setSignedIn(s) { env.signedIn = s; },
        Date: { now: () => now }, AbortController: options.noAbort ? undefined : AbortController,
        CustomEvent: class { constructor(type) { this.type = type; } },
        localStorage: {
            getItem: k => { if (options.readFailure) throw Error('fixture-read'); return store.get(k) ?? null; },
            setItem: (k, v) => { if (options.writeFailure) throw Error('fixture-write'); writes.push(k); store.set(k, v); },
            removeItem: k => store.delete(k),
        },
        window: {
            location: { hash: '', pathname: '/member-map-review' },
            addEventListener(name, fn) { const a = listeners.get(name) || new Set(); a.add(fn); listeners.set(name, a); },
            removeEventListener(name, fn) { listeners.get(name)?.delete(fn); },
            dispatchEvent(event) { events.push(event.type); for (const fn of listeners.get(event.type) || []) fn(event); },
        },
        setTimeout(fn, ms) { const id = Symbol(ms); timers.set(id, { fn, ms }); return id; }, clearTimeout: id => timers.delete(id),
        setInterval(fn, ms) { const id = Symbol(ms); intervals.set(id, fn); return id; }, clearInterval: id => intervals.delete(id),
        fetch: async (url, init) => {
            assert.equal(url, 'https://auth.invalid/auth/v1/token?grant_type=refresh_token');
            assert.equal(init.headers.Authorization, 'Bearer fixture-anon');
            assert.deepEqual(JSON.parse(init.body), { refresh_token: 'fixture-refresh' });
            requests.push({ url, init });
            return options.fetch ? options.fetch(init) : response(validResponse());
        },
    };
    vm.runInNewContext(code, env);
    return { env, store, requests, writes, events, timers,
        start() { const cleanup = env.start(); env.startEntry(); return cleanup; },
        tick: async () => { for (const fn of intervals.values()) await fn(); },
        advance: ms => now += ms,
        expire() { now += 15000; for (const { fn, ms } of [...timers.values()]) { assert.equal(ms, 15000); fn(); } },
        storageEvent(key = KEY) { env.window.dispatchEvent({ type: 'storage', key }); },
    };
}
function noRecovery(h, original) {
    assert.equal(h.env.getSession(), null); assert.equal(h.env.signedIn, false);
    assert.equal(h.store.get(KEY), original); assert.equal(h.writes.length, 0);
    assert.equal(h.events.filter(e => e === 'verity_auth_change').length, 0);
}
test('review auth and entry TSX syntax', () => {
    transformSync(source, { loader: 'tsx' });
    transformSync(entry, { loader: 'tsx' });
});
test('expired getter stays null until validated refresh saves and notifies the exact entry', async () => {
    const d = deferred(), h = harness({ fetch: () => d.promise }); h.start(); await flush();
    assert.equal(h.env.getSession(), null); assert.equal(h.env.signedIn, false); assert.equal(h.requests.length, 1);
    d.resolve(response(validResponse())); await flush();
    assert.equal(h.env.getSession().access_token, 'fixture-new'); assert.equal(h.env.signedIn, true);
    assert.equal(h.writes.length, 1); assert.deepEqual(h.events, ['verity_auth_change']); assert.equal(h.timers.size, 0);
});
test('unexpired ordinary reload has no refresh request', async () => {
    const h = harness({ stored: fixture({ expires_at: 2003600 }) }); h.start(); await flush();
    assert.equal(h.env.signedIn, true); assert.equal(h.requests.length, 0); assert.equal(h.writes.length, 0);
});
test('resume after expiry refreshes on existing interval', async () => {
    const h = harness({ stored: fixture({ expires_at: 2000360 }) }); h.start(); await flush();
    h.advance(420000); assert.equal(h.env.getSession(), null); await h.tick();
    assert.equal(h.requests.length, 1); assert.equal(h.env.signedIn, true);
});
test('init and interval do not duplicate an in-flight refresh', async () => {
    const d = deferred(), h = harness({ fetch: () => d.promise }); h.start(); await flush(); await h.tick();
    assert.equal(h.requests.length, 1); d.resolve(response(validResponse())); await flush(); assert.equal(h.writes.length, 1);
});
for (const [label, stored] of Object.entries({ missing: null, json: '{', empty: {}, array: [], access: fixture({ access_token: ' ' }), user: fixture({ user: {} }), expiry: fixture({ expires_at: '1999940' }), expiryZero: fixture({ expires_at: 0 }), refreshType: fixture({ refresh_token: 4 }), refreshEmpty: fixture({ refresh_token: '' }) })) {
    test('stored input fail-closed: ' + label, async () => {
        const h = harness({ stored }); const before = h.store.get(KEY); h.start(); await flush(); await h.tick();
        noRecovery(h, before); assert.equal(h.requests.length, 0);
    });
}
for (const [label, body] of Object.entries({ empty: null, access: validResponseWith({ access_token: '' }), refresh: validResponseWith({ refresh_token: '' }), user: validResponseWith({ user: {} }), wrongUser: validResponseWith({ user: { id: 'other-user' } }), expired: validResponseWith({ expires_at: 1999999 }), boundary: validResponseWith({ expires_at: 2000000 }), missingExpiry: validResponseWith({ expires_at: undefined }), expiryString: validResponseWith({ expires_at: '2003600' }), infinity: validResponseWith({ expires_at: Infinity }) })) {
    test('server response fail-closed: ' + label, async () => {
        const h = harness({ fetch: async () => response(body) }); const before = h.store.get(KEY); h.start(); await flush(); noRecovery(h, before);
    });
}
function validResponseWith(overrides) { return { ...validResponse(), ...overrides }; }
for (const mode of ['network', 'http', 'json', 'read', 'write']) test('failure preserves stored fixture without recovery: ' + mode, async () => {
    const h = harness({ readFailure: mode === 'read', writeFailure: mode === 'write', fetch: async () => {
        if (mode === 'network') throw Error('fixture-offline');
        if (mode === 'http') return { ok: false, json: async () => validResponse() };
        if (mode === 'json') return { ok: true, json: async () => { throw Error('fixture-json'); } };
        return response(validResponse());
    } }); const before = h.store.get(KEY); h.start(); await flush(); noRecovery(h, before);
});
for (const phase of ['headers', 'body', 'noAbort']) test('15s timeout rejects late success: ' + phase, async () => {
    const d = deferred(), h = harness({ noAbort: phase === 'noAbort', fetch: () => phase === 'body' ? { ok: true, json: () => d.promise } : d.promise });
    const before = h.store.get(KEY); h.start(); await flush(); h.expire(); await flush(); noRecovery(h, before);
    d.resolve(phase === 'body' ? validResponse() : response(validResponse())); await flush(); noRecovery(h, before);
    assert.equal(h.timers.size, 0);
});
test('elapsed deadline rejects response even before delayed timer executes', async () => {
    const d = deferred(), h = harness({ fetch: () => d.promise }); const before = h.store.get(KEY); h.start(); await flush();
    h.advance(16000); d.resolve(response(validResponse())); await flush(); noRecovery(h, before);
});
test('actual logout while refresh waits cannot revive the session', async () => {
    const d = deferred(), h = harness({ fetch: () => d.promise }); h.start(); await flush(); await h.env.logout();
    assert.equal(h.store.has(KEY), false); const eventCount = h.events.length;
    d.resolve(response(validResponse())); await flush();
    assert.equal(h.env.signedIn, false); assert.equal(h.env.session, null); assert.equal(h.store.has(KEY), false);
    assert.equal(h.writes.length, 0); assert.equal(h.events.length, eventCount);
});
for (const mode of ['account', 'rotation', 'sameValueRelogin', 'otherTab', 'otherTabLogout', 'otherTabABA']) test('inflight ownership guard: ' + mode, async () => {
    const d = deferred(), h = harness({ fetch: () => d.promise }); h.start(); await flush();
    const replacement = mode === 'rotation' ? fixture({ access_token: 'fixture-other', expires_at: 2003600 }) : fixture({ user: { id: 'other-user' }, expires_at: 2003600 });
    if (mode === 'sameValueRelogin') { h.env.clear(); h.env.save(fixture()); h.env.emitAuth(); }
    else if (mode === 'otherTabLogout') { h.store.delete(KEY); h.storageEvent(null); }
    else if (mode === 'otherTabABA') { h.store.delete(KEY); h.storageEvent(); h.store.set(KEY, JSON.stringify(fixture())); h.storageEvent(); }
    else if (mode === 'otherTab') { h.store.set(KEY, JSON.stringify(replacement)); h.storageEvent(); }
    else { h.env.save(replacement); h.env.emitAuth(); }
    const expected = h.store.get(KEY), writes = h.writes.length, eventCount = h.events.length;
    d.resolve(response(validResponse())); await flush();
    assert.equal(h.store.get(KEY), expected); assert.equal(h.writes.length, writes); assert.equal(h.events.length, eventCount);
    assert.equal(h.env.session?.user?.id ?? null, h.env.getSession()?.user?.id ?? null);
});
test('unmount invalidates refresh before storage or notification', async () => {
    const d = deferred(), h = harness({ fetch: () => d.promise }); const before = h.store.get(KEY), cleanup = h.start(); await flush();
    cleanup(); d.resolve(response(validResponse())); await flush(); noRecovery(h, before);
});
