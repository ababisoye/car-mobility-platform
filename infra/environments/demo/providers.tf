provider "aws" {
  region              = var.aws_region
  allowed_account_ids = [var.aws_account_id]

  default_tags {
    tags = {
      Application = "luxury-rental"
      Environment = "demo"
      ManagedBy   = "Terraform"
      CostMode    = "zero-funding"
      Owner       = "cloud-engineering"
    }
  }
}

