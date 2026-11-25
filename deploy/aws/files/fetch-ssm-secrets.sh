#!/usr/bin/env bash
# The demo's secrets from AWS Systems Manager Parameter Store, printed as
# KEY='value' lines for the deploy agent (its SECRETS_COMMAND). This is the only
# AWS-specific step on the host. It runs as root on the instance and uses the
# instance role, which may read these parameters and nothing else.
#
# Configuration: /etc/inbox-core/ssm-secrets.conf (written by the instance's
# user data; INBOX_CORE_SSM_SECRETS_CONF overrides), a shell file with
#
#   AWS_REGION=us-east-1
#   SECRET_PARAMETERS="GEMINI_API_KEY=/inbox-core/demo/gemini-api-key DEMO_TUNNEL_TOKEN=/inbox-core/demo/cloudflare-tunnel-token"
#
# It fails, printing nothing, if any parameter is missing or empty, so a deploy
# never starts with half its secrets.
set -euo pipefail

CONF=${INBOX_CORE_SSM_SECRETS_CONF:-/etc/inbox-core/ssm-secrets.conf}
[ -f "$CONF" ] || { echo "fetch-ssm-secrets: no configuration at $CONF" >&2; exit 2; }
# shellcheck source=/dev/null
. "$CONF"
: "${AWS_REGION:?set AWS_REGION in $CONF}"
: "${SECRET_PARAMETERS:?set SECRET_PARAMETERS in $CONF}"

read -r -a pairs <<< "$SECRET_PARAMETERS"
names=()
for pair in "${pairs[@]}"; do names+=("${pair#*=}"); done

# The values travel on a pipe, never on a command line other processes can read.
aws ssm get-parameters --region "$AWS_REGION" --with-decryption \
  --names "${names[@]}" --output json | python3 -I -c '
import json, re, shlex, sys

response = json.load(sys.stdin)
pairs = [pair.split("=", 1) for pair in sys.argv[1:]]
invalid = response.get("InvalidParameters") or []
if invalid:
    sys.exit("fetch-ssm-secrets: missing parameters: " + " ".join(invalid))
values = {p["Name"]: p["Value"] for p in response.get("Parameters", [])}
lines = []
for key, name in pairs:
    if not re.fullmatch(r"[A-Z_][A-Z0-9_]*", key):
        sys.exit(f"fetch-ssm-secrets: {key!r} is not a variable name")
    value = values.get(name, "")
    if not value.strip() or value.startswith("REPLACE_ME"):
        sys.exit(f"fetch-ssm-secrets: {name} is empty or still a placeholder")
    if "\n" in value:
        sys.exit(f"fetch-ssm-secrets: {name} holds more than one line")
    lines.append(f"{key}={shlex.quote(value)}")
print("\n".join(lines))
' "${pairs[@]}"
