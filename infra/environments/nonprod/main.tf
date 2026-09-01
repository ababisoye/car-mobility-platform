module "foundation" {
  source = "../../stacks/foundation"

  application_name             = var.application_name
  environment                  = "nonprod"
  vpc_cidr                     = "10.10.0.0/16"
  availability_zones           = ["${var.aws_region}a", "${var.aws_region}b"]
  public_subnet_cidrs          = ["10.10.0.0/24", "10.10.1.0/24"]
  application_subnet_cidrs     = ["10.10.10.0/24", "10.10.11.0/24"]
  database_subnet_cidrs        = ["10.10.20.0/24", "10.10.21.0/24"]
  single_nat_gateway           = true
  database_name                = "luxuryrental"
  database_instance_class      = "db.t4g.micro"
  database_multi_az            = false
  database_deletion_protection = false
  database_skip_final_snapshot = true
  document_retention_days      = 365
  monthly_budget_usd           = var.monthly_budget_usd
  cost_anomaly_threshold_usd   = 10
  billing_alert_email          = var.billing_alert_email
  tags                         = var.tags
}

