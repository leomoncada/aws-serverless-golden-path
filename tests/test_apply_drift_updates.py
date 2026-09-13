"""Covers the fix for the shell-injection finding: cruft update must be
invoked with a list argument vector (never a shell string built from
registry data), and only for services check_drift reports as behind."""
import json
import os
import pathlib
import subprocess
import textwrap
from datetime import UTC, datetime

from platformops import apply_drift_updates


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
    _git(repo_root, "add", "-A")
    stamp = when.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    env = {**os.environ, "GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp}
    _git(repo_root, "commit", "-q", "-m", message, env=env)
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo_root,
        check=True, capture_output=True, text=True,
    )
    return result.stdout.strip()


def test_apply_updates_runs_cruft_update_only_for_services_behind_via_argv(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    (tmp_path / "template").mkdir()
    (tmp_path / "template" / "cookiecutter.json").write_text("v1\n")
    old_sha = _commit(tmp_path, "old", when=datetime(2020, 1, 1, tzinfo=UTC))

    # check_drift compares against the newest commit that touched template/,
    # not repo HEAD (a service is behind only when the TEMPLATE moved), so
    # the fixture's "new" commit has to actually touch template/ too.
    (tmp_path / "template" / "cookiecutter.json").write_text("v2\n")
    head = _commit(tmp_path, "new (head)", when=datetime(2020, 6, 1, tzinfo=UTC))

    behind_dir = tmp_path / "examples" / "behind-svc"
    behind_dir.mkdir(parents=True)
    (behind_dir / ".cruft.json").write_text(json.dumps({"commit": old_sha}))

    current_dir = tmp_path / "examples" / "current-svc"
    current_dir.mkdir(parents=True)
    (current_dir / ".cruft.json").write_text(json.dumps({"commit": head}))

    registry = tmp_path / "registry.yaml"
    registry.write_text(textwrap.dedent("""
        services:
          - name: behind-svc
            repo: o/behind
            path: examples/behind-svc
          - name: current-svc
            repo: o/current
            path: examples/current-svc
    """))

    calls = []
    real_run = subprocess.run

    def fake_run(argv, **kwargs):
        # Only stub the cruft invocation; let check_drift's own git calls
        # (used to decide who is behind) run for real against tmp_path.
        if argv[0] != "cruft":
            return real_run(argv, **kwargs)
        calls.append((argv, str(kwargs.get("cwd"))))

        class Result:
            returncode = 0

        return Result()

    monkeypatch.setattr(apply_drift_updates.subprocess, "run", fake_run)

    updated = apply_drift_updates.apply_updates(str(registry), str(tmp_path))

    assert updated == ["behind-svc"]
    assert len(calls) == 1
    argv, cwd = calls[0]
    # A list argument vector, not a shell string: nothing here could ever
    # interpret a quote or `$(...)` inside a registry-supplied name.
    assert argv == ["cruft", "update", "--skip-apply-ask", "--allow-untracked-files"]
    assert isinstance(argv, list)
    assert cwd == str(behind_dir)
