variable "application_name" { type = string }
variable "environment" { type = string }
variable "vpc_cidr" { type = string }
variable "availability_zones" { type = list(string) }
variable "public_subnet_cidrs" { type = list(string) }
variable "application_subnet_cidrs" { type = list(string) }
variable "database_subnet_cidrs" { type = list(string) }
variable "single_nat_gateway" { type = bool }
variable "database_name" { type = string }
variable "database_instance_class" { type = string }
variable "database_multi_az" { type = bool }
variable "database_deletion_protection" { type = bool }
variable "database_skip_final_snapshot" { type = bool }
variable "document_retention_days" { type = number }
variable "monthly_budget_usd" { type = number }
variable "cost_anomaly_threshold_usd" { type = number }
variable "billing_alert_email" { type = string }
variable "tags" {
  type    = map(string)
  default = {}
}
