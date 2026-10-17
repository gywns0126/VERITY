#!/usr/bin/env python3
"""VERITY↔AlphaNest 분리 Stage 1 (2026-07-23): 오퍼레이터 full 데이터를 private Supabase Storage 업로드.

공개 blob(sanitize 예정)과 별도로, full portfolio.json (+ 향후 오퍼레이터 파일) 을 verity-reports
private bucket 에 올려 /api/admin(authed, ?type=portfolio_full) 이 서빙. 발행 파이프라인
(daily_analysis_full)에서 portfolio.json 확정 후 실행. SUPABASE_SERVICE_ROLE_KEY 필요(이미 등록).

패턴 = scripts/upload_reports_to_supabase.py 정합(POST storage/v1/object + x-upsert). JSON parse
검증 후 업로드(깨진 발행 방지, [[feedback_published_json_parse_verify]]).
"""
from __future__ import annotations

import json
import hashlib
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import requests

BUCKET = os.environ.get("OPERATOR_BUCKET", "verity-reports")
APPROVED_PRIVATE_DESTS = frozenset({
    "_operator/analyst_reports.json", "_operator/dart_kr_backfill_result.json",
    "_operator/dart_fundamentals_kr.json",
})
EXPLICIT_ONLY_DESTS = frozenset({"_operator/dart_fundamentals_kr.json"})
PORTFOLIO_DEST = "_operator/portfolio_full.json"
STORAGE_ERROR_CODES = frozenset({
    "EntityTooLarge", "InvalidMimeType", "InvalidRequest", "InvalidKey", "InvalidBucketName",
    "InvalidJWT", "AccessDenied", "NoSuchKey", "NoSuchBucket", "ResourceAlreadyExists",
    "KeyAlreadyExists", "AlreadyExists", "already_exists", "not_found", "unauthorized",
})
STORAGE_CACHE_STATES = frozenset({
    "HIT", "MISS", "EXPIRED", "STALE", "BYPASS", "DYNAMIC", "REVALIDATED", "UPDATING", "NONE",
})

# (로컬 소스, bucket 내 경로, content-type).
# 2026-07-23 분리 Stage 3 후속: 오퍼레이터 전용 파일(public-probe 소비 0)을 private bucket 으로.
# 공개 발행 제거(action.yml)와 짝 — authed /api/admin?type=<name> 라우트로 서빙.
UPLOADS = [
    # Sole producer: dart_batch --only dart_fundamentals_kr. Consumers never write this object.
    ("data/dart_fundamentals_kr.json", "_operator/dart_fundamentals_kr.json", "application/json"),
    # PM 승인 2026-09-27: 오퍼레이터 조인의 배포 결손 복구. 공개 발행 금지.
    ("data/analyst_reports.json", "_operator/analyst_reports.json", "application/json"),
    ("data/dart_kr_backfill_result.json", "_operator/dart_kr_backfill_result.json", "application/json"),
    ("data/portfolio.json", "_operator/portfolio_full.json", "application/json"),
    ("data/history.json", "_operator/history.json", "application/json"),
    ("data/system_health_snapshot.json", "_operator/system_health_snapshot.json", "application/json"),
    ("data/brain_kb_usage.json", "_operator/brain_kb_usage.json", "application/json"),
    ("data/admin_todos.json", "_operator/admin_todos.json", "application/json"),
    # 2026-08-04 후보 편입/이탈 diff(오퍼레이터 전용) — private+authed 만.
    ("data/candidates_diff.json", "_operator/candidates_diff.json", "application/json"),
    # 거시 사실 번들(오퍼레이터 전용) — 전망·추천 없이 출처와 기준일만 제공.
    ("data/macro_synthesis.json", "_operator/macro_synthesis.json", "application/json"),
    ("data/verification_report.json", "_operator/verification_report.json", "application/json"),
    # 중용 목표비중 — 태생부터 봉인(gitignore, 공개 발행 금지). private bucket + authed 만.
    ("data/moderation_portfolio.json", "_operator/moderation_portfolio.json", "application/json"),
    # 2026-08-21 멀티배거 워치(오퍼레이터 전용) — 종목 신호라 공개 발행 금지(유사투자자문 회피).
    #   🚨 생산물이 "로깅 전용 — 결정 0" 을 자기신고하므로 UI 도 관측으로만 표시한다.
    ("data/multibagger_watch.json", "_operator/multibagger_watch.json", "application/json"),
    # 2026-08-22 멀티배거 선별 리스트(PM 지시) — 승격→채점 결과를 일반 후보와 분리.
    #   🚨 이 결정의 성적을 나중에 분리 집계하려면 리스트가 남아야 한다.
    ("data/multibagger_picks.json", "_operator/multibagger_picks.json", "application/json"),
    # 2026-08-07 드리프트 점검 — 목표비중 파생물이라 동일 봉인 등급.
    #   🚨 gitignore 라 git add 로는 전달 불가 — 이 목록이 유일한 전달 경로다(RULE 4 등가).
    ("data/rebalance_review.json", "_operator/rebalance_review.json", "application/json"),
]


def _guard_legacy_verification(report: dict) -> dict:
    """An old persisted report must not republish synthetic missing-price losses."""
    if (report.get("_corrections_meta") or {}).get("version") == "2.0-missing-price-unresolved":
        return report
    return {
        **report,
        "performance": {key: None for key in (report.get("performance") or {})},
        "evaluation_coverage": {},
        "feedback_loop_status": "unverified",
        "_corrections_meta": {
            **(report.get("_corrections_meta") or {}),
            "version": "legacy-invalidated",
            "delisted_return_pct": None,
            "evaluation_status": "legacy_requires_recalculation",
        },
    }


def guard_legacy_performance(doc: dict, dest: str) -> dict:
    """Fail closed on cached pre-fix metrics until their normal producer reruns.

    Public Git can retain an older portfolio between producer runs. Publication
    must not restore invalid performance after a private measurement repair.
    Holdings, recommendations, weights, and execution fields are never changed.
    """
    if dest == "_operator/verification_report.json":
        return _guard_legacy_verification(doc)
    if dest != "_operator/portfolio_full.json":
        return doc
    result = dict(doc)
    bt = doc.get("backtest_stats")
    if isinstance(bt, dict) and (bt.get("_corrections_meta") or {}).get("version") != "2.0-missing-price-unresolved":
        result["backtest_stats"] = {
            "periods": {}, "recommendations": [],
            "evaluation_status": "legacy_requires_recalculation",
            "_corrections_meta": {"version": "legacy-invalidated"},
        }
    report = doc.get("verification_report")
    if isinstance(report, dict):
        result["verification_report"] = _guard_legacy_verification(report)
    accuracy = doc.get("brain_accuracy")
    if isinstance(accuracy, dict) and not accuracy.get("evaluation_status"):
        result["brain_accuracy"] = {
            "grades": {}, "evaluation_status": "legacy_requires_recalculation",
            "insight": "이전 평가의 가격 결측 처리 오류 — 재계산 전 등급 성과 판정 보류",
        }
        result["brain_quality"] = {
            "score": None, "status": "no_data", "components": {},
            "period": (doc.get("brain_quality") or {}).get("period"),
            "reason": "legacy_accuracy_requires_recalculation",
        }
    return result


def _backfill_keys(doc: dict) -> set:
    rows = doc.get("rows") if isinstance(doc, dict) else None
    if not isinstance(rows, list) or not rows:
        raise ValueError("empty backfill")
    keys = set()
    for row in rows:
        if not isinstance(row, dict) or not row.get("ticker") or not row.get("fiscal_year"):
            raise ValueError("invalid backfill row")
        keys.add((str(row["ticker"]), str(row["fiscal_year"]), str(row.get("period") or "annual")))
    return keys


def _backfill_preserves_coverage(doc: dict, previous: requests.Response) -> bool:
    """Do not replace the full historical dataset with a smoke-test subset."""
    try:
        new_keys = _backfill_keys(doc)
        old = previous.json()
        if previous.status_code == 200:
            return new_keys.issuperset(_backfill_keys(old))
        return str(old.get("statusCode")) == "404" and old.get("error") == "not_found"
    except (ValueError, AttributeError):
        return False


def _storage_diagnostic(stage: str, response, byte_count: int):
    """Log fixed metadata and known codes only; never response messages or bodies."""
    code = "unknown"
    if response is not None:
        try:
            payload = response.json()
            for field in ("code", "error"):
                value = payload.get(field)
                if isinstance(value, str) and value in STORAGE_ERROR_CODES:
                    code = value
                    break
        except (ValueError, AttributeError, TypeError):
            pass
    else:
        code = "request_failed"
    print("[operator_storage] " + json.dumps({
        "stage": stage, "http_status": response.status_code if response is not None else None,
        "bytes": byte_count, "code": code,
    }, separators=(",", ":")), file=sys.stderr)


def _fresh_private_get(url: str, key: str):
    """One authenticated origin read; cacheNonce bypasses Storage's CDN cache.

    Request no-cache headers alone do not select a new CDN cache entry. Use a
    unique nonce even for immutable archives: create/duplicate preservation must
    verify origin existence and exact bytes, not a cached copy after deletion.
    """
    separator = "&" if "?" in url else "?"
    return requests.get(f"{url}{separator}cacheNonce={uuid4().hex}",
        headers={"apikey": key, "Authorization": f"Bearer {key}",
                 "Cache-Control": "no-cache, no-store, max-age=0"},
        timeout=60, allow_redirects=False)


def _readback_diagnostic(stage: str, response, expected: bytes):
    """Only byte identities and an allowlisted cache state, never response text."""
    headers = getattr(response, "headers", {})
    cache_state = headers.get("CF-Cache-Status")
    print("[operator_readback] " + json.dumps({
        "stage": stage, "http_status": response.status_code,
        "expected_bytes": len(expected), "actual_bytes": len(response.content),
        "expected_sha256": hashlib.sha256(expected).hexdigest(),
        "actual_sha256": hashlib.sha256(response.content).hexdigest(),
        "cf_cache_status": cache_state if isinstance(cache_state, str) and cache_state in STORAGE_CACHE_STATES else "unknown",
    }, separators=(",", ":")), file=sys.stderr)


def _preserve_analysis_archive(supabase_url: str, key: str, body: bytes, archive: dict) -> bool:
    """Create without replacement; accept duplicates only after exact private readback."""
    url = f"{supabase_url}/storage/v1/object/{BUCKET}/{archive['object']}"
    headers = {"apikey": key, "Authorization": f"Bearer {key}",
               "Content-Type": "application/json", "x-upsert": "false",
               "Cache-Control": "no-store"}
    try:
        response = requests.post(url, headers=headers, data=body, timeout=60, allow_redirects=False)
        if response.status_code not in (200, 201):
            _storage_diagnostic("archive_upload", response, len(body))
        # Standard Storage uploads report existing assets as HTTP400 or409.
        # No error body proves preservation: only authenticated exact bytes do.
        if response.status_code not in (200, 201, 400, 409):
            return False
        readback = _fresh_private_get(url, key)
        preserved = (readback.status_code == 200 and readback.content == body
                     and hashlib.sha256(readback.content).hexdigest() == archive["sha256"])
        if not preserved:
            _readback_diagnostic("archive_readback", readback, body)
        return preserved
    except requests.RequestException:
        _storage_diagnostic("archive_request", None, len(body))
        return False


def _validated_paper_summary() -> dict:
    """Recheck the existing promotion contract; staging never supplies a full document."""
    if (os.environ.get("ANALYSIS_MODE") != "quick" or os.environ.get("VERITY_MODE") != "staging"
            or not re.fullmatch(r"[0-9]+", os.environ.get("GITHUB_RUN_ID", ""))
            or not re.fullmatch(r"[0-9]+", os.environ.get("GITHUB_RUN_ATTEMPT", ""))):
        raise ValueError("quick staging context required")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from scripts.promote_exec_paper_to_portfolio import _validate, PromotionError
    staging = json.loads(Path("data/portfolio.dev.json").read_bytes())
    state = json.loads(Path("data/exec_paper_state.json").read_bytes())
    promoted = json.loads(Path("data/portfolio.json").read_bytes())
    if not all(isinstance(doc, dict) for doc in (staging, state, promoted)):
        raise ValueError("paper source objects required")
    summary = staging.get("exec_paper")
    if not isinstance(summary, dict) or promoted.get("exec_paper") != summary:
        raise ValueError("current promoted paper summary missing")
    try:
        _validate(summary, state, staging.get("updated_at"))
    except (PromotionError, TypeError, ValueError, AttributeError):
        raise ValueError("paper promotion contract failed") from None
    return summary


def _merge_paper_summary(private_body: bytes, summary: dict, now: datetime) -> bytes:
    """Patch only exec_paper on the latest complete private full-analysis document."""
    from scripts.ci.operator_portfolio_delivery import _time
    document = json.loads(private_body)
    if not isinstance(document, dict):
        raise ValueError("private portfolio object required")
    proof = document.get("analysis_provenance") or {}
    delivery = proof.get("delivery") or {}
    archive = delivery.get("archive") or {}
    run, attempt = str(proof.get("analysis_run_id") or ""), str(proof.get("analysis_run_attempt") or "")
    digest = archive.get("sha256") or ""
    records = document.get("recommendations")
    if (proof.get("status") != "completed" or proof.get("analysis_mode") not in ("full", "full_us")
            or not re.fullmatch(r"[0-9]+", run) or not re.fullmatch(r"[0-9]+", attempt)
            or archive.get("status") != "preserved" or delivery.get("phase") not in ("analysis_complete", "final")
            or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)
            or archive.get("object") != f"_operator/analysis_runs/{run}/{attempt}/{digest}.json"
            or digest != delivery.get("source_portfolio_sha256")
            or not isinstance(records, list) or proof.get("resulting_analysis_count") != len(records)
            or not isinstance(document.get("analysis_changes"), dict)
            or any(not isinstance(row, dict) or not isinstance(row.get("evidence_snapshot"), dict) for row in records)):
        raise ValueError("complete preserved private analysis required")
    summary_time = _time(summary.get("as_of"))
    previous = document.get("exec_paper") or {}
    if (summary_time > now or summary_time < _time(proof.get("analysis_completed_at"))
            or (previous and summary_time < _time(previous.get("as_of")))
            or (previous and summary_time == _time(previous.get("as_of")) and previous != summary)):
        raise ValueError("stale or conflicting paper summary")
    document["exec_paper"] = summary
    return json.dumps(document, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def main() -> int:
    supabase_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not supabase_url or not key:
        print("ERROR: SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY 미설정 — 업로드 불가", file=sys.stderr)
        return 2

    # --only <substr>: 특정 파일만 업로드 (전용 워크플로가 타 오퍼레이터 파일을 stale 로 덮는 사고 방지).
    only = None
    if "--only" in sys.argv:
        i = sys.argv.index("--only")
        if i + 1 < len(sys.argv):
            only = sys.argv[i + 1]

    require_analysis = "--require-completed-analysis" in sys.argv
    merge_paper = "--merge-exec-paper" in sys.argv
    if ((merge_paper and (require_analysis or only != "portfolio_full"))
            or (only == "portfolio_full" and not require_analysis and not merge_paper)):
        print("ERROR: portfolio delivery requires an explicit completed-analysis or paper-merge contract", file=sys.stderr)
        return 2
    uploads = [u for u in UPLOADS
               if (u[1] not in EXPLICIT_ONLY_DESTS or only == "dart_fundamentals_kr")
               and (u[1] != PORTFOLIO_DEST or require_analysis or merge_paper)
               and (only is None or only in u[0] or only in u[1])]
    prepared_portfolio = None
    archive = None
    source_portfolio = None
    source_serialization = None
    summary = None
    if merge_paper:
        try:
            summary = _validated_paper_summary()
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            print("ERROR: current quick paper promotion contract failed", file=sys.stderr)
            return 2
    if require_analysis:
        # Validate once and upload those exact bytes, even if another local file changes.
        if BUCKET != "verity-reports" or not any(dest == "_operator/portfolio_full.json" for _, dest, _ in uploads):
            print("ERROR: completed analysis requires the private portfolio destination", file=sys.stderr)
            return 2
        try:
            phase = sys.argv[sys.argv.index("--delivery-phase") + 1]
            sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
            from scripts.ci.operator_portfolio_delivery import (
                compact_portfolio_source, prepare_portfolio_delivery, portfolio_archive,
            )
            portfolio_path, snapshot_path = Path("data/portfolio.json"), Path("data/universe_candidates.json")
            source_options = ("--portfolio-source", "--snapshot-source")
            if any(flag in sys.argv for flag in source_options):
                from scripts.ci.private_analysis_files import final_source_paths
                if phase != "final" or not all(flag in sys.argv for flag in source_options):
                    raise ValueError("paired final sources required")
                supplied = tuple(Path(sys.argv[sys.argv.index(flag) + 1]) for flag in source_options)
                expected_paths = final_source_paths(Path.cwd(), os.environ.get("RUNNER_TEMP", ""),
                    os.environ.get("GITHUB_RUN_ID", ""), os.environ.get("GITHUB_RUN_ATTEMPT", ""))
                if any(path.is_symlink() or path.resolve() != expected.resolve()
                       for path, expected in zip(supplied, expected_paths)):
                    raise ValueError("foreign private final source path")
                portfolio_path, snapshot_path = supplied
            source_portfolio, source_serialization = compact_portfolio_source(portfolio_path.read_bytes())
            prepared_portfolio = prepare_portfolio_delivery(
                source_portfolio, snapshot_path.read_bytes(),
                run_id=os.environ.get("GITHUB_RUN_ID", ""),
                run_attempt=os.environ.get("GITHUB_RUN_ATTEMPT", ""),
                expected_scan_id=os.environ.get("UNIVERSE_EXPECTED_SCAN_ID", ""),
                analysis_mode=os.environ.get("ANALYSIS_MODE", ""),
                verity_mode=os.environ.get("VERITY_MODE", ""), phase=phase,
                now=datetime.now(timezone(timedelta(hours=9))),
            )
            archive = portfolio_archive(source_portfolio, run_id=os.environ.get("GITHUB_RUN_ID", ""),
                                        run_attempt=os.environ.get("GITHUB_RUN_ATTEMPT", ""))
        except (OSError, ValueError, TypeError, KeyError, IndexError):
            # Never print exception text or payloads from the private contract.
            print("ERROR: completed analysis delivery contract failed", file=sys.stderr)
            return 2
    # These newly authorized payloads must never follow an accidental public-bucket override.
    if require_analysis or merge_paper or any(dest in APPROVED_PRIVATE_DESTS and os.path.isfile(src) for src, dest, _ in uploads):
        if BUCKET != "verity-reports":
            print("ERROR: approved operator facts require verity-reports", file=sys.stderr)
            return 2
        try:
            check = requests.get(
                f"{supabase_url}/storage/v1/bucket/{BUCKET}",
                headers={"apikey": key, "Authorization": f"Bearer {key}"}, timeout=20,
                allow_redirects=False,
            )
            private = check.status_code == 200 and check.json().get("public") is False
        except (requests.RequestException, ValueError, AttributeError):
            private = False
        if not private:
            print("ERROR: private bucket verification failed; upload blocked", file=sys.stderr)
            return 2
    if merge_paper:
        try:
            current = _fresh_private_get(
                f"{supabase_url}/storage/v1/object/{BUCKET}/{PORTFOLIO_DEST}", key)
            if current.status_code != 200:
                raise ValueError("private current analysis unavailable")
            prepared_portfolio = _merge_paper_summary(current.content, summary,
                datetime.now(timezone(timedelta(hours=9))))
        except (requests.RequestException, ValueError, TypeError, KeyError, AttributeError):
            print("ERROR: private full baseline rejected; paper merge blocked", file=sys.stderr)
            return 2
    archive_ok = True
    if archive is not None:
        archive_ok = _preserve_analysis_archive(supabase_url, key, source_portfolio, archive)
        prepared_doc = json.loads(prepared_portfolio)
        prepared_doc["analysis_provenance"]["delivery"]["archive"] = {
            **archive, "status": "preserved" if archive_ok else "failed",
        }
        prepared_doc["analysis_provenance"]["delivery"]["source_serialization"] = source_serialization
        prepared_portfolio = json.dumps(prepared_doc, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if not archive_ok:
            print("ERROR: private analysis archive not preserved; current delivery still attempted", file=sys.stderr)
    ok = 0
    approved_expected = {dest for src, dest, _ in uploads
                         if dest in APPROVED_PRIVATE_DESTS and (only is not None or os.path.isfile(src))}
    approved_ok = set()
    for src, dest, ctype in uploads:
        if not os.path.isfile(src):
            print(f"WARN: {src} 부재 — skip")
            continue
        if prepared_portfolio is not None and dest == "_operator/portfolio_full.json":
            body = prepared_portfolio
        else:
            with open(src, "rb") as f:
                body = f.read()
        # JSON parse 검증 — 깨진 파일 업로드 차단(오퍼레이터 콘솔 파손 방지)
        if ctype == "application/json":
            try:
                parsed = json.loads(body)
                if isinstance(parsed, dict) and not merge_paper:
                    guarded = guard_legacy_performance(parsed, dest)
                    if guarded != parsed:
                        parsed = guarded
                        if dest != PORTFOLIO_DEST:
                            body = json.dumps(guarded, ensure_ascii=False, indent=2).encode("utf-8")
                        print(f"  cached performance invalidated before publishing: {dest}")
                if dest == PORTFOLIO_DEST:
                    body = json.dumps(parsed, ensure_ascii=False, separators=(",", ":"),
                                      allow_nan=not merge_paper).encode("utf-8")
            except ValueError as e:
                print(f"ERROR: {src} JSON parse 실패 — skip: {e}", file=sys.stderr)
                continue
        try:
            if dest == "_operator/dart_kr_backfill_result.json":
                previous = requests.get(
                    f"{supabase_url}/storage/v1/object/{BUCKET}/{dest}",
                    headers={"apikey": key, "Authorization": f"Bearer {key}"}, timeout=20,
                )
                if not _backfill_preserves_coverage(parsed, previous):
                    print("ERROR: backfill coverage shrank or comparison failed; upload blocked", file=sys.stderr)
                    continue
            r = requests.post(
                f"{supabase_url}/storage/v1/object/{BUCKET}/{dest}",
                headers={
                    "apikey": key,
                    "Authorization": f"Bearer {key}",
                    "Content-Type": ctype,
                    "x-upsert": "true",       # 같은 path 덮어쓰기
                    "Cache-Control": "no-store",
                },
                data=body,
                timeout=60,
                allow_redirects=False,
            )
            if r.status_code in (200, 201) and (dest in EXPLICIT_ONLY_DESTS or merge_paper):
                readback = _fresh_private_get(f"{supabase_url}/storage/v1/object/{BUCKET}/{dest}", key)
                if readback.status_code != 200 or readback.content != body:
                    _readback_diagnostic("object_readback", readback, body)
                    print("ERROR: private object readback mismatch; publication blocked", file=sys.stderr)
                    continue
        except requests.RequestException as e:
            if require_analysis or merge_paper:
                _storage_diagnostic("current_request", None, len(body))
            detail = "request failed" if require_analysis or merge_paper or dest in EXPLICIT_ONLY_DESTS else str(e)
            print(f"  ✗ {src} → 요청 실패: {detail}", file=sys.stderr)
            continue
        if r.status_code in (200, 201):
            print(f"  ✓ {src} → {BUCKET}/{dest} ({len(body):,} bytes)")
            ok += 1
            approved_ok.add(dest)
        else:
            if require_analysis or merge_paper or dest in EXPLICIT_ONLY_DESTS:
                _storage_diagnostic("current_upload", r, len(body))
            detail = "" if require_analysis or merge_paper or dest in EXPLICIT_ONLY_DESTS else r.text[:150]
            print(f"  ✗ {src} → {r.status_code} {detail}", file=sys.stderr)

    print(f"operator upload: {ok}/{len(uploads)}")
    # 새 private 입력에는 공개 fallback이 없다. 실패를 성공 종료로 숨기지 않는다.
    return 1 if (not archive_ok or approved_expected - approved_ok or
                 ((require_analysis or merge_paper) and PORTFOLIO_DEST not in approved_ok)) else 0


if __name__ == "__main__":
    sys.exit(main())
