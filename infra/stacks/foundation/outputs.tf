output "vpc_id" { value = module.network.vpc_id }
output "public_subnet_ids" { value = module.network.public_subnet_ids }
output "application_subnet_ids" { value = module.network.application_subnet_ids }
output "database_subnet_ids" { value = module.network.database_subnet_ids }
output "application_security_group_id" { value = module.network.application_security_group_id }
output "documents_bucket_id" { value = module.storage.documents_bucket_id }
output "database_endpoint" { value = module.database.endpoint }
output "database_secret_arn" {
  value     = module.database.master_user_secret_arn
  sensitive = true
}
output "budget_name" { value = module.cost_controls.budget_name }
