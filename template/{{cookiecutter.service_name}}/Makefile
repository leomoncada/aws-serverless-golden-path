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
