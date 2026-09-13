resource "aws_sns_topic" "alarms" {
  name = "${var.service_name}-alarms"
}

resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  alarm_name          = "${var.service_name}-lambda-errors"
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  statistic           = "Sum"
  period              = 60
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  alarm_actions       = [aws_sns_topic.alarms.arn]
  ok_actions          = [aws_sns_topic.alarms.arn]
  dimensions          = { FunctionName = module.processor.function_name }
  alarm_description   = "The processor is throwing errors."
}

resource "aws_cloudwatch_metric_alarm" "dlq_not_empty" {
  alarm_name          = "${var.service_name}-dlq-not-empty"
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  alarm_actions       = [aws_sns_topic.alarms.arn]
  dimensions          = { QueueName = "${var.service_name}-dlq" }
  alarm_description   = "Events failed processing and landed in the dead letter queue."
}

# Absence of signal. If the function stops being invoked at all, Invocations
# stops being published entirely. With the CloudWatch default of
# treat_missing_data = "missing" this alarm would sit in INSUFFICIENT_DATA
# during precisely the outage it exists to catch.
resource "aws_cloudwatch_metric_alarm" "no_invocations" {
  alarm_name          = "${var.service_name}-no-invocations"
  namespace           = "AWS/Lambda"
  metric_name         = "Invocations"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "LessThanThreshold"
  treat_missing_data  = "breaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]
  dimensions          = { FunctionName = module.processor.function_name }
  alarm_description   = "The processor has stopped being invoked."
}
