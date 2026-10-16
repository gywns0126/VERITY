#!/usr/bin/env python3
"""Push one prepared scan commit without touching the producer's dirty checkout.

Real overlapping data edits fail closed. The workflow uploads the exact selected
outputs and a binary patch before invoking this helper, allowing manual recovery
without another scan. Never use merge strategy 'ours' or force push here.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import tempfile
import time

# Non-append-only outputs are compared as whole blobs. A textual merge can
# silently mix fields from different scan generations even without conflicts.
CANDIDATES_PATH = 'data/universe_candidates.json'
# Shared status aggregation is written by universe, macro, and DART builders;
# it is not a candidate generation. Preserve a concurrent remote writer exactly.
SHARED_DIAGNOSTIC_PATHS = frozenset({'data/metadata/data_pipeline_health.json'})


def git(repo, *args, check=True):
    return subprocess.run(['git', '-C', str(repo), *args], check=check,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def oid(repo, ref, path):
    result = git(repo, 'rev-parse', '--verify', f'{ref}:{path}', check=False)
    return result.stdout.strip() if result.returncode == 0 else None


def persist(repo, branch, attempts=5, retry_delay=10):
    repo = Path(git(repo, 'rev-parse', '--show-toplevel').stdout.strip())
    git(repo, 'check-ref-format', f'refs/heads/{branch}')
    source = git(repo, 'rev-parse', 'HEAD').stdout.strip()
    base = git(repo, 'rev-parse', 'HEAD^').stdout.strip()
    if not oid(repo, source, CANDIDATES_PATH):
        raise RuntimeError('Prepared commit has no candidate snapshot')
    changed = git(repo, 'diff-tree', '--no-commit-id', '--name-only', '-r', source).stdout.splitlines()
    generation_paths = set(path for path in changed if not path.endswith('.jsonl'))
    generation_paths.add(CANDIDATES_PATH)
    # Detached worktree isolates unstaged byproducts and never changes local HEAD.
    with tempfile.TemporaryDirectory(prefix='universe-persist-') as temp:
        worktree = Path(temp) / 'worktree'
        git(repo, 'worktree', 'add', '--detach', str(worktree), source)
        try:
            for attempt in range(1, attempts + 1):
                git(worktree, 'fetch', 'origin', f'refs/heads/{branch}')
                remote = git(worktree, 'rev-parse', 'FETCH_HEAD').stdout.strip()
                # An already-pushed exact source requires no further update.
                if git(worktree, 'merge-base', '--is-ancestor', source, remote,
                       check=False).returncode == 0:
                    print(f'Already persisted: {source}')
                    return
                preserve_shared = set()
                for path in sorted(generation_paths):
                    before, after, incoming = (oid(worktree, ref, path)
                                               for ref in (base, source, remote))
                    if incoming not in (before, after):
                        if path in SHARED_DIAGNOSTIC_PATHS:
                            preserve_shared.add(path)
                            continue
                        raise RuntimeError(f'Remote scan generation changed: {path}; '
                                           'preserve remote and recover from artifact')
                # Reapply only the scan commit to the latest remote each attempt.
                # No autostash, destructive reset of the producer, or -X ours.
                git(worktree, 'checkout', '--detach', remote)
                result = git(worktree, '-c', 'core.hooksPath=/dev/null',
                             '-c', 'rerere.enabled=false',
                             'cherry-pick', '--no-commit', source, check=False)
                if result.returncode:
                    conflicts = set(git(worktree, 'diff', '--name-only',
                                        '--diff-filter=U').stdout.splitlines())
                    active = git(worktree, 'rev-parse', '--verify',
                                 'CHERRY_PICK_HEAD', check=False).returncode == 0
                    if active and not conflicts and git(worktree, 'diff', '--cached', '--quiet',
                                                         check=False).returncode == 0:
                        # Git leaves CHERRY_PICK_HEAD for an empty, already-applied delta.
                        git(worktree, 'cherry-pick', '--abort')
                        print('Scan delta already present on remote')
                        return
                    if not conflicts or conflicts - preserve_shared:
                        raise RuntimeError(f'Conflicting scan outputs: {sorted(conflicts)}\n{result.stderr}')
                for path in sorted(preserve_shared):
                    if oid(worktree, remote, path) is None:
                        git(worktree, 'rm', '-f', '--ignore-unmatch', '--', path)
                    else:
                        git(worktree, 'restore', f'--source={remote}', '--staged', '--worktree', '--', path)
                    print(f'Preserved concurrent shared diagnostic: {path}', flush=True)
                if git(worktree, 'diff', '--cached', '--quiet', check=False).returncode == 0:
                    git(worktree, 'cherry-pick', '--abort', check=False)
                    print('Scan delta already present on remote')
                    return
                git(worktree, '-c', 'core.hooksPath=/dev/null', 'commit', '-C', source)
                result = git(worktree, 'push', 'origin', f'HEAD:refs/heads/{branch}',
                             check=False)
                if result.returncode == 0:
                    print(f'Persisted: {git(worktree, "rev-parse", "HEAD").stdout.strip()}')
                    return
                print(f'Push attempt {attempt}/{attempts} rejected: {result.stderr}', flush=True)
                if attempt < attempts:
                    time.sleep(retry_delay * attempt)
            raise RuntimeError('Push retries exhausted; recover exact outputs from artifact')
        finally:
            # Only our disposable detached worktree is removed; source stays intact.
            git(worktree, 'cherry-pick', '--abort', check=False)
            git(repo, 'worktree', 'remove', '--force', str(worktree), check=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('branch')
    args = parser.parse_args()
    try:
        persist(Path.cwd(), args.branch)
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        detail = getattr(exc, 'stderr', '') or str(exc)
        raise SystemExit(f'::error::Universe persistence failed: {detail}') from exc


if __name__ == '__main__':
    main()
