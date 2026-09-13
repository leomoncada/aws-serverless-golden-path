#!/usr/bin/env bash
set -euo pipefail
awslocal s3api create-bucket --bucket tfstate
