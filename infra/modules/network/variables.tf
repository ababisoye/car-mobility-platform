variable "name" { type = string }
variable "environment" { type = string }
variable "vpc_cidr" { type = string }
variable "availability_zones" {
  type = list(string)
  validation {
    condition     = length(var.availability_zones) == 2
    error_message = "Exactly two Availability Zones are required."
  }
}
variable "public_subnet_cidrs" {
  type = list(string)
  validation {
    condition     = length(var.public_subnet_cidrs) == 2
    error_message = "Exactly two public subnet CIDRs are required."
  }
}
variable "application_subnet_cidrs" {
  type = list(string)
  validation {
    condition     = length(var.application_subnet_cidrs) == 2
    error_message = "Exactly two application subnet CIDRs are required."
  }
}
variable "database_subnet_cidrs" {
  type = list(string)
  validation {
    condition     = length(var.database_subnet_cidrs) == 2
    error_message = "Exactly two database subnet CIDRs are required."
  }
}
variable "single_nat_gateway" {
  description = "Use one NAT gateway for cost control; false creates one per AZ."
  type        = bool
  default     = true
}
variable "tags" {
  type    = map(string)
  default = {}
}
