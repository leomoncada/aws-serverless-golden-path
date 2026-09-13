import subprocess, pathlib, shutil, pytest, yaml

REPO = pathlib.Path(__file__).resolve().parents[1]

@pytest.fixture
def generated(tmp_path):
    subprocess.run(
        ["cruft", "create", str(REPO), "--directory", "template", "--no-input", "--output-dir", str(tmp_path),
         "--extra-context", '{"service_name": "orders-ingest"}'],
        check=True, cwd=REPO,
    )
    return tmp_path / "orders-ingest"

def test_directory_is_named_after_the_service(generated):
    assert generated.is_dir()

def test_service_name_is_substituted_in_readme(generated):
    text = (generated / "README.md").read_text()
    assert "orders-ingest" in text
    assert "cookiecutter" not in text

def test_catalog_entry_declares_the_service(generated):
    entity = yaml.safe_load((generated / "catalog-info.yaml").read_text())
    assert entity["kind"] == "Component"
    assert entity["metadata"]["name"] == "orders-ingest"
    assert entity["spec"]["type"] == "service"

def test_cruft_records_the_template_origin(generated):
    # This file is what makes drift detection possible at all.
    assert (generated / ".cruft.json").is_file()
