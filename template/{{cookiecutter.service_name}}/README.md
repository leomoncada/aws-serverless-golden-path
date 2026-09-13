# {{cookiecutter.service_name}}

{{cookiecutter.description}}

Owned by `{{cookiecutter.owner_team}}`.

Generated from the [aws-serverless-golden-path](https://github.com/leomoncada/aws-serverless-golden-path)
template. Run `cruft check` to see whether this service is behind the template.

## Quickstart

```bash
make up      # start LocalStack
make apply   # provision this service
make test    # run the tests
make down
```

Requires Docker, Terraform >= 1.11, Python 3.12 and make. No AWS account and no
credentials.
