# Fill bucket with a real state bucket before first use.
# See docs/runbooks/first-aws-deploy.md. Never run against AWS by accident:
# this file has no endpoints block, so it targets the real service.
bucket       = "CHANGE-ME-terraform-state"
key          = "{{cookiecutter.service_name}}/terraform.tfstate"
region       = "{{cookiecutter.aws_region}}"
use_lockfile = true
