variable "region" {
  description = "AWS region for the state bucket. Keep it the same as deploy/aws's region."
  type        = string
  default     = "us-east-1"
}

variable "bucket_name" {
  description = "Name of the state bucket. Empty: inbox-core-tfstate-<account id>-<region>, which is unique."
  type        = string
  default     = ""

  validation {
    condition     = var.bucket_name == "" || can(regex("^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$", var.bucket_name))
    error_message = "bucket_name must be a valid S3 bucket name (3-63 lowercase letters, digits, dots, hyphens)."
  }
}
