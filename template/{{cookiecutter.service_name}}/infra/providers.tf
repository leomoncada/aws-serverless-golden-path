#
# This is the single contract that keeps the AWS path open. One codebase, two
# targets. Set aws_endpoint_url and everything below activates and points at
# LocalStack. Leave it empty and this is an ordinary AWS provider.
#
# Do not add target-conditional resources anywhere else. The moment the
# infrastructure itself differs, the local run stops proving anything about AWS.
provider "aws" {
  region = var.aws_region

  access_key = var.aws_endpoint_url != "" ? "test" : null
  secret_key = var.aws_endpoint_url != "" ? "test" : null

  s3_use_path_style           = var.aws_endpoint_url != ""
  skip_credentials_validation = var.aws_endpoint_url != ""
  skip_metadata_api_check     = var.aws_endpoint_url != ""
  skip_requesting_account_id  = var.aws_endpoint_url != ""

  dynamic "endpoints" {
    for_each = var.aws_endpoint_url != "" ? [1] : []
    content {
      s3         = var.aws_endpoint_url
      dynamodb   = var.aws_endpoint_url
      lambda     = var.aws_endpoint_url
      sqs        = var.aws_endpoint_url
      sns        = var.aws_endpoint_url
      iam        = var.aws_endpoint_url
      sts        = var.aws_endpoint_url
      logs       = var.aws_endpoint_url
      cloudwatch = var.aws_endpoint_url
    }
  }

  default_tags {
    tags = {
      Service   = "{{cookiecutter.service_name}}"
      Owner     = "{{cookiecutter.owner_team}}"
      ManagedBy = "terraform"
    }
  }
}

# The CloudWatch metric alarms in alarms.tf are created through this second
# configuration. It is the same contract as the one above, minus default_tags,
# and it is used for both targets, so the alarms are identical on AWS and on
# LocalStack. This is not a target-conditional resource.
#
# Why it exists: LocalStack 4's CloudWatch stores the Tags sent with
# PutMetricAlarm on the alarm object itself and then cannot serialize the
# DescribeAlarms response that contains it. terraform-provider-aws 6.x talks to
# CloudWatch over the rpc-v2-cbor protocol, where that serialization failure is
# a hard 500 InternalError rather than the warning the older query protocol
# produces. Every read of a tagged alarm then fails, the provider retries it 25
# times, and terraform apply hangs for minutes before giving up. Alarms carry no
# cost allocation of their own, so dropping their tags is the cheapest way to
# keep one set of Terraform working against both targets. See
# docs/PARITY-NOTES.md.
provider "aws" {
  alias  = "untagged"
  region = var.aws_region

  access_key = var.aws_endpoint_url != "" ? "test" : null
  secret_key = var.aws_endpoint_url != "" ? "test" : null

  skip_credentials_validation = var.aws_endpoint_url != ""
  skip_metadata_api_check     = var.aws_endpoint_url != ""
  skip_requesting_account_id  = var.aws_endpoint_url != ""

  dynamic "endpoints" {
    for_each = var.aws_endpoint_url != "" ? [1] : []
    content {
      cloudwatch = var.aws_endpoint_url
    }
  }
}
