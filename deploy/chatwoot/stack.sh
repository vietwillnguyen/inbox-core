#!/usr/bin/env bash
# One command to stand up a client's Chatwoot (Community Edition, pinned) and
# the inbox-core service:   ./deploy/chatwoot/stack.sh up
#
# Every docker command is scoped to the compose project "inboxcore" (or
# STACK_PROJECT, with CHATWOOT_PORT, DEMO_PORT and SERVICE_PORT, for a second
# copy on one machine; the end-to-end suite reads them from .local/stack.env); nothing
# here touches any other container, volume or network.
#
#   up                 write local secrets if missing, start everything, seed, wait
#   mode off|draft|auto   restart the service in that delivery mode
#   sources on|off     restart the service with delivery.show_sources on or off
#   stop-service       stop only the inbox-core service (to see Chatwoot's fallback)
#   start-service      start it again
#   retention DAYS     delete Chatwoot transcripts and core content older than DAYS
#   logs               every container's logs
#   status             what is running
#   down               stop everything, keep the volumes
#   destroy            stop and delete this project's volumes (asks first)
set -euo pipefail
cd "$(dirname "$0")"
PROJECT=${STACK_PROJECT:-inboxcore}
case "$PROJECT" in *[!a-z0-9_-]*|'') echo "STACK_PROJECT must be lowercase letters, digits, - and _" >&2; exit 1 ;; esac
COMPOSE=(docker compose -p "$PROJECT" -f compose.yaml)
CHATWOOT_PORT=${CHATWOOT_PORT:-3910}
DEMO_PORT=${DEMO_PORT:-3911}
SERVICE_PORT=${SERVICE_PORT:-3912}
export CHATWOOT_PORT DEMO_PORT SERVICE_PORT
CHATWOOT_ORIGIN="http://127.0.0.1:${CHATWOOT_PORT}"
# The visitor's page uses another host name than Chatwoot's dashboard, because
# browsers share cookies across ports of one host.
WIDGET_ORIGIN="http://localhost:${DEMO_PORT}"
SERVICE_ORIGIN="http://127.0.0.1:${SERVICE_PORT}"

rand() { python3 -c "import secrets,sys; print(secrets.token_urlsafe(int(sys.argv[1])))" "$1"; }
hex() { python3 -c "import secrets,sys; print(secrets.token_hex(int(sys.argv[1])))" "$1"; }

write_secrets() {
  mkdir -p .local/demo
  umask 077
  printf 'STACK_PROJECT=%s\nCHATWOOT_PORT=%s\nSERVICE_PORT=%s\n' "$PROJECT" "$CHATWOOT_PORT" "$SERVICE_PORT" > .local/stack.env
  if [ ! -f .local/chatwoot.env ]; then
    local pg rd
    pg=$(hex 16); rd=$(hex 16)
    cat > .local/chatwoot.env <<ENV
SECRET_KEY_BASE=$(hex 64)
FRONTEND_URL=${CHATWOOT_ORIGIN}
FORCE_SSL=false
ENABLE_ACCOUNT_SIGNUP=false
POSTGRES_HOST=postgres
POSTGRES_USERNAME=postgres
POSTGRES_PASSWORD=${pg}
REDIS_PASSWORD=${rd}
REDIS_URL=redis://:${rd}@redis:6379
RAILS_LOG_TO_STDOUT=true
# The quietest level that still reports failures; see docs/chatwoot.md for what it hides.
LOG_LEVEL=${CHATWOOT_LOG_LEVEL:-warn}
ACTIVE_STORAGE_SERVICE=local
# The bot service is on the compose network, a private address SafeFetch blocks by default.
SAFE_FETCH_ALLOW_PRIVATE_NETWORK=true
# No usage counts to Chatwoot's hub (lib/chatwoot_hub.rb).
DISABLE_TELEMETRY=true
ENV
  fi
  if [ ! -f .local/people.env ]; then
    cat > .local/people.env <<ENV
CHATWOOT_ADMIN_EMAIL=admin@brambleford.example
CHATWOOT_ADMIN_PASSWORD=Local-$(hex 6)-Aa1!
CHATWOOT_AGENT_EMAIL=volunteer@brambleford.example
CHATWOOT_AGENT_PASSWORD=Local-$(hex 6)-Bb2!
ENV
  fi
  if [ ! -f .local/secrets.env ]; then
    cat > .local/secrets.env <<ENV
INBOX_CORE_WEBHOOK_PATH_TOKEN=$(rand 32)
INBOX_CORE_TAB_SECRET=$(rand 48)
INBOX_CORE_ENCRYPTION_KEYS=k1:$(python3 -c "import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())")
ENV
  fi
  [ -f .local/mode ] || echo "${INBOX_CORE_MODE:-auto}" > .local/mode
  [ -f .local/sources ] || echo off > .local/sources
  write_client_config
}

write_client_config() {
  # The worked example's configuration, with its daily cap of 40 automatic
  # sends raised so the end-to-end suite can run many times in one day, and
  # delivery.show_sources set from .local/sources (off unless turned on).
  local show=false
  [ "$(cat .local/sources)" = on ] && show=true
  sed -e 's/^daily_send_cap = .*/daily_send_cap = 1000/' \
    -e "s/^\\[delivery\\]\$/[delivery]\\nshow_sources = ${show}/" \
    ../../src/inbox_core/examples/tool_library/client.toml > .local/client.toml
  # Not a secret, and the service runs as its own user: readable by all.
  chmod 644 .local/client.toml
}

wait_for() {
  local url=$1 what=$2 tries=${3:-120}
  printf 'waiting for %s' "$what"
  for _ in $(seq "$tries"); do
    if curl -fs -o /dev/null "$url"; then echo " - up"; return 0; fi
    printf '.'; sleep 2
  done
  echo; echo "$what did not come up at $url" >&2; return 1
}

seed() {
  set -a; . .local/people.env; . .local/secrets.env; set +a
  local fallback="Thanks for writing to the Brambleford Tool Library. Our assistant is unavailable right now; a volunteer will read your message and reply here."
  "${COMPOSE[@]}" exec -T \
    -e CHATWOOT_ADMIN_EMAIL -e CHATWOOT_ADMIN_PASSWORD -e CHATWOOT_AGENT_EMAIL -e CHATWOOT_AGENT_PASSWORD \
    -e BOT_OUTGOING_URL="http://inbox-core:8000/chatwoot/webhook/${INBOX_CORE_WEBHOOK_PATH_TOKEN}" \
    -e DASHBOARD_APP_URL="${SERVICE_ORIGIN}/tab" \
    -e WIDGET_ORIGIN="${WIDGET_ORIGIN}" -e FALLBACK_TEXT="${fallback}" \
    -e HANDOFF_ASSIGNEE_EMAIL="${CHATWOOT_ADMIN_EMAIL}" \
    rails bundle exec rails runner - < seed.rb | grep -E '^CHATWOOT_[A-Z_]+=' > .local/tokens.env.new
  mv .local/tokens.env.new .local/tokens.env
  write_service_env
  set -a; . .local/tokens.env; set +a
  sed -e "s|{{CHATWOOT_ORIGIN}}|${CHATWOOT_ORIGIN}|" -e "s|{{WEBSITE_TOKEN}}|${CHATWOOT_WEBSITE_TOKEN}|" \
    demo.html.tmpl > .local/demo/index.html
  echo "seeded account ${CHATWOOT_ACCOUNT_ID}, inbox ${CHATWOOT_INBOX_ID}"
}

write_service_env() {
  set -a; . .local/tokens.env; . .local/secrets.env; set +a
  cat > .local/service.env <<ENV
CHATWOOT_URL=http://rails:3000
CHATWOOT_ORIGIN=${CHATWOOT_ORIGIN}
INBOX_CORE_PUBLIC_ORIGIN=${SERVICE_ORIGIN}
CHATWOOT_ACCOUNT_ID=${CHATWOOT_ACCOUNT_ID}
CHATWOOT_BOT_TOKEN=${CHATWOOT_BOT_TOKEN}
CHATWOOT_BOT_SECRET=${CHATWOOT_BOT_SECRET}
INBOX_CORE_WEBHOOK_PATH_TOKEN=${INBOX_CORE_WEBHOOK_PATH_TOKEN}
INBOX_CORE_TAB_SECRET=${INBOX_CORE_TAB_SECRET}
INBOX_CORE_ENCRYPTION_KEYS=${INBOX_CORE_ENCRYPTION_KEYS}
INBOX_CORE_DATABASE_URL=sqlite:////data/inbox-core.db
INBOX_CORE_AUDIT_PATH=/data/audit.jsonl
# Both ways of assigning a hand-off are configured, to different people: the
# service assigns the volunteer, and the seed's rule (which would assign the
# administrator) stands down for a conversation the service assigns. The
# end-to-end suite checks that exactly one of them is notified.
INBOX_CORE_ASSIGNEE_ID=${CHATWOOT_AGENT_USER_ID}
INBOX_CORE_CLASSIFIER=${INBOX_CORE_CLASSIFIER:-example-keywords}
INBOX_CORE_CONFIG=/config/client.toml
INBOX_CORE_MODE=$(cat .local/mode)
ENV
}

case "${1:-help}" in
  up)
    write_secrets
    "${COMPOSE[@]}" up -d postgres redis
    "${COMPOSE[@]}" run --rm rails bundle exec rails db:chatwoot_prepare
    "${COMPOSE[@]}" up -d rails sidekiq
    wait_for "${CHATWOOT_ORIGIN}/api" "Chatwoot on ${CHATWOOT_ORIGIN}"
    seed
    "${COMPOSE[@]}" up -d --build inbox-core widget-demo
    wait_for "${SERVICE_ORIGIN}/healthz" "inbox-core on ${SERVICE_ORIGIN}" 60
    echo
    echo "Agent dashboard: ${CHATWOOT_ORIGIN} (sign-ins in deploy/chatwoot/.local/people.env)"
    echo "Visitor page:    ${WIDGET_ORIGIN}"
    echo "Delivery mode:   $(cat .local/mode)"
    ;;
  mode)
    case "${2:-}" in off|draft|auto) ;; *) echo "usage: $0 mode off|draft|auto" >&2; exit 2;; esac
    echo "$2" > .local/mode
    write_service_env
    "${COMPOSE[@]}" up -d --build --force-recreate inbox-core
    wait_for "${SERVICE_ORIGIN}/healthz" "inbox-core in $2 mode" 60
    ;;
  sources)
    case "${2:-}" in on|off) ;; *) echo "usage: $0 sources on|off" >&2; exit 2;; esac
    echo "$2" > .local/sources
    write_client_config
    "${COMPOSE[@]}" up -d --build --force-recreate inbox-core
    wait_for "${SERVICE_ORIGIN}/healthz" "inbox-core with sources $2" 60
    ;;
  stop-service) "${COMPOSE[@]}" stop inbox-core ;;
  start-service)
    "${COMPOSE[@]}" start inbox-core
    wait_for "${SERVICE_ORIGIN}/healthz" "inbox-core" 60
    ;;
  retention)
    days=${2:?usage: $0 retention DAYS}
    # The administrator's token is passed to this one run only; the service never holds it.
    set -a; . .local/tokens.env; set +a
    "${COMPOSE[@]}" exec -T -e CHATWOOT_ADMIN_TOKEN="${CHATWOOT_ADMIN_TOKEN}" inbox-core \
      /app/.venv/bin/python -m inbox_core.chatwoot retention --days "$days"
    ;;
  logs) "${COMPOSE[@]}" logs --no-color --timestamps ;;
  status) "${COMPOSE[@]}" ps ;;
  down) "${COMPOSE[@]}" stop ;;
  destroy)
    read -r -p "Delete the ${PROJECT} project's containers and volumes? [y/N] " answer
    [ "$answer" = "y" ] && "${COMPOSE[@]}" down -v
    ;;
  *) sed -n '2,20p' "$0" ;;
esac
