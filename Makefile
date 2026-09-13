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

.PHONY: apply test destroy demo drift-demo
apply: ## Provision the generated sandbox service against LocalStack
	$(MAKE) -C $(SANDBOX)/$(SERVICE) apply

test: ## Run the generated service's own tests
	$(MAKE) -C $(SANDBOX)/$(SERVICE) test

destroy: ## Tear down the generated sandbox service's infrastructure
	$(MAKE) -C $(SANDBOX)/$(SERVICE) destroy

drift-demo: ## Move the template, then show cruft detecting and updating the sandbox
	@echo "--> template HEAD: $$(git rev-parse --short HEAD)"
	@echo "--> checking $(SANDBOX)/$(SERVICE) against it"
	cd $(SANDBOX)/$(SERVICE) && cruft check || \
		( echo "--> service is behind, updating"; cruft update --skip-apply-ask --allow-untracked-files )

# The claim this repository makes, executable. Generate a service from our own
# template, provision it, run the tests it shipped with, tear it down.
#
# destroy and down always run, even if an earlier step (new, apply, or test)
# fails, so a failed run never leaves infrastructure applied or LocalStack
# running for the next `make demo`; this target still exits non-zero when a
# step failed.
demo: ## Walk the entire golden path locally
	@set +e; \
	$(MAKE) up new apply test drift-demo; \
	rc=$$?; \
	$(MAKE) destroy; \
	$(MAKE) down; \
	exit $$rc
