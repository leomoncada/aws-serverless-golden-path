SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help

.PHONY: help up down
help:
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*##/\t/'

up: ## Start LocalStack and wait until the tfstate bucket exists
	docker compose up -d --wait

down: ## Stop LocalStack and remove its volumes
	docker compose down -v

SANDBOX ?= sandbox
SERVICE ?= orders-ingest

.PHONY: new
new: ## Generate a service from the template into $(SANDBOX)/$(SERVICE)
	rm -rf $(SANDBOX)/$(SERVICE)
	mkdir -p $(SANDBOX)
	cruft create . --directory template --no-input --output-dir $(SANDBOX) \
		--extra-context '{"service_name": "$(SERVICE)"}'

.PHONY: apply test destroy demo
apply: ## Provision the generated sandbox service against LocalStack
	$(MAKE) -C $(SANDBOX)/$(SERVICE) apply

test: ## Run the generated service's own tests
	$(MAKE) -C $(SANDBOX)/$(SERVICE) test

destroy: ## Tear down the generated sandbox service's infrastructure
	$(MAKE) -C $(SANDBOX)/$(SERVICE) destroy

# The claim this repository makes, executable. Generate a service from our own
# template, provision it, run the tests it shipped with, tear it down.
#
# destroy and down always run, even if an earlier step (new, apply, or test)
# fails, so a failed run never leaves infrastructure applied or LocalStack
# running for the next `make demo`; this target still exits non-zero when a
# step failed. Task 8 inserts drift-demo into the build-steps line below,
# right after test, the same way it is inserted into the generated ci target.
demo: ## Walk the entire golden path locally
	@set +e; \
	$(MAKE) up new apply test; \
	rc=$$?; \
	$(MAKE) destroy; \
	$(MAKE) down; \
	exit $$rc
