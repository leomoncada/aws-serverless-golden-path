import boto3, pytest

ENDPOINT = "http://localhost:4566"

@pytest.fixture
def s3():
    return boto3.client(
        "s3", endpoint_url=ENDPOINT, region_name="us-east-1",
        aws_access_key_id="test", aws_secret_access_key="test",
    )

def test_localstack_is_community_edition():
    import urllib.request, json
    with urllib.request.urlopen(f"{ENDPOINT}/_localstack/health") as r:
        health = json.load(r)
    assert health["edition"] == "community"

def test_required_services_are_available():
    import urllib.request, json
    with urllib.request.urlopen(f"{ENDPOINT}/_localstack/health") as r:
        services = json.load(r)["services"]
    for name in ["s3", "lambda", "dynamodb", "sqs", "sns", "iam", "logs", "cloudwatch"]:
        assert services.get(name) in ("available", "running"), f"{name} is {services.get(name)}"

def test_tfstate_bucket_exists(s3):
    s3.head_bucket(Bucket="tfstate")
