# The demo's own small VPC: one public subnet with a route to the internet, and
# not a single inbound rule. The instance reaches out (packages, images, git,
# the model, Cloudflare's tunnel, Systems Manager); nothing reaches in.

data "aws_ec2_instance_type_offerings" "here" {
  location_type = "availability-zone"

  filter {
    name   = "instance-type"
    values = [var.instance_type]
  }
}

locals {
  # The first zone, in name order, that offers the instance type.
  availability_zone = sort(data.aws_ec2_instance_type_offerings.here.locations)[0]
}

resource "aws_vpc" "demo" {
  #checkov:skip=CKV2_AWS_11:flow logs would record only this instance's own outbound traffic, for a CloudWatch bill
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = { Name = var.name }
}

# The VPC's default security group allows nothing, so nothing launched into the
# VPC by mistake is reachable either.
resource "aws_default_security_group" "demo" {
  vpc_id = aws_vpc.demo.id

  tags = { Name = "${var.name}-default-deny" }
}

resource "aws_internet_gateway" "demo" {
  vpc_id = aws_vpc.demo.id

  tags = { Name = var.name }
}

resource "aws_subnet" "demo" {
  vpc_id                  = aws_vpc.demo.id
  cidr_block              = var.vpc_cidr
  availability_zone       = local.availability_zone
  map_public_ip_on_launch = false

  tags = { Name = var.name }
}

resource "aws_route_table" "demo" {
  vpc_id = aws_vpc.demo.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.demo.id
  }

  tags = { Name = var.name }
}

resource "aws_route_table_association" "demo" {
  subnet_id      = aws_subnet.demo.id
  route_table_id = aws_route_table.demo.id
}

locals {
  # Outbound only, and only what the host uses: HTTPS (images, git, the model,
  # Systems Manager), HTTP (Ubuntu's package mirrors) and the tunnel's port
  # 7844 (QUIC on UDP, HTTP/2 on TCP). DNS and time go to the VPC's own
  # resolver and Amazon's time service, which security groups do not filter.
  egress = [
    { description = "HTTPS", protocol = "tcp", port = 443 },
    { description = "HTTP for the Ubuntu package mirrors", protocol = "tcp", port = 80 },
    { description = "Cloudflare Tunnel over HTTP/2", protocol = "tcp", port = 7844 },
    { description = "Cloudflare Tunnel over QUIC", protocol = "udp", port = 7844 },
  ]
}

#trivy:ignore:AVD-AWS-0104 outbound to the internet is how the host works; there is no inbound rule
resource "aws_security_group" "instance" {
  name        = "${var.name}-instance"
  description = "inbox-core demo: no inbound rules at all; outbound HTTP, HTTPS and the tunnel port"
  vpc_id      = aws_vpc.demo.id

  # Explicitly empty: Terraform removes any inbound rule added by hand.
  ingress = []

  #checkov:skip=CKV_AWS_382:outbound to the internet is how the host works; ports are limited and there is no inbound rule
  egress = [for rule in local.egress : {
    description      = rule.description
    protocol         = rule.protocol
    from_port        = rule.port
    to_port          = rule.port
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = []
    prefix_list_ids  = []
    security_groups  = []
    self             = false
  }]

  tags = { Name = "${var.name}-instance" }
}
