variable "aws_region" {
  type    = string
  default = "af-south-1"
}
variable "aws_account_id" { type = string }
variable "application_name" {
  type    = string
  default = "luxury-rental"
}
variable "billing_alert_email" { type = string }
variable "monthly_budget_usd" {
  type    = number
  default = 120
}
variable "tags" {
  type    = map(string)
  default = { Owner = "cloud-engineering", CostCentre = "platform" }
}
