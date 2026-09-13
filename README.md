# aws-serverless-golden-path

A cookiecutter template for a serverless AWS service that provisions,
tests and destroys itself against LocalStack on every pull request with no
AWS account, and that keeps services already generated from it current
through automated `cruft update` pull requests.

## See it work: `make demo`

```
make demo
```

runs the whole path on a laptop, in order, with no AWS account or
credentials: start LocalStack, generate a service from the template into
`sandbox/`, lint its Terraform (`terraform fmt -check`, `terraform validate`,
`tflint`), provision it, run its integration tests, demonstrate drift
detection and update against a copy pinned to an older template commit, then
tear everything down. It is also exactly what `.github/workflows/ci.yml`
runs on every pull request (`make up`, `python -m pytest tests`, `make
demo`), so a green CI run and a local `make demo` are the same claim.

`make demo` needs the repository's full git history: it pins a copy of the
service to the oldest commit that ever touched `template/`, and reads
committed history rather than your working tree, so a shallow clone cannot
run it and an uncommitted template edit has no effect on what it generates.
See [`docs/PARITY-NOTES.md`](docs/PARITY-NOTES.md).

No terminal recording of this run is committed to the repository yet; the
fastest way to see it is to run it yourself; it takes a few minutes and
needs Docker, Terraform, `tflint`, Python and `make`.

## The drift dashboard

[`DRIFT.md`](DRIFT.md) is a generated file, rebuilt by
`python -m platformops.check_drift`, reading
[`platformops/registry.yaml`](platformops/registry.yaml) and reporting each
registered service's template version and how many days of template history
it is behind the current one. That mean-lag number is the metric this whole
mechanism exists to produce; without it, "we keep generated services
current" is a claim nobody can check.

"The current template version" means one specific thing here, defined once in
[`docs/TEMPLATE-VERSION.md`](docs/TEMPLATE-VERSION.md): the newest commit that
touches `template/`. A service is behind when the template version its code
was generated from is not that commit, and the lag is the distance in days
between those two commits, not the time since the service was generated. Note
that `cruft check` answers a different question (was this service generated
from the tip of the template repository), so it reports a service out of date
after any commit at all, and the two can disagree. That page says which
answers what.

One service is currently registered, [`examples/orders-ingest`](examples/orders-ingest),
generated from this template and committed as a fixture. It is current: the
template version it was generated from is the newest commit touching
`template/`, so the dashboard shows zero days behind.

```
1 service(s) registered, 0 behind the current template.
Mean lag: 0.0 days.

| Service | Repository | Template | Status | Days behind |
|---|---|---|---|---|
| orders-ingest | `leomoncada/aws-serverless-golden-path` | `5ac99ff` | current | 0 |
```

The mechanism that keeps it that way is `.github/workflows/drift.yml`: on a
schedule, it runs `platformops/apply_drift_updates.py`, which runs `cruft
update` for every service reported behind, then refreshes this dashboard with
`platformops/check_drift.py`, then opens a pull request with the result. That
order is not cosmetic and `tests/test_workflows.py` enforces it: `cruft
update` refuses to run against a dirty tree, and `DRIFT.md` is a tracked file
at the repository root, so writing the dashboard first would make every
update refuse, exactly when a service is behind and there is work to do. That
scheduled workflow has not yet run in this repository, so there is no real
update pull request to link to here yet; the mechanism it depends on is
demonstrated locally instead, with `make drift-demo`, which generates a
copy of the service pinned to an older template commit, shows `cruft check`
reporting it behind, runs `cruft update`, and confirms it is current
afterward. A real run of that command against `examples/orders-ingest`:

```
--> template HEAD is 5ac99ff; generating orders-ingest into sandbox/.drift-demo pinned to the older template commit 22d81e8 so it starts out behind
--> checking: orders-ingest was generated from 22d81e8, current template HEAD is 5ac99ff
FAILURE: Project's cruft is out of date! Run `cruft update` to clean this mess up.
--> confirmed behind: orders-ingest is pinned to 22d81e8 while the template is at 5ac99ff; running cruft update
Good work! Project's cruft has been updated and is as clean as possible!
--> .cruft.json now records 5ac99ff
SUCCESS: Good work! Project's cruft is up to date and as clean as possible :).
--> confirmed current: orders-ingest now matches template HEAD 5ac99ff
```

`cruft update` performs a three-way merge, which has real limits: it can
conflict, and sometimes resolve badly, on a service that has diverged
heavily from the template, and it cannot handle a Terraform resource rename
at all. See [`docs/adr/0004-drift-strategy.md`](docs/adr/0004-drift-strategy.md).
The registry itself, `platformops/registry.yaml`, is a plain file, not a
catalog; in a real organization this would be the Backstage catalog.

## What is tested, and what is not

**Tested, on every pull request, against LocalStack (`localstack/localstack:4`,
Community edition), with no AWS account:**

- The template generates a working service (`tests/test_template_generation.py`).
- The generated Terraform provisions a Lambda function, an S3 bucket, a
  DynamoDB table and an SQS dead letter queue, and the shape of each matches
  what the generated contract tests expect (`tests/test_contract.py` in the
  template).
- The S3-to-Lambda-to-DynamoDB flow actually runs end to end
  (`tests/test_integration.py` in the template).
- An absence-of-signal CloudWatch alarm reaches `ALARM` with no datapoints,
  not just `INSUFFICIENT_DATA` (`tests/test_alarms.py` in the template);
  this is the specific defect the design calls out from an earlier project.
  That assertion cannot be skipped: the generated `make test` runs it first,
  in its own pytest session, before anything invokes the function, and it
  fails rather than skipping if the alarm's evaluation window is not empty.
- The generated service's Terraform passes `terraform fmt -check`,
  `terraform validate` and `tflint`, on the service `make demo` generates.
- No Terraform resource in the template is conditional on the deploy target
  (`tests/test_aws_path.py::test_no_infrastructure_is_conditional_on_the_target`),
  so the code exercised locally is the code that would reach AWS.
- The drift detection, dashboard and update code (`platformops/`) has its
  own unit tests (`tests/test_check_drift.py`, `tests/test_drift_report.py`,
  `tests/test_apply_drift_updates.py`).
- `backstage/template.yaml` validates against the scaffolder schema and its
  parameters match `template/cookiecutter.json` exactly
  (`tests/test_backstage_template.py`).
- This repository's own committed prose has no em dashes and states the AWS
  path is unexercised (`tests/test_docs.py`).

**Documented, coded and never executed, stated here rather than implied:**

- **The Backstage adapter has never been run.** `backstage/template.yaml`
  is validated only against the scaffolder's JSON schema, which is weaker
  than executing it: schema validation cannot catch a `fetch:cookiecutter`
  run that fails because cookiecutter is not installed, a `publish:github`
  step that fails without a GitHub token, or a subtly wrong Jinja/Nunjucks
  expression. See [`docs/adr/0003-backstage-not-hosted.md`](docs/adr/0003-backstage-not-hosted.md)
  and [`docs/running-backstage-locally.md`](docs/running-backstage-locally.md).
- **The AWS path has not been exercised.** `make apply-aws`,
  `.github/workflows/deploy-aws.yml` (in the template, as `deploy-aws.yml`)
  and `docs/runbooks/first-aws-deploy.md` all exist and are documented, but
  none of them has ever been run against a real AWS account: there is no
  funded account to run them against. What that means concretely, from
  [`docs/adr/0005-localstack-not-aws.md`](docs/adr/0005-localstack-not-aws.md):
  IAM is not enforced by LocalStack Community, so nothing locally proves a
  policy is minimal or sufficient; cold starts, concurrency and throttling
  do not behave like real AWS; alarm delivery is verified only as far as
  SNS, not email, Slack or paging; cost is not modelled; service quotas do
  not exist locally; cross-account and OIDC trust cannot be tested without
  an account.
- **LocalStack itself diverges from AWS in known, recorded ways.**
  [`docs/PARITY-NOTES.md`](docs/PARITY-NOTES.md) lists what was expected to
  break and what was actually observed. The one divergence that needed a
  workaround: LocalStack's CloudWatch fails to serialize `DescribeAlarms`
  for an alarm carrying `default_tags`-injected tags, so the three metric
  alarms are created through a tag-free provider alias on both LocalStack
  and AWS, meaning those three alarms carry no `Service`/`Owner`/`ManagedBy`
  tags on either target. This is unverified on real AWS itself.
- **No real drift update pull request has been opened yet**, as covered
  above.

## Prerequisites

- Docker (with the Compose plugin)
- Terraform
- [tflint](https://github.com/terraform-linters/tflint), for the lint step in
  `make demo`
- Python and `make`, plus `pip install -r requirements-dev.txt` (cookiecutter,
  cruft, pytest, boto3, PyYAML)
- A full clone: `make demo` and the drift dashboard both read git history, so
  a `--depth 1` clone cannot run them

No AWS account, no credentials and no AWS CLI are needed for `make demo` or
any of its component targets. `make portal` additionally needs Node and a
local Backstage app; it is not part of `make demo` and CI never runs it.

## Architecture

```
aws-serverless-golden-path/
├── template/                              cookiecutter template root
│   ├── cookiecutter.json
│   └── {{cookiecutter.service_name}}/
│       ├── infra/                         Lambda, S3, DynamoDB, SQS DLQ, alarms
│       ├── app/                           Python handler, structured JSON logging
│       ├── tests/                         contract, integration and alarm tests
│       ├── localstack/init/ready.d/       creates the tfstate bucket on startup
│       ├── docs/runbooks/                 first-aws-deploy
│       ├── .github/workflows/             ci.yml, deploy-aws.yml
│       ├── Makefile                       the same targets CI calls
│       └── catalog-info.yaml
├── backstage/template.yaml                the thin fetch:cookiecutter adapter
├── platformops/
│   ├── registry.yaml                      services generated from this template
│   ├── check_drift.py                     resolves each service's template version, builds ServiceStatus
│   ├── apply_drift_updates.py             runs cruft update for services behind
│   └── drift_report.py                    renders DRIFT.md
├── docs/
│   ├── DESIGN.md                          the full design this repository implements
│   ├── TEMPLATE-VERSION.md                what "the current template version" means
│   ├── PARITY-NOTES.md                    LocalStack-vs-AWS divergences, expected vs observed
│   └── adr/                               five architecture decision records
├── examples/orders-ingest/                one generated service, committed, as a fixture
├── DRIFT.md                                generated: the dashboard
├── docker-compose.yml                      LocalStack, pinned to localstack:4
├── Makefile
└── README.md
```

Each generated service is provider-agnostic between LocalStack and real AWS
by construction: the Terraform provider block gates its `endpoints` on a
single `aws_endpoint_url` variable, so the same code targets LocalStack when
it is set and real AWS when it is empty, with no target-conditional
resources anywhere in the template. See
[`docs/adr/0001-serverless-over-ecs.md`](docs/adr/0001-serverless-over-ecs.md)
for why the paved road is serverless rather than the author's other,
ECS-based platform repository, and
[`docs/DESIGN.md`](docs/DESIGN.md) for the complete design, including the
constraints (zero cost, no funded AWS account) that shape every decision
above.

### The five ADRs

- [0001: serverless rather than the ECS stack](docs/adr/0001-serverless-over-ecs.md)
- [0002: cookiecutter and cruft over Backstage's native fetch:template](docs/adr/0002-cookiecutter-over-fetch-template.md)
- [0003: Backstage is not hosted](docs/adr/0003-backstage-not-hosted.md)
- [0004: the drift strategy, and what it cannot do](docs/adr/0004-drift-strategy.md)
- [0005: why verification targets LocalStack, not AWS](docs/adr/0005-localstack-not-aws.md)
