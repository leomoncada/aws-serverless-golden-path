module "ingest_bucket" {
  source       = "./modules/ingest-bucket"
  service_name = var.service_name
}

module "records_table" {
  source       = "./modules/records-table"
  service_name = var.service_name
}

module "processor" {
  source       = "./modules/processor-lambda"
  service_name = var.service_name
  runtime      = "python3.12"
  bucket_arn   = module.ingest_bucket.arn
  bucket_id    = module.ingest_bucket.id
  table_name   = module.records_table.name
  table_arn    = module.records_table.arn
}
