// 기간 원문 인자 전달만 검증한다. Python·SDK·네트워크·실제 환경값은 사용하지 않는다.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { createHash } = require('node:crypto');
const root = path.resolve(__dirname, '..');
const script = path.join(root, 'scripts/member-map/upload-ai-candidates.cjs');
const source = fs.readFileSync(script, 'utf8');
const body = Buffer.from(JSON.stringify({ schema: 'local-ai-review-v1', candidates: [] }));
const digest = createHash('sha256').update(body).digest('hex');
const period = { periodInput: 'synthetic/period.json', periodSourceDir: 'synthetic/period-source',
  issuerRegistryPath: 'synthetic/issuers.json' };
const flags = [['--period-input', 'periodInput'], ['--period-source-dir', 'periodSourceDir'],
  ['--issuer-registry-path', 'issuerRegistryPath']];
const periodArgs = () => flags.flatMap(([flag, key]) => [flag, period[key]]);
const artifactArgs = () => ['--artifact', 'synthetic/public.json', '--artifact-sha256', digest,
  '--source-dir', 'synthetic/source'];
const clean = value => JSON.parse(JSON.stringify(value));

function isolated(t) {
  const forbidden = [], environmentReads = [], outputs = new Set();
  const deny = name => { forbidden.push(name); throw Error('금지된 테스트 접근'); };
  const environment = new Proxy({}, {
    get(_target, name) { environmentReads.push(name); return name === 'PATH' ? '/synthetic-bin' : deny('환경값'); },
    ownKeys() { return deny('환경값 열거'); },
  });
  function guardedRequire(name) {
    if (name === 'node:fs') return new Proxy(fs, { get(target, key) {
      if (key === 'readFileSync') return file => {
        if (!outputs.has(file)) return deny('파일 읽기');
        return target.readFileSync(file);
      };
      return target[key];
    } });
    if (name === 'node:child_process') return { spawnSync: () => deny('실제 자식 프로세스') };
    if (['node:os', 'node:path', 'node:crypto'].includes(name)) return require(name);
    return deny('SDK 또는 미허용 모듈');
  }
  const module = { exports: {} };
  vm.runInNewContext(source, { module, require: guardedRequire, __dirname: path.dirname(script),
    process: { env: environment }, Buffer, URL, AbortSignal,
    fetch: () => deny('전역 네트워크'), setTimeout: () => deny('지연 재시도') }, { filename: script });
  const deps = {};
  for (const key of ['env', 'fetch', 'head', 'put', 'sleep']) {
    Object.defineProperty(deps, key, { get() { return deny('의존성 ' + key); } });
  }
  t.after(() => {
    assert.deepEqual(forbidden, [], '금지 접근 시도도 없어야 한다');
    assert.ok(environmentReads.every(key => key === 'PATH'));
    for (const output of outputs) assert.equal(fs.existsSync(path.dirname(output)), false, '임시 출력 정리');
  });
  return { ...module.exports, deps, outputs, environmentReads };
}

test('artifact 모드에서 기간 세 인자를 정확한 옵션 이름으로 받는다', t => {
  const { parseArgs } = isolated(t);
  assert.deepEqual(clean(parseArgs([...artifactArgs(), ...periodArgs()])), {
    artifact: 'synthetic/public.json', artifactSha256: digest, sourceDir: 'synthetic/source', ...period,
  });
});

for (const [missingFlag, missingKey] of flags) {
  test(`기간 인자 누락을 거부한다: ${missingFlag}`, t => {
    const { parseArgs } = isolated(t);
    const incomplete = flags.filter(([, key]) => key !== missingKey).flatMap(([flag, key]) => [flag, period[key]]);
    assert.throws(() => parseArgs([...artifactArgs(), ...incomplete]), { message: 'public-ai-publish-arguments-rejected' });
  });
}

test('기간 인자 한 개만 제공하는 세 부분 입력을 거부한다', t => {
  const { parseArgs } = isolated(t);
  for (const [flag, key] of flags) {
    assert.throws(() => parseArgs([...artifactArgs(), flag, period[key]]), { message: 'public-ai-publish-arguments-rejected' });
  }
});

for (const [flag, key] of flags) {
  test(`같은 값과 다른 값의 중복 옵션을 거부한다: ${flag}`, t => {
    const { parseArgs } = isolated(t);
    for (const value of [period[key], 'synthetic/other']) {
      assert.throws(() => parseArgs([...artifactArgs(), ...periodArgs(), flag, value]), { message: 'public-ai-publish-arguments-rejected' });
    }
  });
}

for (const [mode, modeArgs] of [['input', ['--input', 'synthetic/input.json']], ['worker', ['--worker-state']]]) {
  test(`${mode} 모드는 기간 인자의 모든 비어 있지 않은 조합을 거부한다`, t => {
    const { parseArgs } = isolated(t);
    for (let mask = 1; mask < 8; mask++) {
      const extra = flags.filter((_, i) => mask & (1 << i)).flatMap(([flag, key]) => [flag, period[key]]);
      assert.throws(() => parseArgs([...modeArgs, '--source-dir', 'synthetic/source', ...extra]),
        { message: 'public-ai-publish-arguments-rejected' });
    }
  });
}

test('미지원 옵션 및 값 없는 기간 옵션을 거부한다', t => {
  const { parseArgs } = isolated(t);
  assert.throws(() => parseArgs([...artifactArgs(), ...periodArgs(), '--period-unknown', 'synthetic']),
    { message: 'public-ai-publish-arguments-rejected' });
  for (const [flag] of flags) {
    for (const suffix of [[], [''], ['--upload']]) {
      assert.throws(() => parseArgs([...artifactArgs(), flag, ...suffix]), { message: 'public-ai-publish-arguments-rejected' });
    }
  }
});

test('dry-run은 Python 검증 인자만 정확히 전달하며 비밀값·SDK·네트워크에 접근하지 않는다', async t => {
  const h = isolated(t), calls = [];
  h.deps.run = (command, args, options) => {
    calls.push({ command, args: clean(args), options: clean(options) });
    const output = args.at(-1);
    h.outputs.add(output);
    fs.writeFileSync(output, body, { flag: 'wx', mode: 0o600 });
    return { status: 0 };
  };
  const result = await h.publish(h.parseArgs([...artifactArgs(), ...periodArgs()]), h.deps);
  assert.equal(calls.length, 1);
  const call = calls[0], output = call.args.at(-1);
  assert.equal(call.command, 'python3');
  assert.deepEqual(call.args, [path.join(path.dirname(script), 'validate-public-ai-artifact.py'),
    '--artifact', path.resolve('synthetic/public.json'), '--sha256', digest,
    '--period-input', path.resolve(period.periodInput), '--period-source-dir', path.resolve(period.periodSourceDir),
    '--issuer-registry-path', path.resolve(period.issuerRegistryPath),
    '--source-dir', path.resolve('synthetic/source'), '--output', output]);
  assert.equal(path.basename(output), 'member_map_ai_candidates.json');
  assert.deepEqual(call.options, { cwd: root, env: { PATH: '/synthetic-bin', PYTHONDONTWRITEBYTECODE: '1' },
    encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'], timeout: 30000, maxBuffer: 16384 });
  assert.deepEqual(clean(result), {
    url: 'https://rte5guenhonw9fzn.public.blob.vercel-storage.com/member_map_ai_candidates.json', sha256: digest, count: 0,
  });
  assert.deepEqual(h.environmentReads, ['PATH']);
});

test('직접 publish 호출도 부분·비문자·다른 모드를 Python 실행 전에 거부한다', async t => {
  const h = isolated(t); let runs = 0;
  h.deps.run = () => { runs++; throw Error('실행되면 안 됨'); };
  const base = h.parseArgs([...artifactArgs(), ...periodArgs()]);
  const invalid = [];
  for (const [, key] of flags) {
    for (const value of [undefined, '', true, 1, [], {}]) invalid.push({ ...base, [key]: value });
  }
  for (const mode of [{ input: 'synthetic/input.json' }, { workerState: true }]) {
    invalid.push({ sourceDir: 'synthetic/source', ...period, ...mode });
  }
  for (const options of invalid) {
    await assert.rejects(h.publish(options, h.deps), { message: 'public-ai-publish-local-validation-rejected' });
  }
  assert.equal(runs, 0); assert.deepEqual(h.environmentReads, []);
});

test('Python 실패와 출력 해시 불일치는 외부 접근 없이 고정 오류로 종료한다', async t => {
  const h = isolated(t), options = h.parseArgs([...artifactArgs(), ...periodArgs()]);
  let runs = 0;
  h.deps.run = () => { runs++; return { status: 1, stderr: '합성 비공개 오류 원문' }; };
  await assert.rejects(h.publish(options, h.deps), { message: 'public-ai-publish-local-validation-rejected' });
  h.deps.run = (_command, args) => {
    runs++; const output = args.at(-1); h.outputs.add(output);
    fs.writeFileSync(output, Buffer.concat([body, Buffer.from('\n')]), { flag: 'wx', mode: 0o600 });
    return { status: 0 };
  };
  await assert.rejects(h.publish(options, h.deps), { message: 'public-ai-publish-local-validation-rejected' });
  assert.equal(runs, 2);
});
