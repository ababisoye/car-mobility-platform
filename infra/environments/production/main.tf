module "foundation" {
  source = "../../stacks/foundation"

  application_name             = var.application_name
  environment                  = "production"
  vpc_cidr                     = "10.20.0.0/16"
  availability_zones           = ["${var.aws_region}a", "${var.aws_region}b"]
  public_subnet_cidrs          = ["10.20.0.0/24", "10.20.1.0/24"]
  application_subnet_cidrs     = ["10.20.10.0/24", "10.20.11.0/24"]
  database_subnet_cidrs        = ["10.20.20.0/24", "10.20.21.0/24"]
  single_nat_gateway           = true
  database_name                = "luxuryrental"
  database_instance_class      = "db.t4g.small"
  database_multi_az            = true
  database_deletion_protection = true
  database_skip_final_snapshot = false
  document_retention_days      = 2555
  monthly_budget_usd           = var.monthly_budget_usd
  cost_anomaly_threshold_usd   = 25
  billing_alert_email          = var.billing_alert_email
  tags                         = var.tags
}

