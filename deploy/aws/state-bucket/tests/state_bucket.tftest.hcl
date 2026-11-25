# Runs with mock providers: no AWS account and no credentials.
#   cd deploy/aws/state-bucket && terraform init -backend=false && terraform test

mock_provider "aws" {
  mock_data "aws_caller_identity" {
    defaults = {
      account_id = "123456789012"
    }
  }
}

run "defaults" {
  # Applied against the mock provider, so values such as the bucket's ARN are known.
  command = apply

  assert {
    condition     = aws_s3_bucket.state.bucket == "inbox-core-tfstate-123456789012-us-east-1"
    error_message = "the default bucket name is derived from the account and region"
  }

  assert {
    condition     = aws_s3_bucket_versioning.state.versioning_configuration[0].status == "Enabled"
    error_message = "state versions are kept"
  }

  assert {
    condition     = one(one(aws_s3_bucket_server_side_encryption_configuration.state.rule).apply_server_side_encryption_by_default).sse_algorithm == "AES256"
    error_message = "state is encrypted at rest"
  }

  assert {
    condition = alltrue([
      aws_s3_bucket_public_access_block.state.block_public_acls,
      aws_s3_bucket_public_access_block.state.block_public_policy,
      aws_s3_bucket_public_access_block.state.ignore_public_acls,
      aws_s3_bucket_public_access_block.state.restrict_public_buckets,
    ])
    error_message = "the bucket can never be public"
  }

  assert {
    condition     = jsondecode(aws_s3_bucket_policy.state.policy).Statement[0].Condition.Bool["aws:SecureTransport"] == "false" && jsondecode(aws_s3_bucket_policy.state.policy).Statement[0].Effect == "Deny"
    error_message = "requests without TLS are refused"
  }

  assert {
    condition     = strcontains(output.backend_hcl, "use_lockfile = true")
    error_message = "the backend uses S3's native locking"
  }
}

run "region_is_a_variable" {
  command = plan

  variables {
    region      = "eu-west-1"
    bucket_name = "my-state-bucket"
  }

  assert {
    condition     = aws_s3_bucket.state.bucket == "my-state-bucket" && output.region == "eu-west-1"
    error_message = "the region and bucket name follow the variables"
  }
}

run "bad_bucket_name" {
  command = plan

  variables {
    bucket_name = "Not_A_Bucket"
  }

  expect_failures = [var.bucket_name]
}
