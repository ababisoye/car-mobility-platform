variable "aws_region" {
  description = "AWS Region containing the demo Lambda function."
  type        = string
  default     = "af-south-1"
}

variable "aws_account_id" {
  description = "Twelve-digit AWS account ID that owns the release role."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}$", var.aws_account_id))
    error_message = "aws_account_id must contain exactly 12 digits."
  }
}

variable "github_repository" {
  description = "GitHub repository allowed to request release credentials."
  type        = string
  default     = "ababisoye/car-mobility-platform"
}

variable "github_environment" {
  description = "Protected GitHub environment required for a release."
  type        = string
  default     = "demo-release"
}
