locals {
  name = "luxury-rental-demo"
}

resource "aws_dynamodb_table" "bookings" {
  name           = "${local.name}-bookings"
  billing_mode   = "PROVISIONED"
  read_capacity  = 1
  write_capacity = 1
  hash_key       = "booking_id"

  attribute {
    name = "booking_id"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  point_in_time_recovery {
    enabled = false
  }

  deletion_protection_enabled = false
}

resource "aws_dynamodb_table" "vehicles" {
  name           = "${local.name}-vehicles"
  billing_mode   = "PROVISIONED"
  read_capacity  = 1
  write_capacity = 1
  hash_key       = "vehicle_id"

  attribute {
    name = "vehicle_id"
    type = "S"
  }
}

resource "aws_dynamodb_table" "chauffeurs" {
  name           = "${local.name}-chauffeurs"
  billing_mode   = "PROVISIONED"
  read_capacity  = 1
  write_capacity = 1
  hash_key       = "chauffeur_id"

  attribute {
    name = "chauffeur_id"
    type = "S"
  }
}

resource "aws_dynamodb_table" "quotes" {
  name           = "${local.name}-quotes"
  billing_mode   = "PROVISIONED"
  read_capacity  = 1
  write_capacity = 1
  hash_key       = "quote_id"

  attribute {
    name = "quote_id"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }
}

resource "aws_dynamodb_table" "notifications" {
  name           = "${local.name}-notifications"
  billing_mode   = "PROVISIONED"
  read_capacity  = 1
  write_capacity = 1
  hash_key       = "notification_id"

  attribute {
    name = "notification_id"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }
}

resource "aws_iam_role" "lambda" {
  name = "${local.name}-lambda"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "lambda" {
  name = "${local.name}-minimum-access"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "BookingTable"
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:Scan",
          "dynamodb:TransactWriteItems",
          "dynamodb:UpdateItem"
        ]
        Resource = [
          aws_dynamodb_table.bookings.arn,
          aws_dynamodb_table.vehicles.arn,
          aws_dynamodb_table.chauffeurs.arn,
          aws_dynamodb_table.quotes.arn,
          aws_dynamodb_table.notifications.arn
        ]
      },
      {
        Sid    = "FunctionLogging"
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "${aws_cloudwatch_log_group.application.arn}:*"
      }
    ]
  })
}

resource "aws_cloudwatch_log_group" "application" {
  name              = "/aws/lambda/${local.name}"
  retention_in_days = 1
}

resource "aws_lambda_function" "application" {
  function_name = local.name
  description   = "Cost-constrained public demo for chauffeur-driven booking requests."
  role          = aws_iam_role.lambda.arn
  handler       = "handler.lambda_handler"
  runtime       = "python3.13"
  architectures = ["arm64"]

  filename         = "${path.module}/luxury-rental-demo.zip"
  source_code_hash = filebase64sha256("${path.module}/luxury-rental-demo.zip")

  memory_size                    = 128
  timeout                        = 5
  reserved_concurrent_executions = 1

  environment {
    variables = {
      BOOKINGS_TABLE      = aws_dynamodb_table.bookings.name
      VEHICLES_TABLE      = aws_dynamodb_table.vehicles.name
      CHAUFFEURS_TABLE    = aws_dynamodb_table.chauffeurs.name
      QUOTES_TABLE        = aws_dynamodb_table.quotes.name
      NOTIFICATIONS_TABLE = aws_dynamodb_table.notifications.name
      ALLOWED_ORIGIN      = var.allowed_origin
      BOOKING_TTL_DAYS    = "30"
      ADMIN_PASSWORD_HASH = var.admin_password_hash
    }
  }

  depends_on = [aws_cloudwatch_log_group.application]
}

resource "aws_lambda_function_url" "application" {
  function_name      = aws_lambda_function.application.function_name
  authorization_type = "NONE"

  cors {
    allow_credentials = false
    allow_headers     = ["content-type", "x-admin-password"]
    allow_methods     = ["GET", "POST", "PATCH"]
    allow_origins     = [var.allowed_origin]
    expose_headers    = ["content-type"]
    max_age           = 300
  }
}

resource "aws_lambda_permission" "public_url" {
  statement_id           = "AllowPublicFunctionUrl"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.application.function_name
  principal              = "*"
  function_url_auth_type = "NONE"
}

resource "aws_lambda_permission" "public_invoke" {
  statement_id             = "AllowPublicFunctionInvocationViaUrl"
  action                   = "lambda:InvokeFunction"
  function_name            = aws_lambda_function.application.function_name
  principal                = "*"
  invoked_via_function_url = true
}

resource "aws_budgets_budget" "demo" {
  name         = "${local.name}-one-dollar-guardrail"
  budget_type  = "COST"
  limit_amount = "1"
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 1
    threshold_type             = "ABSOLUTE_VALUE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.billing_alert_email]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 1
    threshold_type             = "ABSOLUTE_VALUE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.billing_alert_email]
  }
}
