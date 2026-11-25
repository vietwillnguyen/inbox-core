# The public demo

`deploy/demo/` is a deployable bundle that runs inbox-core in public for a made-up business, Quillmoor Cycle Works.
A visitor chats in Chatwoot's website widget on a small page; the core answers from the shop's knowledge base, holds repair advice for the owner to approve, and passes everything else to a person.
It is meant to run on one small server with one command.

Going live needs only:

1. a server (an Oracle Cloud always-free Ampere instance is enough, see [Sizing](#sizing));
2. a domain name you can add DNS records to;
3. a Gemini API key, with a daily spend you are comfortable with.

Everything else, including every secret, is generated on the server by the bring-up command.

To run it on AWS with no inbound port at all, behind a Cloudflare Tunnel, and deploy new versions by pushing a release tag, follow [aws.md](aws.md) instead of the server steps below.

## What is in the bundle

| Container | Image | What it does |
|---|---|---|
| `tunnel` | `cloudflare/cloudflared:2026.10.7` | Only with `DEMO_TUNNEL=on`: connects out to a Cloudflare Tunnel, so nothing is published (see [Behind a Cloudflare Tunnel instead](#behind-a-cloudflare-tunnel-instead)) |
| `proxy` | `traefik:v3.6.2` | The only published ports (80, 443). Certificates from Let's Encrypt, per-address rate limits, and routing; everything not listed below answers 404 |
| `rails`, `sidekiq` | `chatwoot/chatwoot:v4.19.1-ce` | Chatwoot Community Edition: the widget's API and the owner's dashboard |
| `postgres`, `redis` | `pgvector/pgvector:pg16`, `redis:7-alpine` | Chatwoot's database and queue; Redis also keeps the model spend counter |
| `inbox-core` | built from this repository | The Chatwoot connection ([chatwoot.md](chatwoot.md)) with the shop's configuration, reaching the model through the gateway |
| `litellm` | `ghcr.io/berriai/litellm:v1.103.2` | The model gateway, with the daily spend cap. Never published |
| `page` | `busybox:1.37` | The visitor's page with the widget, and the 404 for everything else |
| `reset` | the inbox-core image | Deletes conversations and contacts older than a day, every hour |

Every image is published for `linux/arm64` as well as `linux/amd64`.

Three host names point at the server:

| Host | Serves |
|---|---|
| `DEMO_DOMAIN` (for example `demo.example.com`) | The visitor's page |
| `chat.DEMO_DOMAIN` (or `DEMO_CHAT_HOST`) | Chatwoot: the widget's API and the owner's dashboard |
| `bot.DEMO_DOMAIN` (or `DEMO_BOT_HOST`) | inbox-core's draft tab only (`/tab`), which the dashboard frames |

inbox-core's webhook, `/healthz` and `/metrics`, and the gateway are reachable only inside the compose network.

The shop's configuration, knowledge base (thirty entries), golden set and stand-in rules are in `deploy/demo/client/`.
Everything about the shop is invented; nothing describes a real business, place or person.

## How it behaves

- A question the knowledge base covers is answered.
  The visitor sees the answer alone, with no knowledge entry ids or titles; the owner sees the entries it was based on in a private note on the conversation (which the widget never shows), in the draft tab for held replies, and in the audit record.
- Repair advice (`repair_advice`) is drafted and held: the owner sends, edits or discards it from the `inbox-core drafts` tab in the dashboard, and the visitor sees nothing until then (`delivery.approval_categories`).
- Bookings, questions about an order, refunds, complaints, safety, press, anything that mentions money, anything unsure and anything off-topic get the shop's holding message, which says this is a demo, and the conversation is opened for a person with a staff note saying why.
- The tier is decided in code from the shop's category table, so a message telling the assistant to ignore its instructions has nothing to change.
- Every price question goes to a person, because the core escalates any message that mentions money (see [Open questions](#open-questions)).

## Sizing

Measured on the local bundle (amd64) after its end-to-end suite had run:

| Container | Memory |
|---|---|
| `sidekiq` | 571 MiB |
| `rails` | 516 MiB |
| `litellm` | 508 MiB |
| `inbox-core` | 225 MiB |
| `postgres` | 132 MiB |
| `proxy`, `redis`, `reset`, `page` | 40 MiB together |
| **Total** | **about 2.0 GiB** |

Run `./deploy/demo/demo.sh memory` on the server for its own numbers.
Each container has a memory limit in `compose.yaml` (4.6 GiB in total), so one runaway process cannot take the server down.

- The full always-free Ampere allowance (4 OCPU, 24 GB) is far more than needed.
- The smallest sensible Ampere shape is **1 OCPU and 6 GB**, which leaves room for the image builds and Postgres's cache; 2 OCPU makes the first start and the image build faster.
- The always-free AMD micro shapes (1 GB) are too small: Chatwoot alone needs more.
- Disk: about 6 GB of images plus the data, so the default 47 GB boot volume is plenty.

The bundle was also brought up with every container on `linux/arm64` (under emulation on an amd64 machine): it seeded, served, and passed `demo.sh smoke`.
The first start under emulation took about twenty minutes; a real Ampere core runs these images natively.

## Before you start: prove the real model

The bundle's end-to-end suite runs on the stand-in, which is not a model.
Before switching the demo to Gemini, score Gemini on the shop's golden set from a development machine (it makes about forty model calls):

```sh
uv pip install 'inbox-core[litellm]'
export GEMINI_API_KEY=...        # in your shell only, never in a file in the repository
uv run python -m inbox_core.evals triage --config deploy/demo/client/client.toml \
    --golden deploy/demo/client/golden.toml --out triage.json
uv run python -m inbox_core.evals groundedness --config deploy/demo/client/client.toml \
    --golden deploy/demo/client/golden.toml --knowledge deploy/demo/client/knowledge.md \
    --out grounded.json --answers-out answers.json
```

The triage runner exits 1 if any `needs_executive` case is missed; do not go public until it passes.

## Bring it up on a server

### 1. The server

Create an Ampere (`VM.Standard.A1.Flex`) instance with Ubuntu 24.04, 1 to 4 OCPU and 6 to 24 GB.
In its subnet's security list (or network security group), allow ingress on TCP 80 and 443 from anywhere.
Oracle's Ubuntu images also filter ports with iptables on the instance itself; open the two ports there too:

```sh
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save
```

Install Docker Engine with the compose plugin, git and Python 3 (Docker's own apt repository has arm64 packages), and add your user to the `docker` group.
If Redis exits with a warning about `ARM64-COW-BUG`, the kernel is too old for it to save safely: update the kernel rather than silencing the warning (Ubuntu 24.04's is fine).

### 2. DNS

Add two records at your DNS provider, both pointing at the server's public IP address:

| Type | Name | Value |
|---|---|---|
| `A` | `demo.example.com` | the server's IP |
| `A` | `*.demo.example.com` | the server's IP |

The wildcard covers `chat.` and `bot.`; two plain `A` records for those names work as well.
If the DNS provider can proxy traffic (Cloudflare's orange cloud), leave it off: certificates are issued by HTTP challenge on the server, and the rate limits count the client's own address.

### 3. Settings

```sh
git clone https://github.com/vietwillnguyen/inbox-core && cd inbox-core
cp deploy/demo/.env.example deploy/demo/.env
chmod 600 deploy/demo/.env
```

Fill in `deploy/demo/.env`:

| Setting | What to put |
|---|---|
| `DEMO_DOMAIN` | the page's host name, such as `demo.example.com` |
| `DEMO_ACME_EMAIL` | your address, for Let's Encrypt's expiry notices |
| `DEMO_ADMIN_EMAIL` | your sign-in for the Chatwoot dashboard |
| `DEMO_MODEL` | `gemini` (or `stand-in` to start without a key) |
| `GEMINI_API_KEY` | the key; in Google AI Studio or Cloud, also set a quota or budget alert on it as a second line |
| `DEMO_DAILY_BUDGET_USD` | the most the demo may spend on the model in a day, such as `1.00` |

The rate limits and the reset period have sensible defaults, listed in the file.
`deploy/demo/.env` and everything in `deploy/demo/.local/` are gitignored; never commit either.

### 4. Bring-up

```sh
./deploy/demo/demo.sh up
```

It generates the secrets into `deploy/demo/.local/`, builds the inbox-core image, starts everything, sets up Chatwoot (the shop's account, your administrator sign-in, the widget inbox, the bot, the labels, the draft tab and the service-down rule) and waits until each part answers.
The first run takes ten to twenty minutes on an Ampere instance, most of it pulling images and building; later runs take a minute or two.
Running it again is safe: it keeps the data and the secrets.

Your dashboard password is in `deploy/demo/.local/people.env`.
Sign in at `https://chat.DEMO_DOMAIN` and change it under Profile settings.

### 5. Smoke test

```sh
./deploy/demo/demo.sh smoke
```

It checks that the page, Chatwoot and the draft tab are served, that inbox-core's internals and Chatwoot's super-admin pages are not, and asks one question as a new visitor and waits for the grounded answer.
It then checks that the answer names no knowledge source to the visitor, and that the service's audit record, read from the inbox-core container's log, keeps the answer's sources.
Then open `https://DEMO_DOMAIN` in a browser and try the questions the page suggests.

### Behind a Cloudflare Tunnel instead

The bundle can also publish nothing at all: with `DEMO_TUNNEL=on` the proxy listens on this machine's loopback only, it requests no certificate, and a `tunnel` container (cloudflared, compose profile `tunnel`) connects out to Cloudflare, which serves the host names over https.
No firewall port has to be opened, and the server needs no public inbound address.

1. In Cloudflare Zero Trust, create a tunnel (Networks, Tunnels, Create a tunnel, Cloudflared) and copy its token.
2. Give the tunnel one public hostname per host, each with the service `HTTP` and URL `proxy:80`: `DEMO_DOMAIN`, the chat host and the bot host.
3. In `deploy/demo/.env`, set `DEMO_TUNNEL=on` and `DEMO_TUNNEL_TOKEN`; `DEMO_ACME_EMAIL` is not needed.
4. Run `./deploy/demo/demo.sh up`, then `./deploy/demo/demo.sh settings` to see the mode and the origins.

Cloudflare's free certificate covers names one level below the zone only (`*.example.com`, not `*.demo.example.com`).
With a `DEMO_DOMAIN` such as `demo.example.com`, set `DEMO_CHAT_HOST` and `DEMO_BOT_HOST` to names like `demo-chat.example.com` and `demo-bot.example.com`.
Behind the tunnel every request reaches the proxy from cloudflared, so the rate limits count each visitor by the `Cf-Connecting-Ip` header Cloudflare sets, and the forwarded scheme is trusted; both are safe because nothing but cloudflared can reach the proxy.
`deploy/tests/proxy_tunnel_test.sh` checks this mode's proxy.

`DEMO_ENV_FILE` names a settings file outside the repository (such as `/etc/inbox-core/demo.env`) in place of `deploy/demo/.env`; the deploy agent in [aws.md](aws.md) uses it.

## Running it

### Approving drafts

Repair advice waits in the dashboard with the `draft-pending` label.
Open the conversation and its `inbox-core drafts` tab; sign in to the tab once per session with your personal access token (avatar, Profile settings, Access token).
Send, edit and send, or discard; a staff note records who did what.
Nobody else is notified: a draft no one approves is never sent, and the reset deletes it with its conversation.

### The spend cap

The gateway counts what the model costs in Redis and refuses further calls once `DEMO_DAILY_BUDGET_USD` is spent in the current 24-hour window.
inbox-core then cannot classify, fails closed, and every visitor gets the holding message until the window rolls over.
The prices it counts with are set in `deploy/demo/litellm/config.yaml` and are deliberately pessimistic; check them against Google's current price list.
Changing the budget or a price starts a fresh count, because the gateway keys the count on the deployment's settings.
One call already in flight when the cap is reached still completes, so the cap can be passed by at most a call or two.

### Rate limits

| Limit | Default | Where |
|---|---|---|
| Messages and new conversations a visitor posts | 6 a minute per address, bursts of 5 | Traefik, `DEMO_RATE_MESSAGES_*` |
| New widget sessions (each one is a Chatwoot contact) | 30 an hour per address, bursts of 10 | Traefik, `DEMO_RATE_CONTACTS_*` |
| Everything else | 600 a minute per address | Traefik |
| Replies per conversation, conversations per visitor a day, sends a day | 5, 3, 300 | the shop's `client.toml` |
| Widget conversations and messages, dashboard sign-ins | Chatwoot's own defaults | Chatwoot's Rack::Attack |
| Draft-tab sign-ins | 10 a minute per address | inbox-core |

A limited request is answered 429 by the proxy, between the visitor and Chatwoot.
Nothing sits between Chatwoot and inbox-core, which must never answer 429 or 500 ([chatwoot.md](chatwoot.md#webhook-authenticity)).
To change a limit, edit `deploy/demo/.env` and run `demo.sh up` again.

### What is stored about a visitor

- Chatwoot keeps the conversation, a randomly named contact with no email or phone, and the browser's name, version, platform, language and the page address (Chatwoot's own conversation attributes).
- IP lookup is off, so no address or location is stored on the contact; widget uploads are off in the widget and refused at the proxy; the transcript email and the satisfaction survey are off.
- The core's store keeps each message encrypted until the reset erases it, then a skeleton of ids and decisions.
- The reset deletes every conversation untouched for a day, and then every contact left without one, every hour.
- Logs: Chatwoot runs at `warn`, which leaves visitor text out of its logs; inbox-core and the gateway log ids, decisions and counts only (the gateway with `turn_off_message_logging`); the proxy keeps no access log.
  Chatwoot's Rack::Attack does log a refused request's address and user agent at `warn`.
  Every log is rotated at 10 MB, three files per container.
- The end-to-end suite sends unique phrases through every path and searches every container's log for them.

### Reset, logs, status

```sh
./deploy/demo/demo.sh reset        # delete conversations untouched for a day, now
./deploy/demo/demo.sh status
./deploy/demo/demo.sh logs
./deploy/demo/demo.sh memory
```

### Switching the model

Set `DEMO_MODEL=gemini` and `GEMINI_API_KEY` (or back to `stand-in`) in `deploy/demo/.env` and run `demo.sh up` again.
That is the whole switch: inbox-core always calls the gateway, and the gateway's `stand-in` and `gemini` model groups answer the same calls.

### Upgrading

Every image is pinned.
Upgrade one on purpose: change its tag in `compose.yaml`, run the end-to-end suite locally, then `git pull` and `demo.sh up` on the server.
Chatwoot in particular is pinned because the connection was checked against v4.19.1's source ([chatwoot.md](chatwoot.md)).

### Teardown

```sh
./deploy/demo/demo.sh down         # stop everything, keep the data
./deploy/demo/demo.sh destroy      # delete the containers and every volume (asks first)
```

After `destroy`, delete `deploy/demo/.local/` too, then remove the DNS records and the instance.
Revoke the Gemini key if it was made for the demo.

## Running it locally

With no `deploy/demo/.env`, the same command runs the bundle on `127.0.0.1:3930` with the stand-in model, no key and no network beyond pulling images:

```sh
./deploy/demo/demo.sh up
```

| What | Where |
|---|---|
| The visitor's page | http://demo.localhost:3930 |
| The dashboard | http://chat.demo.localhost:3930 (sign-in in `deploy/demo/.local/people.env`) |

Browsers resolve every `*.localhost` name to this machine.

### The end-to-end suite

```sh
DEMO_RATE_MESSAGES_PER_MINUTE=60 DEMO_RATE_MESSAGES_BURST=20 \
DEMO_RATE_CONTACTS_PER_HOUR=600 DEMO_RATE_CONTACTS_BURST=60 ./deploy/demo/demo.sh up
./deploy/demo/demo.sh smoke
uv run pytest -m demo_e2e tests/demo_e2e
```

It is marked `demo_e2e`, which the default run deselects, and skips itself if the bundle is not up; CI runs it on every push.
It posts more than one visitor would from one address, so it runs with raised rate limits and checks that the raised limit holds.
Everything a visitor or the owner does goes through the proxy.
It covers: a grounded answer reached through the gateway, with no source shown to the visitor and its sources in a private note and the audit record; the smoke test itself; off-topic questions, a booking and a prompt-injection refund demand passed to a person with the holding message; repair advice held, then sent edited from the tab, and another discarded; what is stored on a contact; uploads refused; which routes are public; the widget's embedding policy; sign-up closed; the reset deleting old conversations and contacts and keeping recent ones; the spend cap failing closed once spent; no visitor text in any container's log; and the rate limit.

### The stand-in model

`inbox_core.testing.standin_model` answers the two calls the core's LiteLLM adapters make: the triage call from keyword rules (`deploy/demo/client/standin.toml`), and the answer call with the first retrieved passage, verbatim.
The gateway serves it as a custom provider (`deploy/demo/litellm/standin_provider.py`) and prices its calls like the real model, so the spend cap runs the same way.
It is not accurate; it classifies the shop's golden set correctly, which the unit tests check, and nothing else is claimed.

## Open questions

- **Prices.** The core sends every message that mentions money to `needs_executive`, so "how much is a service?" is never answered automatically. That is right for the nonprofit the core came from and limiting for a shop; whether the money rule should be configurable per category is a decision for the core, not for this bundle.
- **The "what it decided" panel and a bot check** from the plan's phase 3 are not built. The panel needs a way to tie the widget's conversation to its audit records without exposing other visitors' decisions; a bot check (such as Turnstile) needs a site key and cannot stop a script calling the widget's API directly.
- **Notifications.** A hand-off or a held draft only opens the conversation in the dashboard; nobody is pinged.
