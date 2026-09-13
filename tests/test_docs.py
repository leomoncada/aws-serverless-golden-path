import re
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


def test_committed_drift_md_matches_what_the_tool_currently_produces():
    # DRIFT.md is generated, not hand-maintained, and nothing regenerates it
    # automatically on commit. Without this guard it can silently go stale
    # the moment the registry or the template changes and nobody happens to
    # re-run `python -m platformops.check_drift` before committing. This is
    # the same shape as every other defence in this suite: the committed
    # artefact must match what the tool actually produces right now.
    #
    # "Right now" is safe to assert against a committed file only because
    # nothing the tool produces depends on the clock: days_behind is the
    # distance between two commits, not the distance from today. It used to
    # be the latter, which would have turned this guard into a daily CI
    # failure as soon as the template moved. See docs/TEMPLATE-VERSION.md.
    from platformops.check_drift import collect
    from platformops.drift_report import build_report

    statuses = collect(str(REPO / "platformops/registry.yaml"), str(REPO))
    expected = build_report(statuses)
    actual = (REPO / "DRIFT.md").read_text()
    assert actual == expected, (
        "DRIFT.md does not match `python -m platformops.check_drift` output; "
        "regenerate it before committing. If the tool reported `unknown`, this "
        "is a shallow clone and cannot see the history the dashboard needs: "
        "re-clone with full history. CI checks out with fetch-depth: 0 for "
        "this reason. See docs/TEMPLATE-VERSION.md."
    )


def test_no_absolute_local_paths_in_committed_files():
    """A generated .cruft.json records where it was generated from. Generating
    from a local checkout writes an absolute path that only resolves on one
    machine, and it comes back every time the example is regenerated, so the
    guard lives here rather than in a one-off correction."""
    tracked = subprocess.run(
        ["git", "ls-files", "-z"], cwd=REPO, check=True, capture_output=True
    ).stdout.split(b"\0")
    offenders = []
    for raw in tracked:
        if not raw:
            continue
        path = REPO / raw.decode()
        try:
            body = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        if re.search(r"/(Users|home)/[a-z][a-z0-9_-]*/", body):
            offenders.append(raw.decode())
    assert not offenders, f"absolute local paths committed in: {offenders}"
