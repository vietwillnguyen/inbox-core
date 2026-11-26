#!/usr/bin/env bash
# End to end: the deploy agent brings the real bundle up in tunnel mode, and
# the smoke test passes through the tunnel's path, then a release whose smoke
# test fails is rolled back.
#
# Cloudflare is the one part that cannot run here, so a stand-in edge takes its
# place: a Traefik container that ends TLS for the demo's host names (with a
# certificate made for the test), adds Cf-Connecting-Ip, and hands every request
# to http://proxy:80 on the bundle's network, as cloudflared does. The bundle's
# own cloudflared container runs with a token that is not real and is ignored.
#
#   ./deploy/tests/tunnel_e2e.sh
#
# Needs Docker, git, openssl, curl and Python 3, and 127.0.0.1:443 free. It
# touches only the compose project inboxcore-tunnele2e and the container
# inboxcore-tunnele2e-edge, and removes both. Takes several minutes.
set -euo pipefail

src=$(cd "$(dirname "$0")/../.." && pwd)
work=$(mktemp -d)
project=inboxcore-tunnele2e
edge=${project}-edge
port=${TUNNEL_E2E_PORT:-39330}
export GIT_CONFIG_GLOBAL=$work/gitconfig GIT_CONFIG_NOSYSTEM=1
git config --global user.email "test@example.com"
git config --global user.name "test"
git config --global advice.detachedHead false

compose() { docker compose -p "$project" -f "$work/checkout/deploy/demo/compose.yaml" \
  --env-file "$work/checkout/deploy/demo/.local/bundle.env" --profile tunnel "$@"; }
cleanup() {
  if [ -n "${connector:-}" ]; then kill "$connector" 2>/dev/null || true; fi
  docker rm -f "$edge" >/dev/null 2>&1 || true
  if [ -f "$work/checkout/deploy/demo/.local/bundle.env" ]; then
    compose down -v --remove-orphans >/dev/null 2>&1 || true
  fi
  rm -rf "$work"
}
trap cleanup EXIT
fail() {
  echo "FAIL: $*" >&2
  tail -n 60 "$work/agent.log" >&2 2>/dev/null || true
  compose logs --no-color --tail 30 proxy rails inbox-core >&2 2>/dev/null || true
  exit 1
}
passed=0
ok() { passed=$((passed + 1)); echo "ok   $*"; }

# --- releases: this checkout as demo-v0.0.1, and a demo-v0.0.2 whose smoke test fails
git clone --quiet --no-local "$src" "$work/dev"
(cd "$work/dev" && git tag demo-v0.0.1)
(cd "$work/dev" && sed -i '1i raise SystemExit("this release fails its smoke test on purpose")' deploy/demo/smoke.py \
  && git commit --quiet -am "a release whose smoke test fails" && git tag demo-v0.0.2)
git clone --quiet --bare "$work/dev" "$work/origin.git"
(cd "$work/origin.git" && git tag -d demo-v0.0.2 >/dev/null)   # published later
git clone --quiet "$work/origin.git" "$work/checkout"

# --- the host's settings, as the AWS user data or a staging machine writes them
cat > "$work/demo.settings" <<SETTINGS
DEMO_PROJECT=${project}
DEMO_DOMAIN=demo.localhost
DEMO_TUNNEL=on
DEMO_HTTP_BIND=127.0.0.1:${port}
DEMO_HTTPS_BIND=127.0.0.1:$((port + 1))
DEMO_MODEL=stand-in
SETTINGS
printf "DEMO_TUNNEL_TOKEN='not-a-real-token'\n" > "$work/secrets.env"
cat > "$work/deploy.conf" <<CONF
CHECKOUT_DIR=$work/checkout
TAG_PATTERN='demo-v*'
INITIAL_TAG=demo-v0.0.1
SETTINGS_FILE=$work/demo.settings
SECRETS_FILE=$work/secrets.env
ENV_FILE=$work/demo.env
STATE_DIR=$work/state
SMOKE_ATTEMPTS=3
SMOKE_RETRY_SECONDS=10
CONF
export INBOX_CORE_DEPLOY_CONF=$work/deploy.conf

# --- the stand-in edge ------------------------------------------------------------
mkdir -p "$work/edge"
openssl req -x509 -newkey rsa:2048 -nodes -days 1 -subj "/CN=demo.localhost" \
  -addext "subjectAltName=DNS:demo.localhost,DNS:*.demo.localhost" \
  -keyout "$work/edge/key.pem" -out "$work/edge/cert.pem" 2>/dev/null
chmod 644 "$work/edge/key.pem"
cat > "$work/edge/edge.yaml" <<'EDGE'
tls:
  certificates:
    - certFile: /edge/cert.pem
      keyFile: /edge/key.pem
http:
  routers:
    all:
      rule: "HostRegexp(`.+`)"
      entryPoints: [websecure]
      tls: {}
      middlewares: [cloudflare]
      service: proxy
  middlewares:
    cloudflare:
      headers:
        customRequestHeaders:
          Cf-Connecting-Ip: "192.0.2.10"
  services:
    proxy:
      loadBalancer:
        passHostHeader: true
        servers: [{url: "http://proxy:80"}]
EDGE
docker run -d --name "$edge" -p 127.0.0.1:443:443 -v "$work/edge:/edge:ro" traefik:v3.6.2 \
  --entrypoints.websecure.address=:443 --providers.file.filename=/edge/edge.yaml \
  --log.level=WARN --global.checknewversion=false --global.sendanonymoususage=false >/dev/null
# Join the bundle's network once demo.sh has created it, as cloudflared would be.
( until docker network inspect "${project}_default" >/dev/null 2>&1; do sleep 2; done
  docker network connect "${project}_default" "$edge" ) &
connector=$!

# smoke.py trusts the stand-in edge's certificate; nothing else does.
export SSL_CERT_FILE=$work/edge/cert.pem
agent=$src/deploy/gitops/inbox-core-deploy

# --- the first deploy -------------------------------------------------------------
"$agent" run > "$work/agent.log" 2>&1 || fail "the first deploy failed"
grep -qx "outcome=deployed" "$work/state/status" || fail "status after the first deploy: $(cat "$work/state/status")"
ok "the agent deployed demo-v0.0.1 in tunnel mode and the smoke test passed through the edge"

curl() { command curl -s --cacert "$work/edge/cert.pem" --resolve "$1:443:127.0.0.1" "${@:2}"; }
[ "$(curl demo.localhost -o /dev/null -w '%{http_code}' https://demo.localhost/)" = 200 ] || fail "the page is not served over https"
curl demo.localhost -D - -o /dev/null https://demo.localhost/ | grep -qi '^strict-transport-security' || fail "no HSTS"
[ "$(curl bot.demo.localhost -o /dev/null -w '%{http_code}' https://bot.demo.localhost/healthz)" = 404 ] || fail "the bot's health check is public"
ok "visitors get the page over https with HSTS, and the bot's internals stay private"

ports=$(docker ps --filter "label=com.docker.compose.project=${project}" --format '{{.Label "com.docker.compose.service"}} {{.Ports}}' | grep -- '->' || true)
[ "$(echo "$ports" | cut -d' ' -f1 | sort -u)" = proxy ] || fail "something other than the proxy publishes a port: $ports"
if echo "$ports" | tr -s ' ,' '\n' | grep -- '->' | grep -qv '^127\.0\.0\.1:'; then fail "the proxy is published beyond loopback: $ports"; fi
ok "nothing but the proxy publishes a port, and only on loopback"

grep -qx 'TUNNEL_TOKEN=not-a-real-token' "$work/checkout/deploy/demo/.local/tunnel.env" \
  || fail "the tunnel token did not reach cloudflared's env file"
ok "the tunnel token from the secrets reaches the cloudflared container's env file"

# --- a release whose smoke test fails ---------------------------------------------------
(cd "$work/dev" && git push --quiet "$work/origin.git" demo-v0.0.2)
if "$agent" run >> "$work/agent.log" 2>&1; then fail "a failing release reported success"; fi
grep -qx "outcome=rolled-back" "$work/state/status" || fail "status after the failing release: $(cat "$work/state/status")"
[ "$(cat "$work/state/current")" = demo-v0.0.1 ] || fail "current is not demo-v0.0.1 after the rollback"
[ "$(git -C "$work/checkout" describe --tags --exact-match HEAD)" = demo-v0.0.1 ] || fail "the checkout is not back at demo-v0.0.1"
(cd "$work/checkout" && DEMO_ENV_FILE="$work/demo.env" ./deploy/demo/demo.sh smoke >/dev/null) || fail "the rolled-back stack fails its smoke test"
ok "a release whose smoke test fails is rolled back, and the previous release serves again"

"$agent" run >> "$work/agent.log" 2>&1 || fail "an idle run failed"
grep -q "no new tag" "$work/agent.log" || fail "the failed release was retried"
ok "the failed release is not retried"

echo "all ${passed} tunnel-mode end-to-end checks passed"
