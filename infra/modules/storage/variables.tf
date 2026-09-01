variable "name" { type = string }
variable "environment" { type = string }
variable "document_retention_days" {
  type    = number
  default = 2555
}
variable "noncurrent_version_retention_days" {
  type    = number
  default = 90
}
variable "tags" {
  type    = map(string)
  default = {}
}
