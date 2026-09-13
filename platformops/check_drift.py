"""Reads the registry, asks cruft where each service stands, builds the report."""
import json
import pathlib
import subprocess
from datetime import UTC, datetime

import yaml

from .drift_report import ServiceStatus, build_report


def _template_head(repo_root: str) -> str | None:
    # A service is behind only when the TEMPLATE has moved, not when any
    # commit lands in this repository. Comparing against repo HEAD would
    # make every registered service "behind" the moment an unrelated commit
    # (a README edit, a fix to this very module) merges, which is not what
    # drift means and would make DRIFT.md restate a new "days behind" on
    # every commit regardless of whether template/ changed. So this looks
    # for the newest commit that actually touched template/, the same
    # pathspec the Makefile's drift-demo target already uses to find the
    # template's *oldest* touching commit (`git log --format=%H -- template`).
    #
    # In production repo_root is this checked-out platform repo, so this
    # usually succeeds. In a unit test repo_root can be a bare tmp_path with
    # no .git at all, or a repo where nothing has ever touched template/
    # (empty stdout, exit 0, not an error); don't crash on either case, just
    # report "unknown".
    result = subprocess.run(
        ["git", "log", "-1", "--format=%H", "--", "template"], cwd=repo_root,
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return None
    sha = result.stdout.strip()
    return sha or None


def _commit_date(repo_root: str, sha: str) -> datetime | None:
    # A recorded commit can be unknown to this checkout (history rewritten,
    # shallow clone). Treat that as "can't tell how old", not a crash.
    result = subprocess.run(
        ["git", "show", "-s", "--format=%cI", sha], cwd=repo_root,
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return None
    return datetime.fromisoformat(result.stdout.strip())


def collect(registry_path: str, repo_root: str) -> list[ServiceStatus]:
    registry = yaml.safe_load(pathlib.Path(registry_path).read_text()) or {}
    head = None
    head_checked = False
    statuses: list[ServiceStatus] = []

    for entry in registry.get("services", []):
        cruft_file = pathlib.Path(repo_root) / entry["path"] / ".cruft.json"
        if not cruft_file.is_file():
            continue

        recorded = json.loads(cruft_file.read_text()).get("commit", "")
        if not head_checked:
            head = _template_head(repo_root)
            head_checked = True

        # If the template's latest commit can't be determined, or nothing
        # was recorded, there is no reference to compare against. Report
        # this as "unknown", not "current": those are not the same thing,
        # and this dashboard exists to catch drift, not to explain away an
        # inconclusive check.
        if not recorded or head is None:
            statuses.append(ServiceStatus(
                name=entry["name"], repo=entry["repo"],
                template_sha=recorded[:7] if recorded else "unknown",
                behind=False, days_behind=0, unknown=True,
            ))
            continue

        behind = not head.startswith(recorded) and not recorded.startswith(head)
        days = 0
        if behind:
            then = _commit_date(repo_root, recorded)
            if then is not None:
                days = (datetime.now(UTC) - then).days

        statuses.append(ServiceStatus(
            name=entry["name"], repo=entry["repo"],
            template_sha=recorded[:7], behind=behind, days_behind=days,
        ))
    return statuses


def main() -> None:
    root = str(pathlib.Path(__file__).resolve().parents[1])
    statuses = collect(f"{root}/platformops/registry.yaml", root)
    pathlib.Path(f"{root}/DRIFT.md").write_text(build_report(statuses))


if __name__ == "__main__":
    main()
