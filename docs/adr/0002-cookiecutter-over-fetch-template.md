# 0002: cookiecutter and cruft rather than Backstage's native fetch:template

## Context

Backstage ships a built-in scaffolder action, `fetch:template`, that needs no
extra plugin and no Docker daemon. It is the lower-friction choice inside
Backstage.

The differentiating feature of this repository is not scaffolding a new
repository; many "Backstage template" repositories do that. It is answering
the drift question: when the template changes, already-generated services
are updated by an automated pull request, and the lag is measured. That
requires a tool that can compute a three-way merge between the template
version a service was generated from and the template's current state, and
apply it while preserving local edits. `fetch:template` has no equivalent;
building one by hand would be re-implementing `cruft`, worse, for a
demonstration project.

`cookiecutter` is a plain directory tree with `{{cookiecutter.variable}}`
placeholders, driven from the CLI. `cruft` builds on it: a project generated
with cruft records the template commit it came from in `.cruft.json`, and
`cruft check` / `cruft update` use that record to detect and merge drift.

| | cookiecutter | fetch:template |
|---|---|---|
| Works without Backstage | Yes, plain CLI | No |
| Drift tooling | cruft, existing and maintained | None; would be hand rolled |
| Backstage integration | Needs `@backstage/plugin-scaffolder-backend-module-cookiecutter`, plus cookiecutter on PATH or a Docker daemon | Built in |

## Decision

The template is a cookiecutter template, generated and updated through
`cruft`. Backstage's adapter (`backstage/template.yaml`) calls
`fetch:cookiecutter` rather than the native `fetch:template`.

## Consequences

- The accepted cost is real: in Backstage, `fetch:cookiecutter` needs an
  extra backend module,
  `@backstage/plugin-scaffolder-backend-module-cookiecutter`, plus either a
  local cookiecutter install or a container runtime the scaffolder backend
  can shell out to, with the container-in-container complications that
  implies when Backstage itself runs in Docker.
- In exchange, drift detection and update come from a maintained tool
  (`cruft`) instead of being hand rolled, and the template works identically
  from a plain CLI whether or not Backstage is ever involved, which matters
  because Backstage is a front door here, not the product (ADR 0003).
- A template that only worked through Backstage's native fetch would be
  locked to a tool with a contested future; this one is not.

## What this does not solve

- Choosing cookiecutter does not, by itself, keep already-generated services
  current. It only makes drift detectable and mergeable; the mechanism and
  its limits are ADR 0004.
- It does not remove the operational cost of running `fetch:cookiecutter`
  inside a real Backstage instance; that cost is accepted, not eliminated,
  and it has never been paid in this repository, because Backstage is not
  hosted (ADR 0003) and has never been run against this template
  (`docs/running-backstage-locally.md`).
