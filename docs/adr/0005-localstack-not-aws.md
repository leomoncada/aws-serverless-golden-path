# 0005: Verification targets LocalStack, not AWS

## Context

The repository's central claim, that the golden path verifies itself on
every pull request, has to run somewhere. There is no funded AWS account
available, and the design constraint in `docs/DESIGN.md` rules out spending
money on infrastructure. `localstack-ephemeral-infra` already proved the
mechanism this repository reuses: a provider block whose `endpoints` are
gated on a variable (`aws_endpoint_url`), so the identical Terraform targets
LocalStack when the variable is set and real AWS when it is empty, with no
`count = var.is_local ? 0 : 1`-style fork anywhere in the template
(`tests/test_aws_path.py::test_no_infrastructure_is_conditional_on_the_target`
enforces this as a tripwire).

## Decision

Every generated service's own CI (and this repository's own `make demo`)
provisions, integration-tests, and destroys against LocalStack Community
(`localstack/localstack:4`, pinned; the `latest` tag now refuses to start
without a licence token). Real AWS is reachable through the same Terraform
via `make apply-aws` and `env/aws.backend.hcl`, and a `deploy-aws.yml`
`workflow_dispatch` workflow authenticating by OIDC exists in the template,
but as of this writing neither has ever been run: there is no AWS account to
run them against. `docs/runbooks/first-aws-deploy.md` documents the first
real run in advance so that path is not improvised under pressure later.

## Consequences

- The whole verification loop (generate, provision, integration-test,
  destroy) runs for free, on a laptop or in GitHub Actions, with no cloud
  credentials, which is what makes "the golden path verifies itself" testable
  at all.
- Because the Terraform is identical between targets, what runs locally is
  the code that would reach AWS; nothing here proves it behaves identically
  once it does.
- Divergences that were anticipated and then checked against the real
  LocalStack behavior are recorded in `docs/PARITY-NOTES.md` rather than
  hidden or guessed at. The two divergences actually found:
  - The three CloudWatch metric alarms have to be created through a second,
    tag-free AWS provider alias (`aws.untagged` in `infra/providers.tf`),
    because LocalStack's CloudWatch fails to serialize `DescribeAlarms` for
    an alarm that carries `default_tags`-injected `Tags`, which hangs
    `terraform apply` on the provider's read-after-create retry loop. The
    same tag-free alias is used against real AWS too, so the alarms are
    identical on both targets; the real cost is that these three alarms
    carry no `Service` / `Owner` / `ManagedBy` tags on AWS either, so they
    are invisible to tag-based cost allocation and ownership, and would fail
    outright under an SCP that mandates tags. That path has never been
    exercised.
  - `aws_sqs_queue` destroy takes roughly 25 to 45 seconds against LocalStack
    per run, versus sub-second for the S3 bucket, DynamoDB table, IAM role
    and Lambda function in the same run. This is latency, not a correctness
    difference, but it is worth budgeting for in CI time.
  - Every other anticipated risk in `docs/PARITY-NOTES.md` (S3 backend
    conditional-write locking, the shape of `describe_table` /
    `get_function_configuration` / `get_public_access_block` responses, the
    Lambda dead letter queue configuration being reported back correctly, the
    S3-to-Lambda event payload shape) did not materialize: LocalStack matched
    AWS's documented behavior on the first run, and no workaround was needed.

## What this does not prove

This list is deliberately the honest half of this decision, copied from
`docs/DESIGN.md` section 12b:

- **IAM is not enforced** by LocalStack Community by default. Least
  privilege policies are written and reviewable, but nothing locally proves
  they are sufficient or minimal; the first real deploy is where that is
  discovered.
- **Cold starts, concurrency limits and throttling** do not behave like real
  AWS.
- **Alarm delivery is verified only as far as SNS.** Email, Slack and paging
  are not exercised.
- **Cost is not modelled**, because locally there is none.
- **Service quotas do not exist** locally.
- **Cross-account and OIDC trust cannot be tested** without a real account.

None of this is theoretical caution: it is the specific, named reason
`make apply-aws`, `deploy-aws.yml` and
`docs/runbooks/first-aws-deploy.md` exist as a documented, coded, and
unexercised path rather than as a promise. The README states plainly that
this path has not been exercised.
