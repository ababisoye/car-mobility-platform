variable "name" { type = string }
variable "environment" { type = string }
variable "vpc_id" { type = string }
variable "database_subnet_ids" { type = list(string) }
variable "application_security_group_id" { type = string }
variable "database_name" {
  type    = string
  default = "luxuryrental"
}
variable "instance_class" { type = string }
variable "allocated_storage" {
  type    = number
  default = 20
}
variable "max_allocated_storage" {
  type    = number
  default = 100
}
variable "multi_az" { type = bool }
variable "backup_retention_days" {
  type    = number
  default = 14
}
variable "deletion_protection" { type = bool }
variable "skip_final_snapshot" { type = bool }
variable "tags" {
  type    = map(string)
  default = {}
}
