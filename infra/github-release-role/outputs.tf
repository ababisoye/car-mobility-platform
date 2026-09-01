output "release_role_arn" {
  description = "Store this ARN as the AWS_RELEASE_ROLE_ARN secret on the protected GitHub environment."
  value       = aws_iam_role.github_release.arn
}
