#!/usr/bin/env bash
# Behaviour tests for the deploy agent (deploy/gitops/inbox-core-deploy) and
# the Parameter Store secrets step (deploy/aws/files/fetch-ssm-secrets.sh).
#
# The agent runs against a local git remote with release tags whose
# deploy/demo/demo.sh is a stand-in that records each call and fails when told
# to. Nothing here touches Docker, a network or a cloud. CI runs it in a plain
# ubuntu:24.04 container:
#
#   docker run --rm -v "$PWD:/src:ro" ubuntu:24.04 \
#     sh -c 'apt-get update -q && apt-get install -y -q git python3 >/dev/null && /src/deploy/tests/agent_test.sh'
#
# It needs bash, git, flock and python3, and runs as any user.
set -euo pipefail

src=$(cd "$(dirname "$0")/../.." && pwd)
agent=$src/deploy/gitops/inbox-core-deploy
fetch=$src/deploy/aws/files/fetch-ssm-secrets.sh
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

passed=0
fail() { echo "FAIL: $*" >&2; exit 1; }
ok() { passed=$((passed + 1)); echo "ok   $*"; }
expect_eq() { [ "$1" = "$2" ] || fail "$3: expected '$2', got '$1'"; }

# A git configuration of its own: never the user's.
export GIT_CONFIG_GLOBAL=$work/gitconfig GIT_CONFIG_NOSYSTEM=1
git config --global user.email "test@example.com"
git config --global user.name "test"
git config --global init.defaultBranch main
git config --global advice.detachedHead false

# --- a remote with releases --------------------------------------------------
git init --quiet --bare "$work/origin.git"
git clone --quiet "$work/origin.git" "$work/dev" 2>/dev/null
mkdir -p "$work/dev/deploy/demo"
cat > "$work/dev/deploy/demo/demo.sh" <<'STUB'
#!/usr/bin/env bash
# Stand-in for the bundle: records the call and the settings file it was given.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
echo "$(cat "$here/VERSION") $1" >> "$TEST_CALLS"
[ -f "$DEMO_ENV_FILE" ] || exit 9
case "$1" in
  up) [ ! -f "$here/UP_FAILS" ] ;;
  smoke) [ ! -f "$here/SMOKE_FAILS" ] && [ ! -f "$TEST_BREAK_ALL" ] ;;
esac
STUB
chmod +x "$work/dev/deploy/demo/demo.sh"

# release TAG [up-fails|smoke-fails]
release() {
  local tag=$1 how=${2:-}
  (
    cd "$work/dev"
    echo "$tag" > deploy/demo/VERSION
    rm -f deploy/demo/UP_FAILS deploy/demo/SMOKE_FAILS
    case "$how" in
      up-fails) touch deploy/demo/UP_FAILS ;;
      smoke-fails) touch deploy/demo/SMOKE_FAILS ;;
    esac
    git add -A
    git commit --quiet -m "release $tag"
    git tag "$tag"
    git push --quiet origin HEAD:main "$tag" 2>/dev/null
  )
}

git clone --quiet "$work/origin.git" "$work/checkout" 2>/dev/null || true

mkdir -p "$work/etc"
cat > "$work/etc/demo.settings" <<'SETTINGS'
DEMO_DOMAIN=demo.example.com
DEMO_TUNNEL=on
SETTINGS
cat > "$work/secrets.sh" <<'SECRETS'
#!/usr/bin/env bash
[ -f "$TEST_SECRETS_FAIL" ] && { echo "secret store unreachable" >&2; exit 1; }
echo "GEMINI_API_KEY='test-key'"
echo "DEMO_TUNNEL_TOKEN='test-token'"
SECRETS
chmod +x "$work/secrets.sh"

export TEST_CALLS=$work/calls TEST_BREAK_ALL=$work/break-all TEST_SECRETS_FAIL=$work/secrets-fail

# configure NAME [INITIAL_TAG]: a host with its own state directory.
configure() {
  local name=$1 initial=${2:-}
  mkdir -p "$work/$name"
  cat > "$work/$name/deploy.conf" <<CONF
CHECKOUT_DIR=$work/checkout
TAG_PATTERN='demo-v*'
INITIAL_TAG=$initial
SETTINGS_FILE=$work/etc/demo.settings
SECRETS_COMMAND=$work/secrets.sh
ENV_FILE=$work/etc/demo.env
STATE_DIR=$work/$name/state
SMOKE_ATTEMPTS=2
SMOKE_RETRY_SECONDS=0
CONF
  export INBOX_CORE_DEPLOY_CONF=$work/$name/deploy.conf
  STATE=$work/$name/state
}

# run_agent ARGS...: runs the agent, keeps its exit status in $status and its
# output in $out, and the demo.sh calls it made in $calls.
run_agent() {
  : > "$TEST_CALLS"
  set +e
  out=$("$agent" "$@" 2>&1)
  status=$?
  set -e
  calls=$(paste -sd ',' "$TEST_CALLS")
}
field() { grep "^$1=" "$STATE/status" | cut -d= -f2-; }
head_tag() { git -C "$work/checkout" describe --tags --exact-match HEAD; }

# --- the deploy agent ---------------------------------------------------------
release demo-v0.1.0
release demo-v0.2.0
configure host demo-v0.1.0

run_agent run
expect_eq "$status" 0 "first run exit status"
expect_eq "$calls" "demo-v0.1.0 up,demo-v0.1.0 smoke" "first run brings up the initial tag"
expect_eq "$(cat "$STATE/current")" demo-v0.1.0 "current after the first run"
expect_eq "$(field outcome)" deployed "status after the first run"
expect_eq "$(head_tag)" demo-v0.1.0 "checkout after the first run"
ok "a fresh host starts at the pinned initial tag, not the newest"

expect_eq "$(stat -c %a "$work/etc/demo.env")" 600 "settings file mode"
grep -qx "DEMO_DOMAIN=demo.example.com" "$work/etc/demo.env" || fail "settings missing from demo.env"
grep -qx "GEMINI_API_KEY='test-key'" "$work/etc/demo.env" || fail "secret missing from demo.env"
ok "the bundle's settings file holds the settings and the secrets, mode 600"

run_agent run
expect_eq "$status" 0 "second run exit status"
expect_eq "$calls" "demo-v0.2.0 up,demo-v0.2.0 smoke" "second run deploys the newer tag"
expect_eq "$(field previous)" demo-v0.1.0 "previous after the upgrade"
expect_eq "$(head_tag)" demo-v0.2.0 "checkout after the upgrade"
ok "a new release tag is deployed"

run_agent run
expect_eq "$status" 0 "idle run exit status"
expect_eq "$calls" "" "an idle run calls demo.sh"
expect_eq "$(cat "$STATE/current")" demo-v0.2.0 "current after an idle run"
[[ "$out" == *"no new tag"* ]] || fail "idle run does not say so: $out"
ok "nothing happens when there is no new tag"

(cd "$work/dev" && git tag other-v9.0.0 && git tag demo-v0.1.5 HEAD~1 && git push --quiet origin other-v9.0.0 demo-v0.1.5 2>/dev/null)
run_agent run
expect_eq "$calls" "" "tags outside the pattern or older than the current one"
ok "tags outside the pattern, or older than the current tag, are ignored"

release demo-v0.3.0 smoke-fails
run_agent run
expect_eq "$status" 1 "failed deploy exit status"
expect_eq "$calls" "demo-v0.3.0 up,demo-v0.3.0 smoke,demo-v0.3.0 smoke,demo-v0.2.0 up,demo-v0.2.0 smoke" "rollback calls"
expect_eq "$(cat "$STATE/current")" demo-v0.2.0 "current after the rollback"
expect_eq "$(field outcome)" rolled-back "status after the rollback"
expect_eq "$(field tag)" demo-v0.3.0 "status names the failed tag"
expect_eq "$(head_tag)" demo-v0.2.0 "checkout after the rollback"
grep -qx demo-v0.3.0 "$STATE/failed" || fail "failed tag not recorded"
grep -q "outcome=rolled-back tag=demo-v0.3.0 previous=demo-v0.2.0" "$STATE/history.log" || fail "history line missing"
ok "a tag whose smoke test fails is rolled back to the previous tag"

run_agent run
expect_eq "$calls" "" "a failed tag is retried"
ok "a failed tag is not retried by the timer"

release demo-v0.4.0 up-fails
run_agent run
expect_eq "$status" 1 "up failure exit status"
expect_eq "$calls" "demo-v0.4.0 up,demo-v0.2.0 up,demo-v0.2.0 smoke" "up failure calls"
expect_eq "$(field outcome)" rolled-back "status after an up failure"
ok "a tag whose bring-up fails is rolled back without a smoke test"

release demo-v0.10.0
run_agent run
expect_eq "$calls" "demo-v0.10.0 up,demo-v0.10.0 smoke" "version order"
ok "tags are compared in version order (0.10 after 0.4), skipping failed ones"

touch "$TEST_SECRETS_FAIL"
cp "$work/etc/demo.env" "$work/demo.env.before"
release demo-v0.11.0
run_agent run
expect_eq "$status" 1 "secrets failure exit status"
expect_eq "$calls" "" "a deploy without its secrets calls demo.sh"
expect_eq "$(field outcome)" failed "status when the secrets cannot be read"
expect_eq "$(cat "$STATE/current")" demo-v0.10.0 "current when the secrets cannot be read"
cmp -s "$work/etc/demo.env" "$work/demo.env.before" || fail "a failed fetch changed demo.env"
grep -qx demo-v0.11.0 "$STATE/failed" && fail "a secrets failure marked the tag failed"
rm "$TEST_SECRETS_FAIL"
run_agent run
expect_eq "$calls" "demo-v0.11.0 up,demo-v0.11.0 smoke" "retry after the secrets come back"
ok "no secrets, no deploy: the stack and its settings are left alone, and the tag is retried"

"$agent" pause >/dev/null
release demo-v0.12.0
run_agent run
expect_eq "$calls" "" "a paused agent deploys"
run_agent status
[[ "$out" == *"paused=yes"* ]] || fail "status does not show the pause"
"$agent" resume >/dev/null
run_agent run
expect_eq "$calls" "demo-v0.12.0 up,demo-v0.12.0 smoke" "after resume"
ok "pause holds new tags back until resume"

run_agent deploy demo-v0.3.0
expect_eq "$status" 1 "explicit deploy of a broken tag"
expect_eq "$(cat "$STATE/current")" demo-v0.12.0 "current after a broken explicit deploy"
run_agent deploy demo-v0.2.0
expect_eq "$status" 0 "explicit deploy of an older tag"
expect_eq "$(cat "$STATE/current")" demo-v0.2.0 "current after an explicit deploy"
ok "deploy TAG deploys any tag, old or previously failed, with the same gate"

run_agent redeploy
expect_eq "$calls" "demo-v0.2.0 up,demo-v0.2.0 smoke" "redeploy"
ok "redeploy brings the current tag up again"

touch "$TEST_BREAK_ALL"
"$agent" deploy demo-v0.12.0 >/dev/null 2>&1 || true
release demo-v0.13.0
run_agent run
expect_eq "$status" 1 "double failure exit status"
expect_eq "$(field outcome)" rollback-failed "status when the previous tag fails too"
rm "$TEST_BREAK_ALL"
ok "a rollback whose smoke test also fails is reported as rollback-failed"

(
  exec 9>"$STATE/lock"
  flock -n 9
  run_agent run
  expect_eq "$status" 0 "locked run exit status"
  expect_eq "$calls" "" "a second agent ran while one held the lock"
)
ok "only one deploy runs at a time"

configure newest ""
run_agent run
expect_eq "$calls" "demo-v0.13.0 up,demo-v0.13.0 smoke" "no initial tag"
ok "with no initial tag a fresh host starts at the newest tag"

configure broken demo-v0.3.0
run_agent run
expect_eq "$status" 1 "first deploy failure exit status"
expect_eq "$(field outcome)" failed "status of a failed first deploy"
[ -s "$STATE/current" ] && fail "a failed first deploy set a current tag"
ok "a failed first deploy has nothing to return to and says so"

# --- the Parameter Store step, with a stand-in aws command ---------------------
mkdir -p "$work/bin"
cat > "$work/bin/aws" <<'AWS'
#!/usr/bin/env bash
# Stand-in for the AWS CLI: checks the call, answers from $TEST_SSM_RESPONSE.
echo "$*" > "$TEST_AWS_ARGS"
cat "$TEST_SSM_RESPONSE"
AWS
chmod +x "$work/bin/aws"
export TEST_AWS_ARGS=$work/aws-args TEST_SSM_RESPONSE=$work/ssm.json
cat > "$work/ssm.conf" <<'CONF'
AWS_REGION=eu-west-1
SECRET_PARAMETERS="GEMINI_API_KEY=/inbox-core/demo/gemini-api-key DEMO_TUNNEL_TOKEN=/inbox-core/demo/cloudflare-tunnel-token"
CONF
export INBOX_CORE_SSM_SECRETS_CONF=$work/ssm.conf

cat > "$work/ssm.json" <<'JSON'
{"Parameters": [
  {"Name": "/inbox-core/demo/gemini-api-key", "Value": "AIza'with$quote"},
  {"Name": "/inbox-core/demo/cloudflare-tunnel-token", "Value": "eyJtoken"}
], "InvalidParameters": []}
JSON
got=$(PATH="$work/bin:$PATH" "$fetch")
expect_eq "$got" "GEMINI_API_KEY='AIza'\"'\"'with\$quote'
DEMO_TUNNEL_TOKEN=eyJtoken" "fetched secrets"
(eval "$got"; [ "$GEMINI_API_KEY" = "AIza'with\$quote" ]) || fail "quoted value does not round-trip"
args=$(cat "$TEST_AWS_ARGS")
[[ "$args" == *"--region eu-west-1"* && "$args" == *"--with-decryption"* ]] || fail "aws call: $args"
[[ "$args" == *"/inbox-core/demo/gemini-api-key /inbox-core/demo/cloudflare-tunnel-token"* ]] || fail "aws names: $args"
ok "secrets are read from the named parameters in the configured region, shell-quoted"

cat > "$work/ssm.json" <<'JSON'
{"Parameters": [{"Name": "/inbox-core/demo/gemini-api-key", "Value": "k"}],
 "InvalidParameters": ["/inbox-core/demo/cloudflare-tunnel-token"]}
JSON
if out=$(PATH="$work/bin:$PATH" "$fetch" 2>&1); then fail "a missing parameter passed"; fi
[[ "$out" == *"missing parameters: /inbox-core/demo/cloudflare-tunnel-token"* ]] || fail "missing parameter message: $out"
[[ "$out" == *"GEMINI_API_KEY"* ]] && fail "printed a secret when failing"
ok "a missing parameter fails and prints no secret"

cat > "$work/ssm.json" <<'JSON'
{"Parameters": [
  {"Name": "/inbox-core/demo/gemini-api-key", "Value": "REPLACE_ME"},
  {"Name": "/inbox-core/demo/cloudflare-tunnel-token", "Value": "t"}
], "InvalidParameters": []}
JSON
if PATH="$work/bin:$PATH" "$fetch" >/dev/null 2>&1; then fail "a placeholder value passed"; fi
ok "a placeholder value fails"

echo "all ${passed} agent and secrets checks passed"
