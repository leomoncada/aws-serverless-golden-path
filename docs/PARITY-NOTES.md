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
