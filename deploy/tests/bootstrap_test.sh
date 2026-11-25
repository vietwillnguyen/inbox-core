#!/usr/bin/env bash
# Behaviour test for deploy/gitops/bootstrap.sh, run as root in a throwaway
# ubuntu:24.04 container (CI does this; never on a machine you care about):
#
#   docker run --rm -v "$PWD:/src:ro" ubuntu:24.04 /src/deploy/tests/bootstrap_test.sh
#
# It installs the real packages (Docker Engine from Docker's repository and the
# rest), then checks every file the script writes under --root. A container
# has no systemd, so --root also keeps it from touching swap or systemctl.
set -euo pipefail

src=$(cd "$(dirname "$0")/../.." && pwd)
root=$(mktemp -d)
trap 'rm -rf "$root"' EXIT
fail() { echo "FAIL: $*" >&2; exit 1; }
passed=0
ok() { passed=$((passed + 1)); echo "ok   $*"; }

[ "$(id -u)" = 0 ] || fail "run as root, in a container"

# Before the packages: options are checked first.
if "$src/deploy/gitops/bootstrap.sh" --root "$root" --no-packages 2>/dev/null; then fail "ran without --settings"; fi
if "$src/deploy/gitops/bootstrap.sh" --root "$root" --no-packages --settings /nope 2>/dev/null; then fail "ran with a missing settings file"; fi
mkdir -p "$root/etc/inbox-core"
echo "DEMO_DOMAIN=demo.example.com" > "$root/etc/inbox-core/demo.settings"
if "$src/deploy/gitops/bootstrap.sh" --root "$root" --no-packages --settings /etc/inbox-core/demo.settings \
  --auto-reboot sometime 2>/dev/null; then fail "accepted a bad --auto-reboot"; fi
ok "bad options are refused before anything is installed"

# A remote to clone: any repository will do.
export GIT_CONFIG_GLOBAL=$root/gitconfig
apt-get update -q >/dev/null
apt-get install -y -q git >/dev/null 2>&1
git init --quiet -b main "$root/remote"
git -C "$root/remote" -c user.email=t@example.com -c user.name=t commit --quiet --allow-empty -m init

"$src/deploy/gitops/bootstrap.sh" --root "$root" --repo "$root/remote" --checkout /opt/inbox-core \
  --settings /etc/inbox-core/demo.settings --secrets-command "/usr/local/libexec/inbox-core/fetch-secrets --quiet" \
  --initial-tag demo-v0.1.0 --interval 10min --auto-reboot 03:15

docker --version >/dev/null || fail "docker is not installed"
docker compose version >/dev/null || fail "the compose plugin is not installed"
for tool in git python3 flock logrotate unattended-upgrade; do
  command -v "$tool" >/dev/null || fail "$tool is not installed"
done
ok "Docker Engine with compose, git, python3, flock, logrotate and unattended-upgrades are installed"

mode() { stat -c %a "$root$1"; }
[ "$(mode /usr/local/sbin/inbox-core-deploy)" = 755 ] || fail "agent not installed executable"
cmp -s "$root/usr/local/sbin/inbox-core-deploy" "$src/deploy/gitops/inbox-core-deploy" || fail "agent differs"
[ -f "$root/etc/systemd/system/inbox-core-deploy.service" ] || fail "service unit missing"
grep -qx "OnUnitInactiveSec=10min" "$root/etc/systemd/system/inbox-core-deploy.timer" || fail "timer interval not set"
[ -f "$root/etc/logrotate.d/inbox-core-deploy" ] || fail "logrotate config missing"
logrotate --debug "$root/etc/logrotate.d/inbox-core-deploy" >/dev/null 2>&1 || fail "logrotate config does not parse"
[ "$(mode /var/lib/inbox-core-deploy)" = 700 ] || fail "state directory not private"
ok "the agent, its timer (every 10min), its log rotation and its private state directory are installed"

conf=$root/etc/inbox-core/deploy.conf
[ "$(mode /etc/inbox-core)" = 700 ] || fail "/etc/inbox-core is not private"
# shellcheck source=/dev/null
( . "$conf"
  [ "$CHECKOUT_DIR" = /opt/inbox-core ] || fail "CHECKOUT_DIR=$CHECKOUT_DIR"
  [ "$TAG_PATTERN" = 'demo-v*' ] || fail "TAG_PATTERN=$TAG_PATTERN"
  [ "$INITIAL_TAG" = demo-v0.1.0 ] || fail "INITIAL_TAG=$INITIAL_TAG"
  [ "$SETTINGS_FILE" = /etc/inbox-core/demo.settings ] || fail "SETTINGS_FILE=$SETTINGS_FILE"
  [ "$SECRETS_COMMAND" = "/usr/local/libexec/inbox-core/fetch-secrets --quiet" ] || fail "SECRETS_COMMAND=$SECRETS_COMMAND"
)
git -C "$root/opt/inbox-core" rev-parse --git-dir >/dev/null || fail "the repository was not cloned"
ok "deploy.conf carries the options, quoted, and the repository is cloned"

grep -q 'Automatic-Reboot "true"' "$root/etc/apt/apt.conf.d/52inbox-core-unattended" || fail "automatic reboot not on"
grep -q 'Automatic-Reboot-Time "03:15"' "$root/etc/apt/apt.conf.d/52inbox-core-unattended" || fail "reboot time not set"
grep -q 'Unattended-Upgrade "1"' "$root/etc/apt/apt.conf.d/20auto-upgrades" || fail "unattended upgrades not on"
apt-config dump -c "$root/etc/apt/apt.conf.d/20auto-upgrades" >/dev/null || fail "apt configuration does not parse"
grep -qx "SystemMaxUse=500M" "$root/etc/systemd/journald.conf.d/inbox-core.conf" || fail "journal not bounded"
python3 -c 'import json,sys; c=json.load(open(sys.argv[1])); assert c["log-opts"]["max-size"]=="10m"' \
  "$root/etc/docker/daemon.json" || fail "docker log rotation not set"
ok "security updates with a 03:15 reboot, a bounded journal and rotated container logs are configured"

echo '{"log-driver": "local"}' > "$root/etc/docker/daemon.json"
"$src/deploy/gitops/bootstrap.sh" --root "$root" --no-packages --checkout /opt/inbox-core \
  --settings /etc/inbox-core/demo.settings --auto-reboot off >/dev/null
grep -q '"local"' "$root/etc/docker/daemon.json" || fail "an existing daemon.json was replaced"
grep -q 'Automatic-Reboot "false"' "$root/etc/apt/apt.conf.d/52inbox-core-unattended" || fail "--auto-reboot off ignored"
ok "running it again keeps the host's own Docker settings and honours --auto-reboot off"

echo "all ${passed} bootstrap checks passed"
