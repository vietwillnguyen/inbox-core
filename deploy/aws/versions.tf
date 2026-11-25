terraform {
  # 1.11: S3 native state locking (use_lockfile) is generally available, and
  # terraform test has mock providers. OpenTofu 1.10 or later reads this too.
  required_version = ">= 1.11"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.0, < 7.0"
    }
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = ">= 5.8, < 6.0"
    }
  }

  # Partial configuration: the values are in backend.hcl (see backend.hcl.example),
  # written after deploy/aws/state-bucket is applied. terraform init -backend-config=backend.hcl
  backend "s3" {}
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      project   = var.name
      managedBy = "terraform"
    }
  }
}

# Used only when manage_cloudflare is true. The token can also come from the
# CLOUDFLARE_API_TOKEN environment variable, which keeps it out of every file.
provider "cloudflare" {
  api_token = var.cloudflare_api_token
}
