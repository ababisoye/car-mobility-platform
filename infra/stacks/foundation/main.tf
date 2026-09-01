module "network" {
  source = "../../modules/network"

  name                     = var.application_name
  environment              = var.environment
  vpc_cidr                 = var.vpc_cidr
  availability_zones       = var.availability_zones
  public_subnet_cidrs      = var.public_subnet_cidrs
  application_subnet_cidrs = var.application_subnet_cidrs
  database_subnet_cidrs    = var.database_subnet_cidrs
  single_nat_gateway       = var.single_nat_gateway
  tags                     = var.tags
}

module "storage" {
  source = "../../modules/storage"

  name                    = var.application_name
  environment             = var.environment
  document_retention_days = var.document_retention_days
  tags                    = var.tags
}

module "database" {
  source = "../../modules/database"

  name                          = var.application_name
  environment                   = var.environment
  vpc_id                        = module.network.vpc_id
  database_subnet_ids           = module.network.database_subnet_ids
  application_security_group_id = module.network.application_security_group_id
  database_name                 = var.database_name
  instance_class                = var.database_instance_class
  multi_az                      = var.database_multi_az
  deletion_protection           = var.database_deletion_protection
  skip_final_snapshot           = var.database_skip_final_snapshot
  tags                          = var.tags
}

module "cost_controls" {
  source = "../../modules/cost-controls"

  name                  = var.application_name
  environment           = var.environment
  monthly_budget_usd    = var.monthly_budget_usd
  anomaly_threshold_usd = var.cost_anomaly_threshold_usd
  alert_email           = var.billing_alert_email
  tags                  = var.tags
}

