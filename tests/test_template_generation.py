import re
import subprocess, pathlib, pytest, yaml

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


def test_generated_compose_waits_on_the_bucket_not_the_health_endpoint(generated):
    # The platform's own compose file has done this since Task 1; the
    # generated one did not, and compensated with an unbounded shell loop in
    # its Makefile. /_localstack/health answers 200 before the ready.d hooks
    # run, so `--wait` against the base image's healthcheck returns before
    # the tfstate bucket exists, which is the actual precondition for the
    # next command a developer runs.
    compose = yaml.safe_load((generated / "docker-compose.yml").read_text())
    healthcheck = compose["services"]["localstack"].get("healthcheck")
    assert healthcheck, "generated compose has no explicit healthcheck"
    assert "head-bucket" in " ".join(healthcheck["test"])
    assert healthcheck["retries"] == 40, "readiness must be bounded, not infinite"

    mounts = compose["services"]["localstack"]["volumes"]
    assert any("/etc/localstack/init/ready.d" in m for m in mounts), (
        "the bucket has to be created by an init hook if the healthcheck "
        "waits on it"
    )
    hook = generated / "localstack/init/ready.d/01-tfstate-bucket.sh"
    assert hook.is_file(), "the mounted init hook is not generated"
    assert "create-bucket --bucket tfstate" in hook.read_text()


def test_generated_make_up_is_bounded_and_needs_no_aws_cli(generated):
    # The loop this replaced never gave up, and needed the AWS CLI, which the
    # generated README's prerequisites did not list and plenty of laptops do
    # not have: `until aws ...` then fails with command-not-found, the body
    # runs `aws ... || sleep 2`, and `make up` hangs forever with no output.
    body = (generated / "Makefile").read_text()
    up = body.split("\nup:\n", 1)[1].split("\n\n", 1)[0]
    assert "docker compose up -d --wait" in up
    assert "until" not in up, "make up must not loop; the healthcheck is bounded"
    assert "aws " not in up, "make up must not need the AWS CLI"

    readme = (generated / "README.md").read_text()
    assert "no AWS CLI" in readme, "the prerequisites must say what is needed"


def test_the_absence_of_signal_assertion_cannot_be_skipped(generated):
    # The repository's headline observability finding. It used to skip when
    # the alarm's window was not empty, and a skip exits 0, so CI could go
    # green having never asserted it. Nothing enforced the collection order
    # that kept the window empty either: alphabetical collection put alarms
    # before integration by luck, not by design.
    alarms = (generated / "tests/test_alarms.py").read_text()
    assert "pytest.skip" not in alarms, (
        "the absence-of-signal test must not be skippable: it is the one "
        "assertion this template's observability claim rests on"
    )
    assert 'alarm["StateValue"] == "ALARM"' in alarms

    makefile = (generated / "Makefile").read_text()
    test_target = makefile.split("\ntest:\n", 1)[1].split("\n\n", 1)[0]
    assert "tests/test_alarms.py" in test_target.splitlines()[0], (
        "make test must run the alarm test first, in its own session, rather "
        "than relying on alphabetical collection order"
    )


def test_make_demo_exists_and_excludes_the_portal():
    body = (REPO / "Makefile").read_text()
    assert "demo:" in body
    demo_line = [l for l in body.splitlines() if l.startswith("demo:")][0]
    assert "portal" not in demo_line, "portal needs Node and must not be in demo"


def _lock_file(generated):
    return (generated / "infra" / ".terraform.lock.hcl").read_text()


# Without a committed lock file every generated service resolves providers
# fresh, so a new AWS provider release can turn a green pipeline red with
# nobody having touched the code. The version constraints stay as ranges on
# purpose: the lock is what pins, which is the normal Terraform split.
def test_generated_service_ships_a_provider_lock(generated):
    lock = generated / "infra" / ".terraform.lock.hcl"
    assert lock.is_file(), "generated service has no infra/.terraform.lock.hcl"


def test_the_lock_pins_exact_versions_for_every_declared_provider(generated):
    body = _lock_file(generated)
    for provider in ["hashicorp/aws", "hashicorp/archive"]:
        assert f'provider "registry.terraform.io/{provider}"' in body, (
            f"{provider} is declared in versions.tf but absent from the lock"
        )
    # An exact `version = "x.y.z"` line per provider, not a range.
    versions = re.findall(r'^\s*version\s*=\s*"(\d+\.\d+\.\d+)"', body, re.M)
    assert len(versions) >= 2, f"expected an exact version per provider, found {versions}"


# CI runs on linux and this repo is developed on macOS. A lock generated for
# only one of them fails `terraform init` on the other with a checksum error,
# which reads like a supply chain problem and is really a missing platform.
# Regenerate with:
#   terraform providers lock -platform=linux_amd64 -platform=linux_arm64 \
#     -platform=darwin_amd64 -platform=darwin_arm64
def test_the_lock_covers_more_than_one_platform(generated):
    body = _lock_file(generated)
    per_provider = [block.count("h1:") for block in body.split('provider "')[1:]]
    assert per_provider, "no provider blocks in the lock file"
    assert min(per_provider) >= 2, (
        f"lock looks single-platform, h1 hashes per provider: {per_provider}"
    )
