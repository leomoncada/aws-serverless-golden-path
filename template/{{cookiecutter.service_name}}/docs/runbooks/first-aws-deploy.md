# Runbook: first deploy to real AWS

**Status: this path has not been exercised.** The Terraform is the same code
that runs against LocalStack on every pull request, and the workflow below is
syntactically valid, but neither has ever been run against a real account. Treat
this runbook as a tested design, not a tested procedure.

## Before you start

This template creates, per environment: one S3 bucket (Terraform state, plus
whatever the service itself uses), one DynamoDB table in on demand mode, one
Lambda function, one SQS queue, one SNS topic, three CloudWatch metric alarms,
and the CloudWatch log group the Lambda writes to.

At demo volume (a handful of invocations, a few state reads and writes,
torn down the same day), S3, DynamoDB on demand, Lambda, SQS, SNS and log
ingestion each sit inside or near the always free tier: a few requests and
a few megabytes cost fractions of a cent. There is no NAT gateway, no load
balancer and no cluster in this architecture, which is where serverless demos
usually leak money.

CloudWatch metric alarms are the exception and are worth calling out
explicitly, because assuming they are free is a mistake this repository has
already made once. Alarms are billed per alarm per month, roughly 0.10 USD
each, regardless of whether they ever fire. This template creates three, so
they are billed at roughly 0.30 USD per month combined, prorated to the hours
they exist. For a same-day deploy and teardown that prorates to a fraction of
a cent, but it is not zero, and if you forget to tear down, it is the one
resource here that keeps costing money every month it exists.

Estimated cost of following this runbook end to end and tearing down the
same day: under 1 USD, with the CloudWatch alarms as the only line item that
is not effectively free.

## Steps

1. **Bootstrap state.** Create an S3 bucket for Terraform state with versioning
   enabled. Put its name in `infra/env/aws.backend.hcl`, replacing
   `CHANGE-ME-terraform-state`. Locking uses `use_lockfile`, so no DynamoDB
   table is needed.
2. **Create the OIDC provider and role.** Add
   `token.actions.githubusercontent.com` as an IAM OIDC provider. Create a role
   whose trust policy conditions `sub` on
   `repo:<owner>/{{cookiecutter.service_name}}:environment:production`, and
   attach a policy allowing only the resources in `infra/`.
3. **Set the secret.** Repository secret `AWS_DEPLOY_ROLE_ARN`.
4. **Deploy into a throwaway environment.** `make apply-aws`.

## What to verify, because local never proved it

- **IAM sufficiency.** LocalStack Community does not enforce IAM. This is the
  first time the least-privilege policy is actually tested. Expect
  `AccessDenied` and fix forward.
- **Cold start and concurrency.** Behaviour differs from LocalStack.
- **Alarm delivery.** Local verifies alarms reach SNS. Subscribe an address and
  confirm the message arrives.
- **Service quotas.** They do not exist locally.

## Tear down

`terraform -chdir=infra destroy`, then empty and delete the state bucket. Confirm
in Cost Explorer the next day that nothing is still billing, in particular
that the three CloudWatch alarms are gone; they are the one resource here that
keeps a monthly charge going if teardown is skipped.
