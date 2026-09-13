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

def test_generated_service_has_a_ci_workflow(generated):
    wf = yaml.safe_load((generated / ".github/workflows/ci.yml").read_text())
    # PyYAML parses the bare key `on` as boolean True.
    triggers = wf.get("on") or wf.get(True)
    assert "pull_request" in triggers

def test_generated_ci_calls_make_targets_not_inline_commands(generated):
    body = (generated / ".github/workflows/ci.yml").read_text()
    assert "make ci" in body
    assert "terraform apply" not in body, "CI must call the Makefile, not inline terraform"

def test_generated_compose_pins_the_localstack_image(generated):
    compose = yaml.safe_load((generated / "docker-compose.yml").read_text())
    image = compose["services"]["localstack"]["image"]
    assert image == "localstack/localstack:4", "must be pinned; :latest needs a licence token"
