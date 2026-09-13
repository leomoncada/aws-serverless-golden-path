# Design: `aws-serverless-golden-path`

**Status:** designed, ready to implement.
**Date:** 2026-09-13
**Owner:** Leomar Moncada
**Companion repos:** `leomoncada/localstack-ephemeral-infra`, `leomoncada/aws-ecs-fargate-platform`

> This file is the working spec. When the repository exists, it becomes
> `docs/DESIGN.md` in the first commit, and the decisions marked "ADR" below
> are split into `docs/adr/`.

---

## 1. Purpose

Demonstrate platform engineering, not DevOps tooling familiarity.

The product of a platform engineer is not a portal. It is the **paved road**: a
developer asks for a new service and receives a repository with infrastructure,
CI, tests, observability and runbooks already wired, without filing a ticket.

Three things make this repo different from the large population of
"Backstage template" repos:

1. **The golden path verifies itself.** On every pull request, the platform
   repository generates a service from its own template, provisions it,
   integration-tests it, and destroys it. No cloud credentials, no cost.
2. **It answers the drift question.** When the template changes, the services
   already generated from it are updated by an automated pull request, and the
   lag is measured.
3. **It runs on a laptop.** `make demo` walks the entire path locally, so a
   reviewer can watch it rather than read about it.

### Why serverless and not the ECS stack

`aws-ecs-fargate-platform` is the more production-shaped codebase, but ECS and
ALB do not exist in LocalStack Community. A paved road built on them could not
verify itself without a funded AWS account, which breaks point 1 above and the
budget constraint below. A Lambda, DynamoDB, S3 and SQS service fits entirely
inside the loop already proven in `localstack-ephemeral-infra`. **ADR.**

---

## 2. Constraints

- **Money.** Limited personal funds for infrastructure. The whole design must
  run at zero cost. Nothing is hosted 24/7.
- **No AWS account available at time of writing.** Everything must be
  demonstrable against LocalStack Community, which excludes ECS, ALB, ECR and
  EKS.
- **Job search is live.** Prefer a smaller finished artefact over a larger
  unfinished one.

---

## 3. What a generated service contains

The template output is a complete, working repository:

| Path | Contents |
|---|---|
| `infra/` | Terraform modules: Lambda, Function URL, DynamoDB table, S3 bucket, SQS dead letter queue |
| `infra/alarms.tf` | CloudWatch alarms as code, with `treat_missing_data = "breaching"` on the absence-of-signal alarms from day one |
| `app/` | Python handler with structured logging to stdout as JSON |
| `tests/test_contract.py` | Asserts the shape of the provisioned infrastructure |
| `tests/test_integration.py` | Exercises the real flow end to end |
| `tests/test_alarms.py` | Asserts an absence-of-signal alarm actually reaches ALARM with no datapoints. Verified possible on LocalStack Community. |
| `.github/workflows/ci.yml` | lint, contract test, provision, integration test, destroy |
| `Makefile` | The same targets CI calls, so local and CI cannot drift apart |
| `docs/runbooks/` | deploy, rollback, incidents |
| `catalog-info.yaml` | Pre-filled, so the service registers itself in the catalog |
| `.cruft.json` | Written by cruft: which template commit this service came from |

Two lessons are carried in deliberately, because both were real defects found
in `aws-ecs-fargate-platform`:

- Alarms on metrics that stop publishing during an outage set
  `treat_missing_data = "breaching"`. The CloudWatch default renders them
  decorative.
- Every claim in the generated README is checked against the generated code.
  **If it is documented, it is implemented.**

---

## 4. The generator: cookiecutter plus cruft

`cookiecutter` is a directory tree with `{{cookiecutter.variable}}` placeholders
in file names and file contents, plus a `cookiecutter.json` declaring the
variables. Running it produces a real project with the values substituted.

`cruft` builds on top of it. A project generated with cruft records the template
commit it came from in `.cruft.json`. Later, `cruft check` reports whether the
project is behind, and `cruft update` computes the diff between the recorded
commit and the current template and applies it as a three way merge, preserving
local edits.

**This is the entire reason for choosing cookiecutter.** Drift handling is the
differentiator of this repo, and cruft already solves it. Writing a worse
version by hand would be poor engineering, whatever it looks like on a diff.

### ADR: cookiecutter over Backstage's native `fetch:template`

Backstage's built-in `fetch:template` action needs no extra plugin and no
Docker. It is the lower friction choice **inside Backstage**, and it is rejected
anyway.

| | cookiecutter | `fetch:template` |
|---|---|---|
| Works without Backstage | Yes, plain CLI | No |
| Drift tooling | `cruft`, existing and maintained | None; would be hand rolled |
| Backstage integration | Needs `@backstage/plugin-scaffolder-backend-module-cookiecutter`, plus cookiecutter on PATH or a Docker daemon | Built in |

The cost is real and is not hidden: in Backstage, cookiecutter needs an extra
backend module and either a local cookiecutter install or a container runtime,
with the container-in-container problems that implies when Backstage itself runs
in Docker. That friction is accepted because the drift capability is worth more
than the setup convenience, and because a template that only works inside
Backstage is locked to a tool with a contested future.

---

## 5. The Backstage adapter

`backstage/template.yaml`, roughly 40 lines: `fetch:cookiecutter`,
`publish:github`, `catalog:register`.

Backstage is the front door, not the product. It is **not hosted**. It runs
locally to record the demo, which costs nothing and keeps the repo useful if
Backstage falls out of favour, because the paved road underneath is
tool-agnostic.

Validation without running Backstage is done against the scaffolder schema.
This is weaker than executing it, and the README says so rather than implying
the adapter is fully tested. **ADR: why Backstage is not hosted.**

---

## 6. Drift detection and update

The differentiating feature. Three parts:

**Detection.** A scheduled workflow in the platform repository reads a registry
of generated services, runs `cruft check` against each, and records which
template version each service is on.

**Update.** For services behind the current template, the workflow runs
`cruft update` and opens a pull request against that service's repository with
the delta. The receiving team reviews and merges. The platform team does not
force anything.

**Measurement.** A drift dashboard, generated as a committed Markdown table and
a badge: how many services on each template version, and the mean lag in days
behind current. That number is the platform team's product metric. Without it,
"we have a golden path" is unfalsifiable.

### Honest limits, stated in the README

- `cruft update` performs a three way merge. On a service that has diverged
  heavily from the template it produces conflicts, and sometimes a bad
  automatic resolution. It reduces the problem; it does not eliminate it.
- Some template changes cannot be merged automatically at all, for example a
  Terraform resource rename that requires a `moved` block or a state operation.
  The runbook covers this case explicitly rather than pretending it does not
  exist.
- The registry of generated services is a file in this repo. In a real
  organisation it would be the Backstage catalog. The README says which is
  which.

---

## 7. Local experience

First class, not an afterthought. A reviewer who cannot run it will not believe
it, and neither will the author six months later.

```bash
make up            # start LocalStack
make new           # generate a service from the template into ./sandbox/
make apply         # provision the generated service against LocalStack
make test          # run its integration tests
make drift-demo    # move the template, show cruft detecting and updating ./sandbox/
make portal        # run Backstage locally with the template loaded (optional)
make down
```

`make demo` chains `up`, `new`, `apply`, `test`, `drift-demo`, `down`.

Requirements for everything except `make portal`: Docker, Terraform, Python and
`make`. No AWS account, no credentials, no Node.

`make portal` is isolated on purpose. It needs Node and a local Backstage app,
which is a heavier dependency than the rest of the repository deserves. The
other six targets do not depend on it, so the repo works end to end without it.

---

## 8. CI

CI calls **the same Makefile targets**, following the pattern already used in
`localstack-ephemeral-infra`, where CI and local share targets so they cannot
silently diverge.

Two workflows:

- `ci.yml` on every pull request: lint, then `make demo`. This is the job that
  makes the claim credible, because it proves the template produces a service
  that actually provisions and passes its own tests. `make portal` is never
  called in CI; it is not part of `make demo`.
- `drift.yml` on a schedule: check registered services, open update pull
  requests, refresh the dashboard.

---

## 9. Repository layout

```
aws-serverless-golden-path/
├── template/                      cookiecutter template root
│   ├── cookiecutter.json
│   └── {{cookiecutter.service_name}}/
│       ├── infra/
│       ├── app/
│       ├── tests/
│       ├── docs/runbooks/
│       ├── .github/workflows/ci.yml
│       ├── Makefile
│       └── catalog-info.yaml
├── backstage/template.yaml        the thin adapter
├── platform/
│   ├── registry.yaml              services generated from this template
│   └── drift_report.py            builds the dashboard
├── docs/
│   ├── DESIGN.md                  this document
│   └── adr/
├── examples/                      one generated service, committed, as a fixture
├── catalog-info.yaml
├── Makefile
└── README.md
```

---

## 10. ADRs to write

1. Why serverless rather than the ECS stack for the paved road.
2. Why cookiecutter and cruft rather than Backstage's native templating.
3. Why Backstage is not hosted.
4. The drift strategy, and what it cannot do.
5. Why the generated service tests itself against LocalStack rather than AWS,
   including what that does **not** prove.

---

## 11. README structure

Lead with evidence, not architecture. The lesson from the MLOps design applies
here too: a reviewer gives this twenty seconds.

1. One sentence thesis.
2. `make demo`, and an asciinema recording of it.
3. The drift dashboard, showing a real service being updated by a real pull
   request.
4. What is tested and what is not.
5. Architecture, below the fold.

---

## 12. Success criteria

The repo is done when a reviewer can verify all of these without an AWS
account:

1. `make demo` works from a clean clone on Docker, Terraform, Python and make.
2. CI generates a service from the template, provisions it, tests it and
   destroys it on every pull request, green.
3. A generated service exists in `examples/`, registered in `registry.yaml`.
4. A drift pull request has actually been opened against it by the scheduled
   workflow, and is linked from the README.
5. The drift dashboard shows version and lag per service.
6. All five ADRs are written, including the limits of the drift mechanism.
7. `backstage/template.yaml` validates against the scaffolder schema, with the
   README stating that schema validation is weaker than execution.
8. `make apply-aws`, `deploy-aws.yml` and `docs/runbooks/first-aws-deploy.md`
   all exist, with the README stating plainly that none of them has been run.
9. No Terraform resource in the template is conditional on the target, so the
   code exercised locally is the code that would reach AWS.

---

## 12b. Path to real AWS

Local first is a choice about **where it runs today**, not about what it can
ever do. Deploying a generated service to a real AWS account must be a
configuration change, never a rewrite. This section is the contract that keeps
that true, and it is a v1 deliverable even though deploying to AWS is not.

### The mechanism, already proven

`localstack-ephemeral-infra` solved this and the solution is carried over
verbatim. The provider block declares `endpoints` gated on a variable:

```hcl
provider "aws" {
  # Everything below is inert when aws_endpoint_url is "".
  dynamic "endpoints" { ... }
  s3_use_path_style           = var.aws_endpoint_url != ""
  skip_credentials_validation = var.aws_endpoint_url != ""
  skip_metadata_api_check     = var.aws_endpoint_url != ""
  skip_requesting_account_id  = var.aws_endpoint_url != ""
}
```

Set `aws_endpoint_url` and it targets LocalStack. Leave it empty and the same
code targets AWS. State backend follows the same shape, with
`env/local.backend.hcl` and `env/aws.backend.hcl`.

**Every generated service inherits this**, so the property is not something the
platform has and its children lack.

### Three rules that prevent the cliff

1. **Service intersection.** The template only uses AWS services that exist in
   both LocalStack Community and real AWS. Verified on 2026-09-13 against
   `localstack/localstack:4`: Lambda, S3, DynamoDB, SQS, SNS, IAM, CloudWatch
   Logs and CloudWatch **metric alarms** are all available, and alarms genuinely
   evaluate, including `treat_missing_data = "breaching"` moving an alarm to
   ALARM with no datapoints. Anything outside that intersection requires an ADR
   before it enters the template.
2. **Pin the LocalStack image.** `localstack/localstack:4`, never `:latest`.
   The `latest` tag now refuses to start without a licence token, which turns
   into a confusing "LocalStack is broken" failure for anyone cloning the repo.
3. **No conditional resources.** The Terraform must not grow
   `count = var.is_local ? 0 : 1` branches. The moment infrastructure differs
   between targets, local stops proving anything about AWS. Divergences belong
   in `PARITY-NOTES.md` as observations, not in the code as forks.

### The AWS target

- `make apply-aws` runs the same Terraform against a real account, using
  `env/aws.backend.hcl` and real credentials. It exists in v1 and is documented,
  but the README states it has not been exercised.
- `deploy-aws.yml`: a `workflow_dispatch` workflow, authenticating by OIDC,
  present and syntactically valid but never run in this repository. It is the
  coded path, not a claim.

### What local does not prove, stated in the README

This list is the honest half and is the reason the section exists:

- **IAM is not enforced** by LocalStack Community by default. Least-privilege
  policies are written and reviewable, but nothing locally proves they are
  sufficient or minimal. First real deploy is where that is discovered.
- **Cold starts, concurrency limits and throttling** do not behave like AWS.
- **Alarm delivery** is verified as far as SNS. Email, Slack and paging are not
  exercised.
- **Cost** is not modelled, because locally there is none.
- **Service quotas** do not exist locally.
- **Cross-account and OIDC trust** cannot be tested without an account.

### First real deploy runbook

`docs/runbooks/first-aws-deploy.md`, written in v1 so the path is not
reconstructed under pressure later: bootstrap the state bucket and lock table,
create the OIDC provider and roles, set repository secrets, `make apply-aws`
into a throwaway environment, verify each item in the "does not prove" list
above, then tear it down. The estimated cost of that exercise is included, so
the decision to run it is informed.

---

## 13. Out of scope for v1

- Hosting Backstage anywhere.
- More than one service archetype. One archetype done properly beats three
  half-built.
- Scorecards and maturity scoring. Natural v2, and the drift dashboard is the
  more original half of that idea anyway.
- **Running** a generated service on real AWS. The path is designed, coded and
  documented in section 12b, including `make apply-aws`, the OIDC workflow and
  the first-deploy runbook. What is out of scope is *executing* it, because
  there is no funded account. The README states this distinction plainly: the
  path exists and is unexercised.

---

## 14. Risks

| Risk | Mitigation |
|---|---|
| `cruft update` merges badly on diverged services | Named in the README and in ADR 4. The runbook covers manual resolution. |
| LocalStack Community parity gaps on Lambda, DynamoDB, S3 or SQS | `PARITY-NOTES.md`, same format already used in `localstack-ephemeral-infra`: expected, observed, worked around, including risks that did not materialise. |
| Backstage adapter unverifiable without running Backstage | Schema validation in CI, honest statement in the README, `make portal` for anyone who wants to run it. |
| Scope creep into a full IDP | Section 13 is the boundary. |

---

## 15. Open questions

None blocking. The service archetype is a receipt or event ingestion flow,
reusing the shape already proven in `localstack-ephemeral-infra`, which keeps
the focus on the paved road rather than on inventing a domain.
