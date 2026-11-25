# The public demo on AWS

This runbook puts the demo bundle ([demo.md](demo.md)) on one AWS instance, reachable only through a Cloudflare Tunnel, and deploys each new version when you push a release tag.
It is written for the owner: the steps only you can do come first, then the order in which to run everything.

## What it builds

| Part | Where | What |
|---|---|---|
| State bucket | `deploy/aws/state-bucket/` | An S3 bucket for Terraform's state: versioned, encrypted, never public, TLS only, with S3's own state locking |
| Network | `deploy/aws/network.tf` | A small VPC of its own with one public subnet; the instance's security group has no inbound rule at all, and outbound only to ports 80, 443 and 7844 (the tunnel) |
| Instance | `deploy/aws/main.tf` | One `t4g.medium` (2 Graviton vCPU, 4 GB) running Ubuntu 24.04, IMDSv2 required, an encrypted 30 GB gp3 root volume, no SSH key |
| Role | `deploy/aws/iam.tf` | Session Manager (`AmazonSSMManagedInstanceCore`) and read access to the demo's named parameters; every other parameter is explicitly denied |
| Budget | `deploy/aws/budget.tf` | A 40 USD monthly budget that mails you at 80% and 100% of actual spend and at 100% forecast |
| Tunnel and DNS (optional) | `deploy/aws/cloudflare.tf` | With `manage_cloudflare = true`: the tunnel, its three public hostnames and the DNS records |
| First boot | `deploy/aws/templates/cloud-init.yaml.tftpl` | Writes the settings and the parameter names, installs the AWS CLI, clones the repository at `initial_tag` and runs the bootstrap |
| Host setup | `deploy/gitops/bootstrap.sh` | Docker, automatic security updates, bounded logs, a swap file, and the deploy agent with its timer |
| Deploy agent | `deploy/gitops/inbox-core-deploy` | Every five minutes: a new release tag is checked out, brought up and smoke-tested, or rolled back |

The region (`us-east-1`), the instance type and the architecture are variables.
Nothing in `deploy/gitops/` knows about AWS: the only AWS-specific step on the host is `deploy/aws/files/fetch-ssm-secrets.sh`, which reads the secrets from Parameter Store.
The same agent runs a staging machine at home ([Staging on another machine](#staging-on-another-machine)).

How a request reaches the demo, and how a release reaches the server:

```
visitor --https--> Cloudflare --tunnel (outbound from the instance)--> cloudflared --> Traefik --> Chatwoot / page / tab
you --git push tag--> GitHub <--git fetch every 5 min-- deploy agent on the instance --> demo.sh up, demo.sh smoke
```

Nothing connects in to the instance, and GitHub holds no cloud credential.

## What it costs

An estimate for `us-east-1` at on-demand prices; check it with the [AWS Pricing Calculator](https://calculator.aws/) before you rely on it.

| Item | Monthly |
|---|---|
| `t4g.medium`, 730 hours at about 0.0336 USD an hour | about 24.50 USD |
| 30 GB gp3 root volume at about 0.08 USD per GB | about 2.40 USD |
| One public IPv4 address at 0.005 USD an hour (needed for outbound traffic) | about 3.65 USD |
| Data out to the internet | free up to 100 GB a month across the account |
| Session Manager, standard Parameter Store parameters, two budgets | free |
| The state bucket | a few cents |
| **Total** | **about 31 USD** |

- In the default `unlimited` CPU credit mode, a load held above the baseline (20% of each vCPU) for a long time is billed extra; an idle demo stays far below it. Set `cpu_credits = "standard"` to be throttled instead of billed.
- A one-year Savings Plan or a smaller instance lowers the instance line; `t4g.small` (2 GB) is too small for the bundle.
- The Gemini spend is not on the AWS bill: it is capped by `DEMO_DAILY_BUDGET_USD` (1 USD a day by default, so at most about 30 USD a month).
- The budget alerts; it stops nothing. If a mail arrives you did not expect, stop the instance ([Teardown](#teardown)).

## One-time steps only you can do

### 1. The AWS account

1. Create an AWS account at [aws.amazon.com](https://aws.amazon.com/), with an address you use only for it.
2. Sign in as the root user, open *Security credentials* and assign an MFA device to the root user.
3. Do not create access keys for the root user; after the next step, use the root user only for billing and account settings.

### 2. An administrator through IAM Identity Center

1. In the console, open *IAM Identity Center* in `us-east-1` and enable it (an organization instance).
2. Create a user for yourself, with MFA required (*Settings, Authentication*).
3. Create a permission set from the predefined `AdministratorAccess` policy and assign it to your user on this account.
4. On your own machine, install [Terraform](https://developer.hashicorp.com/terraform/install) 1.11 or later, the [AWS CLI v2](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) and the [Session Manager plugin](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html).
5. Configure a profile and sign in:

```sh
aws configure sso --profile inbox-core     # the start URL is on IAM Identity Center's dashboard
aws sso login --profile inbox-core
export AWS_PROFILE=inbox-core
aws sts get-caller-identity                # shows the account and your role
```

Every command below assumes `AWS_PROFILE` is set and the session is fresh.
The credentials stay on your machine; GitHub and the instance never get them.

### 3. The budget address

Pick the address the budget alerts go to.
It goes into `deploy/aws/terraform.tfvars`, which is gitignored; never into a committed file.
Budget mail needs no confirmation.

### 4. The Cloudflare tunnel

The domain's DNS must be on Cloudflare (a free plan is enough).
Choose one of the two ways.

**In the dashboard** (nothing Cloudflare-side in Terraform, and no Cloudflare secret in the state):

1. In Cloudflare Zero Trust, open *Networks, Tunnels*, choose *Create a tunnel*, *Cloudflared*, and name it `inbox-core-demo`.
2. On the install page, copy the token (the long string after `--token` in any of the commands); you do not install anything.
3. Under *Public hostnames*, add three, each with type `HTTP` and URL `proxy:80`:

| Hostname | Service |
|---|---|
| `demo.vnlabs.dev` | `HTTP` `proxy:80` |
| `demo-chat.vnlabs.dev` | `HTTP` `proxy:80` |
| `demo-bot.vnlabs.dev` | `HTTP` `proxy:80` |

Cloudflare adds the DNS records itself.
The chat and bot names are one level below the zone on purpose: Cloudflare's free certificate covers `*.vnlabs.dev` but not `*.demo.vnlabs.dev`.

**With Terraform** (`manage_cloudflare = true`):

1. Create an API token (*My Profile, API Tokens, Create Token, Custom token*) with *Account, Cloudflare Tunnel, Edit* and *Zone, DNS, Edit* on the `vnlabs.dev` zone only.
2. Note the account ID and the zone ID (both on the zone's overview page).
3. Export the token in your shell when you run Terraform: `export CLOUDFLARE_API_TOKEN=...`.

Terraform then creates the tunnel, the three hostnames and the records, and writes the tunnel's token to Parameter Store itself.
The trade-off: the token is then in Terraform's state (which is encrypted and private), where the dashboard way keeps every secret out of it.

### 5. The secrets in Parameter Store

The instance reads two SecureString parameters (names from the `secret_parameters` variable).
Create them before the instance boots; if one is missing, the first deploy waits and retries every five minutes.
Type each value at a prompt so it stays out of your shell history:

```sh
read -rsp 'Gemini API key: ' value && echo
aws ssm put-parameter --region us-east-1 --name /inbox-core/demo/gemini-api-key \
  --type SecureString --value "$value" --overwrite
read -rsp 'Cloudflare tunnel token: ' value && echo      # skip with manage_cloudflare = true
aws ssm put-parameter --region us-east-1 --name /inbox-core/demo/cloudflare-tunnel-token \
  --type SecureString --value "$value" --overwrite
unset value
```

Before you go public with Gemini, score it on the shop's golden set ([demo.md](demo.md#before-you-start-prove-the-real-model)).
In Google AI Studio, also put a quota or budget alert on the key itself.

Why the values are not in Terraform: a parameter whose value Terraform manages is read back into the state on every refresh, even with `ignore_changes`.
Here Terraform only knows the parameter names, to scope the instance role; the values go from your prompt to Parameter Store, and from there to the instance.
They are never in git, in the user data or in the state (except the tunnel token with `manage_cloudflare = true`).

### 6. The first release tag

The instance starts at `initial_tag`, which must exist and contain `deploy/gitops/`.
After this work is merged to `main`:

```sh
git checkout main && git pull
git tag -a demo-v0.1.0 -m "demo v0.1.0"
git push origin demo-v0.1.0
```

Anyone who can push tags to the repository can deploy; keep that list short (a tag protection rule on `demo-v*` in the repository's settings helps).

## Bring it up

### 1. The state bucket (once)

```sh
cd deploy/aws/state-bucket
terraform init
terraform apply                      # one bucket and its settings
terraform output -raw backend_hcl > ../backend.hcl
```

This configuration keeps its own state in a local `terraform.tfstate`; keep that file (it is gitignored), or import the bucket again if you lose it.
The bucket has `prevent_destroy` set, so a stray `destroy` cannot remove it.

### 2. The demo

```sh
cd deploy/aws
cp terraform.tfvars.example terraform.tfvars    # set initial_tag and budget_email; review the rest
terraform init -backend-config=backend.hcl
terraform plan
terraform apply
```

`plan` should show thirteen resources (more with `manage_cloudflare`), all new.
The outputs include the instance ID and the exact `shell` command.

### 3. Watch the first boot

The first boot takes ten to twenty minutes: packages, Docker, the images, building the inbox-core image, Chatwoot's database.

```sh
aws ssm start-session --region us-east-1 --target <instance id>    # the shell output
sudo tail -f /var/log/cloud-init-output.log                          # packages and the bootstrap
sudo journalctl -u inbox-core-deploy -f                              # the first deploy
sudo inbox-core-deploy status                                        # outcome=deployed when done
```

Session Manager needs a minute or two after boot before the instance shows up.
When the status says `deployed`, open `https://demo.vnlabs.dev`.
The smoke test goes out through Cloudflare and back through the tunnel, so it checks what a visitor gets.
If it keeps failing with 403 from Cloudflare, a bot rule is refusing it: turn off *Bot Fight Mode* (*Security, Bots*) for the zone, or add a rule that skips it for the instance's address.

Your dashboard sign-in is on the instance: `sudo cat /opt/inbox-core/deploy/demo/.local/people.env`; change the password after signing in at `https://demo-chat.vnlabs.dev`.

## Releases

### Cut a release that deploys

```sh
git tag -a demo-v0.2.0 -m "demo v0.2.0" <commit>
git push origin demo-v0.2.0
```

Within about five minutes the agent fetches the tag, checks it out, runs `demo.sh up`, then `demo.sh smoke` (up to three attempts) as the gate.
Tags are compared in version order (`demo-v0.10.0` comes after `demo-v0.9.0`); only tags newer than the current one are deployed.

### What happens when one fails

If `up` or the smoke test fails, the agent records the tag as failed, checks out the previous tag and brings it back up, and the status says `rolled-back`.
A failed tag is never retried by the timer; fix the problem and push a newer tag.
If the previous tag fails its smoke test too, the status says `rollback-failed`: open a shell and look.

```sh
sudo inbox-core-deploy status                    # outcome, tag, previous, current, failed tags
sudo cat /var/lib/inbox-core-deploy/history.log  # one line per deploy
sudo journalctl -u inbox-core-deploy --since today
systemctl list-timers inbox-core-deploy.timer
```

### Roll back on purpose

Either push a new, higher tag on the good commit (the agent deploys it as usual), or hold the agent and deploy an older tag by hand:

```sh
sudo inbox-core-deploy pause
sudo inbox-core-deploy deploy demo-v0.1.0
# later, to follow new tags again:
sudo inbox-core-deploy resume
```

Without `pause`, the next timer run would move forward to the newest tag again.

### Settings and secrets

- A new Gemini key or tunnel token: put it into Parameter Store as above, then `sudo inbox-core-deploy redeploy` (the secrets are read again before every deploy).
- A bundle setting (`demo_daily_budget_usd`, `demo_extra_settings`, the host names): change it in `terraform.tfvars` and `terraform apply`. It is in the user data, so the instance is replaced and comes up fresh at `initial_tag` (set that to the current tag first). The demo keeps nothing worth saving: conversations are reset daily.
- A newer Ubuntu image does not replace the instance (`ami` is ignored); the instance updates itself. To move to a new image on purpose, `terraform apply -replace=aws_instance.demo`.

## Running it

### Shell access

```sh
aws ssm start-session --region us-east-1 --target <instance id>
```

There is no SSH key and no port 22.
`sudo -i` gives root; `cd /opt/inbox-core && sudo DEMO_ENV_FILE=/etc/inbox-core/demo.env ./deploy/demo/demo.sh status` (or `memory`, `logs`, `reset`) runs the bundle's own commands.

### What runs on the host

- Security updates are installed every day (`unattended-upgrades`), and the instance reboots at 04:30 UTC when one needs it; every container comes back with Docker.
- Logs are bounded: the journal at 500 MB, every container's log at three files of 10 MB, the deploy history rotated monthly.
- A 2 GB swap file gives the image build room.
- Containers cannot reach the instance's credentials: the metadata service answers one network hop only (IMDSv2 with a hop limit of 1).
- The proxy listens on the instance's loopback only; cloudflared reaches it on the compose network.

### Files on the instance

| Path | What |
|---|---|
| `/etc/inbox-core/demo.settings` | The bundle's settings, without secrets (from the user data) |
| `/etc/inbox-core/ssm-secrets.conf` | The region and the parameter names |
| `/etc/inbox-core/demo.env` | Settings plus secrets, mode 600, rewritten before every deploy |
| `/etc/inbox-core/deploy.conf` | The agent's configuration (`deploy/gitops/deploy.conf.example`) |
| `/opt/inbox-core` | The clone the agent checks tags out in; `deploy/demo/.local/` holds the generated secrets |
| `/var/lib/inbox-core-deploy/` | `current`, `failed`, `status`, `history.log` |

## Staging on another machine

The same agent runs a staging copy on any Ubuntu or Debian machine, such as a mini PC at home, with no AWS at all.

1. Make a second tunnel (for example `staging-demo.vnlabs.dev`, `staging-chat.vnlabs.dev`, `staging-bot.vnlabs.dev`) the same way.
2. As root, clone the repository to `/opt/inbox-core`, and write the settings and the secrets:

```sh
sudo git clone https://github.com/vietwillnguyen/inbox-core.git /opt/inbox-core
sudo install -d -m 700 /etc/inbox-core
sudo tee /etc/inbox-core/demo.settings >/dev/null <<'EOF'
DEMO_DOMAIN=staging-demo.vnlabs.dev
DEMO_CHAT_HOST=staging-chat.vnlabs.dev
DEMO_BOT_HOST=staging-bot.vnlabs.dev
DEMO_TUNNEL=on
DEMO_MODEL=gemini
DEMO_DAILY_BUDGET_USD=0.50
EOF
sudo install -m 600 /dev/null /etc/inbox-core/secrets.env
sudoedit /etc/inbox-core/secrets.env     # GEMINI_API_KEY=... and DEMO_TUNNEL_TOKEN=...
sudo /opt/inbox-core/deploy/gitops/bootstrap.sh --checkout /opt/inbox-core \
  --settings /etc/inbox-core/demo.settings --secrets-file /etc/inbox-core/secrets.env \
  --tag-pattern 'staging-v*' --swap-size 0 --auto-reboot off
```

With its own pattern, staging deploys `staging-v*` tags and production `demo-v*` tags: tag a commit `staging-v0.2.0` first, and `demo-v0.2.0` once it has run well.
`bootstrap.sh --help` lists every option; it keeps an existing `/etc/docker/daemon.json`.

## Teardown

To pause the cost of the instance without losing anything: `aws ec2 stop-instances --region us-east-1 --instance-ids <id>` (the volume still costs about 2.40 USD a month, the public address is released while stopped; `start-instances` brings it back with a new address, and the demo with it).

To remove everything:

```sh
cd deploy/aws
terraform destroy          # the instance, network, role, budget (and the tunnel and records, if Terraform made them)
aws ssm delete-parameters --region us-east-1 \
  --names /inbox-core/demo/gemini-api-key /inbox-core/demo/cloudflare-tunnel-token
```

Then delete the tunnel in the Cloudflare dashboard if you made it there, and revoke the Gemini key if it was made for the demo.
The state bucket stays (`prevent_destroy`); to remove it too, delete every object version in it, take `prevent_destroy` out of `deploy/aws/state-bucket/main.tf` and run `terraform destroy` there.

## Checks

None of this is tested against a real AWS or Cloudflare account; CI checks it without one:

- `terraform fmt`, `validate`, `tflint` (with the AWS rules) and `terraform test` with mock providers, for both configurations. The tests assert that the security group has no inbound rule, IMDSv2 is required, the root volume is encrypted, the role reads only the named parameters, the budget exists, the user data carries no secret, and the region and instance type follow their variables.
- `checkov` over `deploy/aws`; each skipped check carries its reason next to the resource.
- `shellcheck` on every script.
- `deploy/tests/agent_test.sh`: the agent against a local git remote, in an Ubuntu container: a new tag is deployed, a failing one rolled back, nothing happens without a new tag, and the secrets step fails closed.
- `deploy/tests/bootstrap_test.sh`: the bootstrap on a fresh Ubuntu 24.04 container, packages included.
- `deploy/tests/proxy_tunnel_test.sh`: the bundle's proxy in tunnel mode.

The configuration also works with OpenTofu 1.11 or later, except that OpenTofu's support for the write-only value used with `manage_cloudflare` should be checked first.
