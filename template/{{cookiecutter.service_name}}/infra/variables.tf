variable "aws_region" {
  type    = string
  default = "{{cookiecutter.aws_region}}"
}

variable "aws_endpoint_url" {
  description = "Set to a LocalStack endpoint to target it. Empty targets real AWS."
  type        = string
  default     = ""
}

variable "service_name" {
  type    = string
  default = "{{cookiecutter.service_name}}"
}
