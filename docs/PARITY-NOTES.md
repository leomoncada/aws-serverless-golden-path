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
