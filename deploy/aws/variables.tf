# --- where and what --------------------------------------------------------

variable "region" {
  description = "AWS region for everything in this configuration."
  type        = string
  default     = "us-east-1"
}

variable "name" {
  description = "Name prefix for every resource, and the project tag."
  type        = string
  default     = "inbox-core-demo"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,30}$", var.name))
    error_message = "name must be 2-31 lowercase letters, digits or hyphens, starting with a letter."
  }
}

variable "instance_type" {
  description = "EC2 instance type. The bundle uses about 2 GiB; 4 GB leaves room for builds. Must match architecture."
  type        = string
  default     = "t4g.medium"
}

variable "architecture" {
  description = "CPU architecture of the instance type and the Ubuntu image: arm64 (Graviton, t4g) or amd64 (t3)."
  type        = string
  default     = "arm64"

  validation {
    condition     = contains(["arm64", "amd64"], var.architecture)
    error_message = "architecture must be arm64 or amd64."
  }
}

variable "cpu_credits" {
  description = "Burstable CPU credit mode: unlimited (default for t4g; a sustained load above baseline is billed) or standard (throttled to baseline instead)."
  type        = string
  default     = "unlimited"

  validation {
    condition     = contains(["unlimited", "standard"], var.cpu_credits)
    error_message = "cpu_credits must be unlimited or standard."
  }
}

variable "ami_ssm_parameter" {
  description = "Public SSM parameter holding the image ID. Empty: Canonical's Ubuntu 24.04 LTS for the architecture."
  type        = string
  default     = ""
}

variable "root_volume_size_gb" {
  description = "Size of the encrypted gp3 root volume. Images take about 6 GB."
  type        = number
  default     = 30

  validation {
    condition     = var.root_volume_size_gb >= 20 && var.root_volume_size_gb <= 200
    error_message = "root_volume_size_gb must be between 20 and 200."
  }
}

variable "vpc_cidr" {
  description = "CIDR of the demo's own VPC (one public subnet, no inbound rules anywhere)."
  type        = string
  default     = "10.42.0.0/24"

  validation {
    condition     = can(cidrhost(var.vpc_cidr, 0))
    error_message = "vpc_cidr must be a CIDR block."
  }
}

# --- what the host deploys -------------------------------------------------

variable "repository_url" {
  description = "Public git URL the host clones and polls for release tags. No credentials: it must be public."
  type        = string
  default     = "https://github.com/vietwillnguyen/inbox-core.git"

  validation {
    condition     = can(regex("^https://", var.repository_url))
    error_message = "repository_url must be an https URL."
  }
}

variable "tag_pattern" {
  description = "Git glob of the release tags the host deploys."
  type        = string
  default     = "demo-v*"

  validation {
    condition     = can(regex("^[A-Za-z0-9._*/-]+$", var.tag_pattern))
    error_message = "tag_pattern may contain letters, digits, . _ - / and *."
  }
}

variable "initial_tag" {
  description = "The release tag a fresh instance starts at (it must exist and contain deploy/gitops). Read only at first boot; later tags arrive through the timer."
  type        = string

  validation {
    condition     = can(regex("^[A-Za-z0-9._/-]+$", var.initial_tag))
    error_message = "initial_tag must be a plain tag name."
  }
}

variable "deploy_interval" {
  description = "How often the host checks for a new tag, in systemd's time syntax."
  type        = string
  default     = "5min"

  validation {
    condition     = can(regex("^[0-9]+(s|min|h)$", var.deploy_interval))
    error_message = "deploy_interval must look like 30s, 5min or 1h."
  }
}

variable "auto_reboot_time" {
  description = "UTC time at which the host reboots after a security update that needs it, or off."
  type        = string
  default     = "04:30"

  validation {
    condition     = var.auto_reboot_time == "off" || can(regex("^[0-2][0-9]:[0-5][0-9]$", var.auto_reboot_time))
    error_message = "auto_reboot_time must be HH:MM or off."
  }
}

# --- the bundle's settings (not secret) -------------------------------------

variable "demo_domain" {
  description = "The visitor page's host name."
  type        = string
  default     = "demo.vnlabs.dev"

  validation {
    condition     = can(regex("^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$", var.demo_domain))
    error_message = "demo_domain must be a lowercase host name."
  }
}

variable "demo_chat_host" {
  description = "Chatwoot's host name. One level below the zone, so Cloudflare's free certificate covers it."
  type        = string
  default     = "demo-chat.vnlabs.dev"

  validation {
    condition     = can(regex("^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$", var.demo_chat_host))
    error_message = "demo_chat_host must be a lowercase host name."
  }
}

variable "demo_bot_host" {
  description = "The draft tab's host name. One level below the zone, so Cloudflare's free certificate covers it."
  type        = string
  default     = "demo-bot.vnlabs.dev"

  validation {
    condition     = can(regex("^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$", var.demo_bot_host))
    error_message = "demo_bot_host must be a lowercase host name."
  }
}

variable "demo_model" {
  description = "The bundle's model: gemini, or stand-in (no key, not a model)."
  type        = string
  default     = "gemini"

  validation {
    condition     = contains(["gemini", "stand-in"], var.demo_model)
    error_message = "demo_model must be gemini or stand-in."
  }
}

variable "demo_daily_budget_usd" {
  description = "The most the gateway may spend on the model in a day, in US dollars."
  type        = string
  default     = "1.00"

  validation {
    condition     = can(regex("^[0-9]+(\\.[0-9]{1,2})?$", var.demo_daily_budget_usd))
    error_message = "demo_daily_budget_usd must be a number such as 1.00."
  }
}

variable "demo_admin_email" {
  description = "The Chatwoot dashboard sign-in. Chatwoot sends it no mail; any address you recognise works."
  type        = string
  default     = "owner@quillmoor.example"

  validation {
    condition     = can(regex("^[^@\\s'\"]+@[^@\\s'\"]+$", var.demo_admin_email))
    error_message = "demo_admin_email must be an email address."
  }
}

variable "demo_extra_settings" {
  description = "Further bundle settings from deploy/demo/.env.example (rate limits, reset period), as NAME = value. Never secrets."
  type        = map(string)
  default     = {}

  validation {
    condition = alltrue([for k, v in var.demo_extra_settings :
      can(regex("^DEMO_[A-Z0-9_]+$", k)) && can(regex("^[A-Za-z0-9._:/@-]*$", v)) && !contains(["DEMO_TUNNEL_TOKEN", "DEMO_ENV_FILE"], k)
    ])
    error_message = "demo_extra_settings keys must be DEMO_* names (not DEMO_TUNNEL_TOKEN) and values plain words."
  }
}

# --- secrets: names only; the values never pass through Terraform ------------

variable "parameter_prefix" {
  description = "Parameter Store path under which the secrets live."
  type        = string
  default     = "/inbox-core/demo"

  validation {
    condition     = can(regex("^(/[A-Za-z0-9_.-]+)+$", var.parameter_prefix))
    error_message = "parameter_prefix must look like /inbox-core/demo."
  }
}

variable "secret_parameters" {
  description = "The bundle's secrets: environment variable name => parameter name under parameter_prefix. Create each one as a SecureString yourself (docs/aws.md)."
  type        = map(string)
  default = {
    GEMINI_API_KEY    = "gemini-api-key"
    DEMO_TUNNEL_TOKEN = "cloudflare-tunnel-token"
  }

  validation {
    condition = alltrue([for k, v in var.secret_parameters :
      can(regex("^[A-Z_][A-Z0-9_]*$", k)) && can(regex("^[A-Za-z0-9_.-]+$", v))
    ])
    error_message = "secret_parameters keys must be variable names and values plain parameter names."
  }

  validation {
    condition     = contains(keys(var.secret_parameters), "DEMO_TUNNEL_TOKEN")
    error_message = "secret_parameters must include DEMO_TUNNEL_TOKEN: the instance is reachable only through the tunnel."
  }
}

# --- cost guard ---------------------------------------------------------------

variable "budget_limit_usd" {
  description = "Monthly AWS budget in US dollars. Mail goes out at 80% and 100% of actual spend and at 100% forecast."
  type        = number
  default     = 40

  validation {
    condition     = var.budget_limit_usd > 0
    error_message = "budget_limit_usd must be positive."
  }
}

variable "budget_email" {
  description = "Address the budget alerts go to. Set it in terraform.tfvars, which is never committed."
  type        = string

  validation {
    condition     = can(regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", var.budget_email))
    error_message = "budget_email must be an email address."
  }
}

# --- optional: the tunnel and DNS records through Cloudflare's API -------------

variable "manage_cloudflare" {
  description = "Create the tunnel, its public hostnames and the DNS records with the Cloudflare provider. Needs cloudflare_account_id, cloudflare_zone_id and an API token. When false, make the tunnel in the dashboard (docs/aws.md)."
  type        = bool
  default     = false
}

variable "cloudflare_account_id" {
  description = "Cloudflare account ID (manage_cloudflare only)."
  type        = string
  default     = ""
}

variable "cloudflare_zone_id" {
  description = "Zone ID of the domain the host names are in (manage_cloudflare only)."
  type        = string
  default     = ""
}

variable "cloudflare_api_token" {
  description = "Cloudflare API token (manage_cloudflare only). Prefer the CLOUDFLARE_API_TOKEN environment variable."
  type        = string
  default     = null
  sensitive   = true
}
