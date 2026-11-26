output "bucket" {
  description = "The state bucket's name, for deploy/aws/backend.hcl."
  value       = aws_s3_bucket.state.bucket
}

output "region" {
  description = "The state bucket's region, for deploy/aws/backend.hcl."
  value       = var.region
}

output "backend_hcl" {
  description = "The contents of deploy/aws/backend.hcl."
  value       = <<-HCL
    bucket       = "${aws_s3_bucket.state.bucket}"
    key          = "inbox-core/demo/terraform.tfstate"
    region       = "${var.region}"
    encrypt      = true
    use_lockfile = true
  HCL
}
