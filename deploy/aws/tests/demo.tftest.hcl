# The demo's important properties, checked with mock providers: no AWS or
# Cloudflare account, no credentials, nothing created.
#   cd deploy/aws && terraform init -backend=false && terraform test

mock_provider "aws" {
  mock_data "aws_caller_identity" {
    defaults = { account_id = "123456789012" }
  }
  mock_data "aws_partition" {
    defaults = { partition = "aws" }
  }
  mock_data "aws_ec2_instance_type_offerings" {
    defaults = { locations = ["us-east-1c", "us-east-1a", "us-east-1b"] }
  }
  mock_data "aws_ssm_parameter" {
    defaults = { insecure_value = "ami-0123456789abcdef0", value = "ami-0123456789abcdef0" }
  }
}

mock_provider "cloudflare" {
  mock_data "cloudflare_zero_trust_tunnel_cloudflared_token" {
    defaults = { token = "mock-tunnel-token" }
  }
  mock_resource "cloudflare_zero_trust_tunnel_cloudflared" {
    defaults = { id = "00000000-0000-4000-8000-000000000000" }
  }
}

variables {
  initial_tag  = "demo-v0.1.0"
  budget_email = "alerts@example.com"
}

run "defaults" {
  command = apply

  # --- nothing reaches in -----------------------------------------------------
  assert {
    condition     = length(aws_security_group.instance.ingress) == 0
    error_message = "the instance's security group has no inbound rule"
  }
  assert {
    condition     = length(aws_default_security_group.demo.ingress) == 0 && length(aws_default_security_group.demo.egress) == 0
    error_message = "the VPC's default security group allows nothing"
  }
  assert {
    condition     = jsonencode(sort([for rule in aws_security_group.instance.egress : "${rule.protocol}/${rule.from_port}-${rule.to_port}"])) == jsonencode(["tcp/443-443", "tcp/7844-7844", "tcp/80-80", "udp/7844-7844"])
    error_message = "outbound is limited to HTTP, HTTPS and the tunnel's port"
  }
  assert {
    condition     = !aws_subnet.demo.map_public_ip_on_launch
    error_message = "the subnet does not hand out public addresses to whatever is launched in it"
  }

  # --- the instance -------------------------------------------------------------
  assert {
    condition     = aws_instance.demo.metadata_options[0].http_tokens == "required"
    error_message = "IMDSv2 is required"
  }
  assert {
    condition     = aws_instance.demo.metadata_options[0].http_put_response_hop_limit == 1
    error_message = "containers cannot reach the instance metadata service"
  }
  assert {
    condition     = aws_instance.demo.root_block_device[0].encrypted && aws_instance.demo.root_block_device[0].volume_type == "gp3" && aws_instance.demo.root_block_device[0].volume_size == 30
    error_message = "the root volume is an encrypted 30 GB gp3 volume"
  }
  assert {
    condition     = aws_instance.demo.instance_type == "t4g.medium" && aws_instance.demo.ami == "ami-0123456789abcdef0"
    error_message = "a t4g.medium from the looked-up image by default"
  }
  assert {
    condition     = data.aws_ssm_parameter.ami.name == "/aws/service/canonical/ubuntu/server/24.04/stable/current/arm64/hvm/ebs-gp3/ami-id"
    error_message = "the image is Canonical's Ubuntu 24.04 for arm64"
  }
  assert {
    condition     = aws_subnet.demo.availability_zone == "us-east-1a"
    error_message = "the first zone (in name order) that offers the instance type"
  }

  # --- the role reads the named parameters and nothing else --------------------
  assert {
    condition     = aws_iam_role_policy_attachment.ssm_core.policy_arn == "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
    error_message = "Session Manager through the managed-instance policy"
  }
  assert {
    condition = jsondecode(aws_iam_role_policy.read_secrets.policy).Statement[0] == {
      Sid    = "ReadTheDemoSecrets"
      Effect = "Allow"
      Action = ["ssm:GetParameter", "ssm:GetParameters"]
      Resource = [
        "arn:aws:ssm:us-east-1:123456789012:parameter/inbox-core/demo/cloudflare-tunnel-token",
        "arn:aws:ssm:us-east-1:123456789012:parameter/inbox-core/demo/gemini-api-key",
      ]
    }
    error_message = "the role may read exactly the two named parameters"
  }
  assert {
    condition = (
      jsondecode(aws_iam_role_policy.read_secrets.policy).Statement[1].Effect == "Deny" &&
      jsondecode(aws_iam_role_policy.read_secrets.policy).Statement[1].NotResource == jsondecode(aws_iam_role_policy.read_secrets.policy).Statement[0].Resource &&
      contains(jsondecode(aws_iam_role_policy.read_secrets.policy).Statement[1].Action, "ssm:GetParametersByPath")
    )
    error_message = "every other parameter is denied, overriding the managed policy's ssm:GetParameter on *"
  }
  assert {
    condition     = !strcontains(aws_iam_role_policy.read_secrets.policy, "*")
    error_message = "no wildcard in the secrets policy"
  }

  # --- the user data carries no secret ------------------------------------------
  assert {
    condition     = startswith(aws_instance.demo.user_data, "#cloud-config\n")
    error_message = "the user data is cloud-config"
  }
  assert {
    condition     = can(yamldecode(aws_instance.demo.user_data))
    error_message = "the user data is valid YAML"
  }
  assert {
    condition = alltrue([for needle in [
      "DEMO_DOMAIN=demo.vnlabs.dev", "DEMO_CHAT_HOST=demo-chat.vnlabs.dev", "DEMO_TUNNEL=on", "refs/tags/demo-v0.1.0",
      "GEMINI_API_KEY=/inbox-core/demo/gemini-api-key", "AWS_REGION=us-east-1", "--secrets-command",
    ] : strcontains(aws_instance.demo.user_data, needle)])
    error_message = "the user data pins the initial tag, writes the settings and names the parameters"
  }
  assert {
    condition     = !can(regex("(?m)^\\s*(GEMINI_API_KEY|DEMO_TUNNEL_TOKEN)=[^/]", aws_instance.demo.user_data))
    error_message = "the user data never holds a secret's value, only parameter names"
  }
  assert {
    condition     = length(yamldecode(aws_instance.demo.user_data).write_files) == 3
    error_message = "the settings, the parameter names and the secrets step are written"
  }

  # --- the cost guard ------------------------------------------------------------
  assert {
    condition     = aws_budgets_budget.monthly.limit_amount == "40.00" && aws_budgets_budget.monthly.time_unit == "MONTHLY" && aws_budgets_budget.monthly.limit_unit == "USD"
    error_message = "a 40 USD monthly budget"
  }
  assert {
    condition     = length(aws_budgets_budget.monthly.notification) == 3 && alltrue([for n in aws_budgets_budget.monthly.notification : n.subscriber_email_addresses == toset(["alerts@example.com"])])
    error_message = "three alerts, all to the configured address"
  }

  # --- Cloudflare is off unless asked for -----------------------------------------
  assert {
    condition     = length(cloudflare_zero_trust_tunnel_cloudflared.demo) == 0 && length(cloudflare_dns_record.demo) == 0 && length(aws_ssm_parameter.tunnel_token) == 0
    error_message = "nothing is created in Cloudflare, and no parameter value is written, by default"
  }
}

run "region_and_instance_type_are_variables" {
  command = plan

  variables {
    region              = "eu-west-1"
    instance_type       = "t3.medium"
    architecture        = "amd64"
    root_volume_size_gb = 40
    budget_limit_usd    = 25
  }

  assert {
    condition     = aws_instance.demo.instance_type == "t3.medium" && aws_instance.demo.root_block_device[0].volume_size == 40
    error_message = "the instance type and volume size follow the variables"
  }
  assert {
    condition     = data.aws_ssm_parameter.ami.name == "/aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id"
    error_message = "the image follows the architecture"
  }
  assert {
    condition     = output.region == "eu-west-1" && strcontains(aws_instance.demo.user_data, "AWS_REGION=eu-west-1")
    error_message = "the region follows the variable, on the host too"
  }
  assert {
    condition     = aws_budgets_budget.monthly.limit_amount == "25.00"
    error_message = "the budget follows the variable"
  }
}

run "cloudflare_managed" {
  command = apply

  variables {
    manage_cloudflare     = true
    cloudflare_account_id = "0123456789abcdef0123456789abcdef"
    cloudflare_zone_id    = "fedcba9876543210fedcba9876543210"
  }

  assert {
    condition     = length(cloudflare_dns_record.demo) == 3 && alltrue([for r in cloudflare_dns_record.demo : r.proxied && r.type == "CNAME" && r.content == "00000000-0000-4000-8000-000000000000.cfargotunnel.com"])
    error_message = "three proxied records point at the tunnel"
  }
  assert {
    condition = jsonencode([for rule in cloudflare_zero_trust_tunnel_cloudflared_config.demo[0].config.ingress : "${coalesce(rule.hostname, "*")}=${rule.service}"]) == jsonencode([
      "demo.vnlabs.dev=http://proxy:80",
      "demo-chat.vnlabs.dev=http://proxy:80",
      "demo-bot.vnlabs.dev=http://proxy:80",
      "*=http_status:404",
    ])
    error_message = "every host goes to the proxy, everything else is 404"
  }
  assert {
    condition     = aws_ssm_parameter.tunnel_token[0].name == "/inbox-core/demo/cloudflare-tunnel-token" && aws_ssm_parameter.tunnel_token[0].type == "SecureString"
    error_message = "the tunnel's token goes to the parameter the instance reads"
  }
}

run "cloudflare_managed_needs_ids" {
  command = plan

  variables {
    manage_cloudflare = true
  }

  expect_failures = [cloudflare_zero_trust_tunnel_cloudflared.demo]
}

run "budget_email_is_checked" {
  command = plan

  variables {
    budget_email = "not-an-address"
  }

  expect_failures = [var.budget_email]
}

run "the_tunnel_token_is_required" {
  command = plan

  variables {
    secret_parameters = { GEMINI_API_KEY = "gemini-api-key" }
  }

  expect_failures = [var.secret_parameters]
}
