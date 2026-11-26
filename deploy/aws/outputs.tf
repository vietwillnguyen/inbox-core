output "instance_id" {
  description = "The demo instance."
  value       = aws_instance.demo.id
}

output "region" {
  description = "Where everything is."
  value       = var.region
}

output "shell" {
  description = "A root shell on the instance, through Session Manager (needs the Session Manager plugin)."
  value       = "aws ssm start-session --region ${var.region} --target ${aws_instance.demo.id}"
}

output "hostnames" {
  description = "The public host names the tunnel must serve, each to http://proxy:80."
  value       = local.hostnames
}

output "secret_parameters" {
  description = "The SecureString parameters the instance reads; create the ones Terraform does not."
  value       = { for key, name in var.secret_parameters : key => "${var.parameter_prefix}/${name}" }
}

output "tunnel_id" {
  description = "The Cloudflare tunnel (manage_cloudflare only)."
  value       = var.manage_cloudflare ? cloudflare_zero_trust_tunnel_cloudflared.demo[0].id : null
}
