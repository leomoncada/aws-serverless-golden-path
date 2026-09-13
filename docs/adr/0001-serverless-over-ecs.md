# 0001: Serverless rather than the ECS stack

## Context

The author has a second, more production-shaped platform repository,
`aws-ecs-fargate-platform`, built on ECS and an Application Load Balancer.
That is a closer match to what a real infrastructure team runs in production
than Lambda, DynamoDB, S3 and SQS are.

The core claim of this repository is that the golden path verifies itself:
on every pull request it generates a service from its own template,
provisions it, integration-tests it, and destroys it, with no cloud
credentials and no cost. That claim can only be made about infrastructure
that can actually be provisioned somewhere free.

ECS and an Application Load Balancer do not exist in LocalStack Community.
Verifying an ECS-based golden path in CI would need a funded AWS account,
which this project does not have and the budget constraint in
`docs/DESIGN.md` rules out.

## Decision

The paved road in this repository is serverless: Lambda, DynamoDB, S3 and an
SQS dead letter queue, all of which LocalStack Community implements well
enough to provision, integration-test and tear down for free, as recorded in
`docs/PARITY-NOTES.md`.

## Consequences

- The repository can prove its central claim, "the golden path verifies
  itself," end to end on a laptop and in CI with no AWS account.
- What is lost: the ECS repository is the more production-shaped artefact.
  Long-running containers behind a load balancer, service discovery, and
  the operational surface of a scheduler are all real platform-engineering
  concerns this template does not demonstrate, because they cannot be
  verified for free.
- Any future archetype that needs ECS, ALB, ECR or EKS is out of scope for
  this repository's verification loop unless a funded account becomes
  available; see `docs/DESIGN.md` section 2.
