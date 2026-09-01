output "foundation" {
  value = {
    vpc_id              = module.foundation.vpc_id
    documents_bucket_id = module.foundation.documents_bucket_id
    database_endpoint   = module.foundation.database_endpoint
  }
}

output "database_secret_arn" {
  value     = module.foundation.database_secret_arn
  sensitive = true
}

