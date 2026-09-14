"""Reads the registry, works out which template version each registered
service is on, and builds the report.

This module does not shell out to cruft. It reads the commit each service's
`.cruft.json` recorded and compares template versions with `git log`. What
counts as a template version, why the recorded commit is resolved before it
is compared, and why `cruft check` answers a different question are defined
once, in docs/TEMPLATE-VERSION.md. This file implements that page and
nothing else.
"""
import json
import pathlib
import subprocess
from datetime import datetime

import yaml

from .drift_report import ServiceStatus, build_report


def _git(repo_root: str, *args: str) -> str | None:
    """Run git in repo_root, returning stripped stdout, or None on failure.

    Failure here is ordinary: repo_root may not be a git repository at all,
    and a recorded commit may be unknown to this checkout (history
    rewritten, shallow clone). Those are "can't tell", not crashes.
    """
    result = subprocess.run(
        ["git", *args], cwd=repo_root, capture_output=True, text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _is_shallow(repo_root: str) -> bool:
    # In a shallow clone the single fetched commit appears to add every file
    # in the repository, so every lookup below resolves to HEAD and every
    # service reads as behind. That is a wrong answer rather than a missing
    # one, which is the worse kind for a dashboard whose only job is to be
    # believed. Detect it and report unknown instead. Both workflows check
    # out with fetch-depth: 0, so this should not arise in CI.
    return _git(repo_root, "rev-parse", "--is-shallow-repository") == "true"


def _is_reachable(repo_root: str, sha: str) -> bool:
    # A rebase or squash merge rewrites the branch's commits, so the SHA a
    # generated service recorded stops being reachable from the default branch.
    # It survives locally as a dangling object, which is why this passes on the
    # machine that did the merge and fails on a fresh clone: a clone fetches
    # only reachable history. Distinguishing this from a genuinely stale
    # dashboard is the difference between "regenerate the fixture" and
    # "regenerate the dashboard", which are different repairs.
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", sha, "HEAD"],
        cwd=repo_root, capture_output=True, text=True,
    )
    return result.returncode == 0


def _template_version(repo_root: str, rev: str = "HEAD") -> str | None:
    # THE definition, computed in exactly one place: a template version is a
    # commit that touches template/. Asked of HEAD this yields "the current
    # template version"; asked of a service's recorded commit it yields "the
    # template version that service's code is made of", which is not the
    # recorded commit itself, because cruft records repo HEAD at generation
    # time and that commit need not have touched template/ at all.
    #
    # A service is behind only when the TEMPLATE moved, never merely because
    # some other commit landed in this repository. Comparing raw commits
    # would mark every registered service behind the moment an unrelated
    # commit (a README edit, a fix to this very module) merges.
    return _git(repo_root, "log", "-1", "--format=%H", rev, "--", "template") or None


def _commit_date(repo_root: str, sha: str) -> datetime | None:
    stamp = _git(repo_root, "show", "-s", "--format=%cI", sha)
    return datetime.fromisoformat(stamp) if stamp else None


def collect(registry_path: str, repo_root: str) -> list[ServiceStatus]:
    registry = yaml.safe_load(pathlib.Path(registry_path).read_text()) or {}
    current = None
    resolved = False
    statuses: list[ServiceStatus] = []

    for entry in registry.get("services", []):
        cruft_file = pathlib.Path(repo_root) / entry["path"] / ".cruft.json"
        if not cruft_file.is_file():
            continue

        recorded = json.loads(cruft_file.read_text()).get("commit", "")
        if not resolved:
            current = None if _is_shallow(repo_root) else _template_version(repo_root)
            resolved = True

        # Reachability is checked before resolution, not after, because a
        # commit orphaned by a rebase survives in the local object store and
        # resolves perfectly well on the machine that did the merge, while a
        # fresh clone never fetches it. Resolving first would make this module
        # answer differently in CI than on a laptop, which is precisely the
        # failure this check exists to stop.
        usable = bool(recorded) and current is not None and _is_reachable(repo_root, recorded)

        # The service's own template version, resolved exactly the same way
        # as the current one, so both sides of the comparison are the same
        # kind of thing.
        on = _template_version(repo_root, recorded) if usable else None

        # No current template version, nothing recorded, or a recorded
        # commit this checkout has never heard of: there is no usable
        # comparison. Report "unknown", not "current". Those are not the
        # same thing, and this dashboard exists to catch drift, not to
        # explain away an inconclusive check.
        if on is None or current is None:
            if _is_shallow(repo_root):
                reason = "shallow clone, history is not present"
            elif not recorded:
                reason = "no commit recorded in .cruft.json"
            elif not _is_reachable(repo_root, recorded):
                reason = (
                    "recorded commit is not reachable from HEAD, which is what "
                    "a rebase or squash merge does to a branch's commits"
                )
            else:
                reason = "recorded commit resolves to no template version"
            statuses.append(ServiceStatus(
                name=entry["name"], repo=entry["repo"],
                template_sha=recorded[:7] if recorded else "unknown",
                behind=False, days_behind=0, unknown=True, unknown_reason=reason,
            ))
            continue

        behind = on != current
        days = 0
        if behind:
            then, now = _commit_date(repo_root, on), _commit_date(repo_root, current)
            if then is not None and now is not None:
                # The distance between two commits, not the distance from
                # the wall clock. DRIFT.md is committed and asserted against
                # by tests/test_docs.py, so it must change when the template
                # moves and at no other time.
                days = (now - then).days

        statuses.append(ServiceStatus(
            name=entry["name"], repo=entry["repo"],
            template_sha=on[:7], behind=behind, days_behind=days,
        ))
    return statuses


def main() -> None:
    root = str(pathlib.Path(__file__).resolve().parents[1])
    statuses = collect(f"{root}/platformops/registry.yaml", root)
    pathlib.Path(f"{root}/DRIFT.md").write_text(build_report(statuses))


if __name__ == "__main__":
    main()
