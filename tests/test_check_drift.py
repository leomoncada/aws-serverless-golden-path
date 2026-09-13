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


def test_a_service_pinned_to_an_earlier_commit_is_behind_by_its_recorded_age(tmp_path):
    _init_repo(tmp_path)

    old_date = datetime(2020, 1, 1, tzinfo=UTC)
    (tmp_path / "template").mkdir()
    (tmp_path / "template" / "cookiecutter.json").write_text("{}\n")
    old_sha = _commit(tmp_path, "old template commit", when=old_date)

    (tmp_path / "template" / "cookiecutter.json").write_text('{"v": 2}\n')
    _commit(tmp_path, "newer template commit", when=datetime(2020, 6, 1, tzinfo=UTC))

    svc = tmp_path / "examples" / "orders-ingest"
    svc.mkdir(parents=True)
    (svc / ".cruft.json").write_text(json.dumps({"commit": old_sha}))
    registry = _registry(tmp_path, "orders-ingest", "examples/orders-ingest")

    expected_days = (datetime.now(UTC) - old_date).days

    statuses = collect(str(registry), str(tmp_path))
    assert len(statuses) == 1
    assert statuses[0].behind is True
    assert statuses[0].unknown is False
    assert statuses[0].days_behind == expected_days


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
