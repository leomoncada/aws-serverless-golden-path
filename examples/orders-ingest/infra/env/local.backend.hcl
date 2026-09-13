bucket                      = "tfstate"
key                         = "orders-ingest/terraform.tfstate"
region                      = "us-east-1"
endpoints                   = { s3 = "http://localhost:4566" }
access_key                  = "test"
secret_key                  = "test"
use_lockfile                = true
skip_credentials_validation = true
skip_metadata_api_check     = true
skip_requesting_account_id  = true
skip_region_validation      = true
use_path_style              = true
