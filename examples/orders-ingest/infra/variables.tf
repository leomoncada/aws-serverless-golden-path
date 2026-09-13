variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "aws_endpoint_url" {
  description = "Set to a LocalStack endpoint to target it. Empty targets real AWS."
  type        = string
  default     = ""
}

variable "service_name" {
  type    = string
  default = "orders-ingest"
}
