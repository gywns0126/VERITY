# AlphaNest standalone member-map review

Temporary integration surface: `https://project-yw131.vercel.app/member-map-review`.
This is not a replacement for the accepted Sites v36 design and is not a Framer Publish.

## Current renderer — accepted HTML integration (2026-10-01)

### Search exploration and list return

This candidate reuses the existing same-origin public `/api/search` endpoint.
Only public symbol/name/market/ETF metadata is sent to the sandbox, with bounded
results, cancellation and a parent-side current-result allowlist. It does not
expand CSP, auth, API or database permissions. Coverage is the existing search
catalogue, not every listed/unlisted company or a new financial-data source.

The accepted search/add/PC-drag controls now add a stock to the current graph,
not the holdings or watch list. Exploration membership is session-local and
labelled accordingly; private membership persistence is not claimed. Graph
loading is atomic: failure keeps the ready map and current edits. Success
updates the same iframe and retains existing world positions and notes, while
adding/removing returned evidence nodes and links. Shared counts include visible
held, watched and exploratory stocks. Source documents remain distinct from
manually reviewed common events, and missing evidence does not prove no relation.

The Nest return action focuses the single successfully edited stock after the
refreshed frame acknowledges hydration. It does not unhide a filtered stock,
replace the selection window or toggle an already selected stock off. Holdings
also state explicitly that current prices are disconnected and valuation/profit
calculations are deferred; average cost is not a quote.

Source regressions, strict TypeScript and 28 generated snapshot checks passed.
Synthetic isolated Chrome checked real pointer addition, evidence node insertion/
replacement and stale-edge cleanup, existing world positions/notes, unchanged
holding writes, account cleanup and 1280/390px light/dark search. Adding NVDA and
INTC showed the existing dated reviewed common event with two source buttons;
its read mark and an off-window prior mark were saved in the synthetic store.
These checks are not authenticated production acceptance or a live save/reconnect.
They do not change the original Sites artifact or Framer.

### Read-only interest stocks

The standalone candidate opts into the existing authenticated `/api/watchgroups`
GET. Its actual response is an array of owner-scoped groups with nested items.
The client checks both owner and group identity, normalizes supported KR/US
symbols and deduplicates the display universe. Interest-only stocks remain
separate from holdings: they have no inventory quantity, average cost, edit or
delete action. The folded list and map distinguish held, watched and both.
The existing holdings editor/CSV still receives only actual holdings.

At most 30 stocks are shown together; larger unions require an explicit display
selection without changing the member's lists. A failed interest-list read
shows an error while leaving holdings usable. Recovery adds newly available
stocks to an automatic selection but preserves an explicit user selection.
Account changes discard late responses. The request uses a bounded abort and
never writes watch groups or holdings. Existing reviewed relations/events can
include watched companies without changing saved evidence fingerprints.

Local source checks passed 75/75 plus strict TypeScript; generated delivery
snapshot checks passed 23/23 across `member_map_review`, `member_map_holdings`
and `member_map_watchlist.test.cjs`. Synthetic Chrome covered
held/watched deduplication, watched evidence and labels, failure/recovery,
account cleanup and the prior holdings/CSV/map-note flows in light/dark at
1280/390px. These checks do not establish live member isolation or authenticated
save/reconnect. No API, DB, auth, Framer or Sites changes accompany this increment.

### Nest editor increment

The accepted map now opens its shared holdings list with `보유목록`. Merely
switching views preserves the iframe, camera and unsaved map notes. Adding,
editing or deleting a holding requires a before/after preview and a separate
confirm action. Input/preview causes no request. Confirm freshly reads holdings,
refuses a stale target or an existing-ticker POST upsert, then sends one explicit
mutation. It never infers a sale, trade record or holding deletion from hiding a
map node. Only changed editable fields are sent; omitted names, costs and memos
are preserved, including blank stored names. Unsupported assets stay intact.

Requests remain on the existing authenticated holdings API. Logout/account
switch discards the old form and editor; no old-member response refreshes a new
member's workspace. Failure leaves same-member input available. After success,
the shared workspace reloads without discarding unsaved map records. The fresh
read is not an atomic cross-tab compare-and-swap; concurrent editing can still
race the existing API and is not advertised as conflict-proof.

Local synthetic browser acceptance: preview makes zero requests, partial PATCH,
failed-input retention, explicit add/delete, map/list layout continuity, map-note
save after holdings reload, and account switch. Light/dark at 1280px and390px
passed overflow/hover-size checks. Actual private member acceptance is separate;
these checks performed no real holdings write. This increment changes no auth,
API, database permissions, Framer Publish or Sites artifact.

The browser run exposed intermittent blank maps: the frame attribute held the
new canvas URL but its document stayed on a queued srcdoc/about:blank navigation.
URL-mode refresh no longer queues intermediate blank documents. Same-member
loading preserves the canvas; an account reset immediately hides/inerts and
clears the old view. Each new document uses a unique query/hash nonce and a
load-triggered handshake, preventing stale WindowProxy messages from connecting.
Five initial loads and the full synthetic edit/add/delete/account-switch flow
passed after this fix. An empty evidence layer no longer covers a visible stock.
Late theme/resize callbacks stop after the frame is reset, so a disposed member
view cannot redraw cleared controls. The keyboard-focus-expanded synthetic flow
also passes with zero page errors.

The separate React map recreation below is historical and is superseded. The
current snapshot hosts the actual accepted Sites v36 inner HTML at the same-origin
`/member-map-canvas` path, not a restyled map. The v36 baseline source SHA-256 was
`c6e1847ea2f4d07368d4e10bc2a3cbb08ec07eeadb05a48827664d333c7c207c`.
The user-requested blank-click selection fix updates the local source to
`924660b70439ba40cfd9d3c134c34c4270c1dcd745cac135ed94960237856a52`.
One stationary blank click/tap clears selection and restores the overview camera;
positions, notes, marks and filters remain. Marquee, modifier selection, Space-pan
and pointer cancellation retain their previous roles. Local checks passed16/16,
plus isolated Chrome4/4 mouse/touch scenarios at1280/390px with3/30 stocks and
zero browser errors. These are synthetic local checks, not signed-in acceptance.
The original stylesheet blocks and CSP are preserved by the template builder;
the iframe stays `sandbox="allow-scripts"`. React owns only the existing
authenticated Workspace and the parent-side validated MessageChannel bridge.
The outer review keeps `script-src 'self'` and permits only same-origin frames;
the canvas response adds `frame-ancestors 'self'; sandbox allow-scripts` while
preserving its original meta CSP. This avoids inherited `srcdoc` restrictions
without enabling inline scripts on the authenticated parent.
Credentials never enter the iframe. Demo graph inputs are replaced with the
current member's holdings, source documents and bounded reviewed registry facts.

Personal positions, notes and read/important/later/irrelevant marks use the
existing private store and explicit Save. Legacy reviewed connection IDs are
preserved for attached notes. Map interactions never mutate holdings; only the
separately confirmed Nest editor can do so. No access permissions are changed.
Source documents are not automatically labelled common events;
investment impact and connection strength remain unassessed. Synthetic browser
checks and source tests do not establish authenticated live acceptance.

The review snapshot is generated from
`output/member-map-integration-20260927/PortfolioMapReview.entry.tsx` with
esbuild ESM/classic JSX, React/ReactDOM/Framer external and UTF-8.
`scripts/member-map/prototype-template.cjs` produces `vercel-api/public/member-map-canvas.html` from the
accepted artifact and `review/member-map/prototype-member-runtime.js`.
The selection fix also updates the local original HTML; public Sites is not republished.

Local checks: 25 focused source tests and 11 delivery snapshot tests pass. An
isolated browser with synthetic holdings and external network blocked loaded
the separate canvas over local HTTP using the delivery CSP, then passed note
save/reconnect, reviewed event read mark, explicit saved-record reload and
logout clearing. These are not real-member or production acceptance claims.

## Boundaries

- Existing AlphaNest Google/email sign-in; no new provider, test identity creation, or session transfer.
- The review shell is publicly downloadable; holdings and map records require the existing member JWT and owner checks. `noindex` is not an access control.
- Map interactions do not mutate holdings. The Nest editor and CSV import require preview and explicit confirmation through the existing holdings API. Map positions, notes and marks remain drafts until explicit save; existing revision-conflict and account-switch protections are unchanged.
- `Map.snapshot.tsx` is a generated projection of the tested local `PortfolioMapReview.entry.tsx` and its real-controller module graph. It supersedes the earlier two-section visual-only projection. Existing auth, member-state transport, document sources, quote normalizer and API routes are unchanged. This standalone snapshot has not been saved back into Framer.
- `Auth.snapshot.tsx` was fresh-read from `k5Rb6uP` on 2026-09-29 KST; it matches the local mirror after whitespace normalization. It is reused, not pushed back to Framer. Only normal browser login creates the session.
- PublicAuth remains mounted when its account panel is hidden so refresh/listeners survive. The map is not mounted while signed out.
- Only the exact review return URL may be added to Supabase's existing redirect list. Existing URLs and Site URL must remain unchanged.
- The review uses the API's own origin: no CORS allowlist expansion, proxy or origin spoofing.
- Document mode represents company-to-source-document associations, not automatically verified events. Separate reviewed modes contain seven official documents, three dated relationships and two historical common announcements (NVDA/INTC/TSM and SK hynix). Document count is not independent-publisher count: the SK hynix 2024-04-19 Korean/English releases are two editions of one announcement. TSMC's 2023-09-28 memory-partner release corroborates the broader HBM relationship, not that later MOU or current production. These are not a current market-wide feed or evidence of investment impact. Missing matching holdings produce an honest empty state.

## Data and records delivery — 2026-09-29

The current priority is actual data and explicit private persistence; further design alignment is deferred. New reviewed state uses `reviewed:relationships:<id>` and `reviewed:events:<id>` keys. Only personal marks and an equality-only content fingerprint are stored, not copied source documents. Existing notes, positions and document marks are preserved. Content changes request re-reading; the fingerprint is not an event timestamp or an ordered version.

The read-only holdings list reuses the same holdings response; it neither edits holdings nor treats the 30-company map window as a holdings limit. Quantity and cost are shown only when valid, and duplicate lots are not incorrectly summed. Closing-price eligibility remains unchanged; no sample quote replaces missing or permission-blocked data.

Prior source validation: 47/47 focused renderer, reviewed-state and fresh-controller journey checks, strict TypeScript, and 3/3 reviewed-mark payloads accepted by the local API validator. Those used synthetic transport and do not prove deployed member acceptance. After delivery, separately verify authenticated save acknowledgement and a fresh-page restore. No DB, API, CORS, provider or redirect change is part of this delivery.

## Holdings token-rotation recovery — 2026-09-30

The map reads the current same-member session immediately before requesting holdings. After a 401 it retries once only if the normal authentication flow has already produced a different token for that same member. Both attempts share the original 15-second timeout. Logout, account changes, disposal and superseding requests prevent stale results or retries. An unchanged token or a second 401 remains an explicit error; this does not refresh credentials, poll for a future refresh or change shared authentication. The prior live first-load failure was not traced to a captured token race, so synthetic regression coverage alone does not establish its original cause or complete resolution.

## Design-first shell alignment — 2026-09-30

The user moved accepted-design alignment ahead of OHLC integration; no quote work is included. This increment restores the wide-screen item rail, central map and right detail panel, consolidates the header, uses neutral inactive controls and lighter body typography, and removes the duplicate review notice above the signed-in workspace (it remains inside the account panel). The rail shows actual current map items, not fabricated new events, and a second click clears selection. Existing map controls, member persistence, authentication, source evidence and holdings are unchanged. Below 1100px the rail hides, and below 760px details stack after the map. Root UI tests 40/40 and strict TypeScript passed; synthetic browser checks covered 30 holdings, desktop/dark selection, keyboard focus and 390px overflow. Local visual checks do not prove deployment or real-member acceptance.

## Earlier compact design provenance (historical)

The same local renderer passed 53 focused checks plus bounded 30-company browser checks before projection into this snapshot. Rebuilt with existing esbuild (`bundle`, ESM, classic JSX transform, UTF-8, React/ReactDOM/Framer external), only these two source sections were substituted; the other generated sections were compared exactly before writing:

- `PortfolioMapCanvas.tsx`: `e4943d3a267add06d2acb95723a1be69ebef6afcd842b71b5454c2d3b8b5e611`
- `PublicPortfolioMap.tsx`: `8271b591aeee91241d02c119ffb1b082dde03a5b6ea9a40c9c3b60975841b03c`
- Resulting `Map.snapshot.tsx`: `d5aec3b9cf7263e3f16f55d65e750efa0b59c6e968078a64581f9a18a7b4d700`

Long-title follow-up: each card title and subtitle is limited to two visible lines. Full text stays in the DOM, accessible name, hover and detail panel; saved coordinates are not rewritten. A synthetic 30-company / 6-long-document view measured 78px document heights and zero overlapping pairs out of 630 at the default layout. This does not prevent a user from deliberately dragging cards on top of each other.

This brings the accepted v36 compact controls, source colors, pan/zoom grid, measured cards and above-card hover placement into the authenticated review. Actual document content and evidence boundaries intentionally differ from the fictional design fixture. A real pointer-hover placement acceptance remains separate from the source/geometry checks.

## Build

`node review/member-map/build.cjs /path/to/existing/verity/workspace`

The path supplies already-installed esbuild/React and existing `.env` public Supabase URL/anon key. The build validates project ref and `role=anon`; no service key, private response or member record is included. No source map or external script is loaded. Review-specific CSP/robots/cache headers do not modify existing API routes, `ignoreCommand`, authentication or database permissions.

Static files belong under the API project's existing `vercel-api/public/` output directory. `public/member-map-review.html` is served at `/member-map-review` with the existing `cleanUrls` setting; its script and stylesheet live under `public/member-map-review/`. Do not place them beside `vercel.json`: the existing `public` directory means those root-level files are not served.

## Verify

CSV follow-up (2026-10-01): the same holdings panel now reads UTF-8 CSV locally,
previews additions/explicit-ID edits, and saves only after confirmation. It does
not upload the original file, increment quantities, infer companies from names,
delete omitted holdings, or create trades. Invalid rows block the whole preview.
Repeated identical imports are no-ops. Sequential saves stop on first failure;
acknowledged count and an uncertain row are shown separately, without automatic
retry or rollback. Account identity is pinned across the sequence. Unsupported
inventory blocks bulk import because its complete identity/count cannot be proven.
The parser's 30-unique-company add limit does not prevent editing existing larger
inventories; the consistent file/save cap is 200 rows. Cross-tab writes are not
atomic: existing fresh preflight checks remain advisory, not database CAS.

Local source parser/save tests20/20 and synthetic original-renderer browser flows
passed (preview requests0; add/edit; reimport; partial-stop; account change;
1280/390px light/dark). This is not real-member acceptance or deployment proof.

Check the signed-out page and console first. Once deployed, read back HTML/asset hashes and scoped headers, then have the user complete normal Google sign-in. Verify holdings retrieval, existing map-state retrieval, explicit test edits, save acknowledgement and a fresh page restoration separately. Preserve existing notes/layouts/marks. Do not infer browser acceptance from prior API-runner tests.
