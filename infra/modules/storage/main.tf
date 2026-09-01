data "aws_caller_identity" "current" {}

resource "aws_s3_bucket" "documents" {
  bucket_prefix = "${var.name}-${var.environment}-documents-${data.aws_caller_identity.current.account_id}-"
  force_destroy = false
  tags          = merge(var.tags, { Name = "${var.name}-${var.environment}-documents", DataClass = "confidential" })
}

resource "aws_s3_bucket_public_access_block" "documents" {
  bucket = aws_s3_bucket.documents.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "documents" {
  bucket = aws_s3_bucket.documents.id
  rule { object_ownership = "BucketOwnerEnforced" }
}

resource "aws_s3_bucket_versioning" "documents" {
  bucket = aws_s3_bucket.documents.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "documents" {
  bucket = aws_s3_bucket.documents.id
  rule {
    bucket_key_enabled = true
    apply_server_side_encryption_by_default { sse_algorithm = "aws:kms" }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "documents" {
  bucket = aws_s3_bucket.documents.id

  rule {
    id     = "document-retention"
    status = "Enabled"

    filter {}

    expiration { days = var.document_retention_days }
    noncurrent_version_expiration { noncurrent_days = var.noncurrent_version_retention_days }
    abort_incomplete_multipart_upload { days_after_initiation = 7 }
  }

  depends_on = [aws_s3_bucket_versioning.documents]
}

resource "aws_s3_bucket_policy" "documents" {
  bucket = aws_s3_bucket.documents.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "DenyInsecureTransport"
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:*"
      Resource  = [aws_s3_bucket.documents.arn, "${aws_s3_bucket.documents.arn}/*"]
      Condition = { Bool = { "aws:SecureTransport" = "false" } }
    }]
  })
}

