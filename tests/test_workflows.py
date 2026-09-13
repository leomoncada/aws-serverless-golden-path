"""Guards on this repository's own workflows.

Both of the defects these cover were invisible to every task-scoped review:
each file was correct on its own, and wrong next to the other one.
"""
import pathlib

import pytest
import yaml

REPO = pathlib.Path(__file__).resolve().parents[1]


def _workflow(name):
    return yaml.safe_load((REPO / ".github/workflows" / name).read_text())


def _steps(workflow):
    (job,) = workflow["jobs"].values()
    return job["steps"]


@pytest.mark.parametrize("name", ["ci.yml", "drift.yml"])
def test_workflows_check_out_full_git_history(name):
    # actions/checkout defaults to fetch-depth: 1, and a depth-1 clone does
    # not fail the code below it, it feeds it a wrong answer: the single
    # fetched commit appears to add every file, so "the newest commit
    # touching template/" resolves to HEAD, every registered service reads as
    # behind, and `make demo` finds no earlier template commit to pin its
    # demo service to. ci.yml was missing this while drift.yml had it, which
    # is why this is asserted for both and not just the one that broke.
    checkout = [s for s in _steps(_workflow(name)) if "checkout" in str(s.get("uses", ""))]
    assert checkout, f"{name} has no checkout step"
    for step in checkout:
        assert (step.get("with") or {}).get("fetch-depth") == 0, (
            f"{name}: checkout must set fetch-depth: 0. check_drift and "
            f"make demo both resolve template versions from git history; on a "
            f"shallow clone they silently report the wrong thing. See "
            f"docs/TEMPLATE-VERSION.md."
        )


def test_drift_workflow_updates_before_it_writes_the_dashboard():
    # `cruft update` refuses to run against a dirty tree, and the tree it
    # asks about is the whole repository. check_drift rewrites DRIFT.md,
    # which is tracked, and --allow-untracked-files does not forgive that.
    # So running the dashboard first made the workflow fail in precisely the
    # case it exists for: a service actually being behind. Order matters, so
    # it is asserted rather than left to a comment.
    steps = _steps(_workflow("drift.yml"))
    runs = [str(s.get("run", "")) for s in steps]
    update = next(i for i, r in enumerate(runs) if "apply_drift_updates" in r)
    dashboard = next(i for i, r in enumerate(runs) if "check_drift" in r)
    assert update < dashboard, (
        "drift.yml must run apply_drift_updates before check_drift: writing "
        "the dashboard first leaves a modified tracked file and every cruft "
        "update then refuses"
    )


def test_the_demo_the_platform_ci_runs_actually_lints():
    # tflint is installed by ci.yml. It was installed and never invoked,
    # because the only lint target in the tree belonged to the generated
    # service and nothing in this repository called it. CI runs `make demo`,
    # so demo is where lint has to be for the installed linter to mean
    # anything.
    body = (REPO / "Makefile").read_text()
    demo_line = next(l for l in body.splitlines() if l.strip().startswith("$(MAKE) up new"))
    assert "lint" in demo_line, f"make demo does not run lint: {demo_line}"
    assert "lint:" in body, "the platform Makefile has no lint target"
