# The Chatwoot connection

`inbox-core[chatwoot]` runs the core as a Chatwoot agent bot.
A visitor writes in Chatwoot's website widget (or any inbox the bot is connected to), Chatwoot sends the bot a webhook, and the service takes the message through the core: guard, triage, handle, deliver, hand off.
Held drafts are reviewed in a tab inside the Chatwoot conversation.

It is pinned to Chatwoot Community Edition **v4.19.1** (`chatwoot/chatwoot:v4.19.1-ce`).
Everything below about Chatwoot's behaviour was read from that release's source and checked against a running instance; upgrade on purpose and re-run the end-to-end suite when you do.

## Run it locally

```sh
./deploy/chatwoot/stack.sh up
```

That one command writes throwaway secrets to `deploy/chatwoot/.local/` (gitignored), starts Postgres, Redis, Chatwoot's rails and sidekiq processes, seeds a made-up organisation (an account, an administrator, a volunteer agent, a website inbox, the agent bot, labels, the draft tab and the service-down rule), builds and starts the inbox-core service and a page with the widget on it, and waits until each answers.
On a machine that already has the images it takes under two minutes.

| What | Where |
|---|---|
| Agent dashboard | http://127.0.0.1:3910 (sign-ins in `deploy/chatwoot/.local/people.env`) |
| A visitor's page with the widget | http://localhost:3911 |
| The inbox-core service | http://127.0.0.1:3912 (`/healthz`, `/metrics`, `/tab`) |

The compose project is `inboxcore` and every port is published on 127.0.0.1 only.
The visitor page uses `localhost` and the dashboard `127.0.0.1` on purpose: browsers share cookies across the ports of one host name, so clearing a visitor's cookies would otherwise sign the agent out.

Other commands: `stack.sh mode off|draft|auto` restarts the service in that delivery mode, `stack.sh stop-service` and `start-service` take the service away to see Chatwoot's fallback, `stack.sh retention DAYS` runs the retention job, `stack.sh logs`, `stack.sh status`, `stack.sh down` (stop, keep the data) and `stack.sh destroy` (delete this project's volumes, after asking).

The local stack uses the worked example's deterministic keyword stand-in (`INBOX_CORE_CLASSIFIER=example-keywords`), which is not a model, and the example's configuration with its daily cap of 40 automatic sends raised to 1000, so the end-to-end suite can run many times in a day.
When a cap is reached the core holds the reply, and in Chatwoot that shows as a `draft-pending` conversation for a person, not as silence.
For a real deployment set `INBOX_CORE_CLASSIFIER=litellm` (the default), install the `litellm` extra and provide the provider key, and point `INBOX_CORE_CONFIG` and `INBOX_CORE_KNOWLEDGE` at the client's own files.

## Settings

| Variable | Meaning |
|---|---|
| `CHATWOOT_URL` | Chatwoot's API base as the service reaches it (`http://rails:3000` in compose) |
| `CHATWOOT_ORIGIN` | The origin agents' browsers load Chatwoot from; the only page allowed to frame the draft tab |
| `INBOX_CORE_PUBLIC_ORIGIN` | The origin browsers load this service from; state-changing tab requests must come from it |
| `CHATWOOT_ACCOUNT_ID`, `CHATWOOT_BOT_TOKEN`, `CHATWOOT_BOT_SECRET` | The account, and the agent bot's access token and webhook secret |
| `INBOX_CORE_WEBHOOK_PATH_TOKEN` | At least 24 characters; the bot's webhook URL is `/chatwoot/webhook/<token>` |
| `INBOX_CORE_TAB_SECRET` | At least 32 characters; signs draft-tab sessions |
| `INBOX_CORE_TAB_SESSION_SECONDS` | How long a tab sign-in lasts; default 1800, between 60 and 28800 |
| `INBOX_CORE_DATABASE_URL`, `INBOX_CORE_ENCRYPTION_KEYS` | The core's SQL store and its key setting (required: the store is the draft queue) |
| `INBOX_CORE_ASSIGNEE_ID` | Optional agent id that hand-offs are assigned to |
| `INBOX_CORE_MODE` | Optional runtime override of the delivery mode; anything unknown reads as `off` |
| `INBOX_CORE_CLASSIFIER`, `INBOX_CORE_CONFIG`, `INBOX_CORE_KNOWLEDGE`, `INBOX_CORE_AUDIT_PATH` | See above |
| `INBOX_CORE_MODEL` | With `litellm`, the model both the classifier and the grounded answer call; default Gemini Flash-Lite (`gemini/gemini-3.5-flash-lite`) |
| `INBOX_CORE_MODEL_API_BASE`, `INBOX_CORE_MODEL_API_KEY` | Optional: a LiteLLM gateway and its key, with `INBOX_CORE_MODEL` set to `litellm_proxy/<model group>`; without them LiteLLM calls the provider with the key in its own variable |

Chatwoot itself needs `SAFE_FETCH_ALLOW_PRIVATE_NETWORK=true` when the service is on a private network (SafeFetch blocks private addresses otherwise), and the stack sets `DISABLE_TELEMETRY=true` and `ENABLE_ACCOUNT_SIGNUP=false`.

## Webhook authenticity

Chatwoot v4.19.1 signs every agent-bot webhook (`lib/webhooks/trigger.rb`): `X-Chatwoot-Signature: sha256=` HMAC-SHA256 of `"{X-Chatwoot-Timestamp}.{raw body}"` under the bot's secret, plus a random `X-Chatwoot-Delivery` id per job.
The webhook guide documents the scheme for account webhooks; that agent bots use it is from the source and was confirmed live.
A unit test checks the service's computation against a value computed inside the pinned image with Chatwoot's own Ruby expression.

The service checks, before reading the body: the unguessable path token (constant time), the signature over the exact raw bytes (constant time), a timestamp within five minutes either way, and that the delivery id has not been seen in this process.
Anything that fails is answered 401 with a fixed phrase and counted by reason at `/metrics`; a body that is not valid JSON counts as `malformed`.

It then re-reads the conversation with the bot's token.
A bot token may not list a conversation's messages (`BOT_ACCESSIBLE_ENDPOINTS` in `app/controllers/concerns/access_token_auth_helper.rb` allows only conversation `show`, status, typing, priority, custom attributes, message `create`, assignments and labels), so the check uses what `show` returns: the conversation must be in this account, the message id must not be newer than Chatwoot's latest message, and when the message is the latest (the usual case) Chatwoot's copy must agree that it is incoming from a contact (or, for a staff reply, outgoing from a user) and not private, and Chatwoot's text is the one the core reads.

Residual risk, plainly:

- With the bot secret and the path token, someone can forge a webhook for a message that is not the conversation's latest; the core would act on that text in that conversation (an answer or a hand-off to the real visitor). Keep both secrets as secret as the bot token, which already lets its holder post as the bot.
- The delivery-id replay check is per process. A replay inside the five-minute window to another process is caught by the core's dedupe on Chatwoot's message id, so it does nothing.
- Chatwoot writes the webhook URL, path token included, to its log at `warn` when delivery fails (the end-to-end suite pins this). The signature check does not depend on the path token.

The service answers every verified webhook 200 and works in the background, and never answers 429 or 500: Chatwoot retries those and logs the whole payload, visitor text included, at `warn` (`app/jobs/agent_bots/webhook_job.rb`).
Do not put a proxy in front of it that can answer 500 or 429 on its behalf.

## What the bot does with an event

- An incoming, non-private message from a contact goes through `Pipeline.process`.
- An outgoing, non-private message from a user (a person in the dashboard) is "a person replied": `Pipeline.person_replied`, after which the bot stays silent in that conversation until resumed.
- Everything else is ignored and counted: the bot's own messages, private notes, activity and template messages, `message_updated`, status changes and `webwidget_triggered`.

Every conversation the service processes gets the label `inbox-core`.
An answer the bot sends is the answer alone: the visitor never sees a source id or title.
With `delivery.show_sources = true` it ends with one line linking to the public pages of its sources that have one, such as `More: https://brambleford-tools.example/visit`, which the widget shows as a link (`19`); see "Sources" in [design.md](design.md).
`./deploy/chatwoot/stack.sh sources on|off` restarts the local service with the option on or off (off by default).
Right after it, the bot adds a private note (Chatwoot's `private: true` message, which the widget never shows) naming the knowledge entries the answer was based on, for example `Sources: TL-01 Opening hours.`, so a person reading the conversation later sees what it was based on.
A failed note is logged, recorded as `source_note` in the audit record's `handoff_failures`, and does not undo the answer.

A hand-off adds a staff-only note (fixed phrases, category, tier and reason, never the visitor's text), the labels `handoff` and the category, assigns to `INBOX_CORE_ASSIGNEE_ID` and opens the conversation.
A held draft adds a note naming its sources, `draft-pending` and the category, and opens the conversation; the bot keeps it, so with one bot reply per conversation the next message is handed off.

Processing of one conversation is serialised by a lease in the core store, so two webhooks for one conversation cannot produce two replies, across processes too with a shared SQL database.

## The draft tab

The seed registers a Dashboard App called `inbox-core drafts`, which Chatwoot shows as a tab beside Messages in every conversation.
It lists the conversation's held drafts with their sources, category, tier, confidence and why they were held, lets the agent edit the text, and has Send and Discard.
The sources are shown beside the draft, not in its text, so what the agent sends never names them.
With `delivery.show_sources = true` the draft's text already ends with the public link line, so the agent sees, and may edit, exactly what will be sent.

Chatwoot posts the conversation and the "current agent" to the frame unsigned and to any origin (`app/javascript/dashboard/components/widgets/DashboardApp/Frame.vue`), so the tab never trusts that identity.
Instead:

1. The agent signs in once per session by pasting their personal Chatwoot access token (avatar, Profile settings, Access token).
   The service asks Chatwoot, with that token, who it belongs to (`GET /api/v1/profile`) and which inboxes they may see in the account (`GET /api/v1/accounts/{id}/inboxes`, which Chatwoot scopes to the agent's own), then forgets the token.
   It mints a session token: the agent id, the account, those inbox ids, an expiry and a random id, signed with HMAC-SHA256 under `INBOX_CORE_TAB_SECRET`.
   Sign-in is limited to ten attempts a minute per client address.
2. Every request sends the session as `Authorization: Bearer`; there is no cookie for a cross-site request to ride on, and state-changing requests must carry the tab's own `Origin`.
   The page is served with `frame-ancestors` set to the Chatwoot origin only, `script-src 'self'` and no inline script, and the page writes only text into the document.
3. Listing drafts gives each one an action token bound to this session, this conversation and this draft, valid for ten minutes.
   Send and Discard need it, and the service re-reads the conversation from Chatwoot to check its inbox is one this agent may see.
   The draft moves from held to sent (or discarded) exactly once, by an atomic compare-and-set in the store.
4. The send goes through the core's `DraftReview.send`, which reaches the public only through the delivery module.
   The store records the outcome (`sent_as_written`, `sent_edited`, `discarded`, `expired`) and the reviewer as `chatwoot-user:<id>`, a staff note in the conversation says who sent or discarded it, and once no draft is left waiting the `draft-pending` label is taken off.

What remains: anyone holding an agent's Chatwoot access token can sign in as that agent (as they can to Chatwoot's API); a session is valid until it expires even if the agent is removed from the inbox meanwhile (the inbox list is fixed at sign-in, so keep the session short); and the reply is posted with the bot's token, so it shows in the widget as from the bot, with the note recording the agent.

## When the service is down

If the service cannot finish a message (the store, a model or Chatwoot's API failing), it retries with back-off, then sends the client's holding text through the core's delivery rules (once per conversation per process) and opens the conversation with a note and the label `inbox-core-unavailable`.

If the whole service is down, Chatwoot opens the conversation itself ("marked open by system due to an error with the agent bot") and tells the visitor nothing.
The seed adds an automation rule for that: on `conversation_opened`, if the conversation has no labels, send a holding message and add `inbox-core-unavailable`.
The widget shows that message as from "Bot", Chatwoot's name for an automation.
Because the service labels every conversation it processes and labels a hand-off before opening it, the rule does not fire for an agent taking over a conversation the bot handled, nor for a normal hand-off.

To make it work, and its limits:

- The seed turns off the widget's email-collect prompt. That prompt posts two template messages with each new conversation, the bot receives those too, and while the service is down each failed delivery opens the conversation at the same moment, so the rule fired three times. If you turn it back on, expect the holding message up to three times during an outage.
- A conversation the bot already handled gets no holding message if the service goes down mid-conversation: it is labelled, so the rule does not fire. Chatwoot still opens it for a person.
- A person opening an unlabelled conversation by hand from the status menu also triggers the rule.
- Conditions on the assignee do not help: inbox auto-assignment gives the conversation to an online agent as Chatwoot opens it.

## Logs

Chatwoot at its default `LOG_LEVEL=info` writes visitor text to its rails and sidekiq logs.
The stack sets `LOG_LEVEL=warn` (rails' `config.log_level` and sidekiq's logger both read it).

The end-to-end suite proves it: it sends unique phrases through every path (answered, handed off, a staff reply from the dashboard, and the service down), then searches the whole log of every container (rails, sidekiq, postgres, redis, the service and the widget page) for them, and for the phrases the rest of the suite used.
At `warn` none was found.
As a control, the same search at `info` found a phrase in 4 rails lines and 5 sidekiq lines, and none in the service's log.

What does reach Chatwoot's logs at `warn`, precisely:

- When delivery to the bot fails, sidekiq logs the webhook URL, path token included (`lib/webhooks/trigger.rb`, `handle_failure`).
- If the service ever answered 429 or 500, sidekiq would log the whole payload, visitor text included (`app/jobs/agent_bots/webhook_job.rb`); the service never does, and a proxy in front of it must not either.
- Errors are logged at `error` with their messages; none seen in these runs carried message text, but that is not a proof for every error Chatwoot can raise.

The service's own logs carry ids, decisions, counts and exception type names, plus httpx's request lines (method, URL path, status); its access log is off because the webhook URL holds the path token.

## Retention

Chatwoot Community Edition keeps every transcript; its scheduled jobs resolve conversations but never delete them.
`stack.sh retention DAYS` (or `python -m inbox_core.chatwoot retention --days N` with `CHATWOOT_ADMIN_TOKEN` set for that run only) deletes every conversation whose last activity is older than N days, waits for Chatwoot's background deletion to land, deletes the contacts left with no conversation, and then erases the core store's content older than N days, keeping its skeleton.
Deleting is for administrators only, so the run uses an administrator's token; the service never holds one.
Schedule it with cron or your platform's scheduler, and read its JSON report of counts.

## The end-to-end suite

```sh
./deploy/chatwoot/stack.sh up
uv run pytest -m e2e tests/e2e
```

It is marked `e2e`, which the default run deselects, and it skips itself if the stack is not up.
It switches the service's mode and `show_sources` as it goes and leaves them in `auto` and off; it takes about four minutes.
It covers: an answer in the widget with no source in it, and its sources in a private note the widget does not show; with `show_sources` on, an answer ending with its public link and no id or title, an answer from an entry without a page with no line, and an approved draft reaching the widget with the line the reviewer saw; a hand-off with its holding message, labels, note and assignment; a person replying silencing the bot; draft mode holding a reply and nothing reaching the visitor; a draft sent as written, sent edited, and discarded from the tab; the hostile cases (no session, a session signed with another secret, the bot's token trying to sign in, a replayed send, another conversation's draft with this conversation's token, an expired session signed with the real secret, a draft already sent, cross-origin requests and the framing policy, and an agent removed from the inbox); the service-down fallback and that neither a hand-off nor an agent taking over triggers it; the retention job in Chatwoot and the core; and the log proof above.

## Evidence

Screenshots from the running stack, in [`docs/evidence/chatwoot/`](evidence/chatwoot/):

| File | What it shows |
|---|---|
| `01`, `02` | An answer in the widget, with no source in it, at desktop and phone widths |
| `03`, `04` | A hand-off: the holding message in the widget; the note, labels, assignment and reopening in the dashboard |
| `05`, `06` | A volunteer takes over and replies; the bot then stays silent on a question it would have answered |
| `07` | Draft mode: nothing reaches the visitor |
| `08` to `12` | The tab: signing in, the draft with its sources and decision, edited, sent, and the edited reply in the widget |
| `13`, `14` | The tab at a phone width, and a discard |
| `15`, `16` | The tab refusing to be framed by another origin, and opened outside Chatwoot |
| `17` | The service stopped: Chatwoot's fallback rule tells the visitor, once |
| `18` | The same kind of answer in the agent dashboard, followed by the private note naming its source |
| `19` | With `show_sources` on: the answer in the widget ending with a link to its public page, and no id or title |

## Regenerating code

```sh
uv run python scripts/generate.py          # regenerate
uv run python scripts/generate.py --check  # what CI runs: fail if the committed code is stale
```

The service's routes and models come from `src/inbox_core/chatwoot/openapi.yaml` (fastapi-code-generator, with the template in `codegen/service`).
The Chatwoot client comes from Chatwoot's own spec at the pinned tag, checked against its SHA-256 and cut down to the operations in `codegen/chatwoot/operations.txt`, plus `codegen/chatwoot/overlay.json`: conversation delete (served by Chatwoot, missing from its spec) and the `snoozed` conversation status (in Chatwoot's model, missing from its spec), each citing the source.
Never edit `_chatwoot_api` or `_service_api` by hand.
