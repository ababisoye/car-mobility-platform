provider "aws" {
  region              = var.aws_region
  allowed_account_ids = [var.aws_account_id]

  default_tags {
    tags = {
      Application = "luxury-rental"
      ManagedBy   = "Terraform"
      Purpose     = "github-release-identity"
    }
  }
}
