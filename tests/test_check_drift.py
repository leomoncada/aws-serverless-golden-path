import json, pathlib, textwrap, pytest
from platformops.check_drift import collect

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
