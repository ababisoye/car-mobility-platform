resource "aws_db_subnet_group" "this" {
  name       = "${var.name}-${var.environment}"
  subnet_ids = var.database_subnet_ids
  tags       = merge(var.tags, { Name = "${var.name}-${var.environment}-db-subnets" })
}

resource "aws_security_group" "database" {
  name_prefix = "${var.name}-${var.environment}-db-"
  description = "PostgreSQL access from the application security group only."
  vpc_id      = var.vpc_id

  ingress {
    description     = "PostgreSQL from application tier"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [var.application_security_group_id]
  }

  egress {
    description = "Return traffic within VPC"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, { Name = "${var.name}-${var.environment}-database-sg" })
  lifecycle { create_before_destroy = true }
}

resource "aws_db_instance" "this" {
  identifier = "${var.name}-${var.environment}"

  engine                       = "postgres"
  instance_class               = var.instance_class
  db_name                      = var.database_name
  username                     = "platform_admin"
  manage_master_user_password  = true
  port                         = 5432
  allocated_storage            = var.allocated_storage
  max_allocated_storage        = var.max_allocated_storage
  storage_type                 = "gp3"
  storage_encrypted            = true
  multi_az                     = var.multi_az
  publicly_accessible          = false
  db_subnet_group_name         = aws_db_subnet_group.this.name
  vpc_security_group_ids       = [aws_security_group.database.id]
  backup_retention_period      = var.backup_retention_days
  backup_window                = "01:00-02:00"
  maintenance_window           = "sun:03:00-sun:04:00"
  auto_minor_version_upgrade   = true
  deletion_protection          = var.deletion_protection
  skip_final_snapshot          = var.skip_final_snapshot
  final_snapshot_identifier    = var.skip_final_snapshot ? null : "${var.name}-${var.environment}-final"
  copy_tags_to_snapshot        = true
  performance_insights_enabled = false

  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]
  tags                            = merge(var.tags, { Name = "${var.name}-${var.environment}-postgres" })
}

