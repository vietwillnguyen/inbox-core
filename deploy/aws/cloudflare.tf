# Optional (manage_cloudflare = true): the tunnel, its three public hostnames
# pointing at the bundle's proxy, and proxied DNS records for them.
#
# The tunnel's token is then read by Terraform and written to Parameter Store,
# so it is in the Terraform state (encrypted, private, versioned bucket). With
# manage_cloudflare = false nothing secret is in the state: you make the tunnel
# in the dashboard and put its token in Parameter Store yourself (docs/aws.md).

locals {
  cloudflare = var.manage_cloudflare ? 1 : 0
  hostnames  = [var.demo_domain, var.demo_chat_host, var.demo_bot_host]
}

resource "cloudflare_zero_trust_tunnel_cloudflared" "demo" {
  count = local.cloudflare

  account_id = var.cloudflare_account_id
  name       = var.name
  config_src = "cloudflare"

  lifecycle {
    precondition {
      condition     = var.cloudflare_account_id != "" && var.cloudflare_zone_id != ""
      error_message = "manage_cloudflare needs cloudflare_account_id and cloudflare_zone_id."
    }
  }
}

resource "cloudflare_zero_trust_tunnel_cloudflared_config" "demo" {
  count = local.cloudflare

  account_id = var.cloudflare_account_id
  tunnel_id  = cloudflare_zero_trust_tunnel_cloudflared.demo[0].id

  config = {
    # Every host goes to the bundle's proxy on the compose network, which routes
    # by host name; anything else gets 404 at Cloudflare's edge.
    ingress = concat(
      [for host in local.hostnames : { hostname = host, service = "http://proxy:80" }],
      [{ service = "http_status:404" }],
    )
  }
}

resource "cloudflare_dns_record" "demo" {
  for_each = var.manage_cloudflare ? toset(local.hostnames) : toset([])

  zone_id = var.cloudflare_zone_id
  name    = each.value
  type    = "CNAME"
  content = "${cloudflare_zero_trust_tunnel_cloudflared.demo[0].id}.cfargotunnel.com"
  proxied = true
  ttl     = 1
  comment = "inbox-core demo, through the ${var.name} tunnel"
}

data "cloudflare_zero_trust_tunnel_cloudflared_token" "demo" {
  count = local.cloudflare

  account_id = var.cloudflare_account_id
  tunnel_id  = cloudflare_zero_trust_tunnel_cloudflared.demo[0].id
}

resource "aws_ssm_parameter" "tunnel_token" {
  #checkov:skip=CKV_AWS_337:the AWS managed key for SSM is enough for one token; a customer key costs a dollar a month
  count = local.cloudflare

  name        = "${var.parameter_prefix}/${var.secret_parameters["DEMO_TUNNEL_TOKEN"]}"
  description = "inbox-core demo: the Cloudflare tunnel's token (written by Terraform)"
  type        = "SecureString"
  value_wo    = data.cloudflare_zero_trust_tunnel_cloudflared_token.demo[0].token
  # Bump to write the token again (a write-only value is not compared).
  value_wo_version = 1
}
