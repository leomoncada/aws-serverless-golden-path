import json, time, uuid, pytest

def _wait_for_item(dynamodb, table, record_id, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        got = dynamodb.get_item(TableName=table, Key={"record_id": {"S": record_id}})
        if "Item" in got:
            return got["Item"]
        time.sleep(1)
    raise AssertionError(f"no item {record_id} in {table} after {timeout}s")

def test_uploading_an_object_writes_a_record(s3, dynamodb, tf_outputs):
    record_id = str(uuid.uuid4())
    body = json.dumps({"record_id": record_id, "amount": 42}).encode()

    s3.put_object(Bucket=tf_outputs["bucket_name"], Key=f"uploads/{record_id}.json", Body=body)

    item = _wait_for_item(dynamodb, tf_outputs["table_name"], record_id)
    assert item["source_key"]["S"] == f"uploads/{record_id}.json"
    assert int(item["byte_size"]["N"]) == len(body)

def test_objects_outside_the_uploads_prefix_are_ignored(s3, dynamodb, tf_outputs):
    ignored_id = str(uuid.uuid4())
    control_id = str(uuid.uuid4())

    s3.put_object(Bucket=tf_outputs["bucket_name"], Key=f"other/{ignored_id}.json",
                  Body=json.dumps({"record_id": ignored_id}).encode())
    s3.put_object(Bucket=tf_outputs["bucket_name"], Key=f"uploads/{control_id}.json",
                  Body=json.dumps({"record_id": control_id}).encode())

    # Wait for the in-prefix control object to be processed. This proves the
    # pipeline had time to run (rather than relying on a fixed sleep, which
    # would pass just as well if the prefix filter were silently removed and
    # every object, including the ignored one, went unprocessed because the
    # pipeline was merely slow).
    _wait_for_item(dynamodb, tf_outputs["table_name"], control_id)

    got = dynamodb.get_item(TableName=tf_outputs["table_name"],
                            Key={"record_id": {"S": ignored_id}})
    assert "Item" not in got
