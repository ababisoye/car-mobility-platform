variable "name" { type = string }
variable "environment" { type = string }
variable "monthly_budget_usd" { type = number }
variable "alert_email" { type = string }
variable "anomaly_threshold_usd" {
  type    = number
  default = 20
}
variable "tags" {
  type    = map(string)
  default = {}
}
