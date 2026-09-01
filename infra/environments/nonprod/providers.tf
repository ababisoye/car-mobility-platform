provider "aws" {
  region              = var.aws_region
  allowed_account_ids = [var.aws_account_id]

  default_tags {
    tags = merge(var.tags, {
      Application = var.application_name
      Environment = "nonprod"
      ManagedBy   = "Terraform"
    })
  }
}

