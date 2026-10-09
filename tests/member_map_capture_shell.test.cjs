const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const cp = require('node:child_process');
const yaml = fs.readFileSync(path.join(__dirname,'../.github/workflows/kr_company_facts_backfill.yml'),'utf8');
const step = yaml.split('      - name: Build path-free automatic evidence catalog\n')[1].split('\n      - name:')[0];
const script = step.split('        run: |\n')[1].split('\n').map(line=>line.replace(/^          /,'')).join('\n');
const stubs = `
node() { printf '%s\\n' "$*" >> "$CALLS"; }
python3() {
  if [ "$1" != scripts/member-map/capture-contract-facts.py ]; then command python3 "$@"; return; fi
  shift
  command python3 - "$@" <<'PY'
import sys, os, json, pathlib
args=sys.argv[1:]
kind=args[args.index('--filing-type')+1]
out=pathlib.Path(args[args.index('--output-dir')+1])
assert not out.exists(), 'output directory must not exist'
out.mkdir()
with open(os.environ['CALLS'],'a') as f: f.write(kind+'\\n')
stopped=kind=='contract' and os.environ['STOP_SOURCE']=='1'
doc=dict(schema='local-public-contract-capture-v1',filing_type=kind,available=10,selected=6,attempted=1 if stopped else 6,parsed=0 if stopped else 6,not_attempted=5 if stopped else 0,stopped='source-access-or-rate-limit' if stopped else None)
(out/'manifest.json').write_text(json.dumps(doc))
PY
}
`;
for (const stop of [false,true]) test('executes actual workflow shell; source stop='+stop,()=>{
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'map-capture-shell-'));
  fs.mkdirSync(path.join(dir,'data'));fs.mkdirSync(path.join(dir,'tmp'));
  fs.writeFileSync(path.join(dir,'data/member_map_auto_evidence.json'),' {"contract_facts":[]}');
  const env={...process.env,RUNNER_TEMP:path.join(dir,'tmp'),GITHUB_ENV:path.join(dir,'env'),GITHUB_OUTPUT:path.join(dir,'out'),GITHUB_STEP_SUMMARY:path.join(dir,'summary'),CALLS:path.join(dir,'calls'),STOP_SOURCE:stop?'1':'0'};
  const result=cp.spawnSync('bash',['-euo','pipefail','-c',stubs+'\n'+script],{cwd:dir,env,encoding:'utf8'});
  assert.equal(result.status,0,result.stderr);
  const calls=fs.readFileSync(env.CALLS,'utf8');
  assert.match(calls,/--prior-captures data\/member_map_auto_evidence.json/);
  assert.match(calls,/\ncontract\n/);
  assert.equal(calls.includes('\ntermination\n'),!stop);
  assert.match(fs.readFileSync(env.GITHUB_OUTPUT,'utf8'),new RegExp('source_access_stop='+stop));
  assert.match(fs.readFileSync(env.GITHUB_STEP_SUMMARY,'utf8'),stop?/not-attempted-after-contract-source-stop/:/selected-set-parsed/);
});

const annualStep = yaml.split('      - name: Capture bounded annual customer tables\n')[1].split('\n      - name:')[0];
const annualScript = annualStep.split('        run: |\n')[1].split('\n').map(line => line.replace(/^          /, '')).join('\n');
for (const state of ['parsed', 'empty', 'stopped', 'maintenance', 'over-budget']) test('executes annual workflow shell; '+state, t => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'map-annual-shell-'));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const env = {...process.env, RUNNER_TEMP: dir, GITHUB_ENV: path.join(dir, 'env'),
    GITHUB_OUTPUT: path.join(dir, 'out'), GITHUB_STEP_SUMMARY: path.join(dir, 'summary'), CASE_STATE: state};
  const stub = `python3() {
    if [ "$1" != scripts/member-map/capture-annual-customer-tables.py ]; then command python3 "$@"; return; fi
    shift
    command python3 - "$@" <<'PY'
import sys, os, json, pathlib
args = sys.argv[1:]
assert args[args.index('--limit')+1] == '3'
assert '--fetch-public' in args and '--apply-local' in args
out = pathlib.Path(args[args.index('--output-dir')+1]); out.mkdir()
state = os.environ['CASE_STATE']
selected = 0 if state == 'empty' else 3
stopped = state in ('stopped', 'maintenance')
attempted = 1 if stopped else selected
row = dict(schema='local-public-annual-customer-capture-v1', available=10,
           selected=selected, attempted=attempted, parsed=0 if stopped else selected,
           not_attempted=selected-attempted, public_gets=4 if state=='over-budget' else attempted)
if state == 'stopped': row['stopped']='source-access-or-rate-limit'
if state == 'maintenance': row['stopped']='source-maintenance'
(out/'manifest.json').write_text(json.dumps(row))
PY
  }\n`;
  const result = cp.spawnSync('bash', ['-euo', 'pipefail', '-c', stub + annualScript], {cwd: dir, env, encoding:'utf8'});
  if (state === 'over-budget') {
    assert.notEqual(result.status, 0);
    assert.equal(fs.existsSync(env.GITHUB_OUTPUT), false);
  } else {
    assert.equal(result.status, 0, result.stderr);
    assert.match(fs.readFileSync(env.GITHUB_OUTPUT, 'utf8'), new RegExp('source_access_stop='+(['stopped', 'maintenance'].includes(state))));
    if (state === 'maintenance') assert.match(fs.readFileSync(env.GITHUB_STEP_SUMMARY, 'utf8'), /state=source-maintenance/);
    assert.match(fs.readFileSync(env.GITHUB_STEP_SUMMARY, 'utf8'), /Parsed reports do not imply matched customer relationships/);
  }
});
