# Company core delivery candidate

The existing AlphaNest site and full analysis path remain the operating default.
This candidate moves public financial facts and disclosure projection from the
first user request to the existing public-data publication step. Relations,
news, judgments, prices and changes still come from the existing full lane.

## Publication contract

`publish-data` builds candidates in a new runner-temporary directory, outside
the existing `_public_dist` bundle. It projects all companies from these six
existing public inputs: universe, KR/US stock reports, KR/US disclosure feeds
and KR business overviews. It does not read member rows or call a model.

The release names immutable, content-addressed company buckets. It binds their
exact bytes/counts, the six staged input byte hashes, projection/engine code,
publication day and exact parent receipt bytes. The publisher verifies the six
current public inputs and parent, writes/verifies create-only buckets, rechecks
the parent, then changes the root with the original ETag (or create-only for
the first root). A failed candidate never replaces the operating route or the
last successful candidate root. No transport/412 retry relaxes that condition.

Only the new safe-summary artifact is needed for natural followup. Its fields
are status, fixed reason code, bucket/company counts, release SHA/bytes, parent
receipt SHA and source revision. It contains no source bodies, selected stocks,
auth tokens or member records. The existing collection/publication schedules
are unchanged.

## Request and state contract

`/api/member_map_company_snapshot` reuses the existing origin/JWT boundary and
private/no-store response encoder. It accepts at most 30 market/ticker pairs,
reads only the root/current parent/selected buckets, verifies their exact
generation and selected record schemas, and returns an initial **read-only**
core payload. It never reads layouts, notes, holdings or stored member state.

The publication day is not an original filing date or a freshness assertion.
The exact current parent remains usable across midnight while a scheduled run
is delayed; a future publication day, changed parent or changed code fails
closed. Original fact periods and disclosure dates are preserved.

The inactive frontend helper reuses the strict existing adapter. The first
core preview uses the existing private-restore, owner, generation and abort
guards. A full replacement requires both pre-cap fact/document content
inclusion and retention of already delivered core document IDs. On mismatch
or enrichment failure the verified core stays read-only; the existing manual
recheck retries enrichment without reloading private records or the frame.
The ordinary full API adds content claims only for `?core_claims=1`; its default
serialized result remains unchanged.

## Acceptance before switching the site

1. Compare fixed public selections and the same renderer under the same
   conditions. Record API latency, data arrival and actually visible core
   evidence cards separately. An identity-only preview, hidden card, local-file
   speed or HTTP timing is not operating card completion. Target: 5 seconds.
2. Verify notes, manual positions and dirty drafts with synthetic private state;
   do not inspect or reload the user's original tab/state.
3. Observe the next existing natural KR/US publication with this exact code.
   Bind run/event/checkout, six sources, source/store/public bytes and candidate
   release. Show its newly changed public evidence in the actual candidate map.
4. Independently review the candidate and only then switch/publish the Framer
   delivery route. If evidence is missing, retain the operating route and state
   which acceptance step remains. Do not force collection to manufacture proof.

No new AI inspection schedule is part of this change. Local or CI checks are
not natural publication, authenticated operating UI acceptance or formal release.
