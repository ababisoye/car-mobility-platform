variable "aws_region" {
  description = "AWS Region for the zero-funding demo."
  type        = string
  default     = "af-south-1"
}

variable "aws_account_id" {
  description = "Twelve-digit AWS account ID allowed for deployment."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}$", var.aws_account_id))
    error_message = "aws_account_id must contain exactly 12 digits."
  }
}

variable "billing_alert_email" {
  description = "Email address that receives the USD 1 budget alerts."
  type        = string

  validation {
    condition     = can(regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", var.billing_alert_email))
    error_message = "Provide a valid billing alert email address."
  }
}

variable "allowed_origin" {
  description = "Browser origin allowed by CORS. Use * only for the initial public demo."
  type        = string
  default     = "*"
}

