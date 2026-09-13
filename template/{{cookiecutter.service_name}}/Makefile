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
	terraform -chdir=infra fmt -check -recursive
	terraform -chdir=infra validate
	tflint --chdir=infra --recursive

.PHONY: up down ci
up:
	docker compose up -d --wait
	until aws --endpoint-url=$(ENDPOINT) s3api head-bucket --bucket tfstate 2>/dev/null; do \
		aws --endpoint-url=$(ENDPOINT) s3api create-bucket --bucket tfstate || sleep 2; \
	done

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

.PHONY: apply-aws
apply-aws: ## Provision against a real AWS account. Never run by CI. Costs money.
	@echo "This targets real AWS. Read docs/runbooks/first-aws-deploy.md first."
	terraform -chdir=infra init -input=false -backend-config=env/aws.backend.hcl
	terraform -chdir=infra apply -input=false
