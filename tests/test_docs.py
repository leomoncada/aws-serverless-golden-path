import pathlib
import subprocess

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]


def test_all_five_adrs_exist():
    adrs = sorted((REPO / "docs/adr").glob("0*.md"))
    assert len(adrs) == 5, f"found {[a.name for a in adrs]}"


def test_no_em_dashes_in_committed_prose():
    # The constraint is about prose committed to the repository, not about
    # every Markdown file this working tree happens to contain. Walking the
    # filesystem (REPO.rglob) would also catch .superpowers/, which holds
    # this pipeline's own agent-written reports and reviews and is
    # git-ignored scratch, deleted when the work finishes. Driving this from
    # `git ls-files` instead scopes the check to what is actually tracked,
    # matching the rule it is named after.
    result = subprocess.run(
        ["git", "ls-files", "*.md"],
        cwd=REPO, check=True, capture_output=True, text=True,
    )
    tracked_md = [line for line in result.stdout.splitlines() if line]
    offenders = []
    for rel in tracked_md:
        path = REPO / rel
        if not path.is_file():
            continue
        if "—" in path.read_text():
            offenders.append(rel)
    assert not offenders, f"em dashes found in {offenders}"


def test_readme_states_the_aws_path_is_unexercised():
    body = (REPO / "README.md").read_text().lower()
    assert "not been exercised" in body or "unexercised" in body


def test_the_example_service_is_committed_and_registered():
    assert (REPO / "examples/orders-ingest/.cruft.json").is_file()
    registry = (REPO / "platformops/registry.yaml").read_text()
    assert "examples/orders-ingest" in registry
