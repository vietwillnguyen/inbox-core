# The S3 bucket that holds deploy/aws's Terraform state, with versioning,
# encryption, no public access, TLS-only access and S3's native state locking
# (use_lockfile in the backend; no DynamoDB table). Applied once, before
# deploy/aws, with local state; see docs/aws.md for the order.

terraform {
  required_version = ">= 1.11"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.0, < 7.0"
    }
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      project   = "inbox-core-demo"
      managedBy = "terraform"
    }
  }
}

data "aws_caller_identity" "current" {}

locals {
  bucket_name = coalesce(var.bucket_name, "inbox-core-tfstate-${data.aws_caller_identity.current.account_id}-${var.region}")
}

# Access logging, replication and event notifications are left out on purpose:
# one person's state for one small demo, kept with versioning.
resource "aws_s3_bucket" "state" {
  #checkov:skip=CKV_AWS_18:access logs for a single-user state bucket would cost more than they tell
  #checkov:skip=CKV_AWS_144:cross-region replication is out of proportion for a demo's state
  #checkov:skip=CKV2_AWS_62:nothing reacts to state writes
  #checkov:skip=CKV_AWS_145:SSE-S3 is enough here; a customer key costs a dollar a month and adds a key policy to keep

  bucket = local.bucket_name

  # Losing this bucket loses track of everything deploy/aws created.
  force_destroy = false

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "state" {
  bucket                  = aws_s3_bucket.state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "state" {
  bucket = aws_s3_bucket.state.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

# Old state versions are kept for 90 days, then removed; so are failed uploads.
resource "aws_s3_bucket_lifecycle_configuration" "state" {
  bucket = aws_s3_bucket.state.id

  rule {
    id     = "expire-old-versions"
    status = "Enabled"
    filter {}

    noncurrent_version_expiration {
      noncurrent_days = 90
    }
    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

resource "aws_s3_bucket_policy" "state" {
  bucket = aws_s3_bucket.state.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "DenyInsecureTransport"
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:*"
      Resource  = [aws_s3_bucket.state.arn, "${aws_s3_bucket.state.arn}/*"]
      Condition = { Bool = { "aws:SecureTransport" = "false" } }
    }]
  })

  depends_on = [aws_s3_bucket_public_access_block.state]
}
