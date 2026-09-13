# aws-serverless-golden-path Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a cookiecutter template that generates a production-shaped serverless AWS service, verifies itself end to end against LocalStack on every pull request with no cloud credentials, and keeps already-generated services up to date through automated `cruft update` pull requests.

**Architecture:** A platform repository holding three things: the cookiecutter template (`template/`), the drift machinery (`platform/`), and a thin Backstage adapter (`backstage/`). The platform's own CI generates a service from its template into a sandbox, provisions it against LocalStack, runs the generated service's own tests, and destroys it. Local and CI share the same Makefile targets so they cannot diverge.

**Tech Stack:** Terraform >= 1.11, LocalStack Community (image pinned to `localstack/localstack:4`), Python 3.12, cookiecutter, cruft, pytest, boto3, GitHub Actions, tflint, checkov, Make.

**Spec:** `/Users/leomar/leo/golden-path-design.md` (becomes `docs/DESIGN.md` in the repo's first commit)

## Global Constraints

- **Zero cost.** Nothing is hosted. No AWS account is used at any point in this plan.
- **LocalStack image is pinned to `localstack/localstack:4`.** Never `:latest`, which refuses to start without a licence token.
- **Service intersection only.** The template may use only: Lambda, S3, DynamoDB, SQS, SNS, IAM, CloudWatch Logs, CloudWatch metric alarms. Verified available in Community on 2026-09-13. Anything else requires an ADR first.
- **No target-conditional infrastructure.** No `count = var.is_local ? 0 : 1` or equivalent anywhere in `template/`. The code exercised locally must be the code that would reach AWS. Divergences go in `PARITY-NOTES.md`, never into the Terraform as a fork.
- **Terraform floor is 1.11**, because the S3 backend locks with `use_lockfile`.
- **No em dashes** in any prose committed to this repository, including README, ADRs and commit messages. Use commas, colons, parentheses, or split the sentence.
- **If it is documented, it is implemented.** Before any task is complete, every claim added to a README or doc in that task must be true of the code in that task. Where something is not verified, say so explicitly rather than omitting it.
- **Every Makefile target used by CI is the target CI calls.** CI never inlines a command that a target already wraps.

---

## File Structure

```
aws-serverless-golden-path/
├── Makefile                          platform targets: up, down, new, apply, test, drift-demo, demo, portal
├── docker-compose.yml                LocalStack, pinned to :4
├── localstack/init/ready.d/          bootstrap hook: creates the tfstate bucket
├── requirements-dev.txt              cookiecutter, cruft, pytest, boto3, checkov
├── .tflint.hcl
├── template/
│   ├── cookiecutter.json             the variables
│   └── {{cookiecutter.service_name}}/
│       ├── infra/
│       │   ├── versions.tf           terraform + provider version floors
│       │   ├── providers.tf          the endpoint-gating block (the AWS path contract)
│       │   ├── variables.tf
│       │   ├── main.tf               module wiring
│       │   ├── alarms.tf
│       │   ├── outputs.tf
│       │   ├── modules/ingest-bucket/
│       │   ├── modules/processor-lambda/
│       │   ├── modules/records-table/
│       │   └── env/{local,aws}.backend.hcl
│       ├── app/handler.py
│       ├── tests/{conftest,test_contract,test_integration,test_alarms}.py
│       ├── .github/workflows/ci.yml
│       ├── .github/workflows/deploy-aws.yml
│       ├── Makefile
│       ├── docs/runbooks/{deploy,rollback,incidents,first-aws-deploy}.md
│       ├── catalog-info.yaml
│       └── README.md
├── platform/
│   ├── registry.yaml                 services generated from this template
│   └── drift_report.py               builds DRIFT.md from cruft check results
├── backstage/template.yaml
├── tests/test_template_generation.py platform-level tests
├── docs/
│   ├── DESIGN.md
│   ├── adr/
│   └── PARITY-NOTES.md
├── examples/                         one committed generated service, the drift fixture
├── catalog-info.yaml
├── DRIFT.md                          generated dashboard
└── README.md
```

**Why this split:** `template/` is the product and must be generatable in isolation. `platform/` is the machinery that operates on generated services and never ships inside them. `backstage/` is one consumer of `template/` and nothing depends on it.

---

## Task 1: Repository skeleton and LocalStack harness

**Files:**
- Create: `Makefile`, `docker-compose.yml`, `localstack/init/ready.d/01-tfstate-bucket.sh`, `requirements-dev.txt`, `.gitignore`, `README.md`
- Test: `tests/test_harness.py`

**Interfaces:**
- Consumes: nothing
- Produces: `make up` / `make down`; a LocalStack endpoint at `http://localhost:4566`; an S3 bucket named `tfstate` that later tasks use as the Terraform backend.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_harness.py
import boto3, pytest

ENDPOINT = "http://localhost:4566"

@pytest.fixture
def s3():
    return boto3.client(
        "s3", endpoint_url=ENDPOINT, region_name="us-east-1",
        aws_access_key_id="test", aws_secret_access_key="test",
    )

def test_localstack_is_community_edition():
    import urllib.request, json
    with urllib.request.urlopen(f"{ENDPOINT}/_localstack/health") as r:
        health = json.load(r)
    assert health["edition"] == "community"

def test_required_services_are_available():
    import urllib.request, json
    with urllib.request.urlopen(f"{ENDPOINT}/_localstack/health") as r:
        services = json.load(r)["services"]
    for name in ["s3", "lambda", "dynamodb", "sqs", "sns", "iam", "logs", "cloudwatch"]:
        assert services.get(name) in ("available", "running"), f"{name} is {services.get(name)}"

def test_tfstate_bucket_exists(s3):
    s3.head_bucket(Bucket="tfstate")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_harness.py -v`
Expected: FAIL. All three error with `URLError` or `ConnectionRefusedError`, because nothing is listening on 4566.

- [ ] **Step 3: Write the harness**

```yaml
# docker-compose.yml
services:
  localstack:
    # Pinned deliberately. The :latest tag refuses to start without a licence
    # token, which surfaces as a confusing "LocalStack is broken" for anyone
    # cloning this repo.
    image: localstack/localstack:4
    container_name: golden-path-localstack
    ports:
      - "4566:4566"
    environment:
      DEBUG: ${DEBUG:-0}
      SERVICES: s3,lambda,dynamodb,iam,sts,logs,sqs,sns,cloudwatch
      LAMBDA_RUNTIME_EXECUTOR: docker
    volumes:
      - "./localstack/init/ready.d:/etc/localstack/init/ready.d"
      - "/var/run/docker.sock:/var/run/docker.sock"
    # Readiness is the bucket, not /_localstack/health. That endpoint answers
    # 200 before the ready.d hooks run, and the bucket is the real precondition
    # for the very next command a user runs.
    healthcheck:
      test: ["CMD-SHELL", "awslocal s3api head-bucket --bucket tfstate || exit 1"]
      interval: 3s
      timeout: 10s
      retries: 40
      start_period: 10s
```

```bash
# localstack/init/ready.d/01-tfstate-bucket.sh
#!/usr/bin/env bash
set -euo pipefail
awslocal s3api create-bucket --bucket tfstate
```

```
# requirements-dev.txt
cookiecutter==2.6.0
cruft==2.15.0
pytest==8.4.2
boto3==1.40.47
checkov==3.2.505
PyYAML==6.0.3
```

```makefile
# Makefile
SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help

.PHONY: help up down
help:
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*##/\t/'

up: ## Start LocalStack and wait until the tfstate bucket exists
	docker compose up -d --wait

down: ## Stop LocalStack and remove its volumes
	docker compose down -v
```

Also create `.gitignore` containing `sandbox/`, `.venv/`, `__pycache__/`, `*.tfstate*`, `.terraform/`, `.pytest_cache/`.

- [ ] **Step 4: Run test to verify it passes**

Run: `make up && python -m pytest tests/test_harness.py -v`
Expected: PASS, 3 passed. If `test_required_services_are_available` fails on `cloudwatch`, the `SERVICES` list in `docker-compose.yml` is wrong; it must include `cloudwatch` and `sns`.

- [ ] **Step 5: Commit**

```bash
git add Makefile docker-compose.yml localstack requirements-dev.txt .gitignore tests/test_harness.py README.md
git commit -m "feat: LocalStack harness pinned to image 4 with tfstate bootstrap"
```

---

## Task 2: Cookiecutter template skeleton and `make new`

**Files:**
- Create: `template/cookiecutter.json`, `template/{{cookiecutter.service_name}}/README.md`, `template/{{cookiecutter.service_name}}/catalog-info.yaml`
- Modify: `Makefile`
- Test: `tests/test_template_generation.py`

**Interfaces:**
- Consumes: Task 1's `make` conventions
- Produces: `make new` generates into `sandbox/<service_name>/`; the cookiecutter variables `service_name`, `owner_team`, `description`, `python_runtime`, `aws_region`, which every later template file may reference.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_template_generation.py
import subprocess, pathlib, shutil, pytest, yaml

REPO = pathlib.Path(__file__).resolve().parents[1]

@pytest.fixture
def generated(tmp_path):
    subprocess.run(
        ["cruft", "create", str(REPO), "--no-input", "--output-dir", str(tmp_path),
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_template_generation.py -v`
Expected: FAIL with `subprocess.CalledProcessError`, because `cookiecutter.json` does not exist and cruft cannot find a template.

- [ ] **Step 3: Write the template skeleton**

```json
// template/cookiecutter.json
{
  "service_name": "my-service",
  "owner_team": "platform",
  "description": "A serverless ingestion service",
  "python_runtime": "python3.12",
  "aws_region": "us-east-1"
}
```

Note: cruft and cookiecutter look for `cookiecutter.json` at the repository root by default. Add a `.cruft` pointer by placing this in the repo root `cookiecutter.json` as a one line re-export is not supported, so instead pass `--directory template` on every cruft invocation. Update the test's `cruft create` call to include `--directory template`, and use that flag consistently everywhere in this plan.

```markdown
<!-- template/{{cookiecutter.service_name}}/README.md -->
# {{cookiecutter.service_name}}

{{cookiecutter.description}}

Owned by `{{cookiecutter.owner_team}}`.

Generated from the [aws-serverless-golden-path](https://github.com/leomoncada/aws-serverless-golden-path)
template. Run `cruft check` to see whether this service is behind the template.

## Quickstart

```bash
make up      # start LocalStack
make apply   # provision this service
make test    # run the tests
make down
```

Requires Docker, Terraform >= 1.11, Python 3.12 and make. No AWS account and no
credentials.
```

```yaml
# template/{{cookiecutter.service_name}}/catalog-info.yaml
apiVersion: backstage.io/v1alpha1
kind: Component
metadata:
  name: {{cookiecutter.service_name}}
  description: {{cookiecutter.description}}
spec:
  type: service
  lifecycle: experimental
  owner: {{cookiecutter.owner_team}}
```

```makefile
# append to Makefile
SANDBOX ?= sandbox
SERVICE ?= orders-ingest

.PHONY: new
new: ## Generate a service from the template into $(SANDBOX)/$(SERVICE)
	rm -rf $(SANDBOX)/$(SERVICE)
	mkdir -p $(SANDBOX)
	cruft create . --directory template --no-input --output-dir $(SANDBOX) \
		--extra-context '{"service_name": "$(SERVICE)"}'
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_template_generation.py -v`
Expected: PASS, 4 passed.

- [ ] **Step 5: Commit**

```bash
git add template Makefile tests/test_template_generation.py
git commit -m "feat: cookiecutter template skeleton generated via cruft"
```

---

## Task 3: Generated service infrastructure

**Files:**
- Create: under `template/{{cookiecutter.service_name}}/infra/`: `versions.tf`, `providers.tf`, `variables.tf`, `main.tf`, `outputs.tf`, `env/local.backend.hcl`, `env/aws.backend.hcl`, and modules `ingest-bucket/`, `records-table/`, `processor-lambda/`
- Create: `template/{{cookiecutter.service_name}}/tests/conftest.py`, `tests/test_contract.py`
- Modify: `template/{{cookiecutter.service_name}}/Makefile` (create it here)
- Test: the generated service's own `tests/test_contract.py`

**Interfaces:**
- Consumes: Task 2's cookiecutter variables
- Produces: Terraform outputs `bucket_name`, `table_name`, `function_name`, `dlq_url`, `alarm_topic_arn`; the generated `make apply` / `make destroy`; the `aws_endpoint_url` variable contract that Task 11 relies on.

- [ ] **Step 1: Write the failing test**

```python
# template/{{cookiecutter.service_name}}/tests/conftest.py
import os, subprocess, json, pytest, boto3

ENDPOINT = os.environ.get("AWS_ENDPOINT_URL", "http://localhost:4566")
REGION = "{{cookiecutter.aws_region}}"

def _client(service):
    return boto3.client(
        service, endpoint_url=ENDPOINT, region_name=REGION,
        aws_access_key_id="test", aws_secret_access_key="test",
    )

@pytest.fixture(scope="session")
def tf_outputs():
    raw = subprocess.run(
        ["terraform", "-chdir=infra", "output", "-json"],
        check=True, capture_output=True, text=True,
    ).stdout
    return {k: v["value"] for k, v in json.loads(raw).items()}

@pytest.fixture
def s3(): return _client("s3")
@pytest.fixture
def dynamodb(): return _client("dynamodb")
@pytest.fixture
def sqs(): return _client("sqs")
@pytest.fixture
def cloudwatch(): return _client("cloudwatch")
@pytest.fixture
def lambda_(): return _client("lambda")
```

```python
# template/{{cookiecutter.service_name}}/tests/test_contract.py
def test_bucket_blocks_public_access(s3, tf_outputs):
    conf = s3.get_public_access_block(Bucket=tf_outputs["bucket_name"])
    block = conf["PublicAccessBlockConfiguration"]
    assert all(block[k] for k in
               ["BlockPublicAcls", "IgnorePublicAcls", "BlockPublicPolicy", "RestrictPublicBuckets"])

def test_bucket_has_versioning_enabled(s3, tf_outputs):
    assert s3.get_bucket_versioning(Bucket=tf_outputs["bucket_name"])["Status"] == "Enabled"

def test_table_is_on_demand(dynamodb, tf_outputs):
    table = dynamodb.describe_table(TableName=tf_outputs["table_name"])["Table"]
    assert table["BillingModeSummary"]["BillingMode"] == "PAY_PER_REQUEST"

def test_lambda_has_a_dead_letter_queue(lambda_, tf_outputs):
    conf = lambda_.get_function_configuration(FunctionName=tf_outputs["function_name"])
    assert conf.get("DeadLetterConfig", {}).get("TargetArn"), "no DLQ configured"

def test_lambda_runtime_is_pinned(lambda_, tf_outputs):
    conf = lambda_.get_function_configuration(FunctionName=tf_outputs["function_name"])
    assert conf["Runtime"] == "{{cookiecutter.python_runtime}}"
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
make new && cd sandbox/orders-ingest && make apply
```
Expected: FAIL at `make apply`, because `infra/` does not exist yet. This is the correct failure.

- [ ] **Step 3: Write the infrastructure**

```hcl
# infra/versions.tf
terraform {
  # 1.11 is the floor because the S3 backend locks with use_lockfile.
  required_version = ">= 1.11"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 6.0" }
  }
  backend "s3" {}
}
```

```hcl
# infra/providers.tf
#
# This is the single contract that keeps the AWS path open. One codebase, two
# targets. Set aws_endpoint_url and everything below activates and points at
# LocalStack. Leave it empty and this is an ordinary AWS provider.
#
# Do not add target-conditional resources anywhere else. The moment the
# infrastructure itself differs, the local run stops proving anything about AWS.
provider "aws" {
  region = var.aws_region

  access_key = var.aws_endpoint_url != "" ? "test" : null
  secret_key = var.aws_endpoint_url != "" ? "test" : null

  s3_use_path_style           = var.aws_endpoint_url != ""
  skip_credentials_validation = var.aws_endpoint_url != ""
  skip_metadata_api_check     = var.aws_endpoint_url != ""
  skip_requesting_account_id  = var.aws_endpoint_url != ""

  dynamic "endpoints" {
    for_each = var.aws_endpoint_url != "" ? [1] : []
    content {
      s3         = var.aws_endpoint_url
      dynamodb   = var.aws_endpoint_url
      lambda     = var.aws_endpoint_url
      sqs        = var.aws_endpoint_url
      sns        = var.aws_endpoint_url
      iam        = var.aws_endpoint_url
      sts        = var.aws_endpoint_url
      logs       = var.aws_endpoint_url
      cloudwatch = var.aws_endpoint_url
    }
  }

  default_tags {
    tags = {
      Service   = "{{cookiecutter.service_name}}"
      Owner     = "{{cookiecutter.owner_team}}"
      ManagedBy = "terraform"
    }
  }
}
```

```hcl
# infra/variables.tf
variable "aws_region" {
  type    = string
  default = "{{cookiecutter.aws_region}}"
}

variable "aws_endpoint_url" {
  description = "Set to a LocalStack endpoint to target it. Empty targets real AWS."
  type        = string
  default     = ""
}

variable "service_name" {
  type    = string
  default = "{{cookiecutter.service_name}}"
}
```

```hcl
# infra/main.tf
module "ingest_bucket" {
  source       = "./modules/ingest-bucket"
  service_name = var.service_name
}

module "records_table" {
  source       = "./modules/records-table"
  service_name = var.service_name
}

module "processor" {
  source       = "./modules/processor-lambda"
  service_name = var.service_name
  runtime      = "{{cookiecutter.python_runtime}}"
  bucket_arn   = module.ingest_bucket.arn
  bucket_id    = module.ingest_bucket.id
  table_name   = module.records_table.name
  table_arn    = module.records_table.arn
}
```

```hcl
# infra/modules/ingest-bucket/main.tf
resource "aws_s3_bucket" "this" {
  bucket        = "${var.service_name}-ingest"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "this" {
  bucket                  = aws_s3_bucket.this.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "this" {
  bucket = aws_s3_bucket.this.id
  versioning_configuration { status = "Enabled" }
}
```

```hcl
# infra/modules/ingest-bucket/variables.tf
variable "service_name" { type = string }
# infra/modules/ingest-bucket/outputs.tf
output "id" { value = aws_s3_bucket.this.id }
output "arn" { value = aws_s3_bucket.this.arn }
```

```hcl
# infra/modules/records-table/main.tf
resource "aws_dynamodb_table" "this" {
  name         = "${var.service_name}-records"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "record_id"
  attribute {
    name = "record_id"
    type = "S"
  }
}
```
with `variables.tf` declaring `service_name` and `outputs.tf` exposing `name = aws_dynamodb_table.this.name` and `arn = aws_dynamodb_table.this.arn`.

```hcl
# infra/modules/processor-lambda/main.tf
resource "aws_sqs_queue" "dlq" {
  name = "${var.service_name}-dlq"
}

data "archive_file" "app" {
  type        = "zip"
  source_dir  = "${path.root}/../app"
  output_path = "${path.root}/.build/app.zip"
}

resource "aws_iam_role" "this" {
  name               = "${var.service_name}-processor"
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "permissions" {
  statement {
    actions   = ["s3:GetObject"]
    resources = ["${var.bucket_arn}/*"]
  }
  statement {
    actions   = ["dynamodb:PutItem"]
    resources = [var.table_arn]
  }
  statement {
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.dlq.arn]
  }
  statement {
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.this.arn}:*"]
  }
}

resource "aws_iam_role_policy" "this" {
  role   = aws_iam_role.this.id
  policy = data.aws_iam_policy_document.permissions.json
}

resource "aws_cloudwatch_log_group" "this" {
  name              = "/aws/lambda/${var.service_name}-processor"
  retention_in_days = 14
}

resource "aws_lambda_function" "this" {
  function_name    = "${var.service_name}-processor"
  role             = aws_iam_role.this.arn
  handler          = "handler.handle"
  runtime          = var.runtime
  filename         = data.archive_file.app.output_path
  source_code_hash = data.archive_file.app.output_base64sha256
  timeout          = 10

  dead_letter_config { target_arn = aws_sqs_queue.dlq.arn }

  environment {
    variables = {
      TABLE_NAME = var.table_name
      LOG_JSON   = "true"
    }
  }

  depends_on = [aws_cloudwatch_log_group.this]
}

resource "aws_lambda_permission" "s3" {
  statement_id  = "AllowS3Invoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.this.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = var.bucket_arn
}

resource "aws_s3_bucket_notification" "this" {
  bucket = var.bucket_id
  lambda_function {
    lambda_function_arn = aws_lambda_function.this.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "uploads/"
  }
  depends_on = [aws_lambda_permission.s3]
}
```
with `variables.tf` declaring `service_name`, `runtime`, `bucket_arn`, `bucket_id`, `table_name`, `table_arn`, and `outputs.tf` exposing `function_name`, `dlq_url = aws_sqs_queue.dlq.url`, `log_group_name`.

```hcl
# infra/outputs.tf
output "bucket_name" { value = module.ingest_bucket.id }
output "table_name" { value = module.records_table.name }
output "function_name" { value = module.processor.function_name }
output "dlq_url" { value = module.processor.dlq_url }
```

```hcl
# infra/env/local.backend.hcl
bucket                      = "tfstate"
key                         = "{{cookiecutter.service_name}}/terraform.tfstate"
region                      = "{{cookiecutter.aws_region}}"
endpoints                   = { s3 = "http://localhost:4566" }
access_key                  = "test"
secret_key                  = "test"
use_lockfile                = true
skip_credentials_validation = true
skip_metadata_api_check     = true
skip_requesting_account_id  = true
skip_region_validation      = true
use_path_style              = true
```

```hcl
# infra/env/aws.backend.hcl
# Fill bucket with a real state bucket before first use.
# See docs/runbooks/first-aws-deploy.md. Never run against AWS by accident:
# this file has no endpoints block, so it targets the real service.
bucket       = "CHANGE-ME-terraform-state"
key          = "{{cookiecutter.service_name}}/terraform.tfstate"
region       = "{{cookiecutter.aws_region}}"
use_lockfile = true
```

```makefile
# template/{{cookiecutter.service_name}}/Makefile
SHELL := /usr/bin/env bash
ENDPOINT ?= http://localhost:4566
export AWS_ENDPOINT_URL := $(ENDPOINT)
export AWS_ACCESS_KEY_ID := test
export AWS_SECRET_ACCESS_KEY := test
export AWS_DEFAULT_REGION := {{cookiecutter.aws_region}}

.PHONY: init apply destroy test lint
init:
	terraform -chdir=infra init -input=false -backend-config=env/local.backend.hcl

apply: init
	terraform -chdir=infra apply -auto-approve -input=false -var=aws_endpoint_url=$(ENDPOINT)

destroy:
	terraform -chdir=infra destroy -auto-approve -input=false -var=aws_endpoint_url=$(ENDPOINT)

test:
	python -m pytest tests -v

lint:
	terraform -chdir=infra fmt -check
	terraform -chdir=infra validate
	tflint --chdir=infra --recursive
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
make up && make new
cd sandbox/orders-ingest && make apply && python -m pytest tests/test_contract.py -v
```
Expected: PASS, 5 passed. If `test_lambda_has_a_dead_letter_queue` fails, check `dead_letter_config` reached the function; LocalStack reports it on `get_function_configuration`.

- [ ] **Step 5: Record any LocalStack divergence**

If any assertion needed a workaround, append it to `docs/PARITY-NOTES.md` in the format expected / observed / worked around. Record anticipated risks that did **not** materialise too, in the same format with "no workaround needed"; a register that only lists failures overstates them.

- [ ] **Step 6: Commit**

```bash
git add template docs/PARITY-NOTES.md
git commit -m "feat: generated service provisions S3, DynamoDB, Lambda and a DLQ"
```

---

## Task 4: Handler and integration test

**Files:**
- Create: `template/{{cookiecutter.service_name}}/app/handler.py`, `app/requirements.txt`
- Create: `template/{{cookiecutter.service_name}}/tests/test_integration.py`

**Interfaces:**
- Consumes: Task 3's `tf_outputs` fixture and the `TABLE_NAME` environment variable
- Produces: a handler entry point `handle(event, context)`; a DynamoDB item shape `{record_id, source_key, byte_size, received_at}` that Task 5 and the drift fixture rely on.

- [ ] **Step 1: Write the failing test**

```python
# template/{{cookiecutter.service_name}}/tests/test_integration.py
import json, time, uuid, pytest

def _wait_for_item(dynamodb, table, record_id, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        got = dynamodb.get_item(TableName=table, Key={"record_id": {"S": record_id}})
        if "Item" in got:
            return got["Item"]
        time.sleep(1)
    raise AssertionError(f"no item {record_id} in {table} after {timeout}s")

def test_uploading_an_object_writes_a_record(s3, dynamodb, tf_outputs):
    record_id = str(uuid.uuid4())
    body = json.dumps({"record_id": record_id, "amount": 42}).encode()

    s3.put_object(Bucket=tf_outputs["bucket_name"], Key=f"uploads/{record_id}.json", Body=body)

    item = _wait_for_item(dynamodb, tf_outputs["table_name"], record_id)
    assert item["source_key"]["S"] == f"uploads/{record_id}.json"
    assert int(item["byte_size"]["N"]) == len(body)

def test_objects_outside_the_uploads_prefix_are_ignored(s3, dynamodb, tf_outputs):
    record_id = str(uuid.uuid4())
    s3.put_object(Bucket=tf_outputs["bucket_name"], Key=f"other/{record_id}.json",
                  Body=json.dumps({"record_id": record_id}).encode())
    time.sleep(5)
    got = dynamodb.get_item(TableName=tf_outputs["table_name"],
                            Key={"record_id": {"S": record_id}})
    assert "Item" not in got
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd sandbox/orders-ingest && python -m pytest tests/test_integration.py -v`
Expected: FAIL on `test_uploading_an_object_writes_a_record` with `AssertionError: no item ... after 30s`, because `app/handler.py` does not exist so the Lambda cannot process the event.

- [ ] **Step 3: Write the handler**

```python
# template/{{cookiecutter.service_name}}/app/handler.py
"""S3 ObjectCreated to DynamoDB. One record per uploaded object."""
import json, logging, os, sys, urllib.parse
from datetime import UTC, datetime

import boto3

logger = logging.getLogger("{{cookiecutter.service_name}}")
if not logger.handlers:
    h = logging.StreamHandler(sys.stdout)
    if os.environ.get("LOG_JSON", "true").lower() == "true":
        h.setFormatter(logging.Formatter('{"level":"%(levelname)s","event":"%(message)s"}'))
    logger.addHandler(h)
logger.setLevel(logging.INFO)

_dynamodb = boto3.client("dynamodb")
_s3 = boto3.client("s3")
TABLE_NAME = os.environ["TABLE_NAME"]


def handle(event, context):
    written = 0
    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key = urllib.parse.unquote_plus(record["s3"]["object"]["key"])

        body = _s3.get_object(Bucket=bucket, Key=key)["Body"].read()
        payload = json.loads(body)
        record_id = payload["record_id"]

        _dynamodb.put_item(
            TableName=TABLE_NAME,
            Item={
                "record_id": {"S": record_id},
                "source_key": {"S": key},
                "byte_size": {"N": str(len(body))},
                "received_at": {"S": datetime.now(UTC).isoformat()},
            },
        )
        logger.info(json.dumps({"msg": "record written", "record_id": record_id, "key": key}))
        written += 1
    return {"written": written}
```

`app/requirements.txt` is empty on purpose: boto3 is present in the Lambda runtime. Create the file with a single comment line explaining that, so nobody adds it later out of habit.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd sandbox/orders-ingest && make apply && python -m pytest tests -v`
Expected: PASS, 7 passed (5 contract + 2 integration).

- [ ] **Step 5: Commit**

```bash
git add template
git commit -m "feat: processor handler writes one record per uploaded object"
```

---

## Task 5: Alarms and the absence-of-signal test

**Files:**
- Create: `template/{{cookiecutter.service_name}}/infra/alarms.tf`
- Create: `template/{{cookiecutter.service_name}}/tests/test_alarms.py`
- Modify: `template/{{cookiecutter.service_name}}/infra/outputs.tf`

**Interfaces:**
- Consumes: Task 3's `module.processor.function_name` and `dlq_url`
- Produces: output `alarm_topic_arn`; alarm names `<service>-lambda-errors`, `<service>-dlq-not-empty`, `<service>-no-invocations`.

**Why this task exists:** the absence-of-signal alarm bug found in `aws-ecs-fargate-platform` was invisible because nothing tested it. CloudWatch's default `treat_missing_data` is `missing`, so an alarm on a metric that stops publishing during an outage goes to INSUFFICIENT_DATA rather than ALARM and never pages anyone. Verified on 2026-09-13 that LocalStack Community evaluates this correctly, so it is testable here for free.

- [ ] **Step 1: Write the failing test**

```python
# template/{{cookiecutter.service_name}}/tests/test_alarms.py
import pytest

def _alarm(cloudwatch, name):
    found = cloudwatch.describe_alarms(AlarmNames=[name])["MetricAlarms"]
    assert found, f"alarm {name} does not exist"
    return found[0]

def test_error_alarm_exists_and_notifies_the_topic(cloudwatch, tf_outputs):
    alarm = _alarm(cloudwatch, "{{cookiecutter.service_name}}-lambda-errors")
    assert alarm["MetricName"] == "Errors"
    assert tf_outputs["alarm_topic_arn"] in alarm["AlarmActions"]

def test_dlq_alarm_watches_visible_messages(cloudwatch, tf_outputs):
    alarm = _alarm(cloudwatch, "{{cookiecutter.service_name}}-dlq-not-empty")
    assert alarm["MetricName"] == "ApproximateNumberOfMessagesVisible"

# The point of the whole task. An alarm that cannot fire when its metric stops
# being published is decorative, and that is the CloudWatch default.
def test_absence_of_signal_alarm_fires_with_no_data(cloudwatch):
    alarm = _alarm(cloudwatch, "{{cookiecutter.service_name}}-no-invocations")
    assert alarm["TreatMissingData"] == "breaching"
    assert alarm["StateValue"] == "ALARM", (
        "alarm should already be in ALARM: no datapoints have been published "
        "and missing data is treated as breaching"
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd sandbox/orders-ingest && python -m pytest tests/test_alarms.py -v`
Expected: FAIL, 3 failed, each with `AssertionError: alarm <name> does not exist`.

- [ ] **Step 3: Write the alarms**

```hcl
# infra/alarms.tf
resource "aws_sns_topic" "alarms" {
  name = "${var.service_name}-alarms"
}

resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  alarm_name          = "${var.service_name}-lambda-errors"
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  statistic           = "Sum"
  period              = 60
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  alarm_actions       = [aws_sns_topic.alarms.arn]
  ok_actions          = [aws_sns_topic.alarms.arn]
  dimensions          = { FunctionName = module.processor.function_name }
  alarm_description   = "The processor is throwing errors."
}

resource "aws_cloudwatch_metric_alarm" "dlq_not_empty" {
  alarm_name          = "${var.service_name}-dlq-not-empty"
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  alarm_actions       = [aws_sns_topic.alarms.arn]
  dimensions          = { QueueName = "${var.service_name}-dlq" }
  alarm_description   = "Events failed processing and landed in the dead letter queue."
}

# Absence of signal. If the function stops being invoked at all, Invocations
# stops being published entirely. With the CloudWatch default of
# treat_missing_data = "missing" this alarm would sit in INSUFFICIENT_DATA
# during precisely the outage it exists to catch.
resource "aws_cloudwatch_metric_alarm" "no_invocations" {
  alarm_name          = "${var.service_name}-no-invocations"
  namespace           = "AWS/Lambda"
  metric_name         = "Invocations"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "LessThanThreshold"
  treat_missing_data  = "breaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]
  dimensions          = { FunctionName = module.processor.function_name }
  alarm_description   = "The processor has stopped being invoked."
}
```

Append to `infra/outputs.tf`:
```hcl
output "alarm_topic_arn" { value = aws_sns_topic.alarms.arn }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd sandbox/orders-ingest && make apply && python -m pytest tests/test_alarms.py -v`
Expected: PASS, 3 passed.

- [ ] **Step 5: Commit**

```bash
git add template
git commit -m "feat: alarms, including a tested absence-of-signal alarm"
```

---

## Task 6: Generated service CI

**Files:**
- Create: `template/{{cookiecutter.service_name}}/.github/workflows/ci.yml`
- Modify: `template/{{cookiecutter.service_name}}/Makefile` (add `up`, `down`, `ci`)
- Create: `template/{{cookiecutter.service_name}}/docker-compose.yml`

**Interfaces:**
- Consumes: Task 3's `make apply` / `destroy`, Task 4 and 5's tests
- Produces: the generated repository's `make ci` target, which Task 7 calls from the platform CI.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_template_generation.py
import yaml

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_template_generation.py -v`
Expected: FAIL, 3 failed with `FileNotFoundError` for the workflow and compose file.

- [ ] **Step 3: Write the CI and compose**

Copy `docker-compose.yml` from Task 1 into the template, changing `container_name` to `{{cookiecutter.service_name}}-localstack` and dropping the `ready.d` volume and healthcheck bucket (the generated service creates its own state bucket in `make up`).

```makefile
# append to template/{{cookiecutter.service_name}}/Makefile
.PHONY: up down ci
up:
	docker compose up -d --wait
	until aws --endpoint-url=$(ENDPOINT) s3api head-bucket --bucket tfstate 2>/dev/null; do \
		aws --endpoint-url=$(ENDPOINT) s3api create-bucket --bucket tfstate || sleep 2; \
	done

down:
	docker compose down -v

ci: lint up apply test destroy down
```

```yaml
# template/{{cookiecutter.service_name}}/.github/workflows/ci.yml
name: ci

on:
  pull_request:
  push:
    branches: [main]

concurrency:
  group: ci-${{ '{{' }} github.ref {{ '}}' }}
  cancel-in-progress: true

jobs:
  ci:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: hashicorp/setup-terraform@v4
        with:
          terraform_version: 1.14.8
      - uses: terraform-linters/setup-tflint@v6
      - uses: actions/setup-python@v6
        with:
          python-version: "3.12"
      - run: pip install boto3 pytest
      # Exactly what a developer runs locally. If this diverges from the
      # Makefile, the Makefile is wrong, not this file.
      - run: make ci
```

Note on the Jinja escaping: cookiecutter renders every templated file, so GitHub Actions `${{ ... }}` expressions must be escaped as `${{ '{{' }} ... {{ '}}' }}` inside the template, otherwise cookiecutter tries to resolve them as its own variables and fails. This is the single most common way this template breaks. Add it to `docs/PARITY-NOTES.md`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_template_generation.py -v && make new && grep -n 'github.ref' sandbox/orders-ingest/.github/workflows/ci.yml`
Expected: PASS on the tests, and the grep shows `${{ github.ref }}` correctly unescaped in the generated file.

- [ ] **Step 5: Commit**

```bash
git add template tests docs/PARITY-NOTES.md
git commit -m "feat: generated services ship their own CI calling make ci"
```

---

## Task 7: Platform self-test and `make demo`

**Files:**
- Modify: `Makefile`
- Create: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: Task 2's `make new`, Task 6's generated `make ci`
- Produces: `make demo`, the claim the whole repository rests on.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_template_generation.py
import subprocess

def test_make_demo_exists_and_excludes_the_portal():
    body = (REPO / "Makefile").read_text()
    assert "demo:" in body
    demo_line = [l for l in body.splitlines() if l.startswith("demo:")][0]
    assert "portal" not in demo_line, "portal needs Node and must not be in demo"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_template_generation.py::test_make_demo_exists_and_excludes_the_portal -v`
Expected: FAIL with `AssertionError` on `"demo:" in body`, because the target does not exist.

- [ ] **Step 3: Write the targets and CI**

```makefile
# append to Makefile
.PHONY: apply test destroy demo
apply: ## Provision the generated sandbox service against LocalStack
	$(MAKE) -C $(SANDBOX)/$(SERVICE) apply

test: ## Run the generated service's own tests
	$(MAKE) -C $(SANDBOX)/$(SERVICE) test

destroy:
	$(MAKE) -C $(SANDBOX)/$(SERVICE) destroy

# The claim this repository makes, executable. Generate a service from our own
# template, provision it, run the tests it shipped with, tear it down.
demo: up new apply test drift-demo destroy down ## Walk the entire golden path locally
```

```yaml
# .github/workflows/ci.yml
name: ci

on:
  pull_request:
  push:
    branches: [main]

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true

jobs:
  golden-path:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: hashicorp/setup-terraform@v4
        with:
          terraform_version: 1.14.8
      - uses: terraform-linters/setup-tflint@v6
      - uses: actions/setup-python@v6
        with:
          python-version: "3.12"
      - run: pip install -r requirements-dev.txt
      - run: python -m pytest tests -v
      - run: make demo
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests -v && make demo`
Expected: tests pass, then `make demo` runs to completion. `drift-demo` does not exist until Task 8; until then, temporarily run `make up new apply test destroy down` to confirm the chain, and add `drift-demo` to the `demo` line in Task 8.

- [ ] **Step 5: Commit**

```bash
git add Makefile .github/workflows/ci.yml tests
git commit -m "feat: the platform generates, provisions and tests its own template in CI"
```

---

## Task 8: Drift detection and the dashboard

**Files:**
- Create: `platform/registry.yaml`, `platform/drift_report.py`
- Create: `tests/test_drift_report.py`
- Modify: `Makefile`

**Interfaces:**
- Consumes: Task 2's `.cruft.json` in generated services
- Produces: `build_report(entries: list[ServiceStatus]) -> str`, `ServiceStatus(name: str, repo: str, template_sha: str, behind: bool, days_behind: int)`; the file `DRIFT.md`; `make drift-demo`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_drift_report.py
import pytest
from platform.drift_report import ServiceStatus, build_report

def test_report_lists_each_service_with_its_template_version():
    md = build_report([
        ServiceStatus("orders-ingest", "leomoncada/orders-ingest", "abc1234", False, 0),
    ])
    assert "orders-ingest" in md
    assert "abc1234" in md

def test_services_behind_the_template_are_marked():
    md = build_report([
        ServiceStatus("orders-ingest", "leomoncada/orders-ingest", "abc1234", True, 12),
    ])
    assert "behind" in md.lower()
    assert "12" in md

def test_report_states_the_mean_lag():
    md = build_report([
        ServiceStatus("a", "o/a", "sha1", True, 10),
        ServiceStatus("b", "o/b", "sha2", True, 20),
        ServiceStatus("c", "o/c", "sha3", False, 0),
    ])
    assert "10.0" in md, "mean lag over three services with 10, 20 and 0 days is 10.0"

def test_empty_registry_produces_a_report_rather_than_crashing():
    md = build_report([])
    assert "No services" in md
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_drift_report.py -v`
Expected: FAIL, 4 errors with `ModuleNotFoundError: No module named 'platform.drift_report'`.

Note: `platform` shadows a Python standard library module name. Name the package directory `platform/` on disk as the spec says, but import it via a path insert in the test, or rename to `platformops/`. **Decision: rename to `platformops/`** to avoid a subtle stdlib shadowing bug. Update the spec's layout section accordingly when the repo is created.

- [ ] **Step 3: Write the report builder**

```python
# platformops/drift_report.py
"""Builds DRIFT.md from cruft check results.

The number this produces is the platform team's product metric. Without it,
"we have a golden path" is unfalsifiable.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class ServiceStatus:
    name: str
    repo: str
    template_sha: str
    behind: bool
    days_behind: int


def build_report(entries: list[ServiceStatus]) -> str:
    if not entries:
        return "# Template drift\n\nNo services are registered yet.\n"

    behind = [e for e in entries if e.behind]
    mean_lag = sum(e.days_behind for e in entries) / len(entries)

    lines = [
        "# Template drift",
        "",
        f"{len(entries)} service(s) registered, {len(behind)} behind the current template.",
        f"Mean lag: {mean_lag:.1f} days.",
        "",
        "| Service | Repository | Template | Status | Days behind |",
        "|---|---|---|---|---|",
    ]
    for e in sorted(entries, key=lambda x: (-x.days_behind, x.name)):
        status = "behind" if e.behind else "current"
        lines.append(
            f"| {e.name} | `{e.repo}` | `{e.template_sha}` | {status} | {e.days_behind} |"
        )
    lines.append("")
    return "\n".join(lines)
```

```yaml
# platformops/registry.yaml
# Services generated from this template. In a real organisation this would be
# the Backstage catalog; here it is a file, and the README says so.
services:
  - name: orders-ingest
    repo: leomoncada/aws-serverless-golden-path
    path: examples/orders-ingest
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_drift_report.py -v`
Expected: PASS, 4 passed.

- [ ] **Step 5: Add the drift demo target**

```makefile
# append to Makefile
.PHONY: drift-demo
drift-demo: ## Move the template, then show cruft detecting and updating the sandbox
	@echo "--> template HEAD: $$(git rev-parse --short HEAD)"
	@echo "--> checking $(SANDBOX)/$(SERVICE) against it"
	cd $(SANDBOX)/$(SERVICE) && cruft check || \
		( echo "--> service is behind, updating"; cruft update --skip-apply-ask --allow-untracked-files )
```

Then change the `demo` line from Task 7 to include it:
```makefile
demo: up new apply test drift-demo destroy down
```

- [ ] **Step 6: Commit**

```bash
git add platformops tests/test_drift_report.py Makefile
git commit -m "feat: drift report and local drift demo"
```

---

## Task 9: Scheduled drift workflow

**Files:**
- Create: `.github/workflows/drift.yml`, `platformops/check_drift.py`
- Create: `tests/test_check_drift.py`

**Interfaces:**
- Consumes: Task 8's `ServiceStatus` and `build_report`
- Produces: `collect(registry_path: str, repo_root: str) -> list[ServiceStatus]`; writes `DRIFT.md`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_check_drift.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_check_drift.py -v`
Expected: FAIL, 2 errors with `ModuleNotFoundError: No module named 'platformops.check_drift'`.

- [ ] **Step 3: Write the collector and workflow**

```python
# platformops/check_drift.py
"""Reads the registry, asks cruft where each service stands, builds the report."""
import json
import pathlib
import subprocess
from datetime import UTC, datetime

import yaml

from .drift_report import ServiceStatus, build_report


def _template_head(repo_root: str) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo_root,
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def _commit_date(repo_root: str, sha: str) -> datetime | None:
    result = subprocess.run(
        ["git", "show", "-s", "--format=%cI", sha], cwd=repo_root,
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return None
    return datetime.fromisoformat(result.stdout.strip())


def collect(registry_path: str, repo_root: str) -> list[ServiceStatus]:
    registry = yaml.safe_load(pathlib.Path(registry_path).read_text()) or {}
    head = None
    statuses: list[ServiceStatus] = []

    for entry in registry.get("services", []):
        cruft_file = pathlib.Path(repo_root) / entry["path"] / ".cruft.json"
        if not cruft_file.is_file():
            continue

        recorded = json.loads(cruft_file.read_text())["commit"]
        if head is None:
            head = _template_head(repo_root)

        behind = not head.startswith(recorded) and not recorded.startswith(head)
        days = 0
        if behind:
            then = _commit_date(repo_root, recorded)
            if then is not None:
                days = (datetime.now(UTC) - then).days

        statuses.append(ServiceStatus(
            name=entry["name"], repo=entry["repo"],
            template_sha=recorded[:7], behind=behind, days_behind=days,
        ))
    return statuses


def main() -> None:
    root = str(pathlib.Path(__file__).resolve().parents[1])
    statuses = collect(f"{root}/platformops/registry.yaml", root)
    pathlib.Path(f"{root}/DRIFT.md").write_text(build_report(statuses))


if __name__ == "__main__":
    main()
```

```yaml
# .github/workflows/drift.yml
name: drift

on:
  schedule:
    - cron: "0 6 * * 1"
  workflow_dispatch:

permissions:
  contents: write
  pull-requests: write

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
        with:
          fetch-depth: 0
      - uses: actions/setup-python@v6
        with:
          python-version: "3.12"
      - run: pip install -r requirements-dev.txt

      - name: Refresh the drift dashboard
        run: python -m platformops.check_drift

      - name: Update registered services that are behind
        run: |
          set -euo pipefail
          python - <<'PY' > behind.txt
          import pathlib, sys
          sys.path.insert(0, ".")
          from platformops.check_drift import collect
          root = str(pathlib.Path.cwd())
          for s in collect(f"{root}/platformops/registry.yaml", root):
              if s.behind:
                  print(s.name)
          PY
          while read -r name; do
            [ -z "$name" ] && continue
            path=$(python -c "import yaml,sys;print(next(s['path'] for s in yaml.safe_load(open('platformops/registry.yaml'))['services'] if s['name']=='$name'))")
            ( cd "$path" && cruft update --skip-apply-ask --allow-untracked-files )
          done < behind.txt

      - name: Open a pull request with the updates
        uses: peter-evans/create-pull-request@v7
        with:
          branch: drift/template-update
          title: "chore: bring registered services up to the current template"
          body: |
            Opened automatically by the drift workflow.

            `cruft update` performs a three way merge. Review the diff: on a
            service that has diverged from the template this can conflict, and
            occasionally resolves badly. See docs/adr/0004-drift-strategy.md
            for what this mechanism cannot do.
          commit-message: "chore: cruft update registered services"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_check_drift.py -v && python -m platformops.check_drift && cat DRIFT.md`
Expected: PASS, 2 passed, and `DRIFT.md` is written with a table.

- [ ] **Step 5: Commit**

```bash
git add platformops .github/workflows/drift.yml tests/test_check_drift.py DRIFT.md
git commit -m "feat: scheduled drift check opens update pull requests"
```

---

## Task 10: Backstage adapter

**Files:**
- Create: `backstage/template.yaml`
- Create: `tests/test_backstage_template.py`
- Modify: `Makefile` (add `portal`)

**Interfaces:**
- Consumes: Task 2's cookiecutter variables, which the template's parameter schema must mirror exactly
- Produces: `backstage/template.yaml`, validated against the scaffolder schema in CI.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_backstage_template.py
import json, pathlib, yaml, pytest

REPO = pathlib.Path(__file__).resolve().parents[1]

@pytest.fixture
def template():
    return yaml.safe_load((REPO / "backstage/template.yaml").read_text())

def test_is_a_scaffolder_template(template):
    assert template["kind"] == "Template"
    assert template["apiVersion"].startswith("scaffolder.backstage.io/")

def test_uses_the_cookiecutter_fetch_action(template):
    actions = [s["action"] for s in template["spec"]["steps"]]
    assert "fetch:cookiecutter" in actions
    assert "publish:github" in actions
    assert "catalog:register" in actions

# If these drift apart, the portal collects answers the template ignores.
def test_parameters_match_cookiecutter_variables(template):
    declared = set(json.loads((REPO / "template/cookiecutter.json").read_text()))
    exposed = set()
    for section in template["spec"]["parameters"]:
        exposed |= set(section.get("properties", {}))
    assert exposed == declared, f"missing {declared - exposed}, extra {exposed - declared}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_backstage_template.py -v`
Expected: FAIL, 3 errors with `FileNotFoundError` for `backstage/template.yaml`.

- [ ] **Step 3: Write the adapter**

```yaml
# backstage/template.yaml
apiVersion: scaffolder.backstage.io/v1beta3
kind: Template
metadata:
  name: aws-serverless-service
  title: AWS serverless service
  description: >
    A Lambda, S3, DynamoDB and SQS service that provisions and tests itself
    against LocalStack, with runbooks, alarms and CI already wired.
  tags: [aws, serverless, terraform, golden-path]
spec:
  owner: platform
  type: service

  parameters:
    - title: Service
      required: [service_name, owner_team, description]
      properties:
        service_name:
          type: string
          title: Name
          pattern: "^[a-z][a-z0-9-]{2,40}$"
          description: Lowercase, hyphens allowed.
        owner_team:
          type: string
          title: Owning team
        description:
          type: string
          title: What does it do
    - title: Runtime
      required: [python_runtime, aws_region]
      properties:
        python_runtime:
          type: string
          default: python3.12
          enum: [python3.12, python3.13]
        aws_region:
          type: string
          default: us-east-1

  steps:
    # Requires @backstage/plugin-scaffolder-backend-module-cookiecutter in the
    # backend, plus cookiecutter on PATH or a Docker daemon. That cost is
    # accepted deliberately; see docs/adr/0002-cookiecutter-over-fetch-template.md
    - id: fetch
      name: Generate from the golden path template
      action: fetch:cookiecutter
      input:
        url: https://github.com/leomoncada/aws-serverless-golden-path/tree/main/template
        values:
          service_name: ${{ parameters.service_name }}
          owner_team: ${{ parameters.owner_team }}
          description: ${{ parameters.description }}
          python_runtime: ${{ parameters.python_runtime }}
          aws_region: ${{ parameters.aws_region }}

    - id: publish
      name: Create the repository
      action: publish:github
      input:
        repoUrl: github.com?owner=leomoncada&repo=${{ parameters.service_name }}
        description: ${{ parameters.description }}

    - id: register
      name: Register in the catalog
      action: catalog:register
      input:
        repoContentsUrl: ${{ steps.publish.output.repoContentsUrl }}
        catalogInfoPath: /catalog-info.yaml

  output:
    links:
      - title: Repository
        url: ${{ steps.publish.output.remoteUrl }}
```

```makefile
# append to Makefile
.PHONY: portal
portal: ## Run Backstage locally with this template loaded (needs Node; not part of demo)
	@echo "See docs/running-backstage-locally.md"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_backstage_template.py -v`
Expected: PASS, 3 passed. If `test_parameters_match_cookiecutter_variables` fails, the two files have drifted; that is the test doing its job.

- [ ] **Step 5: Commit**

```bash
git add backstage tests/test_backstage_template.py Makefile
git commit -m "feat: Backstage adapter, with parameters tested against cookiecutter.json"
```

---

## Task 11: The AWS path artifacts

**Files:**
- Create: `template/{{cookiecutter.service_name}}/.github/workflows/deploy-aws.yml`
- Create: `template/{{cookiecutter.service_name}}/docs/runbooks/first-aws-deploy.md`
- Modify: `template/{{cookiecutter.service_name}}/Makefile` (add `apply-aws`)
- Create: `tests/test_aws_path.py`

**Interfaces:**
- Consumes: Task 3's `aws_endpoint_url` variable and `env/aws.backend.hcl`
- Produces: `make apply-aws`; a `workflow_dispatch` deploy workflow. Neither is ever executed.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_aws_path.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_aws_path.py -v`
Expected: FAIL, 3 failed with `FileNotFoundError` (the first test passes already, which is correct: nothing conditional has been written).

- [ ] **Step 3: Write the AWS path**

```makefile
# append to template/{{cookiecutter.service_name}}/Makefile
.PHONY: apply-aws
apply-aws: ## Provision against a real AWS account. Never run by CI. Costs money.
	@echo "This targets real AWS. Read docs/runbooks/first-aws-deploy.md first."
	terraform -chdir=infra init -input=false -backend-config=env/aws.backend.hcl
	terraform -chdir=infra apply -input=false
```

```yaml
# template/{{cookiecutter.service_name}}/.github/workflows/deploy-aws.yml
# Manual only, and never executed in this repository. It exists so the path to
# AWS is code rather than a promise. See docs/runbooks/first-aws-deploy.md.
name: deploy-aws

on:
  workflow_dispatch:
    inputs:
      confirm:
        description: Type the service name to confirm a real AWS deploy
        required: true

permissions:
  id-token: write
  contents: read

jobs:
  deploy:
    if: ${{ '{{' }} github.event.inputs.confirm == '{{cookiecutter.service_name}}' {{ '}}' }}
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v6
      - uses: hashicorp/setup-terraform@v4
        with:
          terraform_version: 1.14.8
      - uses: aws-actions/configure-aws-credentials@v6
        with:
          role-to-assume: ${{ '{{' }} secrets.AWS_DEPLOY_ROLE_ARN {{ '}}' }}
          aws-region: {{cookiecutter.aws_region}}
      - run: make apply-aws
```

```markdown
<!-- template/{{cookiecutter.service_name}}/docs/runbooks/first-aws-deploy.md -->
# Runbook: first deploy to real AWS

**Status: this path has not been exercised.** The Terraform is the same code
that runs against LocalStack on every pull request, and the workflow below is
syntactically valid, but neither has ever been run against a real account. Treat
this runbook as a tested design, not a tested procedure.

## Before you start

Estimated cost of following this runbook end to end and tearing down the same
day: under 1 USD. S3, DynamoDB on demand, Lambda and SQS at demo volume all sit
inside or near the always free tier. There is no NAT gateway, no load balancer
and no cluster in this architecture, which is where serverless demos usually
leak money.

## Steps

1. **Bootstrap state.** Create an S3 bucket for Terraform state with versioning
   enabled. Put its name in `infra/env/aws.backend.hcl`, replacing
   `CHANGE-ME-terraform-state`. Locking uses `use_lockfile`, so no DynamoDB
   table is needed.
2. **Create the OIDC provider and role.** Add
   `token.actions.githubusercontent.com` as an IAM OIDC provider. Create a role
   whose trust policy conditions `sub` on
   `repo:<owner>/{{cookiecutter.service_name}}:environment:production`, and
   attach a policy allowing only the resources in `infra/`.
3. **Set the secret.** Repository secret `AWS_DEPLOY_ROLE_ARN`.
4. **Deploy into a throwaway environment.** `make apply-aws`.

## What to verify, because local never proved it

- **IAM sufficiency.** LocalStack Community does not enforce IAM. This is the
  first time the least-privilege policy is actually tested. Expect
  `AccessDenied` and fix forward.
- **Cold start and concurrency.** Behaviour differs from LocalStack.
- **Alarm delivery.** Local verifies alarms reach SNS. Subscribe an address and
  confirm the message arrives.
- **Service quotas.** They do not exist locally.

## Tear down

`terraform -chdir=infra destroy`, then empty and delete the state bucket. Confirm
in Cost Explorer the next day that nothing is still billing.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_aws_path.py -v`
Expected: PASS, 4 passed.

- [ ] **Step 5: Commit**

```bash
git add template tests/test_aws_path.py
git commit -m "feat: AWS deploy path, coded and documented but never executed"
```

---

## Task 12: ADRs, README and the committed example

**Files:**
- Create: `docs/adr/0001-serverless-over-ecs.md` through `0005-localstack-not-aws.md`
- Create: `examples/orders-ingest/` (a committed generated service)
- Modify: `README.md`, `platformops/registry.yaml`
- Create: `tests/test_docs.py`

**Interfaces:**
- Consumes: everything
- Produces: the drift fixture that Task 9's workflow operates on.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_docs.py
import pathlib, re, pytest

REPO = pathlib.Path(__file__).resolve().parents[1]

def test_all_five_adrs_exist():
    adrs = sorted((REPO / "docs/adr").glob("0*.md"))
    assert len(adrs) == 5, f"found {[a.name for a in adrs]}"

def test_no_em_dashes_in_committed_prose():
    offenders = []
    for md in REPO.rglob("*.md"):
        if any(part in md.parts for part in ("sandbox", ".venv", "node_modules")):
            continue
        if "\u2014" in md.read_text():
            offenders.append(str(md.relative_to(REPO)))
    assert not offenders, f"em dashes found in {offenders}"

def test_readme_states_the_aws_path_is_unexercised():
    body = (REPO / "README.md").read_text().lower()
    assert "not been exercised" in body or "unexercised" in body

def test_the_example_service_is_committed_and_registered():
    assert (REPO / "examples/orders-ingest/.cruft.json").is_file()
    registry = (REPO / "platformops/registry.yaml").read_text()
    assert "examples/orders-ingest" in registry
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_docs.py -v`
Expected: FAIL, 4 failed. `test_all_five_adrs_exist` finds 0, the README assertion fails, and `examples/` does not exist.

- [ ] **Step 3: Write the docs and generate the example**

Write five ADRs, each following the same short structure (Context, Decision, Consequences, and for 2 and 4 an explicit "What this does not solve"):

- `0001-serverless-over-ecs.md`: the paved road is serverless because ECS and ALB are absent from LocalStack Community, so an ECS golden path could not verify itself without a funded account. Names what is lost: the ECS repo is the more production-shaped artefact.
- `0002-cookiecutter-over-fetch-template.md`: the comparison table from the spec. States the accepted cost, that `fetch:cookiecutter` needs an extra backend module plus cookiecutter on PATH or Docker.
- `0003-backstage-not-hosted.md`: Backstage is a front door, not the product. Hosting needs Postgres and a Node process, which costs money for no portfolio gain. Local run plus recording instead.
- `0004-drift-strategy.md`: cruft three way merge. **What this does not solve:** heavily diverged services conflict and can resolve badly; Terraform resource renames need `moved` blocks or state surgery and cannot be automated; the registry is a file, not a catalog.
- `0005-localstack-not-aws.md`: why the verification loop targets LocalStack, and the full list of what that does not prove, copied from spec section 12b.

Generate and commit the example:
```bash
make up
SERVICE=orders-ingest SANDBOX=examples make new
git add examples
```

Write `README.md` leading with evidence: one sentence thesis, `make demo` plus an asciinema recording, the drift dashboard with a link to a real update pull request, then "what is tested and what is not", then architecture last.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests -v`
Expected: PASS, whole suite green.

- [ ] **Step 5: Run the full demo one final time from a clean clone**

```bash
cd $(mktemp -d) && git clone <repo> gp && cd gp
pip install -r requirements-dev.txt
make demo
```
Expected: completes without manual intervention. This is success criterion 1 and it is the only one a reviewer will actually try.

- [ ] **Step 6: Commit**

```bash
git add docs examples README.md platformops/registry.yaml tests/test_docs.py
git commit -m "docs: ADRs, README and the committed example service"
```

---

## Self-Review

**Spec coverage.** Section 1 purpose maps to Tasks 7 and 12. Section 3 generated service contents to Tasks 3, 4, 5, 6. Section 4 cookiecutter and cruft to Tasks 2 and 8. Section 5 Backstage adapter to Task 10. Section 6 drift to Tasks 8 and 9. Section 7 local experience to Tasks 1, 7, 8. Section 8 CI to Tasks 6 and 7. Section 9 layout to the File Structure block, with one correction: `platform/` is renamed `platformops/` because `platform` shadows a Python standard library module. Section 10 ADRs to Task 12. Section 11 README structure to Task 12. Section 12 success criteria: 1 to Task 12 step 5, 2 to Task 7, 3 and 4 to Tasks 9 and 12, 5 to Task 8, 6 to Task 12, 7 to Task 10, 8 and 9 to Task 11. Section 12b AWS path to Task 11. Section 14 risks: the cruft limit is ADR 0004, LocalStack parity is recorded in Task 3 step 5 and Task 6 step 3, the Backstage limit is Task 10.

**Placeholder scan.** No TBDs. Every code step carries real code. `CHANGE-ME-terraform-state` in `aws.backend.hcl` is a deliberate sentinel that the first-deploy runbook tells the operator to replace, not a plan placeholder.

**Type consistency.** `ServiceStatus(name, repo, template_sha, behind, days_behind)` is defined in Task 8 and consumed unchanged in Task 9 and its tests. `build_report(entries)` and `collect(registry_path, repo_root)` signatures match their call sites. Terraform outputs `bucket_name`, `table_name`, `function_name`, `dlq_url` (Task 3) and `alarm_topic_arn` (Task 5) match every `tf_outputs[...]` lookup in Tasks 3, 4 and 5. The cookiecutter variables in Task 2's `cookiecutter.json` match Task 10's parameter test exactly.

**One correction folded in:** Task 2 notes that cruft needs `--directory template` on every invocation, and that flag is used consistently in Tasks 2, 8 and the Makefile.
