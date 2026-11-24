# inbox-core

Fail-closed triage and delivery core for inbox assistants.

> **Status: pre-release (0.x).**
> The interface may change between minor versions until 1.0.
> It is installed from tagged GitHub releases and is not published to PyPI.
> **The model path is unproven:** the test suite uses fakes only, and no golden set has yet been scored against a real model.
> The evaluation runner for that is ready (see [Evaluating](#evaluating)).

## What it is

The reusable "brain" of an inbox assistant.
A message comes in from any channel and takes the same steps:

1. **Guard**: cheap checks before any model sees it (empty, oversize, a sender flooding).
2. **Triage**: a classifier reports what the message is about, its language, whether the sender asked for a person and whether money or a commitment is mentioned. The **tier is then decided in code** from the client's category table, never by the model.
3. **Handle**: a pluggable handler answers from the client's knowledge, returns a fixed template, or hands off.
4. **Deliver**: under an `off`, `draft` or `auto` mode, with per-language gates and send caps.
5. **Hand off**: anything sensitive, unsure or failed goes to a person, with a holding message and a notification.

Every message produces one audit record with ids and decisions and no content.

It is a library, not a service.
The core has no channel code: a Gmail adapter, a Chatwoot connection or a web widget plugs in through two small protocols.
One connection ships with it as an optional extra: [the Chatwoot connection](docs/chatwoot.md), which runs the core as a Chatwoot agent bot with a draft-review tab.

## What it guarantees, and what it does not

It guarantees, and its tests check:

- **The tier is decided in code.** A model's output can choose a category from the client's table; it cannot choose a tier, a recipient or a delivery mode. A category marked as never auto-answered is never auto-answered, whatever the confidence.
- **It fails closed.** An unavailable or malformed classifier, a handler that fails, a failed delivery and a reached reply cap all hand the message to a person. If no person could be told, the message is left unhandled so it is retried.
- **`off` delivers nothing and `draft` never sends.** There is exactly one code path that can send to the public, and a test walks the package source to keep it that way.
- **No message content in the core's logs, exceptions, notifications or audit records.** A reusable privacy sweep checks this, and you can run it against your own corpus and wiring.
- **Stored text is encrypted** (AES-256-GCM with key rotation), and content can be deleted while the record of what happened is kept.
- **A message is skipped only once it was handled**, not merely seen, so a crash does not silently drop it; and a delivery that may have happened is never repeated.

It does not guarantee:

- **That an answer is correct.** A grounded answer uses only retrieved knowledge entries and refuses when nothing relevant is found, but a model can still misread an entry. Measure it with the groundedness runner before turning on `auto`, and use `draft` mode first.
- **That the classifier is accurate.** The tier rules make low confidence and sensitive categories safe, but a classifier that confidently mislabels a sensitive message as an FAQ will be answered. That is what the triage evaluation and its 100 percent executive-recall gate are for.
- **Anything about your code.** Your channel adapter, your own logging and your hosting are yours; run the privacy sweep over them.
- **Retention, unless you schedule it.** The store deletes content when asked, and `inbox_core.retention` is the job that asks (content older than N days, keeping the skeleton); running it on a schedule is yours.
- **Exactly-once sending under every crash.** If a process dies after a reply leaves but before it is recorded, the next attempt hands off to a person rather than risk a second send.
- **One worker per conversation across machines with unsynchronised clocks.** Processing of a conversation is serialised by a lease in the store, across threads with any store and across processes with the SQL store; the lease's expiry is read from each worker's clock (see [`docs/design.md`](docs/design.md)).
- **Shared limits across processes for the in-memory parts.** The flood guard and `InMemorySendCaps` are per process; use `StoreSendCaps` for caps that hold across processes and restarts.

## Install

```sh
uv add "inbox-core @ git+https://github.com/vietwillnguyen/inbox-core@v0.1.0"
# with extras
uv add "inbox-core[litellm,sqlalchemy,yaml] @ git+https://github.com/vietwillnguyen/inbox-core@v0.1.0"
```

The core needs only `cryptography`.
Extras: `litellm` (the LiteLLM classifier and generator), `jev` (the Jev classifier), `sqlalchemy` (the SQL store), `yaml` (YAML configuration files), `chatwoot` (the Chatwoot connection, the only extra with a web framework).

## A configuration

```toml
[organisation]
name = "Example Tool Library"
summary = "a made-up volunteer-run lending library for tools"

[triage]
confidence_threshold = 0.6
fallback_category = "other"

[triage.languages]
en = "English"
es = "Spanish"

[[triage.categories]]
name = "faq"
auto_answer = true
description = "a general question about the library"

[[triage.categories]]
name = "damage_report"
escalates_to = "needs_executive"
description = "a borrowed tool was damaged, lost or hurt someone"

[[triage.categories]]
name = "other"
description = "a person writing about anything else"

[delivery]
mode = "draft"
auto_languages = ["en"]

[delivery.holding]
en = "Thanks for writing. A person from the library will reply here."
es = "Gracias por escribir. Una persona de la biblioteca responderá aquí."
```

Validation refuses anything that could auto-answer without a confidence threshold, an unknown tier, duplicate categories, and unknown keys.
See [`docs/design.md`](docs/design.md) for every rule.

## Wiring it up

```python
from inbox_core import GroundedAnswer, HandlerRegistry, Pipeline, load_config
from inbox_core.adapters.litellm import LiteLLMClassifier, LiteLLMGenerator
from inbox_core.knowledge import InMemoryRetriever, load_markdown_knowledge
from inbox_core.pipeline import JsonlAuditSink
from inbox_core.store.memory import InMemoryConversationStore

config = load_config("client.toml")
retriever = InMemoryRetriever(load_markdown_knowledge("knowledge.md"))
pipeline = Pipeline(
    config=config,
    classifier=LiteLLMClassifier(config),  # Gemini Flash-Lite by default
    handlers=HandlerRegistry({"faq": GroundedAnswer(retriever, LiteLLMGenerator(), min_score=1.0)}),
    sink=my_channel_sink,  # implements ReplySink
    store=InMemoryConversationStore(),
    notifier=my_notifier,  # implements Notifier
    audit=JsonlAuditSink("audit.jsonl"),
)
record = pipeline.process(incoming_message)
```

A channel provides two things: a parser into `IncomingMessage`, and a `ReplySink` with `send_to_public` and `hold_for_review`.
A channel with a shared inbox can also pass `handoff_actions` (a note, labels, an assignee and opening the conversation), call `pipeline.person_replied(...)` when a person answers, and review held drafts through `pipeline.drafts`.

## The Chatwoot connection

```sh
./deploy/chatwoot/stack.sh up       # Chatwoot CE v4.19.1, the service, a widget page; all on 127.0.0.1
uv run pytest -m e2e tests/e2e      # the end-to-end suite against it
```

Webhooks are checked against Chatwoot's signature, held drafts are reviewed in a tab inside the conversation whose agent is verified with Chatwoot, Chatwoot is set to log without visitor text (proved by the suite), and a retention job deletes old transcripts.
[`docs/chatwoot.md`](docs/chatwoot.md) has the details and the residual risks.

## The public demo

```sh
./deploy/demo/demo.sh up      # Chatwoot, the service, a LiteLLM gateway, a TLS proxy; a made-up bike shop
```

A deployable bundle for one small server (an Oracle Cloud Ampere instance is enough): a made-up shop's knowledge base and configuration, per-address rate limits, a daily model spend cap, an hourly reset of conversations, and a stand-in model so it runs and is tested end to end with no key.
Switching to Gemini is one setting.
[`docs/demo.md`](docs/demo.md) is the runbook: sizing, DNS, settings, bring-up, smoke test, reset and teardown.

## A worked example

[`examples/`](examples/README.md) describes the Brambleford Tool Library, a made-up organisation with a configuration, thirty knowledge entries and a forty-three message golden set in English and Spanish.

```sh
uv run python -m inbox_core.examples.demo --mode auto "What are your opening hours?"
```

It prints what would be sent or held, any escalation, and the audit record.

## Evaluating

Three runners answer three questions, and none of them runs in CI, because they spend real model calls:

```sh
uv pip install 'inbox-core[litellm]'      # LiteLLM reads GEMINI_API_KEY (or a gateway) from the environment

# May this classifier decide? Exits 1 below 100 percent recall on needs_executive.
python -m inbox_core.evals triage --config client.toml --golden golden.toml --out triage.json

# Are the answers grounded? Exits 1 below 90 percent.
python -m inbox_core.evals groundedness --config client.toml --golden golden.toml \
    --knowledge knowledge.md --out grounded.json --answers-out answers.json

# Where should the two thresholds sit? One pass of calls, re-scored at every threshold.
python -m inbox_core.evals calibrate --config client.toml --golden golden.toml --answers answers.json
```

No real-model run has been recorded yet; [`docs/evidence/`](docs/evidence/README.md) says how to make the first one.
What does run in CI is what can be wrong for free: golden-set validation, including that every case's `expected_tier` is what `derive_tier` actually returns for it under the client's table, and the metric arithmetic.
Summaries written to disk hold numbers, category names and case ids only.

## Development

```sh
uv sync
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pytest --cov
```

The suite is deterministic, makes no network calls, and keeps coverage at 90 percent or more.
The end-to-end suite against a local Chatwoot is opt-in (`-m e2e`); see [`docs/chatwoot.md`](docs/chatwoot.md).
Generated code is regenerated with `uv run python scripts/generate.py`, and CI checks it is current.
See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the rules, which matter because this repository is public.

## Licence and origin

MIT.
Much of the core started as the inbound answer engine of the Vietnam Hearts volunteer platform, which is also MIT-licensed; that project's copyright notice is kept alongside this one, and [`NOTICE`](NOTICE) lists which modules came from it.
