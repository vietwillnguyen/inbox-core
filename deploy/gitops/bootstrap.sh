#!/usr/bin/env bash
# Prepares an Ubuntu or Debian host to run the demo with the pull-based deploy
# agent, and starts the first deploy. The same script sets up the AWS instance
# (from its cloud-init user data) and a staging machine at home; it knows
# nothing about any cloud. Run it as root from a clone of the repository:
#
#   sudo ./deploy/gitops/bootstrap.sh --settings /etc/inbox-core/demo.settings \
#       --secrets-file /etc/inbox-core/secrets.env --initial-tag demo-v0.1.0
#
# It installs Docker Engine with the compose plugin (from Docker's apt
# repository), git, Python 3 and automatic security updates; bounds the logs;
# adds a swap file; installs the agent with its systemd timer; writes
# /etc/inbox-core/deploy.conf; and starts the first deploy without waiting for it.
#
# Options (defaults in brackets):
#   --checkout DIR          the clone the agent deploys from [this script's clone]
#   --repo URL              clone URL into --checkout when it is not a clone yet
#   --tag-pattern GLOB      release tags to deploy ['demo-v*']
#   --initial-tag TAG       the tag a fresh host starts at [the newest]
#   --settings FILE         the bundle's settings without secrets (required)
#   --secrets-command CMD   prints the secrets as KEY=value lines
#   --secrets-file FILE     or: a root-only file of KEY=value lines
#   --swap-size SIZE        swap file size, 0 for none [2G]
#   --auto-reboot HH:MM     reboot after an update that needs one, at this time (UTC), or off [04:30]
#   --interval SPAN         how often the timer checks for a tag, in systemd's syntax [5min]
#   --no-packages           do not install packages (they are already there)
#   --no-start              install and enable, but do not start the first deploy
#   --root DIR              write every file under DIR, and add no swap and run no
#                           systemctl (packages are still installed unless
#                           --no-packages): for tests
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
checkout=$(cd "$here/../.." && pwd)
repo=""
tag_pattern='demo-v*'
initial_tag=""
settings=""
secrets_command=""
secrets_file=""
swap_size=2G
auto_reboot=04:30
interval=5min
packages=yes
start=yes
root=""

die() { echo "bootstrap.sh: $*" >&2; exit 1; }
say() { echo "bootstrap.sh: $*"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --checkout) checkout=$2; shift 2 ;;
    --repo) repo=$2; shift 2 ;;
    --tag-pattern) tag_pattern=$2; shift 2 ;;
    --initial-tag) initial_tag=$2; shift 2 ;;
    --settings) settings=$2; shift 2 ;;
    --secrets-command) secrets_command=$2; shift 2 ;;
    --secrets-file) secrets_file=$2; shift 2 ;;
    --swap-size) swap_size=$2; shift 2 ;;
    --auto-reboot) auto_reboot=$2; shift 2 ;;
    --interval) interval=$2; shift 2 ;;
    --no-packages) packages=no; shift ;;
    --no-start) start=no; shift ;;
    --root) root=$2; shift 2 ;;
    -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
    *) die "unknown option $1 (see --help)" ;;
  esac
done

[ -n "$settings" ] || die "--settings FILE is required"
[ -f "${root}${settings}" ] || die "no settings file at ${root}${settings}"
if [ -n "$secrets_file" ] && [ ! -f "${root}${secrets_file}" ]; then
  die "no secrets file at ${root}${secrets_file}"
fi
case "$auto_reboot" in off|[0-2][0-9]:[0-5][0-9]) ;; *) die "--auto-reboot must be HH:MM or off" ;; esac
case "$swap_size" in 0|[1-9]*[GM]) ;; *) die "--swap-size must look like 2G, 512M or 0" ;; esac
if [ -z "$root" ] || [ "$packages" = yes ]; then
  [ "$(id -u)" = 0 ] || die "run as root"
fi

# --- packages ------------------------------------------------------------
install_packages() {
  export DEBIAN_FRONTEND=noninteractive
  apt-get -o DPkg::Lock::Timeout=600 update -q
  apt-get -o DPkg::Lock::Timeout=600 install -y -q ca-certificates curl git python3 unattended-upgrades util-linux logrotate
  if docker compose version >/dev/null 2>&1; then
    say "Docker with compose is already installed"
    return 0
  fi
  # Docker's own repository: the distribution's docker.io has no compose plugin.
  # shellcheck source=/dev/null
  . /etc/os-release
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL "https://download.docker.com/linux/${ID}/gpg" -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/${ID} ${VERSION_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get -o DPkg::Lock::Timeout=600 update -q
  apt-get -o DPkg::Lock::Timeout=600 install -y -q docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
}

# --- host settings -------------------------------------------------------
write_file() {  # MODE PATH, content on stdin
  local mode=$1 path=${root}$2
  mkdir -p "$(dirname "$path")"
  cat > "$path"
  chmod "$mode" "$path"
}

configure_host() {
  # Security updates every day, from the distribution's security pocket.
  write_file 0644 /etc/apt/apt.conf.d/20auto-upgrades <<'CONF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
CONF
  if [ "$auto_reboot" = off ]; then
    write_file 0644 /etc/apt/apt.conf.d/52inbox-core-unattended <<'CONF'
Unattended-Upgrade::Automatic-Reboot "false";
CONF
  else
    # Every container restarts with Docker (restart: unless-stopped).
    write_file 0644 /etc/apt/apt.conf.d/52inbox-core-unattended <<CONF
Unattended-Upgrade::Automatic-Reboot "true";
Unattended-Upgrade::Automatic-Reboot-Time "${auto_reboot}";
CONF
  fi
  # The journal is bounded; every container's log is rotated by compose.yaml,
  # and by Docker's default for anything else, unless the host set its own.
  write_file 0644 /etc/systemd/journald.conf.d/inbox-core.conf <<'CONF'
[Journal]
SystemMaxUse=500M
CONF
  if [ ! -f "${root}/etc/docker/daemon.json" ]; then
    write_file 0644 /etc/docker/daemon.json <<'CONF'
{
  "log-driver": "json-file",
  "log-opts": {"max-size": "10m", "max-file": "3"}
}
CONF
  fi
}

add_swap() {
  [ "$swap_size" = 0 ] && return 0
  if swapon --show --noheadings | grep -q .; then say "swap is already on"; return 0; fi
  if [ ! -f /swapfile ]; then
    fallocate -l "$swap_size" /swapfile
    chmod 600 /swapfile
    mkswap /swapfile >/dev/null
  fi
  swapon /swapfile
  grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
}

# --- the agent -----------------------------------------------------------
install_agent() {
  mkdir -p "${root}/usr/local/sbin" "${root}/etc/systemd/system" "${root}/etc/logrotate.d" \
    "${root}/var/lib/inbox-core-deploy"
  chmod 700 "${root}/var/lib/inbox-core-deploy"
  install -m 0755 "$here/inbox-core-deploy" "${root}/usr/local/sbin/inbox-core-deploy"
  install -m 0644 "$here/systemd/inbox-core-deploy.service" "${root}/etc/systemd/system/"
  sed "s|^OnUnitInactiveSec=.*|OnUnitInactiveSec=${interval}|" "$here/systemd/inbox-core-deploy.timer" \
    | write_file 0644 /etc/systemd/system/inbox-core-deploy.timer
  install -m 0644 "$here/logrotate.conf" "${root}/etc/logrotate.d/inbox-core-deploy"
  write_file 0644 /etc/inbox-core/deploy.conf <<CONF
# Written by deploy/gitops/bootstrap.sh; see deploy/gitops/deploy.conf.example.
CHECKOUT_DIR=${checkout}
REMOTE=origin
TAG_PATTERN='${tag_pattern}'
INITIAL_TAG=${initial_tag}
SETTINGS_FILE=${settings}
SECRETS_COMMAND='${secrets_command}'
SECRETS_FILE=${secrets_file}
ENV_FILE=/etc/inbox-core/demo.env
STATE_DIR=/var/lib/inbox-core-deploy
CONF
  chmod 700 "${root}/etc/inbox-core"
}

prepare_checkout() {
  if ! git -C "${root}${checkout}" rev-parse --git-dir >/dev/null 2>&1; then
    [ -n "$repo" ] || die "${checkout} is not a clone; pass --repo URL"
    git clone --quiet "$repo" "${root}${checkout}"
  fi
  # The agent runs as root; the clone may belong to someone else.
  if [ -z "$root" ] && [ "$(stat -c %u "$checkout")" != 0 ]; then
    git config --system --get-all safe.directory | grep -qxF "$checkout" \
      || git config --system --add safe.directory "$checkout"
  fi
}

start_agent() {
  systemctl daemon-reload
  systemctl restart systemd-journald
  systemctl enable --now docker.service
  systemctl enable --now inbox-core-deploy.timer
  if [ "$start" = yes ]; then
    # Not waited for: the first bring-up takes a while. Watch it with
    # journalctl -u inbox-core-deploy -f
    systemctl start --no-block inbox-core-deploy.service
    say "first deploy started; follow it with: journalctl -u inbox-core-deploy -f"
  fi
}

[ "$packages" = yes ] && install_packages
configure_host
prepare_checkout
install_agent
if [ -z "$root" ]; then
  add_swap
  start_agent
fi
say "done"
