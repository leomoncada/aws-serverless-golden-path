# aws-serverless-golden-path

A cookiecutter template that generates a production-shaped serverless AWS service,
verifies itself against LocalStack on every pull request with no cloud credentials,
and keeps already-generated services current through automated `cruft update` pull
requests.

See [docs/DESIGN.md](docs/DESIGN.md) for the full design.

## LocalStack harness

`make up` starts a LocalStack container (pinned to `localstack/localstack:4`,
community edition) at `http://localhost:4566` and waits until an S3 bucket
named `tfstate` exists. Later tasks use that bucket as the Terraform backend.

`make down` stops LocalStack and removes its volumes.

## Prerequisites

- Docker (with the Compose plugin)
- make

Under construction: this covers only the LocalStack harness built so far.
