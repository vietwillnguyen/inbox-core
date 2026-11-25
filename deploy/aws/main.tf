# One instance, reachable only through Session Manager and the tunnel. Its user
# data installs the host and starts the demo at initial_tag; after that the
# deploy agent on the host follows the release tags (deploy/gitops).

locals {
  ami_parameter = coalesce(var.ami_ssm_parameter,
  "/aws/service/canonical/ubuntu/server/24.04/stable/current/${var.architecture}/hvm/ebs-gp3/ami-id")

  # The bundle's settings, not secret (deploy/demo/.env.example's names). The
  # secrets are appended on the host from Parameter Store before every deploy.
  demo_settings = merge(
    {
      DEMO_DOMAIN           = var.demo_domain
      DEMO_CHAT_HOST        = var.demo_chat_host
      DEMO_BOT_HOST         = var.demo_bot_host
      DEMO_TUNNEL           = "on"
      DEMO_MODEL            = var.demo_model
      DEMO_DAILY_BUDGET_USD = var.demo_daily_budget_usd
      DEMO_ADMIN_EMAIL      = var.demo_admin_email
    },
    var.demo_extra_settings,
  )

  secret_parameters = join(" ", [for key in sort(keys(var.secret_parameters)) :
  "${key}=${var.parameter_prefix}/${var.secret_parameters[key]}"])

  user_data = templatefile("${path.module}/templates/cloud-init.yaml.tftpl", {
    region            = var.region
    repository_url    = var.repository_url
    initial_tag       = var.initial_tag
    tag_pattern       = var.tag_pattern
    deploy_interval   = var.deploy_interval
    auto_reboot_time  = var.auto_reboot_time
    demo_settings     = join("\n", [for key in sort(keys(local.demo_settings)) : "${key}=${local.demo_settings[key]}"])
    secret_parameters = local.secret_parameters
    fetch_secrets_b64 = filebase64("${path.module}/files/fetch-ssm-secrets.sh")
  })
}

data "aws_ssm_parameter" "ami" {
  name = local.ami_parameter
}

resource "aws_instance" "demo" {
  #checkov:skip=CKV_AWS_88:the public address is for outbound traffic only (no inbound rule); a NAT gateway would cost more than the instance
  ami                         = data.aws_ssm_parameter.ami.insecure_value
  instance_type               = var.instance_type
  subnet_id                   = aws_subnet.demo.id
  vpc_security_group_ids      = [aws_security_group.instance.id]
  iam_instance_profile        = aws_iam_instance_profile.instance.name
  associate_public_ip_address = true # outbound only: the security group has no inbound rule
  ebs_optimized               = true
  monitoring                  = false #checkov:skip=CKV_AWS_126:one-minute metrics cost extra and nothing reads them

  user_data                   = local.user_data
  user_data_replace_on_change = true

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required" # IMDSv2 only
    http_put_response_hop_limit = 1          # containers (one hop further) cannot reach the instance's credentials
    instance_metadata_tags      = "disabled"
  }

  root_block_device {
    volume_type           = "gp3"
    volume_size           = var.root_volume_size_gb
    encrypted             = true
    delete_on_termination = true
  }

  credit_specification {
    cpu_credits = var.cpu_credits
  }

  tags = { Name = var.name }

  lifecycle {
    # A newer Ubuntu image is not a reason to replace the running demo; it gets
    # security updates in place. Replace it on purpose (docs/aws.md).
    ignore_changes = [ami]
  }
}
