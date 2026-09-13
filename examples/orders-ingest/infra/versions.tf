terraform {
  # 1.11 is the floor because the S3 backend locks with use_lockfile.
  required_version = ">= 1.11"
  required_providers {
    aws     = { source = "hashicorp/aws", version = "~> 6.0" }
    archive = { source = "hashicorp/archive", version = "~> 2.0" }
  }
  backend "s3" {}
}
