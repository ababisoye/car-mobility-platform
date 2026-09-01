output "demo_url" {
  description = "Public URL for the zero-funding booking demo."
  value       = aws_lambda_function_url.application.function_url
}

output "bookings_table" {
  description = "DynamoDB table containing temporary demo requests."
  value       = aws_dynamodb_table.bookings.name
}

output "monthly_budget_usd" {
  description = "Notification threshold; AWS Budgets alerts do not automatically stop usage."
  value       = 1
}

