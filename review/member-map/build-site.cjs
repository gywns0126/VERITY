// Reuse the accepted renderer on AlphaNest's origin; never bundle auth/session values.
const fs = require('node:fs'), path = require('node:path'), crypto = require('node:crypto');
const root = path.resolve(__dirname, '../..');
const dependencyRoot = process.env.MEMBER_MAP_TEST_DEPENDENCY_ROOT || root;
const esbuild = require(path.join(dependencyRoot, 'node_modules/esbuild'));
const API = 'https://project-yw131.vercel.app';
function replaceOne(source, old, value, count = 1) {
  if (source.split(old).length - 1 !== count) throw Error('Site build boundary changed: ' + old);
  return source.split(old).join(value);
}
const plugin = { name: 'site-map-existing-renderer', setup(build) {
  build.onResolve({ filter: /^alphanest-site-map$/ }, () => ({ path: 'existing-map', namespace: 'site-map' }));
  build.onLoad({ filter: /.*/, namespace: 'site-map' }, () => {
    const original = fs.readFileSync(path.join(__dirname, 'Map.snapshot.tsx'), 'utf8');
    let contents = replaceOne(original, 'api = "/api/search"', 'api = "' + API + '/api/search"');
    contents = replaceOne(contents, '      ref: frame,', '      ref: frame,\n      "data-an-site-map": "",');
    contents += '\nexport { PublicPortfolioPrototype as SiteMap, readMapSession as readSiteMapSession };\n';
    return { contents, loader: 'tsx', resolveDir: __dirname };
  });
  build.onLoad({ filter: /company-structure-view\.tsx$/ }, args => {
    let contents = fs.readFileSync(args.path, 'utf8');
    contents = replaceOne(contents, 'fetcher(`/api/company_structure?', 'fetcher(`' + API + '/api/company_structure?');
    contents = replaceOne(contents, 'fetcher("/member-map-review/company-structure.json"', 'fetcher("' + API + '/member-map-review/company-structure.json"');
    contents = replaceOne(contents, 'new URL(f.src).pathname === "/member-map-canvas"', '(f.matches("iframe[data-an-site-map]") || new URL(f.src).pathname === "/member-map-canvas")', 2);
    contents = replaceOne(contents, '"/member-map-review/solidigm-logo.png"', '"' + API + '/member-map-review/solidigm-logo.png"');
    return { contents, loader: 'tsx', resolveDir: __dirname };
  });
} };
async function buildSite(outfile = path.join(root, 'framer-components/public-probe/PublicMindmap.tsx')) {
  const result = await esbuild.build({ entryPoints: [path.join(__dirname, 'site-entry.tsx')], bundle: true, write: false,
    format: 'esm', platform: 'browser', target: ['es2020'], jsx: 'transform', external: ['react', 'framer'], plugins: [plugin] });
  const bytes = result.outputFiles[0].contents;
  let runtime = new TextDecoder().decode(bytes);
  runtime = replaceOne(runtime, 'export {\n  PublicMindmap as default\n};', '');
  const body = '// @ts-nocheck\n// Generated from review/member-map/site-entry.tsx; preserve existing data, notes, positions and unsaved drafts.\nimport * as SiteReact from "react";\nimport { addPropertyControls as sitePropertyControls } from "framer";\n' + runtime + `
/**
 * Same-origin AlphaNest mindmap; keep the accepted renderer and existing session.
 * @framerIntrinsicWidth 1200
 * @framerIntrinsicHeight 900
 * @framerSupportedLayoutWidth any-prefer-fixed
 * @framerSupportedLayoutHeight auto
 */
export default function AlphaNestMindmap({ style }: { style?: SiteReact.CSSProperties }) {
  return <PublicMindmap style={style} />;
}
sitePropertyControls(AlphaNestMindmap, {});
`;
  if (/sb_secret_|refresh_token=|access_token=/.test(body)) throw Error('Unexpected authentication material in site bundle');
  fs.mkdirSync(path.dirname(outfile), { recursive: true }); fs.writeFileSync(outfile, body);
  return { outfile, bytes: Buffer.byteLength(body), sha256: crypto.createHash('sha256').update(body).digest('hex') };
}
module.exports = { buildSite, plugin, replaceOne };
if (require.main === module) buildSite(process.argv[2]).then(x => console.log(JSON.stringify(x))).catch(e => { console.error(e.message); process.exitCode = 1; });
