#!/usr/bin/env python3
"""REVIEW BEFORE RUNNING. Resume ONLY the two journaled users; no create/delete/reset.
Requires --execute --project-ref EXPECTED --resume-artifact OLD.jsonl --artifact NEW.jsonl.
OLD is read-only; NEW must not exist. Environment:
SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY (dotenv supported). No holdings access.
Artifact is append-only, non-secret: check type/count/status and test UUID/email.
Tokens/links stay in memory; losing them is NOT revocation or secure erasure.
Incomplete/ambiguous identity journals are rejected; existing users are never listed.
Do not concurrently delete/rename these accounts: generate_link can create an absent email.
Official contracts checked 2026-09-27:
https://supabase.com/docs/reference/self-hosting-auth/verifies-a-sign-up
https://supabase.com/docs/reference/javascript/auth-admin-generatelink
https://supabase.com/docs/reference/javascript/auth-verifyotp
https://supabase.com/docs/guides/api
REST fields: github.com/supabase/auth-js, src/GoTrueAdminApi.ts, GoTrueClient.ts, lib/fetch.ts.
--api-surface verifies the fixed existing AlphaNest API instead of repeating the DB-only suite.
Only the same journaled test accounts and known synthetic documents are used.
"""
import argparse
import json
import os
import re
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock
from uuid import UUID


class Stop(Exception):
    pass


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise Stop()  # Never echo supplied arguments.


API_ENDPOINT = "https://project-yw131.vercel.app/api/member_map_state"
SITE_ORIGIN = "https://www.alphanest.kr"


def api_headers(method, token, origin):
    headers = {"Origin": origin}
    if token:
        headers["Authorization"] = "Bearer " + token
    if method == "OPTIONS":
        headers.update({"Access-Control-Request-Method": "POST",
                        "Access-Control-Request-Headers": "authorization,content-type"})
    return headers


def check_api_surface(request, check, users, tokens, states, signin, own):
    """A → API → RLS → DB → new login → API. Caller supplies only known test accounts.

    Deliberately no configurable origin: neither member JWTs nor admin keys can be
    redirected to a preview/third-party URL. The request transport uses member JWTs only.
    """
    def call(method, token=None, body=None, query="", origin=SITE_ORIGIN):
        status, data, headers = request(method, token, body, query, origin)
        check("api_private_headers", "no-store" in headers.get("Cache-Control", "")
              and "Authorization" in headers.get("Vary", "")
              and headers.get("Access-Control-Allow-Origin") == (SITE_ORIGIN if origin == SITE_ORIGIN else None), [status])
        if method == "OPTIONS":
            allowed = lambda key: {item.strip().lower() for item in headers.get(key, "").split(",")}
            check("api_preflight_permissions", {"get", "post"} <= allowed("Access-Control-Allow-Methods")
                  and {"authorization", "content-type"} <= allowed("Access-Control-Allow-Headers"), [status])
        return status, data

    def matches(data, revision, document):
        return (isinstance(data, dict) and set(data) == {"revision", "document", "public_event_cursor_at"}
                and data["revision"] == revision and data["document"] == document
                and data["public_event_cursor_at"] is None)

    status, _ = call("OPTIONS")
    check("api_preflight", status == 200, [status])
    for method in ("GET", "POST"):
        status, _ = call(method, body={"expected_revision": 0, "document": {"layouts": []}} if method == "POST" else None)
        check("api_anon_" + method, status == 401, [status])
    status, _ = call("GET", origin="https://untrusted.invalid")
    check("api_untrusted_origin", status == 401, [status])
    for index, user in enumerate(users):
        state = states[index]
        revision, document = state["revision"], state["document"]
        status, data = call("GET", tokens[index])
        check("api_restore_own", status == 200 and matches(data, revision, document), [status])
        # Query parameters must never select another owner. Handler derives identity from JWT.
        status, data = call("GET", tokens[index], query="?user_id=" + users[1-index]["id"])
        check("api_owner_query_ignored", status == 200 and matches(data, revision, document), [status])
        status, _ = call("POST", tokens[index], {"expected_revision": revision, "document": document, "user_id": users[1-index]["id"]})
        check("api_owner_payload_rejected", status == 400, [status])
        status, data = call("POST", tokens[index], {"expected_revision": revision, "document": document})
        check("api_save_acknowledged", status == 200 and matches(data, revision + 1, document), [status])
        status, data = call("POST", tokens[index], {"expected_revision": revision, "document": document})
        check("api_stale_rejected", status == 409 and data == {"error": "revision_conflict"}, [status])
        expected = {**state, "revision": revision + 1}
        own(tokens[index], user, "api_database_readback", expected)
        status, data = call("GET", signin(user))
        check("api_fresh_signin_restore", status == 200 and matches(data, revision + 1, document), [status])
        # Reading and refreshing identity cannot advance the reserved event cursor.
        own(tokens[index], user, "api_read_has_no_side_effect", expected)


def main():
    parser = Parser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--project-ref", required=True)
    parser.add_argument("--artifact", required=True)
    parser.add_argument("--resume-artifact", required=True)
    parser.add_argument("--api-surface", action="store_true")
    args = parser.parse_args()
    if not args.execute or not re.fullmatch(r"[a-z0-9]{20}", args.project_ref):
        raise Stop()
    import requests
    from dotenv import load_dotenv
    load_dotenv(verbose=False)
    base, anon, service = (os.environ.get(k, "") for k in
                           ("SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY"))
    if base.rstrip("/") != f"https://{args.project_ref}.supabase.co" or not anon or not service or anon == service:
        raise Stop()
    base = base.rstrip("/")
    created = []
    # Exclusive creation refuses overwriting any existing artifact (including symlinks).
    with open(args.artifact, "x", encoding="utf-8") as journal:
        journal_lock = Lock()
        def record(event):
            with journal_lock:
                journal.write(json.dumps(event, separators=(",", ":")) + "\n")
                journal.flush()
                os.fsync(journal.fileno())

        def check(kind, ok, statuses=(), count=1):
            event = {"type": kind, "status": "pass" if ok else "fail",
                     "count": count, "http_status": list(statuses)}
            record(event)
            print(json.dumps(event), flush=True)
            if not ok:
                raise Stop()

        def call(method, path, token=None, body=None, admin=False):
            if admin and not ((method == "GET" and path in ["/auth/v1/admin/users/" + u["id"] for u in created])
                              or (method == "POST" and path == "/auth/v1/admin/generate_link"
                                  and body in [{"type": "magiclink", "email": u["email"]} for u in created])):
                raise Stop()
            key = service if admin else anon
            headers = {"apikey": key, "Authorization": "Bearer " + (token or key)}
            with requests.Session() as session:
                session.trust_env = False  # No inherited proxy/.netrc credentials.
                response = session.request(method, base + path, headers=headers, json=body,
                                           timeout=(10, 20), allow_redirects=False)
                try:
                    data = response.json()
                except ValueError:
                    data = None
                return response.status_code, data

        table, rpc = "/rest/v1/member_map_state", "/rest/v1/rpc/save_member_map_state_v1"
        def save(token, document, revision=0):
            return call("POST", rpc, token, {"p_expected_revision": revision, "p_document": document})

        def conflict(result):
            # The DB raises custom SQLSTATE PT409; verify the direct REST contract.
            status, data = result
            return (status == 409 and isinstance(data, dict) and data.get("code") == "PT409"
                    and data.get("message") == "member_map_revision_conflict")

        def same_user(data, user):
            return isinstance(data, dict) and data.get("id") == user["id"] and data.get("email") == user["email"]

        def admin_user(user):
            status, data = call("GET", "/auth/v1/admin/users/" + user["id"], admin=True)
            check("admin_exact_user", status == 200 and same_user(data, user)
                  and bool(data.get("email_confirmed_at")) and data.get("role") == "authenticated", [status])

        def signin(user):
            admin_user(user)  # Fail before generate_link if the recorded account no longer exists.
            status, data = call("POST", "/auth/v1/admin/generate_link", body={
                "type": "magiclink", "email": user["email"]}, admin=True)
            # Raw REST is flat: SDK moves hashed_token into properties and remaining fields into user.
            check("generate_magiclink", status == 200 and same_user(data, user)
                  and data.get("verification_type") == "magiclink"
                  and isinstance(data.get("hashed_token"), str) and bool(data["hashed_token"]), [status])
            status, data = call("POST", "/auth/v1/verify", body={"type": "magiclink", "token_hash": data["hashed_token"]})
            valid = isinstance(data, dict) and isinstance(data.get("user"), dict)
            check("signin", status == 200 and valid and same_user(data["user"], user)
                  and data["user"].get("role") == "authenticated"
                  and isinstance(data.get("access_token"), str) and bool(data["access_token"]), [status])
            return data["access_token"]

        def document(label):
            return {"layouts": [{"map_key": "live_test", "positions": [{"node_id": "test-node", "x": 12, "y": -9}],
                    "notes": [{"note_id": "test-note", "anchor": {"kind": "node", "id": "test-node"},
                               "x": 3, "y": 4, "text": "test-only " + label, "done": False}],
                    "marks": {"test-node": {"read_revision": 7, "important": True, "disposition": "later"}}}]}

        def own(token, user, kind, expected=None):
            status, data = call("GET", table + "?select=user_id,revision,document,public_event_cursor_at&user_id=eq." + user["id"], token)
            valid = isinstance(data, list) and len(data) <= 1
            state = data[0] if valid and data else {"user_id": user["id"], "revision": 0, "document": {"layouts": []}, "public_event_cursor_at": None}
            valid = valid and isinstance(state, dict) and state.get("user_id") == user["id"]
            valid = valid and type(state.get("revision")) is int and 0 <= state["revision"] < 9007199254740990
            check(kind, status == 200 and valid and (expected is None or state == expected), [status])
            # *_revision count is the observed revision, never an assertion about a pending request.
            record({"type": kind + "_revision", "status": "present" if data else "absent", "count": state["revision"]})
            return state

        outcome = "failed"
        try:
            record({"type": "run", "status": "started", "count": 2,
                    "project_ref": args.project_ref, "at": datetime.now(timezone.utc).isoformat()})
            with open(args.resume_artifact, encoding="utf-8") as previous:
                events = [json.loads(line) for line in previous if line.strip()]
            runs = [e for e in events if e.get("type") == "run"]
            users = [e for e in events if e.get("type") in ("created_user", "confirmed_user")]
            check("resume_project", len(runs) == 1 and runs[0].get("project_ref") == args.project_ref
                  and runs[0].get("count") == 2)
            check("resume_user_count", len(users) == 2, count=len(users))
            for user in users:
                check("resume_identity", user.get("status") == "confirmed" and user.get("count") == 1
                      and isinstance(user.get("id"), str) and str(UUID(user["id"])) == user["id"]
                      and UUID(user["id"]).version == 4 and isinstance(user.get("email"), str)
                      and re.fullmatch(r"member-map-[0-9a-f]{24}-[ab]@test-only\.invalid", user["email"]) is not None)
            check("resume_distinct_users", len({u["id"] for u in users}) == 2
                  and {u["email"].split("@")[0][-1] for u in users} == {"a", "b"})
            attempts = [e.get("email") for e in events if e.get("type") == "create_attempt"]
            check("resume_no_unknown_creation", not attempts or sorted(attempts) == sorted(u["email"] for u in users))
            expected_users = [{"id": u["id"], "email": u["email"]} for u in users]
            for event in events:
                if event.get("type") == "final":
                    check("resume_final_identities", event.get("count") == 2 and event.get("created_users") == expected_users)
            created.extend({"id": u["id"], "email": u["email"]} for u in sorted(users, key=lambda u: u["email"].split("@")[0][-1]))
            for user in created:
                record({"type": "confirmed_user", "status": "confirmed", "count": 1, **user})
            # Require schema-level permission denial, not merely an invalid-key 401.
            for kind, result in (("table", call("GET", table + "?select=user_id&limit=0")),
                                 ("rpc", save(None, {"layouts": []}))):
                status, data = result
                code = data.get("code") if isinstance(data, dict) else None
                missing = status == 404 or code in ("PGRST202", "PGRST205", "42P01", "42883")
                check("schema_NOTFOUND" if missing else "preflight_" + kind,
                      not missing and status in (401, 403) and code == "42501", [status])
            for user in created:
                admin_user(user)  # Validate BOTH identities before generating either link.
            tokens = [signin(user) for user in created]
            docs = [document("A"), document("B-race-0"), document("B-race-1")]
            states = [own(tokens[i], user, "resume_" + label) for i, (label, user) in enumerate(zip(("A", "B"), created))]
            for i, state in enumerate(states):
                allowed = [{"layouts": []}] if state["revision"] == 0 else ([docs[0]] if i == 0 else docs[1:])
                check("resume_test_document", state.get("document") in allowed and state.get("public_event_cursor_at") is None)
            if args.api_surface:
                check("api_existing_test_records", all(state["revision"] > 0 and state["document"]["layouts"] for state in states), count=2)
                def api_request(method, token, body, query, origin):
                    headers = api_headers(method, token, origin)
                    with requests.Session() as session:
                        session.trust_env = False
                        response = session.request(method, API_ENDPOINT + query, headers=headers,
                                                   json=body, timeout=(10, 25), allow_redirects=False)
                        try:
                            data = response.json()
                        except ValueError:
                            data = None
                        return response.status_code, data, response.headers
                check_api_surface(api_request, check, created, tokens, states, signin, own)
                outcome = "passed"
                return
            status, data = save(tokens[0], docs[0], states[0]["revision"])
            revisions = [states[0]["revision"] + 1, states[1]["revision"] + 1]
            check("save_A", status == 200 and isinstance(data, dict)
                  and data.get("user_id") == created[0]["id"]
                  and data.get("revision") == revisions[0] and data.get("document") == docs[0], [status])
            barrier = Barrier(2)
            def first_save(index):
                try:
                    barrier.wait(timeout=10)
                    result = save(tokens[1], docs[index + 1], states[1]["revision"])
                except (Exception, KeyboardInterrupt) as exc:
                    record({"type": "concurrent_request_exception", "request_index": index,
                            "status": type(exc).__name__})
                    raise
                # Persist independently before pool.map can propagate the other request's error.
                record({"type": "concurrent_request_result", "request_index": index,
                        "status": "returned", "http_status": result[0]})
                return result
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(first_save, range(2)))
            statuses = [result[0] for result in results]
            check("concurrent_first_save" if states[1]["revision"] == 0 else "concurrent_same_revision_update", statuses.count(200) == 1
                  and sum(conflict(result) for result in results) == 1, statuses, 2)
            selected = [docs[0], docs[statuses.index(200) + 1]]
            for index, user in enumerate(created):
                token, other = tokens[index], created[1 - index]
                expected = {"user_id": user["id"], "revision": revisions[index], "document": selected[index], "public_event_cursor_at": None}
                own(token, user, "own_GET", expected)
                status, data = call("GET", table + "?select=user_id&user_id=eq." + other["id"], token)
                check("cross_owner_GET", status == 200 and data == [], [status], len(data) if isinstance(data, list) else 0)
                for method in ("POST", "PATCH", "DELETE"):
                    path = table if method == "POST" else table + "?user_id=eq." + user["id"]
                    body = {"user_id": user["id"], "document": selected[index]} if method == "POST" else {"document": selected[index]}
                    status, _ = call(method, path, token, None if method == "DELETE" else body)
                    check("direct_" + method, status == 403, [status])
                status, _ = save(token, {**selected[index], "user_id": other["id"]}, revisions[index])
                check("forged_user_payload", status == 400, [status])
                stale_result = save(token, document("stale-must-not-persist"), revisions[index] - 1)
                check("stale_RPC", conflict(stale_result), [stale_result[0]])
                own(signin(user), user, "fresh_signin_restore", expected)
            status, _ = call("GET", table + "?select=user_id&user_id=eq." + created[0]["id"])
            check("anon_GET_denied", status in (401, 403), [status])
            status, _ = save(None, document("anon-must-not-persist"))
            check("anon_RPC_denied", status in (401, 403), [status])
            outcome = "passed"
        except (Exception, KeyboardInterrupt) as exc:
            record({"type": "exception", "status": type(exc).__name__})
            raise
        finally:
            # No cleanup mutations: users remain, credentials are not retained.
            record({"type": "final", "status": outcome, "count": len(created), "created_users": created})
            print(json.dumps({"type": "final", "status": outcome, "count": len(created)}), flush=True)


if __name__ == "__main__":
    try:
        main()
    except (Exception, KeyboardInterrupt) as exc:
        print(json.dumps({"type": "stopped", "status": type(exc).__name__}))
        raise SystemExit(1) from None
