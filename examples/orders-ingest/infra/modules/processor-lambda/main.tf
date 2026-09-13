resource "aws_sqs_queue" "dlq" {
  name = "${var.service_name}-dlq"
}

data "archive_file" "app" {
  type        = "zip"
  source_dir  = "${path.root}/../app"
  output_path = "${path.root}/.build/app.zip"
  excludes = [
    "__pycache__",
    "**/__pycache__",
    "**/__pycache__/**",
    "*.pyc",
    "**/*.pyc",
  ]
}

resource "aws_iam_role" "this" {
  name               = "${var.service_name}-processor"
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "permissions" {
  statement {
    actions   = ["s3:GetObject"]
    resources = ["${var.bucket_arn}/*"]
  }
  statement {
    actions   = ["dynamodb:PutItem"]
    resources = [var.table_arn]
  }
  statement {
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.dlq.arn]
  }
  statement {
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.this.arn}:*"]
  }
}

resource "aws_iam_role_policy" "this" {
  role   = aws_iam_role.this.id
  policy = data.aws_iam_policy_document.permissions.json
}

resource "aws_cloudwatch_log_group" "this" {
  name              = "/aws/lambda/${var.service_name}-processor"
  retention_in_days = 14
}

resource "aws_lambda_function" "this" {
  function_name    = "${var.service_name}-processor"
  role             = aws_iam_role.this.arn
  handler          = "handler.handle"
  runtime          = var.runtime
  filename         = data.archive_file.app.output_path
  source_code_hash = data.archive_file.app.output_base64sha256
  timeout          = 10

  dead_letter_config { target_arn = aws_sqs_queue.dlq.arn }

  environment {
    variables = {
      TABLE_NAME = var.table_name
      LOG_JSON   = "true"
    }
  }

  depends_on = [aws_cloudwatch_log_group.this, aws_iam_role_policy.this]
}

resource "aws_lambda_permission" "s3" {
  statement_id  = "AllowS3Invoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.this.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = var.bucket_arn
}

resource "aws_s3_bucket_notification" "this" {
  bucket = var.bucket_id
  lambda_function {
    lambda_function_arn = aws_lambda_function.this.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "uploads/"
  }
  depends_on = [aws_lambda_permission.s3]
}
