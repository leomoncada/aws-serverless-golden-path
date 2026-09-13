import pathlib, re, yaml, pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
TPL = REPO / "template/{{cookiecutter.service_name}}"

def test_no_infrastructure_is_conditional_on_the_target():
    # The whole AWS path contract: local must exercise the same resources AWS
    # would get. A count or for_each keyed on the endpoint variable breaks it.
    offenders = []
    for tf in (TPL / "infra").rglob("*.tf"):
        if tf.name == "providers.tf":
            continue  # the provider block is the one sanctioned place
        body = tf.read_text()
        for line in body.splitlines():
            if re.search(r"(count|for_each)\s*=.*aws_endpoint_url", line):
                offenders.append(f"{tf}: {line.strip()}")
    assert not offenders, f"target-conditional infrastructure found: {offenders}"

def test_an_aws_deploy_workflow_exists_and_is_manual_only():
    wf = yaml.safe_load((TPL / ".github/workflows/deploy-aws.yml").read_text())
    triggers = wf.get("on") or wf.get(True)
    assert "workflow_dispatch" in triggers
    assert "push" not in triggers, "must never deploy to AWS automatically"

def test_aws_deploy_uses_oidc_not_stored_keys():
    body = (TPL / ".github/workflows/deploy-aws.yml").read_text()
    assert "id-token: write" in body
    assert "AWS_SECRET_ACCESS_KEY" not in body

def test_first_deploy_runbook_exists():
    body = (TPL / "docs/runbooks/first-aws-deploy.md").read_text()
    for required in ["state bucket", "OIDC", "not been exercised", "cost"]:
        assert required.lower() in body.lower(), f"runbook does not mention {required}"
