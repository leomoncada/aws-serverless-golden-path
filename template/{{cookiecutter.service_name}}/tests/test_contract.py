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

def test_lambda_has_a_dead_letter_queue(lambda_, sqs, tf_outputs):
    conf = lambda_.get_function_configuration(FunctionName=tf_outputs["function_name"])
    target_arn = conf.get("DeadLetterConfig", {}).get("TargetArn")
    assert target_arn, "no DLQ configured"
    dlq_arn = sqs.get_queue_attributes(
        QueueUrl=tf_outputs["dlq_url"], AttributeNames=["QueueArn"]
    )["Attributes"]["QueueArn"]
    assert target_arn == dlq_arn, "DLQ target is not this stack's queue"

def test_lambda_runtime_is_pinned(lambda_, tf_outputs):
    conf = lambda_.get_function_configuration(FunctionName=tf_outputs["function_name"])
    assert conf["Runtime"] == "{{cookiecutter.python_runtime}}"

def test_bucket_notifies_the_processor_on_upload(s3, lambda_, tf_outputs):
    function_arn = lambda_.get_function_configuration(
        FunctionName=tf_outputs["function_name"]
    )["FunctionArn"]
    conf = s3.get_bucket_notification_configuration(Bucket=tf_outputs["bucket_name"])
    lambda_configs = conf.get("LambdaFunctionConfigurations", [])
    assert lambda_configs, "no lambda notification configured on the bucket"
    matching = [c for c in lambda_configs if c["LambdaFunctionArn"] == function_arn]
    assert matching, "notification does not target the processor function"
    notification = matching[0]
    assert "s3:ObjectCreated:*" in notification["Events"]
    prefixes = [
        rule["Value"]
        for rule in notification["Filter"]["Key"]["FilterRules"]
        if rule["Name"] == "prefix"
    ]
    assert prefixes == ["uploads/"]
