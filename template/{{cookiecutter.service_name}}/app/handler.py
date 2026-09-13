"""S3 ObjectCreated to DynamoDB. One record per uploaded object."""
import json, logging, os, sys, urllib.parse
from datetime import UTC, datetime

import boto3

class _JsonFormatter(logging.Formatter):
    """Serialise each record's fields as one JSON object, once.

    A hand-rolled template like `'{"level":"%(levelname)s",...}'` splices the
    message in unescaped, so a message containing a quote or backslash (or,
    worse, an already-`json.dumps`-encoded string) breaks the resulting line.
    Building a dict and calling `json.dumps` once avoids that entirely.
    """

    def format(self, record):
        return json.dumps({"level": record.levelname, "event": record.getMessage()})


logger = logging.getLogger("{{cookiecutter.service_name}}")
if not logger.handlers:
    h = logging.StreamHandler(sys.stdout)
    if os.environ.get("LOG_JSON", "true").lower() == "true":
        h.setFormatter(_JsonFormatter())
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
        logger.info("record written record_id=%s key=%s", record_id, key)
        written += 1
    return {"written": written}
