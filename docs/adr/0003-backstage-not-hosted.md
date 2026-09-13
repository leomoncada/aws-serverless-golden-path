# 0003: Backstage is not hosted

## Context

`backstage/template.yaml` is a thin adapter (roughly 40 lines: `fetch:cookiecutter`,
`publish:github`, `catalog:register`) that lets a Backstage instance drive the
same cookiecutter template this repository verifies on its own. Running a
real Backstage instance needs a Postgres database and a long-lived Node
process. Hosting that continuously costs money, which the budget constraint
in `docs/DESIGN.md` rules out, for a component that is a front door onto the
golden path, not the golden path itself.

## Decision

Backstage is not hosted anywhere. The adapter is validated against the
scaffolder's own JSON schema in CI (`tests/test_backstage_template.py`),
which also checks that its declared parameters match
`template/cookiecutter.json` exactly. Anyone who wants to confirm the adapter
against a real Backstage instance runs it locally, following
`docs/running-backstage-locally.md`.

## Consequences

- No recurring hosting cost, and no Node/Postgres dependency for the rest of
  the repository. `make demo` never depends on Backstage; `make portal` is a
  stub that points at the local-run instructions.
- Schema validation is weaker than execution. It catches a structural
  mismatch (wrong action name, parameters that do not match the cookiecutter
  variables) but it cannot catch a `fetch:cookiecutter` run that fails
  because cookiecutter is not installed, a `publish:github` step that fails
  without a GitHub token, or a subtly wrong Jinja or Nunjucks expression.
  The Backstage adapter has never been executed in this repository; only its
  schema has been checked. The README states this plainly rather than
  implying the adapter is fully tested.
- If Backstage falls out of favor as a tool, the paved road underneath is
  unaffected: the template, the drift mechanism and the verification loop
  are all plain CLI and work with no portal at all.

## What this does not solve

- It does not prove the adapter's Jinja/Nunjucks templating renders
  correctly inside a real scaffolder run, or that `publish:github` and
  `catalog:register` behave as the adapter assumes.
- It does not exercise the operator experience of filling in the form and
  watching the scaffold happen; that is only described, in
  `docs/running-backstage-locally.md`, as untested steps for a future run.
