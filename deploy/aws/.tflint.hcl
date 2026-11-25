# tflint for deploy/aws and deploy/aws/state-bucket:
#   tflint --init && tflint --chdir=deploy/aws && tflint --chdir=deploy/aws/state-bucket --config=$PWD/deploy/aws/.tflint.hcl
config {
  call_module_type = "none"
}

plugin "terraform" {
  enabled = true
  preset  = "all"
}

plugin "aws" {
  enabled = true
  version = "0.50.0"
  source  = "github.com/terraform-linters/tflint-ruleset-aws"
}
