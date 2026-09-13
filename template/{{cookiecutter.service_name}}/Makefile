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

# Two sessions, deliberately, and the order matters.
#
# tests/test_alarms.py asserts the no-invocations alarm is in ALARM, which is
# only true while nothing has invoked the function inside the alarm's five
# minute window. tests/test_integration.py invokes it. Alphabetical
# collection happens to put alarms first today, which is luck, not a
# guarantee: a new tests/test_a*.py, pytest-randomly, or `pytest -k` in a
# different order all break it, and the alarm assertion is the one this
# service's observability claim rests on. So it runs first, on its own, here
# where the order is visible, and it fails rather than skips if the window is
# not empty.
test:
	python -m pytest tests/test_alarms.py -v
	python -m pytest tests -v --ignore=tests/test_alarms.py

lint:
	terraform -chdir=infra fmt -check -recursive
	terraform -chdir=infra validate
	tflint --chdir=infra --recursive

.PHONY: up down ci
# One command, and nothing to install beyond Docker. The tfstate bucket is
# created by localstack/init/ready.d/01-tfstate-bucket.sh inside the
# container, and docker-compose.yml's healthcheck is a head-bucket on it, so
# `--wait` returns only once the bucket exists and gives up after a bounded
# number of retries. This used to be an `until aws s3api head-bucket` loop
# here, which needed the AWS CLI (undeclared in the README, absent on plenty
# of laptops) and never gave up: without the CLI it hung silently forever.
up:
	docker compose up -d --wait

down:
	docker compose down -v

# LocalStack must be reachable before `terraform init` can configure the S3
# backend (it dials the tfstate bucket at apply-time init), and `lint`'s
# `terraform validate` / `tflint` both need an initialised working directory.
# So: bring LocalStack up, initialise, then lint, then the rest.
#
# `destroy` and `down` always run, even if an earlier step (lint, apply, or
# test) fails, so a failed run never leaves infrastructure applied or
# LocalStack running for the next invocation; `ci` still exits non-zero when
# a step failed. `up init lint apply test` is one `make` invocation, so
# `init` (an explicit goal and also `apply`'s prerequisite) still runs once.
ci:
	@set +e; \
	$(MAKE) up init lint apply test; \
	rc=$$?; \
	$(MAKE) destroy; \
	$(MAKE) down; \
	exit $$rc

# apply-aws is the human-facing entry point: run it from your own terminal,
# where Terraform can prompt and a person types "yes" before anything real
# changes. It deliberately has no -auto-approve and no -input=false on the
# apply step, so it needs a TTY and cannot be called this way from CI; see
# deploy-aws.yml for the non-interactive path, which plans and applies a
# saved plan file instead of skipping approval outright.
.PHONY: apply-aws
apply-aws: ## Provision against a real AWS account. Interactive; never run by CI. Costs money.
	@echo "This targets real AWS. Read docs/runbooks/first-aws-deploy.md first."
	terraform -chdir=infra init -input=false -backend-config=env/aws.backend.hcl
	terraform -chdir=infra apply
