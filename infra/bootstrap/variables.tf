variable "aws_region" {
  description = "AWS Region that will store Terraform state."
  type        = string
  default     = "af-south-1"
}

variable "aws_account_id" {
  description = "Twelve-digit AWS account ID allowed for bootstrap operations."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}$", var.aws_account_id))
    error_message = "aws_account_id must contain exactly 12 digits."
  }
}

variable "state_bucket_name" {
  description = "Globally unique S3 bucket name for Terraform state."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$", var.state_bucket_name))
    error_message = "Use a valid lowercase S3 bucket name between 3 and 63 characters."
  }
}

variable "application_name" {
  description = "Short application identifier used for tags."
  type        = string
  default     = "luxury-rental"
}

variable "owner" {
  description = "Team or person responsible for the infrastructure."
  type        = string
  default     = "cloud-engineering"
}

