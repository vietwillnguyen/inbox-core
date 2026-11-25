#!/usr/bin/env bash
# The public demo bundle for the made-up Quillmoor Cycle Works. One command:
#
#   ./deploy/demo/demo.sh up
#
# With no deploy/demo/.env it runs locally: plain HTTP on 127.0.0.1:3930, host
# names under demo.localhost, and the stand-in model, so it needs no key and no
# network beyond pulling images. With a .env copied from .env.example (on the
# server) it serves DEMO_DOMAIN on ports 80 and 443 with certificates from
# Let's Encrypt, and the model named by DEMO_MODEL. With DEMO_TUNNEL=on in that
# .env it publishes no port at all: a Cloudflare Tunnel connects out to the
# proxy and Cloudflare serves the certificates. DEMO_ENV_FILE names a settings
# file other than deploy/demo/.env. See docs/demo.md.
#
#   up              write secrets if missing, start everything, seed, wait
#   settings        the mode and public origins this configuration gives
#   smoke           check every public route and one answered question
#   status          what is running
#   memory          each container's memory use now, and the total
#   reset [DAYS]    delete conversations older than DAYS (default 1) right now
#   logs            every container's logs
#   down            stop everything, keep the data
#   destroy         stop and delete this project's containers and volumes (asks first)
#
# Every docker command is scoped to the compose project "inboxcore-demo";
# nothing here touches any other container, volume or network.
set -euo pipefail
cd "$(dirname "$0")"
PROJECT=inboxcore-demo
ENV_FILE=${DEMO_ENV_FILE:-.env}

rand() { python3 -c "import secrets,sys; print(secrets.token_urlsafe(int(sys.argv[1])))" "$1"; }
hex() { python3 -c "import secrets,sys; print(secrets.token_hex(int(sys.argv[1])))" "$1"; }
die() { echo "demo.sh: $*" >&2; exit 1; }

# --- settings: the owner's .env on a server, local defaults otherwise -------
load_settings() {
  DEMO_TUNNEL=${DEMO_TUNNEL:-off}
  if [ -f "$ENV_FILE" ]; then
    set -a
    # shellcheck source=/dev/null
    . "$ENV_FILE"
    set +a
    DEMO_TUNNEL=${DEMO_TUNNEL:-off}
    : "${DEMO_DOMAIN:?set DEMO_DOMAIN in ${ENV_FILE}}"
    if [ "$DEMO_TUNNEL" = on ]; then
      # Cloudflare ends TLS and connects out to the proxy: no certificates
      # here, and nothing published beyond this machine's loopback.
      [ -n "${DEMO_TUNNEL_TOKEN:-}" ] || die "DEMO_TUNNEL=on needs DEMO_TUNNEL_TOKEN in ${ENV_FILE}"
      [ "${DEMO_TLS:-off}" = off ] || die "DEMO_TUNNEL=on and DEMO_TLS=on are exclusive: Cloudflare serves the certificates"
      DEMO_TLS=off
      DEMO_ACME_EMAIL=${DEMO_ACME_EMAIL:-owner@example.com}
      DEMO_HTTP_BIND=${DEMO_HTTP_BIND:-127.0.0.1:3930}
      DEMO_HTTPS_BIND=${DEMO_HTTPS_BIND:-127.0.0.1:3931}
    else
      : "${DEMO_ACME_EMAIL:?set DEMO_ACME_EMAIL in ${ENV_FILE}}"
      DEMO_TLS=${DEMO_TLS:-on}
      DEMO_HTTP_BIND=${DEMO_HTTP_BIND:-80}
      DEMO_HTTPS_BIND=${DEMO_HTTPS_BIND:-443}
    fi
  else
    DEMO_DOMAIN=${DEMO_DOMAIN:-demo.localhost}
    DEMO_ACME_EMAIL=${DEMO_ACME_EMAIL:-owner@example.com}
    DEMO_TLS=${DEMO_TLS:-off}
    DEMO_HTTP_BIND=${DEMO_HTTP_BIND:-127.0.0.1:3930}
    DEMO_HTTPS_BIND=${DEMO_HTTPS_BIND:-127.0.0.1:3931}
  fi
  DEMO_MODEL=${DEMO_MODEL:-stand-in}
  DEMO_GEMINI_MODEL=${DEMO_GEMINI_MODEL:-gemini/gemini-3.5-flash-lite}
  DEMO_DAILY_BUDGET_USD=${DEMO_DAILY_BUDGET_USD:-1.00}
  DEMO_ADMIN_EMAIL=${DEMO_ADMIN_EMAIL:-owner@quillmoor.example}
  DEMO_RATE_MESSAGES_PER_MINUTE=${DEMO_RATE_MESSAGES_PER_MINUTE:-6}
  DEMO_RATE_MESSAGES_BURST=${DEMO_RATE_MESSAGES_BURST:-5}
  DEMO_RATE_CONTACTS_PER_HOUR=${DEMO_RATE_CONTACTS_PER_HOUR:-30}
  DEMO_RATE_CONTACTS_BURST=${DEMO_RATE_CONTACTS_BURST:-10}
  DEMO_RESET_DAYS=${DEMO_RESET_DAYS:-1}
  DEMO_RESET_EVERY_SECONDS=${DEMO_RESET_EVERY_SECONDS:-3600}
  case "$DEMO_MODEL" in
    stand-in) ;;
    gemini) [ -n "${GEMINI_API_KEY:-}" ] || die "DEMO_MODEL=gemini needs GEMINI_API_KEY in deploy/demo/.env" ;;
    *) die "DEMO_MODEL must be stand-in or gemini" ;;
  esac
  case "$DEMO_TLS" in on|off) ;; *) die "DEMO_TLS must be on or off" ;; esac
  case "$DEMO_TUNNEL" in on|off) ;; *) die "DEMO_TUNNEL must be on or off" ;; esac
  # The chat and bot hosts default to subdomains of the page's host. Name them
  # explicitly when the certificate cannot cover a second level (Cloudflare's
  # free certificate covers *.example.com, not *.demo.example.com).
  DEMO_CHAT_HOST=${DEMO_CHAT_HOST:-chat.${DEMO_DOMAIN}}
  DEMO_BOT_HOST=${DEMO_BOT_HOST:-bot.${DEMO_DOMAIN}}
  local scheme=http suffix=""
  if [ "$DEMO_TLS" = on ] || [ "$DEMO_TUNNEL" = on ]; then scheme=https; fi
  # A local run publishes on a high port; the origins browsers use carry it.
  if [ "$scheme" = http ] && [ "${DEMO_HTTP_BIND##*:}" != 80 ]; then suffix=":${DEMO_HTTP_BIND##*:}"; fi
  PAGE_HOST="${DEMO_DOMAIN}${suffix}"
  PAGE_ORIGIN="${scheme}://${PAGE_HOST}"
  CHAT_ORIGIN="${scheme}://${DEMO_CHAT_HOST}${suffix}"
  BOT_ORIGIN="${scheme}://${DEMO_BOT_HOST}${suffix}"
  # Behind the tunnel every request reaches the proxy from cloudflared, so the
  # visitor's address is the header Cloudflare sets, and the forwarded scheme
  # (https) is trusted. Nothing else can reach the proxy: no port is published
  # beyond loopback.
  if [ "$DEMO_TUNNEL" = on ]; then
    DEMO_CLIENT_IP_HEADER=Cf-Connecting-Ip
    DEMO_TRUST_FORWARDED=true
  else
    DEMO_CLIENT_IP_HEADER=""
    DEMO_TRUST_FORWARDED=false
  fi
  DEMO_PUBLIC_HTTPS=off
  [ "$scheme" = https ] && DEMO_PUBLIC_HTTPS=on
  COMPOSE=(docker compose -p "$PROJECT" -f compose.yaml --env-file .local/bundle.env)
  [ "$DEMO_TUNNEL" = on ] && COMPOSE+=(--profile tunnel)
  return 0
}

write_bundle_env() {
  mkdir -p .local/page
  umask 077
  cat > .local/bundle.env <<ENV
DEMO_DOMAIN=${DEMO_DOMAIN}
DEMO_CHAT_HOST=${DEMO_CHAT_HOST}
DEMO_BOT_HOST=${DEMO_BOT_HOST}
DEMO_TLS=${DEMO_TLS}
DEMO_PUBLIC_HTTPS=${DEMO_PUBLIC_HTTPS}
DEMO_CLIENT_IP_HEADER=${DEMO_CLIENT_IP_HEADER}
DEMO_TRUST_FORWARDED=${DEMO_TRUST_FORWARDED}
DEMO_ACME_EMAIL=${DEMO_ACME_EMAIL}
DEMO_HTTP_BIND=${DEMO_HTTP_BIND}
DEMO_HTTPS_BIND=${DEMO_HTTPS_BIND}
DEMO_RATE_MESSAGES_PER_MINUTE=${DEMO_RATE_MESSAGES_PER_MINUTE}
DEMO_RATE_MESSAGES_BURST=${DEMO_RATE_MESSAGES_BURST}
DEMO_RATE_CONTACTS_PER_HOUR=${DEMO_RATE_CONTACTS_PER_HOUR}
DEMO_RATE_CONTACTS_BURST=${DEMO_RATE_CONTACTS_BURST}
PAGE_ORIGIN=${PAGE_ORIGIN}
CHAT_ORIGIN=${CHAT_ORIGIN}
BOT_ORIGIN=${BOT_ORIGIN}
ENV
  # Written in every mode, empty without the tunnel, so the file compose reads exists.
  printf 'TUNNEL_TOKEN=%s\n' "${DEMO_TUNNEL_TOKEN:-}" > .local/tunnel.env
}

write_secrets() {
  umask 077
  if [ ! -f .local/secrets.env ]; then
    cat > .local/secrets.env <<ENV
POSTGRES_PASSWORD=$(hex 16)
REDIS_PASSWORD=$(hex 16)
SECRET_KEY_BASE=$(hex 64)
LITELLM_MASTER_KEY=sk-$(rand 32)
INBOX_CORE_WEBHOOK_PATH_TOKEN=$(rand 32)
INBOX_CORE_TAB_SECRET=$(rand 48)
INBOX_CORE_ENCRYPTION_KEYS=k1:$(python3 -c "import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())")
ENV
  fi
  if [ ! -f .local/people.env ]; then
    cat > .local/people.env <<ENV
CHATWOOT_ADMIN_EMAIL=${DEMO_ADMIN_EMAIL}
CHATWOOT_ADMIN_PASSWORD=Demo-$(hex 8)-Aa1!
ENV
  fi
  set -a; . .local/secrets.env; set +a
  cat > .local/chatwoot.env <<ENV
SECRET_KEY_BASE=${SECRET_KEY_BASE}
FRONTEND_URL=${CHAT_ORIGIN}
# TLS ends at the proxy; inbox-core calls rails over plain HTTP inside the network.
FORCE_SSL=false
ENABLE_ACCOUNT_SIGNUP=false
POSTGRES_HOST=postgres
POSTGRES_USERNAME=postgres
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
REDIS_PASSWORD=${REDIS_PASSWORD}
REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379
RAILS_LOG_TO_STDOUT=true
# The quietest level that still reports failures; at info Chatwoot logs visitor text.
LOG_LEVEL=warn
ACTIVE_STORAGE_SERVICE=local
SAFE_FETCH_ALLOW_PRIVATE_NETWORK=true
DISABLE_TELEMETRY=true
# Sized for a small server: one puma process and a smaller sidekiq pool.
WEB_CONCURRENCY=0
RAILS_MAX_THREADS=5
SIDEKIQ_CONCURRENCY=5
ENV
  cat > .local/litellm.env <<ENV
LITELLM_MASTER_KEY=${LITELLM_MASTER_KEY}
REDIS_PASSWORD=${REDIS_PASSWORD}
DEMO_DAILY_BUDGET_USD=${DEMO_DAILY_BUDGET_USD}
DEMO_GEMINI_MODEL=${DEMO_GEMINI_MODEL}
GEMINI_API_KEY=${GEMINI_API_KEY:-}
ENV
}

write_service_env() {
  set -a; . .local/secrets.env; . .local/tokens.env; set +a
  umask 077
  cat > .local/service.env <<ENV
CHATWOOT_URL=http://rails:3000
CHATWOOT_ORIGIN=${CHAT_ORIGIN}
INBOX_CORE_PUBLIC_ORIGIN=${BOT_ORIGIN}
CHATWOOT_ACCOUNT_ID=${CHATWOOT_ACCOUNT_ID}
CHATWOOT_BOT_TOKEN=${CHATWOOT_BOT_TOKEN}
CHATWOOT_BOT_SECRET=${CHATWOOT_BOT_SECRET}
INBOX_CORE_WEBHOOK_PATH_TOKEN=${INBOX_CORE_WEBHOOK_PATH_TOKEN}
INBOX_CORE_TAB_SECRET=${INBOX_CORE_TAB_SECRET}
INBOX_CORE_ENCRYPTION_KEYS=${INBOX_CORE_ENCRYPTION_KEYS}
INBOX_CORE_DATABASE_URL=sqlite:////data/inbox-core.db
INBOX_CORE_ASSIGNEE_ID=${CHATWOOT_ADMIN_USER_ID}
INBOX_CORE_CLASSIFIER=litellm
INBOX_CORE_MODEL=litellm_proxy/${DEMO_MODEL}
INBOX_CORE_MODEL_API_BASE=http://litellm:4000
INBOX_CORE_MODEL_API_KEY=${LITELLM_MASTER_KEY}
INBOX_CORE_CONFIG=/config/client.toml
INBOX_CORE_KNOWLEDGE=/config/knowledge.md
LITELLM_LOCAL_MODEL_COST_MAP=True
ENV
  cat > .local/reset.env <<ENV
CHATWOOT_ADMIN_TOKEN=${CHATWOOT_ADMIN_TOKEN}
DEMO_RESET_DAYS=${DEMO_RESET_DAYS}
DEMO_RESET_EVERY_SECONDS=${DEMO_RESET_EVERY_SECONDS}
ENV
}

wait_for() {
  local what=$1 tries=$2; shift 2
  printf 'waiting for %s' "$what"
  for _ in $(seq "$tries"); do
    if "$@" >/dev/null 2>&1; then echo " - up"; return 0; fi
    printf '.'; sleep 3
  done
  echo; die "$what did not come up"
}

inside() { "${COMPOSE[@]}" exec -T "$1" sh -c "$2"; }
rails_up() { inside rails 'wget -q -O /dev/null http://127.0.0.1:3000/api'; }
service_up() {
  inside inbox-core "/app/.venv/bin/python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3)\""
}
gateway_up() {
  inside inbox-core "/app/.venv/bin/python -c \"import urllib.request; urllib.request.urlopen('http://litellm:4000/health/liveliness', timeout=3)\""
}

seed() {
  set -a; . .local/people.env; . .local/secrets.env; set +a
  local fallback="Thanks for writing to Quillmoor Cycle Works. Our assistant is unavailable right now; a person from the shop will read your message. (This is a demo of a made-up shop.)"
  "${COMPOSE[@]}" exec -T \
    -e CHATWOOT_ADMIN_EMAIL -e CHATWOOT_ADMIN_PASSWORD -e TEST_FIXTURES=false \
    -e ORG_NAME="Quillmoor Cycle Works" -e BOT_NAME="Quillmoor assistant" \
    -e WIDGET_TAGLINE="A demo of a made-up bike shop. Conversations are deleted within a day." \
    -e CATEGORY_LABELS="faq repair_advice booking repair_status refund complaint safety press other" \
    -e WIDGET_ATTACHMENTS=false -e WIDGET_ALLOWED_DOMAINS="${PAGE_HOST}" \
    -e BOT_OUTGOING_URL="http://inbox-core:8000/chatwoot/webhook/${INBOX_CORE_WEBHOOK_PATH_TOKEN}" \
    -e DASHBOARD_APP_URL="${BOT_ORIGIN}/tab" \
    -e WIDGET_ORIGIN="${PAGE_ORIGIN}" -e FALLBACK_TEXT="${fallback}" \
    rails bundle exec rails runner - < ../chatwoot/seed.rb | grep -E '^CHATWOOT_[A-Z_]+=' > .local/tokens.env.new
  mv .local/tokens.env.new .local/tokens.env
  chmod 600 .local/tokens.env
  set -a; . .local/tokens.env; set +a
  # Not a secret, and the page server runs as another user: readable by all.
  sed -e "s|{{CHATWOOT_ORIGIN}}|${CHAT_ORIGIN}|" -e "s|{{WEBSITE_TOKEN}}|${CHATWOOT_WEBSITE_TOKEN}|" \
    page/index.html.tmpl > .local/page/index.html
  chmod 755 .local/page
  chmod 644 .local/page/index.html
  echo "seeded account ${CHATWOOT_ACCOUNT_ID}, inbox ${CHATWOOT_INBOX_ID}"
}

load_settings

case "${1:-help}" in
  up)
    write_bundle_env
    write_secrets
    "${COMPOSE[@]}" build inbox-core
    "${COMPOSE[@]}" up -d postgres redis
    "${COMPOSE[@]}" run --rm rails bundle exec rails db:chatwoot_prepare
    edge=(proxy)
    [ "$DEMO_TUNNEL" = on ] && edge+=(tunnel)
    "${COMPOSE[@]}" up -d rails sidekiq litellm page "${edge[@]}"
    wait_for "Chatwoot" 100 rails_up
    seed
    write_service_env
    "${COMPOSE[@]}" up -d --force-recreate inbox-core reset
    wait_for "inbox-core" 40 service_up
    wait_for "the LiteLLM gateway" 60 gateway_up
    echo
    echo "Visitor page:    ${PAGE_ORIGIN}"
    echo "Owner dashboard: ${CHAT_ORIGIN} (sign-in in deploy/demo/.local/people.env)"
    echo "Model:           ${DEMO_MODEL}, at most ${DEMO_DAILY_BUDGET_USD} US dollars a day"
    ;;
  settings)
    mode=local
    [ "$DEMO_TLS" = on ] && mode=letsencrypt
    [ "$DEMO_TUNNEL" = on ] && mode=tunnel
    echo "mode:            ${mode}"
    echo "page:            ${PAGE_ORIGIN}"
    echo "chat:            ${CHAT_ORIGIN}"
    echo "bot:             ${BOT_ORIGIN}"
    echo "published ports: ${DEMO_HTTP_BIND} ${DEMO_HTTPS_BIND}"
    echo "model:           ${DEMO_MODEL}"
    ;;
  smoke)
    set -a; . .local/tokens.env; set +a
    python3 smoke.py --page "$PAGE_ORIGIN" --chat "$CHAT_ORIGIN" --bot "$BOT_ORIGIN" \
      --website-token "$CHATWOOT_WEBSITE_TOKEN"
    ;;
  status) "${COMPOSE[@]}" ps ;;
  memory)
    mapfile -t containers < <("${COMPOSE[@]}" ps -q)
    docker stats --no-stream --format '{{.Name}} {{.MemUsage}}' \
      "${containers[@]}" | python3 -c '
import re, sys
units = {"B": 1, "KiB": 2**10, "MiB": 2**20, "GiB": 2**30}
total = 0
for line in sys.stdin:
    name, used = line.split()[0], line.split()[1]
    number, unit = re.match(r"([\d.]+)(\w+)", used).groups()
    total += float(number) * units[unit]
    print(f"{name:40} {used}")
print("total".ljust(40), f"{total / 2**20:.0f}MiB")'
    ;;
  reset)
    days=${2:-1}
    # shellcheck disable=SC2016 # expanded by the container's shell
    "${COMPOSE[@]}" exec -T -e DEMO_RESET_DAYS="$days" reset \
      sh -c '/app/.venv/bin/python -m inbox_core.chatwoot retention --days "$DEMO_RESET_DAYS"'
    ;;
  logs) "${COMPOSE[@]}" logs --no-color --timestamps ;;
  down) "${COMPOSE[@]}" stop ;;
  destroy)
    read -r -p "Delete the ${PROJECT} project's containers and volumes? [y/N] " answer
    [ "$answer" = "y" ] && "${COMPOSE[@]}" down -v
    ;;
  *) sed -n '2,26p' "$(basename "$0")" ;;
esac
