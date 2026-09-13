"""Runs `cruft update` for every registered service that check_drift reports
as behind.

Registry data (service names and paths) never becomes shell text here: each
`cruft update` is invoked with a list argument vector and a `cwd`, not a
shell string built by interpolating a name into a command. A service name
containing a quote, backtick, or `$(...)` cannot do anything to this
process.
"""
import pathlib
import subprocess

import yaml

from .check_drift import collect


def _modified_tracked_files(repo_root: str) -> list[str]:
    """Tracked files with uncommitted changes anywhere in the repository.

    `cruft update` refuses to run against a dirty tree, and the tree it asks
    about is the WHOLE repository, not the service directory it was pointed
    at: `git status --porcelain` answers repository-wide regardless of cwd.
    `--allow-untracked-files`, which this module passes, forgives only the
    `??` lines, so untracked files are filtered out here too and modified
    tracked files are not.
    """
    result = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo_root,
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return []
    return [
        line[3:] for line in result.stdout.splitlines()
        if line and not line.startswith("??")
    ]


def apply_updates(registry_path: str, repo_root: str) -> list[str]:
    registry = yaml.safe_load(pathlib.Path(registry_path).read_text()) or {}
    paths = {entry["name"]: entry["path"] for entry in registry.get("services", [])}

    updated: list[str] = []
    for status in collect(registry_path, repo_root):
        if not status.behind:
            continue

        # Checked here, on the first service that actually needs an update,
        # rather than at the top of the function: a clean tree is only a
        # precondition when there is a cruft update to run, and failing a
        # run that had nothing to do would be worse than useless.
        #
        # This is the defect that made drift.yml incapable of its one job.
        # The dashboard step used to run first and leave a modified, tracked
        # DRIFT.md at the repository root, so cruft refused for every
        # service and the workflow failed in exactly the case it exists for:
        # a service being behind. The workflow now updates before it writes
        # the dashboard. If a future edit ever puts a write back in front of
        # this, fail here, naming the files and the reason, rather than
        # leaving someone to decode cruft's red text.
        dirty = _modified_tracked_files(repo_root)
        if dirty:
            raise RuntimeError(
                "cruft update needs a clean working tree and this repository has "
                f"uncommitted changes to tracked files: {dirty}. git status answers "
                "for the whole repository, not just the service being updated, and "
                "--allow-untracked-files does not cover modified tracked files. "
                "Commit or stash them; if this fired in CI, something wrote a "
                "tracked file before this step, and the step order in "
                ".github/workflows/drift.yml explains why it must not."
            )

        service_dir = pathlib.Path(repo_root) / paths[status.name]
        subprocess.run(
            ["cruft", "update", "--skip-apply-ask", "--allow-untracked-files"],
            cwd=service_dir, check=True,
        )
        updated.append(status.name)
    return updated


def main() -> None:
    root = str(pathlib.Path(__file__).resolve().parents[1])
    apply_updates(f"{root}/platformops/registry.yaml", root)


if __name__ == "__main__":
    main()
