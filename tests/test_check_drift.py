import json, os, pathlib, subprocess, textwrap
from datetime import UTC, datetime

import pytest

from platformops.check_drift import collect
from platformops.drift_report import ServiceStatus


def _git(repo_root, *args, env=None):
    subprocess.run(
        ["git", *args], cwd=repo_root, check=True,
        capture_output=True, text=True, env=env,
    )


def _init_repo(repo_root):
    _git(repo_root, "init", "-q")
    _git(repo_root, "config", "user.email", "drift-test@example.invalid")
    _git(repo_root, "config", "user.name", "drift-test")


def _commit(repo_root, message, when):
    """Commit whatever is staged, with a fixed author/committer date so the
    commit's age is deterministic regardless of when the suite runs."""
    _git(repo_root, "add", "-A")
    stamp = when.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    env = {**os.environ, "GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp}
    _git(repo_root, "commit", "-q", "-m", message, env=env)
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo_root,
        check=True, capture_output=True, text=True,
    )
    return result.stdout.strip()


def _git_out(repo_root, *args):
    result = subprocess.run(
        ["git", *args], cwd=repo_root, check=True, capture_output=True, text=True,
    )
    return result.stdout.strip()


def _registry(tmp_path, name, path):
    registry = tmp_path / "registry.yaml"
    registry.write_text(textwrap.dedent(f"""
        services:
          - name: {name}
            repo: o/r
            path: {path}
    """))
    return registry


def test_collect_reads_the_registry_and_reports_each_service(tmp_path):
    svc = tmp_path / "examples" / "orders-ingest"
    svc.mkdir(parents=True)
    (svc / ".cruft.json").write_text(json.dumps({"commit": "abc1234567890"}))

    registry = tmp_path / "registry.yaml"
    registry.write_text(textwrap.dedent("""
        services:
          - name: orders-ingest
            repo: leomoncada/aws-serverless-golden-path
            path: examples/orders-ingest
    """))

    statuses = collect(str(registry), str(tmp_path))
    assert len(statuses) == 1
    assert statuses[0].name == "orders-ingest"
    assert statuses[0].template_sha == "abc1234"

def test_a_service_with_no_cruft_file_is_skipped_not_crashed(tmp_path):
    (tmp_path / "examples" / "ghost").mkdir(parents=True)
    registry = tmp_path / "registry.yaml"
    registry.write_text("services:\n  - name: ghost\n    repo: o/g\n    path: examples/ghost\n")
    assert collect(str(registry), str(tmp_path)) == []


def test_a_service_pinned_to_the_current_head_is_not_behind(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / "template").mkdir()
    (tmp_path / "template" / "cookiecutter.json").write_text("{}\n")
    head = _commit(tmp_path, "template commit", when=datetime(2020, 1, 1, tzinfo=UTC))

    svc = tmp_path / "examples" / "orders-ingest"
    svc.mkdir(parents=True)
    (svc / ".cruft.json").write_text(json.dumps({"commit": head}))
    registry = _registry(tmp_path, "orders-ingest", "examples/orders-ingest")

    statuses = collect(str(registry), str(tmp_path))
    assert statuses == [
        ServiceStatus("orders-ingest", "o/r", head[:7], behind=False, days_behind=0),
    ]


def test_the_lag_is_the_distance_between_two_commits_not_the_distance_from_today(tmp_path):
    # The lag used to be `now - the recorded commit's date`, which made
    # DRIFT.md a committed file whose contents changed every 24 hours while
    # nothing about the service changed. tests/test_docs.py asserts the
    # committed file equals what the tool produces right now, so that
    # combination was a scheduled daily CI failure from the first commit
    # that touched template/. The lag is now the distance between the
    # service's template version and the current one, two fixed commit
    # dates, so this expectation is a literal: 2020-01-01 to 2020-06-01 is
    # 152 days, today and in ten years.
    _init_repo(tmp_path)

    (tmp_path / "template").mkdir()
    (tmp_path / "template" / "cookiecutter.json").write_text("{}\n")
    old_sha = _commit(tmp_path, "old template commit", when=datetime(2020, 1, 1, tzinfo=UTC))

    (tmp_path / "template" / "cookiecutter.json").write_text('{"v": 2}\n')
    _commit(tmp_path, "newer template commit", when=datetime(2020, 6, 1, tzinfo=UTC))

    svc = tmp_path / "examples" / "orders-ingest"
    svc.mkdir(parents=True)
    (svc / ".cruft.json").write_text(json.dumps({"commit": old_sha}))
    registry = _registry(tmp_path, "orders-ingest", "examples/orders-ingest")

    statuses = collect(str(registry), str(tmp_path))
    assert len(statuses) == 1
    assert statuses[0].behind is True
    assert statuses[0].unknown is False
    assert statuses[0].days_behind == 152


def test_a_service_generated_from_a_commit_that_did_not_touch_the_template_is_current(tmp_path):
    # cruft writes the template repository's HEAD into .cruft.json at
    # generation time, whatever that commit touched. Generate a service one
    # commit after a docs change and .cruft.json records the docs commit,
    # which is not a template version at all. Comparing that raw SHA against
    # the newest template-touching commit reported a service generated
    # seconds ago as behind, and apply_drift_updates would then run a cruft
    # update with nothing to merge. The recorded commit is resolved to the
    # template version underneath it first; see docs/TEMPLATE-VERSION.md.
    _init_repo(tmp_path)
    (tmp_path / "template").mkdir()
    (tmp_path / "template" / "cookiecutter.json").write_text("{}\n")
    template_sha = _commit(tmp_path, "template commit", when=datetime(2020, 1, 1, tzinfo=UTC))

    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "NOTES.md").write_text("a docs change\n")
    docs_sha = _commit(tmp_path, "docs only commit", when=datetime(2020, 2, 1, tzinfo=UTC))

    svc = tmp_path / "examples" / "orders-ingest"
    svc.mkdir(parents=True)
    # Freshly generated, so cruft recorded repo HEAD: a docs commit.
    (svc / ".cruft.json").write_text(json.dumps({"commit": docs_sha}))
    registry = _registry(tmp_path, "orders-ingest", "examples/orders-ingest")

    statuses = collect(str(registry), str(tmp_path))
    assert statuses == [
        ServiceStatus("orders-ingest", "o/r", template_sha[:7], behind=False, days_behind=0),
    ], "a service generated seconds ago must not be reported behind"


def test_a_shallow_clone_is_reported_unknown_not_behind(tmp_path):
    # The condition that stopped this repository's own CI from going green.
    # In a depth-1 clone the single fetched commit appears to add every file,
    # so the newest commit touching template/ resolves to HEAD and every
    # service reads as behind: a wrong answer, not a missing one. The fix is
    # fetch-depth: 0 in both workflows (tests/test_workflows.py), but a tool
    # that cannot see the history it needs has to say so rather than guess.
    origin = tmp_path / "origin"
    origin.mkdir()
    _init_repo(origin)
    (origin / "template").mkdir()
    (origin / "template" / "cookiecutter.json").write_text("{}\n")
    _commit(origin, "template commit", when=datetime(2020, 1, 1, tzinfo=UTC))
    (origin / "README.md").write_text("later, unrelated\n")
    _commit(origin, "docs commit", when=datetime(2020, 2, 1, tzinfo=UTC))

    shallow = tmp_path / "shallow"
    subprocess.run(
        ["git", "clone", "--depth", "1", f"file://{origin}", str(shallow)],
        check=True, capture_output=True, text=True,
    )
    assert _git_out(shallow, "rev-parse", "--is-shallow-repository") == "true"

    svc = shallow / "examples" / "orders-ingest"
    svc.mkdir(parents=True)
    (svc / ".cruft.json").write_text(json.dumps({"commit": "abc1234567890"}))
    registry = _registry(tmp_path, "orders-ingest", "examples/orders-ingest")

    statuses = collect(str(registry), str(shallow))
    assert len(statuses) == 1
    assert statuses[0].unknown is True
    assert statuses[0].behind is False


def test_a_commit_that_only_touches_docs_does_not_make_a_service_behind(tmp_path):
    # This is the semantics this whole module exists to get right: a
    # service is behind only when the TEMPLATE has moved, never merely
    # because some other commit landed in the platform repository. A commit
    # that only touches docs/ (a README edit, an ADR) must leave every
    # registered service exactly as current (or behind) as it was before
    # that commit, not newly behind.
    _init_repo(tmp_path)
    (tmp_path / "template").mkdir()
    (tmp_path / "template" / "cookiecutter.json").write_text("{}\n")
    template_sha = _commit(tmp_path, "template commit", when=datetime(2020, 1, 1, tzinfo=UTC))

    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "NOTES.md").write_text("unrelated docs change\n")
    _commit(tmp_path, "docs only commit", when=datetime(2024, 1, 1, tzinfo=UTC))

    svc = tmp_path / "examples" / "orders-ingest"
    svc.mkdir(parents=True)
    (svc / ".cruft.json").write_text(json.dumps({"commit": template_sha}))
    registry = _registry(tmp_path, "orders-ingest", "examples/orders-ingest")

    statuses = collect(str(registry), str(tmp_path))
    assert statuses == [
        ServiceStatus("orders-ingest", "o/r", template_sha[:7], behind=False, days_behind=0),
    ]


def test_an_unresolvable_head_is_reported_unknown_not_current(tmp_path):
    # tmp_path is deliberately NOT a git repository, so the template's
    # latest commit cannot be determined at all. This must not be reported
    # as "current".
    svc = tmp_path / "examples" / "orders-ingest"
    svc.mkdir(parents=True)
    (svc / ".cruft.json").write_text(json.dumps({"commit": "abc1234567890"}))
    registry = _registry(tmp_path, "orders-ingest", "examples/orders-ingest")

    statuses = collect(str(registry), str(tmp_path))
    assert len(statuses) == 1
    assert statuses[0].unknown is True
    assert statuses[0].behind is False


def test_an_empty_recorded_commit_is_reported_unknown_not_current(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / "README.md").write_text("template v1\n")
    _commit(tmp_path, "template commit", when=datetime(2020, 1, 1, tzinfo=UTC))

    svc = tmp_path / "examples" / "orders-ingest"
    svc.mkdir(parents=True)
    (svc / ".cruft.json").write_text(json.dumps({"commit": ""}))
    registry = _registry(tmp_path, "orders-ingest", "examples/orders-ingest")

    statuses = collect(str(registry), str(tmp_path))
    assert len(statuses) == 1
    assert statuses[0].unknown is True
    assert statuses[0].behind is False


def test_an_unreachable_recorded_commit_says_so_rather_than_just_unknown(tmp_path):
    """A rebase or squash merge rewrites a branch's commits, so the SHA a
    generated service recorded stops being reachable. It survives locally as a
    dangling object, so this passes on the machine that merged and fails on a
    fresh clone. The repair is to regenerate the fixture, not the dashboard,
    and the two are only distinguishable if the reason is carried."""
    repo = tmp_path
    _init_repo(repo)
    (repo / "template").mkdir()
    (repo / "template" / "main.tf").write_text("# v1\n")
    _commit(repo, "template v1", datetime(2026, 9, 1, 10, 0))

    svc = repo / "examples" / "orders-ingest"
    svc.mkdir(parents=True)
    orphan = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True,
        capture_output=True, text=True,
    ).stdout.strip()

    # Rewrite history so the recorded commit stops being an ancestor of HEAD,
    # exactly as a rebase merge does.
    subprocess.run(["git", "checkout", "-q", "--orphan", "rewritten"], cwd=repo, check=True)
    (repo / "template" / "main.tf").write_text("# v1 rewritten\n")
    _commit(repo, "template v1, rewritten", datetime(2026, 9, 2, 10, 0))

    (svc / ".cruft.json").write_text(json.dumps({"commit": orphan}))
    registry = repo / "registry.yaml"
    registry.write_text(
        "services:\n  - name: orders-ingest\n    repo: o/orders-ingest\n"
        "    path: examples/orders-ingest\n"
    )

    statuses = collect(str(registry), str(repo))
    assert len(statuses) == 1
    assert statuses[0].unknown is True
    assert "not reachable" in statuses[0].unknown_reason
    assert "rebase or squash" in statuses[0].unknown_reason
