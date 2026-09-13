resource "aws_dynamodb_table" "this" {
  name         = "${var.service_name}-records"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "record_id"
  attribute {
    name = "record_id"
    type = "S"
  }
}
