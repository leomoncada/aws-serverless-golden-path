# {{cookiecutter.service_name}}

{{cookiecutter.description}}

Owned by `{{cookiecutter.owner_team}}`.

Generated from the [aws-serverless-golden-path](https://github.com/leomoncada/aws-serverless-golden-path)
template.

`cruft check` (needs `pip install cruft`) tells you whether this service was
generated from the tip of the template repository. Note what that is and is not:
it reports out of date after any commit to the template repository, including
commits that do not touch the template at all. Whether the template itself has
moved since this service was generated is what the platform's `DRIFT.md`
dashboard answers, and
[`docs/TEMPLATE-VERSION.md`](https://github.com/leomoncada/aws-serverless-golden-path/blob/main/docs/TEMPLATE-VERSION.md)
defines both.

## Quickstart

```bash
make up      # start LocalStack, with the tfstate bucket ready
make apply   # provision this service
make test    # run the tests
make down
```

Requires Docker (with the Compose plugin), Terraform >= 1.11, Python 3.12 and
make. No AWS account, no credentials, and no AWS CLI: `make up` waits on the
compose healthcheck, and the tfstate bucket is created inside the container by
`localstack/init/ready.d/01-tfstate-bucket.sh`.

`make lint` and `make ci` additionally need [tflint](https://github.com/terraform-linters/tflint)
on your PATH; `make up`, `make apply`, `make test` and `make down` do not.
