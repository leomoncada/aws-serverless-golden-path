# orders-ingest

A serverless ingestion service

Owned by `platform`.

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

## Inspecting the running stack by hand

The `make` targets export dummy credentials for you. Raw `aws` commands do not
get them, and the CLI resolves credentials before it ever looks at
`--endpoint-url`, so an expired SSO session fails with a message about
reauthenticating even though nothing is talking to real AWS. Export these once
per terminal:

```bash
export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test
export AWS_DEFAULT_REGION=us-east-1
unset AWS_PROFILE
```

LocalStack accepts any credentials. `test` is the conventional value.

Then, with the stack applied:

```bash
# Alarm states. The no-invocations alarm sits in ALARM with no data, by design.
aws --endpoint-url=http://localhost:4566 cloudwatch describe-alarms \
  --query 'MetricAlarms[*].[AlarmName,StateValue,TreatMissingData]' --output table

# Push an object through the pipeline and read the record back.
BUCKET=$(terraform -chdir=infra output -raw bucket_name)
TABLE=$(terraform -chdir=infra output -raw table_name)
echo '{"record_id":"probe-1","amount":42}' > /tmp/probe.json
aws --endpoint-url=http://localhost:4566 s3 cp /tmp/probe.json "s3://$BUCKET/uploads/probe.json"
aws --endpoint-url=http://localhost:4566 dynamodb get-item \
  --table-name "$TABLE" --key '{"record_id":{"S":"probe-1"}}'

# Same object outside the uploads/ prefix is ignored, which is the filter working.
aws --endpoint-url=http://localhost:4566 s3 cp /tmp/probe.json "s3://$BUCKET/other/probe.json"

# Processor logs.
aws --endpoint-url=http://localhost:4566 logs tail /aws/lambda/orders-ingest-processor
```

If you would rather not touch your environment, `pip install awscli-local` gives
you `awslocal`, which sets the endpoint and the dummy credentials itself:
`awslocal cloudwatch describe-alarms`.
