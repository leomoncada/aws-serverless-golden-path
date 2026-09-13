"""S3 ObjectCreated to DynamoDB. One record per uploaded object."""
import json, logging, os, sys, urllib.parse
from datetime import UTC, datetime

import boto3

logger = logging.getLogger("{{cookiecutter.service_name}}")
if not logger.handlers:
    h = logging.StreamHandler(sys.stdout)
    if os.environ.get("LOG_JSON", "true").lower() == "true":
        h.setFormatter(logging.Formatter('{"level":"%(levelname)s","event":"%(message)s"}'))
    logger.addHandler(h)
logger.setLevel(logging.INFO)

_dynamodb = boto3.client("dynamodb")
_s3 = boto3.client("s3")
TABLE_NAME = os.environ["TABLE_NAME"]


def handle(event, context):
    written = 0
    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key = urllib.parse.unquote_plus(record["s3"]["object"]["key"])

        body = _s3.get_object(Bucket=bucket, Key=key)["Body"].read()
        payload = json.loads(body)
        record_id = payload["record_id"]

        _dynamodb.put_item(
            TableName=TABLE_NAME,
            Item={
                "record_id": {"S": record_id},
                "source_key": {"S": key},
                "byte_size": {"N": str(len(body))},
                "received_at": {"S": datetime.now(UTC).isoformat()},
            },
        )
        logger.info(json.dumps({"msg": "record written", "record_id": record_id, "key": key}))
        written += 1
    return {"written": written}
