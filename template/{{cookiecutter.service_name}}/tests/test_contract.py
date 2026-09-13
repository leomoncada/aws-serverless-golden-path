def test_bucket_blocks_public_access(s3, tf_outputs):
    conf = s3.get_public_access_block(Bucket=tf_outputs["bucket_name"])
    block = conf["PublicAccessBlockConfiguration"]
    assert all(block[k] for k in
               ["BlockPublicAcls", "IgnorePublicAcls", "BlockPublicPolicy", "RestrictPublicBuckets"])

def test_bucket_has_versioning_enabled(s3, tf_outputs):
    assert s3.get_bucket_versioning(Bucket=tf_outputs["bucket_name"])["Status"] == "Enabled"

def test_table_is_on_demand(dynamodb, tf_outputs):
    table = dynamodb.describe_table(TableName=tf_outputs["table_name"])["Table"]
    assert table["BillingModeSummary"]["BillingMode"] == "PAY_PER_REQUEST"

def test_lambda_has_a_dead_letter_queue(lambda_, tf_outputs):
    conf = lambda_.get_function_configuration(FunctionName=tf_outputs["function_name"])
    assert conf.get("DeadLetterConfig", {}).get("TargetArn"), "no DLQ configured"

def test_lambda_runtime_is_pinned(lambda_, tf_outputs):
    conf = lambda_.get_function_configuration(FunctionName=tf_outputs["function_name"])
    assert conf["Runtime"] == "{{cookiecutter.python_runtime}}"
