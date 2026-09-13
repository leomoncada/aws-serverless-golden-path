# LocalStack parity notes

Divergences between what the Terraform in `template/{{cookiecutter.service_name}}/infra`
expects of AWS and what LocalStack (community edition, image `localstack:4`,
services `s3, lambda, dynamodb, iam, sts, logs, sqs, sns, cloudwatch`) actually
does, plus risks that were anticipated going in but did not materialize.
Recording both so this register does not overstate how much diverges.

## Task 3: generated service infrastructure

- Expected: `terraform -chdir=infra output -json` and the S3/DynamoDB/Lambda
  read calls in `tests/test_contract.py` might not reflect fields the way real
  AWS does, since LocalStack re-implements each API.
  Observed: `get_public_access_block`, `get_bucket_versioning`,
  `describe_table`'s `BillingModeSummary.BillingMode`, and
  `get_function_configuration`'s `Runtime` all matched real AWS's shape
  exactly on the first run.
  No workaround needed.

- Expected (flagged explicitly in the task brief as the most likely failure):
  `dead_letter_config` set via Terraform on `aws_lambda_function` might not be
  reported back on `get_function_configuration`'s `DeadLetterConfig` field.
  Observed: LocalStack returns `DeadLetterConfig.TargetArn` correctly; the
  `test_lambda_has_a_dead_letter_queue` test passed on the first run.
  No workaround needed.

- Expected: the S3 backend's `use_lockfile = true` (the reason the repo's
  Terraform floor is `>= 1.11`) needs the backend's S3-compatible store to
  support conditional writes (`If-None-Match` on `PutObject`) to implement
  locking without DynamoDB. Older S3-compatible stores commonly lack this.
  Observed: `terraform -chdir=infra init -backend-config=env/local.backend.hcl`
  configured and used the S3 backend against LocalStack without any locking
  error, across repeated `init` / `apply` / `destroy` cycles.
  No workaround needed.

- Expected: `aws_sqs_queue` destroy would be roughly as fast as the other
  resources.
  Observed: every `terraform destroy` of the processor module's DLQ took
  roughly 25-45 seconds ("Still destroying...") against LocalStack, versus
  sub-second for the S3 bucket, DynamoDB table, IAM role, and Lambda function
  in the same run. Destroy still completes successfully; this is latency, not
  a correctness divergence.
  No workaround needed (noted for anyone budgeting CI time in a later task).

## Task 4: processor handler and S3 to DynamoDB integration test

- Expected: the Lambda's own `boto3.client("s3")` and `boto3.client("dynamodb")`
  calls, made from inside the LocalStack Lambda execution environment with no
  `endpoint_url` argument and no `aws_endpoint_url` variable threaded into the
  function's environment, might resolve to real AWS endpoints instead of
  LocalStack and hang or fail with a credentials error.
  Observed: LocalStack's Lambda runtime transparently rewrites the AWS SDK
  endpoint for code running inside its containers, so the handler's
  `get_object` and `put_item` calls reached LocalStack's S3 and DynamoDB
  automatically. Both integration tests passed on the first run with no
  endpoint configuration in `app/handler.py`.
  No workaround needed.

- Expected: the S3 to Lambda event notification might deliver the object key
  in a form (URL-encoded, different casing, etc.) that the handler's naive
  key handling would mishandle, given the brief's own `urllib.parse.unquote_plus`
  call as a hint that this was anticipated.
  Observed: LocalStack's event payload matched the documented AWS S3 event
  shape exactly (`Records[].s3.bucket.name` / `.object.key`); the
  `unquote_plus` call is defensive and not currently exercised by any
  observed divergence.
  No workaround needed.

## Task 5: alarms and the absence-of-signal test

- Expected: `treat_missing_data = "breaching"` might be stored but not acted
  on, leaving the `<service>-no-invocations` alarm in INSUFFICIENT_DATA
  locally and making the one test that justifies this task unable to
  distinguish a correct alarm from the broken CloudWatch default.
  Observed: LocalStack evaluates missing data exactly as documented. With no
  `AWS/Lambda Invocations` datapoints published, the alarm reaches
  `StateValue` `ALARM` within one evaluation period with `StateReason`
  "Threshold Crossed: no datapoints were received for 1 period and 1 missing
  datapoint was treated as [Breaching].", and the `-lambda-errors` alarm next
  to it, which keeps the CloudWatch default, sits in INSUFFICIENT_DATA with
  "Unchecked: Initial alarm creation". The divergence the task exists to catch
  is therefore visible locally.
  No workaround needed.

- Expected: nothing in particular about tags on alarms. The provider's
  `default_tags` had applied cleanly to every resource in Tasks 1 to 4.
  Observed: `terraform apply` hung for minutes on all three
  `aws_cloudwatch_metric_alarm` resources ("Still creating...") and never
  finished. LocalStack keeps the `Tags` sent with `PutMetricAlarm` on the
  stored alarm object and then fails to serialize the `DescribeAlarms`
  response that contains it: `exception during call chain: An unknown error
  occurred when trying to serialize the response` and
  `AWS cloudwatch.DescribeAlarms => 500 (InternalError)`.
  terraform-provider-aws 6.64.0 speaks to CloudWatch over the rpc-v2-cbor
  protocol (`POST /service/GraniteServiceVersion20100801/operation/DescribeAlarms`,
  `smithy-protocol: rpc-v2-cbor`), where that failure is a hard 500; the
  older query protocol the AWS CLI still uses turns the same condition into a
  logged warning ("Response object MetricAlarm contains a member which is not
  specified: Tags") and a 200, which is why `aws cloudwatch describe-alarms`
  succeeds against the very alarm the provider cannot read. The provider then
  retries the read 25 times with backoff, so the create never returns. Reduced
  to a two resource repro: the same alarm applies in 0s with no tags and fails
  with `tags = { Service = "zz" }`.
  Worked around: the three alarms are created through the `aws.untagged`
  provider configuration declared in `infra/providers.tf`, which is the same
  contract as the default one minus `default_tags`. It is used for both
  targets, so the alarms are identical on AWS and on LocalStack, and no
  `var.aws_endpoint_url` branch was added outside `providers.tf`. The cost is
  real and it falls on the AWS path: the three alarms carry no `Service` /
  `Owner` / `ManagedBy` tags there either, so they do not appear under this
  service in cost allocation (metric alarms are billed) and nothing on them
  names the owning team. In an account that enforces mandatory tags through an
  SCP these three alarms will fail to create until the alias is removed, and
  that path has never been exercised here. If LocalStack fixes its CloudWatch
  serializer, delete the `aws.untagged` provider and the three
  `provider = aws.untagged` lines.

## Task 6: generated CI workflow and cookiecutter/Jinja escaping

- This is not a LocalStack divergence but the most common way this template
  itself breaks, so it is recorded here rather than left to be rediscovered.
  Cookiecutter renders every file under `template/{{cookiecutter.service_name}}`
  through Jinja2, including `.github/workflows/ci.yml`. GitHub Actions
  expressions use the exact same `${{ ... }}` delimiter as Jinja's variable
  syntax, so any unescaped Actions expression in a template file (for example
  `${{ github.ref }}` in a `concurrency.group` key) is interpreted by
  cookiecutter as one of its own template variables. Since `github` and
  `ref` are not defined in `cookiecutter.json`, generation fails outright with
  a Jinja `UndefinedError`; a variable that happens to share a name with a
  real cookiecutter key would instead render silently wrong.
  Fix: inside any template file, escape each Actions expression as
  `${{ '{{' }} <expression> {{ '}}' }}`. Cookiecutter evaluates the two
  Jinja literals `'{{'` and `'}}'` and concatenates them around the
  expression text, so the file cookiecutter emits contains a plain,
  unescaped `${{ <expression> }}` that GitHub Actions then parses normally.
  Verified for this task: `template/{{cookiecutter.service_name}}/.github/workflows/ci.yml`
  contains `group: ci-${{ '{{' }} github.ref {{ '}}' }}` in the template, and
  the generated `sandbox/orders-ingest/.github/workflows/ci.yml` contains the
  unescaped `group: ci-${{ github.ref }}`.
  Anyone adding a new workflow (or any other Actions/Jinja-colliding syntax)
  to the template must apply this escaping to every `${{ ... }}` expression,
  not just `github.ref`, or `cruft create` / `make new` will fail or mangle
  the file.

## cruft generates from committed history, never from your working tree

Not a LocalStack divergence either, and the single most likely way to lose an
hour working on this repository, so it is recorded here rather than left to be
rediscovered.

`cruft create` clones the template repository at a commit (`--checkout`, or
HEAD by default) into a temporary directory and generates from that clone. It
never reads your working tree. So `make new`, `make demo` and `make drift-demo`
all generate from **committed** history, and an uncommitted edit under
`template/` has no effect whatsoever on what they produce: no error, no
warning, just the old file in the generated service. The first time this
happens it reads as "my template change did nothing", which in a repository
whose pitch is "edit the template, watch the path verify it" is the worst
possible first experience.

Two consequences worth knowing before they bite:

- **Commit before you generate.** Editing `template/`, then running `make demo`
  and finding the generated service unchanged means the edit is still
  uncommitted, not that the template is broken. `git commit` (or `git stash`
  and re-check) and run it again.
- **The same root cause breaks a shallow clone.** Everything that resolves a
  template version reads git history rather than the filesystem, so a
  `--depth 1` clone, where the one fetched commit appears to add every file,
  makes `check_drift` unable to tell the current template version from HEAD and
  leaves `make drift-demo` with no earlier template commit to pin its demo
  service to. Both workflows check out with `fetch-depth: 0` for that reason
  (`tests/test_workflows.py` asserts it), and `check_drift` reports `unknown`
  rather than guessing. See [`TEMPLATE-VERSION.md`](TEMPLATE-VERSION.md).
