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

DRIFT_DIR ?= sandbox/.drift-demo

# Generates its own service, in its own directory, deliberately pinned to the
# oldest commit that ever touched template/ rather than to HEAD, so every run
# starts genuinely behind. This is separate from $(SANDBOX)/$(SERVICE) (which
# `new`/`apply`/`test` keep at HEAD) precisely because the two want the
# generated service in different states: current for apply/test, stale for
# this demo.
#
# The generated copy gets its own throwaway git repo (git init + one commit)
# rather than living as an untracked directory inside this repo's working
# tree. cruft resolves the nearest .git upward when asked to check or update,
# and `cruft update` refuses to run against a dirty tree; without its own
# repo it would find *this* repo's .git and (a) refuse to run any time this
# working tree has any unrelated uncommitted change, and (b) risk staging
# files under $(DRIFT_DIR) into this repo's index. Giving it its own repo
# makes the demo self-contained and deterministic regardless of what else is
# going on in this working tree.
#
# A no-op here (cruft reporting the fresh copy already clean) would be a
# silent false pass on the repository's whole differentiating claim, so each
# step below fails loudly instead of falling through quietly.
drift-demo: ## Generate a service pinned to an old template commit, then show cruft detect and fix the drift
	@set -e; \
	rm -rf $(DRIFT_DIR); \
	mkdir -p $(DRIFT_DIR); \
	HEAD_SHA=$$(git rev-parse HEAD); \
	HEAD_SHORT=$$(git rev-parse --short HEAD); \
	OLD_SHA=$$(git log --format=%H -- template | tail -1); \
	OLD_SHORT=$$(git rev-parse --short $$OLD_SHA); \
	if [ "$$OLD_SHA" = "$$HEAD_SHA" ]; then \
		echo "--> ERROR: cannot demonstrate drift: the template has only ever existed at HEAD ($$HEAD_SHORT); there is no earlier commit to pin the demo service to" >&2; \
		exit 1; \
	fi; \
	echo "--> template HEAD is $$HEAD_SHORT; generating $(SERVICE) into $(DRIFT_DIR) pinned to the older template commit $$OLD_SHORT so it starts out behind"; \
	cruft create . --directory template --no-input --checkout $$OLD_SHA \
		--output-dir $(DRIFT_DIR) --extra-context '{"service_name": "$(SERVICE)"}'; \
	cd $(DRIFT_DIR)/$(SERVICE); \
	git init -q; \
	git -c user.email=drift-demo@example.invalid -c user.name=drift-demo add -A; \
	git -c user.email=drift-demo@example.invalid -c user.name=drift-demo commit -q -m "snapshot pinned to $$OLD_SHORT for drift-demo"; \
	echo "--> checking: $(SERVICE) was generated from $$OLD_SHORT, current template HEAD is $$HEAD_SHORT"; \
	if cruft check; then \
		echo "--> ERROR: expected $(SERVICE) to be reported behind ($$OLD_SHORT vs $$HEAD_SHORT) but cruft reports it clean; drift-demo could not create drift on this run" >&2; \
		exit 1; \
	fi; \
	echo "--> confirmed behind: $(SERVICE) is pinned to $$OLD_SHORT while the template is at $$HEAD_SHORT; running cruft update"; \
	cruft update --skip-apply-ask --allow-untracked-files; \
	NEW_FULL=$$(grep -m1 '"commit"' .cruft.json | sed -E 's/.*"commit": *"([^"]+)".*/\1/'); \
	echo "--> .cruft.json now records $${NEW_FULL:0:7}"; \
	if cruft check; then \
		echo "--> confirmed current: $(SERVICE) now matches template HEAD $$HEAD_SHORT"; \
	else \
		echo "--> ERROR: ran cruft update but $(SERVICE) is still reported behind" >&2; \
		exit 1; \
	fi

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
