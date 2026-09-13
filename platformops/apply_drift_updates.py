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


def apply_updates(registry_path: str, repo_root: str) -> list[str]:
    registry = yaml.safe_load(pathlib.Path(registry_path).read_text()) or {}
    paths = {entry["name"]: entry["path"] for entry in registry.get("services", [])}

    updated: list[str] = []
    for status in collect(registry_path, repo_root):
        if not status.behind:
            continue
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
