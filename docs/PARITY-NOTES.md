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
  that alarms carry no `Service` / `Owner` / `ManagedBy` tags on real AWS
  either. If LocalStack fixes its CloudWatch serializer, delete the
  `aws.untagged` provider and the three `provider = aws.untagged` lines.
