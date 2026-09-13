import os, subprocess, json, pytest, boto3

ENDPOINT = os.environ.get("AWS_ENDPOINT_URL", "http://localhost:4566")
REGION = "us-east-1"

def _client(service):
    return boto3.client(
        service, endpoint_url=ENDPOINT, region_name=REGION,
        aws_access_key_id="test", aws_secret_access_key="test",
    )

@pytest.fixture(scope="session")
def tf_outputs():
    raw = subprocess.run(
        ["terraform", "-chdir=infra", "output", "-json"],
        check=True, capture_output=True, text=True,
    ).stdout
    return {k: v["value"] for k, v in json.loads(raw).items()}

@pytest.fixture
def s3(): return _client("s3")
@pytest.fixture
def dynamodb(): return _client("dynamodb")
@pytest.fixture
def sqs(): return _client("sqs")
@pytest.fixture
def cloudwatch(): return _client("cloudwatch")
@pytest.fixture
def lambda_(): return _client("lambda")
