# AlphaNest standalone member-map review

Temporary integration surface: `https://project-yw131.vercel.app/member-map-review`.
This is not a replacement for the accepted Sites v36 design and is not a Framer Publish.

## Boundaries

- Existing AlphaNest Google/email sign-in; no new provider, test identity creation, or session transfer.
- The review shell is publicly downloadable; holdings and map records require the existing member JWT and owner checks. `noindex` is not an access control.
- Holdings are read-only in this client. Map positions, notes and marks are drafts until explicit save; existing revision-conflict and account-switch protections are unchanged.
- `Map.snapshot.tsx` is the saved Framer review component (`aPYjLyI`, source SHA `e4660dcfb7e0eb814a8d6586acc739748a32a2d9032cd0b1c78ebd9819e0e0be`).
- `Auth.snapshot.tsx` was fresh-read from `k5Rb6uP` on 2026-09-29 KST; it matches the local mirror after whitespace normalization. It is reused, not pushed back to Framer. Only normal browser login creates the session.
- PublicAuth remains mounted when its account panel is hidden so refresh/listeners survive. The map is not mounted while signed out.
- Only the exact review return URL may be added to Supabase's existing redirect list. Existing URLs and Site URL must remain unchanged.
- The review uses the API's own origin: no CORS allowlist expansion, proxy or origin spoofing.
- Graph data represents company-to-source-document associations. Shared documents are not automatically verified common events or investment impact. Accepted visual parity and verified relationship/event inputs remain pending.

## Build

`node review/member-map/build.cjs /path/to/existing/verity/workspace`

The path supplies already-installed esbuild/React and existing `.env` public Supabase URL/anon key. The build validates project ref and `role=anon`; no service key, private response or member record is included. No source map or external script is loaded. Review-specific CSP/robots/cache headers do not modify existing API routes, `ignoreCommand`, authentication or database permissions.

## Verify

Check the signed-out page and console first. Once deployed, read back HTML/asset hashes and scoped headers, then have the user complete normal Google sign-in. Verify holdings retrieval, existing map-state retrieval, explicit test edits, save acknowledgement and a fresh page restoration separately. Preserve existing notes/layouts/marks. Do not infer browser acceptance from prior API-runner tests.
