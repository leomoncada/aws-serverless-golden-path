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
# So: bring LocalStack up, initialise, then lint, then the rest. `apply`
# still declares `init` as its own prerequisite (harmless: terraform init is
# idempotent), so this does not skip any existing target's contract.
ci: up init lint apply test destroy down
