#!/usr/bin/env bash
# The bundle's proxy in tunnel mode (DEMO_TUNNEL=on), with the real Traefik
# flags and routes from deploy/demo and stand-in upstreams. Checks what changes
# behind a Cloudflare Tunnel: the rate limits count each visitor by the
# Cf-Connecting-Ip header rather than by the one cloudflared address, the
# forwarded scheme (https) reaches Chatwoot, HSTS is sent, the named chat host
# is routed, and no certificate is requested. Needs Docker; touches only the
# compose project inboxcore-proxytest, which it removes.
#
#   ./deploy/tests/proxy_tunnel_test.sh
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
work=$(mktemp -d)
port=${PROXYTEST_PORT:-39390}
compose=(docker compose -p inboxcore-proxytest -f "$here/proxy-tunnel/compose.yaml" --env-file "$work/bundle.env")
cleanup() { "${compose[@]}" down -v --remove-orphans >/dev/null 2>&1 || true; rm -rf "$work"; }
trap cleanup EXIT
fail() { echo "FAIL: $*" >&2; "${compose[@]}" logs --no-color proxy | tail -n 40 >&2; exit 1; }
passed=0
ok() { passed=$((passed + 1)); echo "ok   $*"; }

# What demo.sh writes for DEMO_TUNNEL=on, with the named hosts.
cat > "$work/bundle.env" <<ENV
PROXYTEST_PORT=${port}
DEMO_DOMAIN=demo.example.com
DEMO_CHAT_HOST=demo-chat.example.com
DEMO_BOT_HOST=demo-bot.example.com
DEMO_TLS=off
DEMO_PUBLIC_HTTPS=on
DEMO_CLIENT_IP_HEADER=Cf-Connecting-Ip
DEMO_TRUST_FORWARDED=true
DEMO_ACME_EMAIL=owner@example.com
DEMO_HTTP_BIND=127.0.0.1:${port}
DEMO_HTTPS_BIND=127.0.0.1:0
DEMO_RATE_MESSAGES_PER_MINUTE=6
DEMO_RATE_MESSAGES_BURST=3
DEMO_RATE_CONTACTS_PER_HOUR=30
DEMO_RATE_CONTACTS_BURST=10
ENV

"${compose[@]}" up -d --quiet-pull >/dev/null 2>&1 || { "${compose[@]}" up -d; fail "the proxy did not start"; }
url="http://127.0.0.1:${port}"
code() { curl -s -o /dev/null -w '%{http_code}' "$@"; }
for _ in $(seq 40); do
  [ "$(code -H 'Host: demo.example.com' "$url/")" = 200 ] && break
  sleep 0.5
done

[ "$(code -H 'Host: demo.example.com' "$url/")" = 200 ] || fail "the page host is not routed"
[ "$(code -H 'Host: demo-chat.example.com' "$url/")" = 200 ] || fail "the named chat host is not routed"
[ "$(code -H 'Host: chat.demo.example.com' "$url/index.html")" = 404 ] || fail "the default chat host is still routed"
[ "$(code -H 'Host: demo-bot.example.com' "$url/healthz")" = 404 ] || fail "the bot host serves more than the tab"
ok "the page, the named chat host and only the bot host's tab are routed"

headers=$(curl -s -D - -o /dev/null -H 'Host: demo.example.com' "$url/")
grep -qi '^strict-transport-security: max-age=31536000' <<< "$headers" || fail "no HSTS behind the tunnel"
ok "HSTS is sent, since visitors reach the demo over https"

echoed=$(curl -s -H 'Host: demo-chat.example.com' -H 'X-Forwarded-Proto: https' "$url/cgi-bin/headers")
grep -qx 'proto=https' <<< "$echoed" || fail "the forwarded scheme did not reach Chatwoot: $echoed"
grep -qx 'host=demo-chat.example.com' <<< "$echoed" || fail "the host did not reach Chatwoot: $echoed"
ok "Chatwoot sees the visitor's https scheme and host, as cloudflared forwards them"

post() { code -X POST -H 'Host: demo-chat.example.com' -H "Cf-Connecting-Ip: $1" "$url/api/v1/widget/messages"; }
statuses=""
for _ in 1 2 3 4 5 6; do statuses="$statuses $(post 198.51.100.7)"; done
[[ "$statuses" == *429* ]] || fail "one visitor was never limited: $statuses"
[ "$(post 203.0.113.9)" != 429 ] || fail "a second visitor was limited by the first one's count"
ok "the message limit counts each visitor by Cf-Connecting-Ip:$statuses, then a new visitor passes"

if "${compose[@]}" logs --no-color proxy | grep -Eiq 'acme|certificate'; then fail "the proxy tried to get a certificate"; fi
ok "no certificate is requested"

echo "all ${passed} tunnel-mode proxy checks passed"
