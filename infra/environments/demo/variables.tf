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

variable "admin_password_hash" {
  description = "PBKDF2 password hash for the demo operations dashboard. Generate it with scripts/generate-admin-password-hash.py."
  type        = string
  sensitive   = true

  validation {
    condition     = can(regex("^[0-9]+:[A-Za-z0-9+/=]+:[A-Za-z0-9+/=]+$", var.admin_password_hash))
    error_message = "admin_password_hash must use the iterations:salt:digest format produced by the helper script."
  }
}

variable "payment_webhook_secret" {
  description = "Shared HMAC secret used to verify payment-provider webhook requests. Use at least 32 characters."
  type        = string
  sensitive   = true

  validation {
    condition     = length(var.payment_webhook_secret) >= 32
    error_message = "payment_webhook_secret must contain at least 32 characters."
  }
}
