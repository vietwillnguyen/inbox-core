# The instance's role: Systems Manager's managed-instance policy (Session
# Manager shell, no SSH) and read access to the demo's named parameters only.

data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

locals {
  parameter_arns = sort([for name in values(var.secret_parameters) :
    "arn:${data.aws_partition.current.partition}:ssm:${var.region}:${data.aws_caller_identity.current.account_id}:parameter${var.parameter_prefix}/${name}"
  ])
}

resource "aws_iam_role" "instance" {
  name        = "${var.name}-instance"
  description = "inbox-core demo instance: Session Manager and the demo's secrets, nothing else"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ssm_core" {
  role       = aws_iam_role.instance.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

# AmazonSSMManagedInstanceCore itself allows ssm:GetParameter and
# ssm:GetParameters on every parameter. The explicit deny below overrides it, so
# the role reads the demo's parameters and no other, whatever else is in the account.
resource "aws_iam_role_policy" "read_secrets" {
  name = "read-demo-secrets"
  role = aws_iam_role.instance.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ReadTheDemoSecrets"
        Effect   = "Allow"
        Action   = ["ssm:GetParameter", "ssm:GetParameters"]
        Resource = local.parameter_arns
      },
      {
        Sid         = "ReadNoOtherParameter"
        Effect      = "Deny"
        Action      = ["ssm:GetParameter", "ssm:GetParameters", "ssm:GetParametersByPath", "ssm:GetParameterHistory"]
        NotResource = local.parameter_arns
      },
    ]
  })
}

resource "aws_iam_instance_profile" "instance" {
  name = "${var.name}-instance"
  role = aws_iam_role.instance.name
}
