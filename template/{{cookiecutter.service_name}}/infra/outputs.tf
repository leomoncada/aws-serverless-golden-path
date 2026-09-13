output "bucket_name" { value = module.ingest_bucket.id }
output "table_name" { value = module.records_table.name }
output "function_name" { value = module.processor.function_name }
output "dlq_url" { value = module.processor.dlq_url }
