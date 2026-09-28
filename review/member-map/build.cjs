// Temporary review build. Uses already-installed tools and only the existing public anon key.
const fs = require('node:fs'), path = require('node:path'), util = require('node:util'), crypto = require('node:crypto');
const sourceRoot = path.resolve(process.argv[2] || '.');
const repo = path.resolve(__dirname, '../..');
const env = util.parseEnv(fs.readFileSync(path.join(sourceRoot, '.env'), 'utf8'));
const url = env.SUPABASE_URL?.replace(/\/+$/, ''), anon = env.SUPABASE_ANON_KEY;
if (url !== 'https://lykqebdcurreppowulsl.supabase.co' || !anon) throw Error('Expected AlphaNest public auth config');
const payload = JSON.parse(Buffer.from(anon.split('.')[1] || '', 'base64url').toString());
if (payload.role !== 'anon' || payload.ref !== 'lykqebdcurreppowulsl') throw Error('Only project public anon key is allowed');
const esbuild = require(path.join(sourceRoot, 'node_modules/esbuild'));
esbuild.buildSync({ entryPoints: [path.join(__dirname, 'entry.tsx')],
    outfile: path.join(repo, 'vercel-api/member-map-review/app.js'), bundle: true, minify: true,
    platform: 'browser', format: 'iife', jsx: 'automatic', target: ['es2020'],
    nodePaths: [path.join(sourceRoot, 'operator-web/node_modules')],
    alias: { framer: path.join(__dirname, 'framer-shim.ts') },
    define: { 'process.env.NODE_ENV': '"production"', __PUBLIC_AUTH__: JSON.stringify({ url, anon }) },
    legalComments: 'eof' });
const output = fs.readFileSync(path.join(repo, 'vercel-api/member-map-review/app.js'));
for (const token of output.toString().match(/eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+/g) || []) {
    const claims = JSON.parse(Buffer.from(token.split('.')[1], 'base64url').toString());
    if (claims.role !== 'anon' || claims.ref !== payload.ref) throw Error('Non-public token in browser output');
}
if (output.includes('sb_secret_')) throw Error('Private key marker in browser output');
const hash = file => crypto.createHash('sha256').update(fs.readFileSync(path.join(repo, file))).digest('hex');
console.log(JSON.stringify({ bytes: output.length, publicAuthOnly: true, hashes: Object.fromEntries([
    'review/member-map/Map.snapshot.tsx', 'review/member-map/Auth.snapshot.tsx',
    'review/member-map/entry.tsx', 'vercel-api/member-map-review/app.js'
].map(file => [file, hash(file)])) }, null, 2));
