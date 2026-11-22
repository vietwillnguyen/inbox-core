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
It has no channel code: a Gmail adapter, a Chatwoot connection or a web widget plugs in through two small protocols.

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
- **Retention.** The store deletes content when asked; it does not decide when.
- **Exactly-once sending under every crash.** If a process dies after a reply leaves but before it is recorded, the next attempt hands off to a person rather than risk a second send.
- **Shared limits across processes for the in-memory parts.** The flood guard and `InMemorySendCaps` are per process; use `StoreSendCaps` for caps that hold across processes and restarts.

## Install

```sh
uv add "inbox-core @ git+https://github.com/vietwillnguyen/inbox-core@v0.1.0"
# with extras
uv add "inbox-core[litellm,sqlalchemy,yaml] @ git+https://github.com/vietwillnguyen/inbox-core@v0.1.0"
```

The core needs only `cryptography`.
Extras: `litellm` (the LiteLLM classifier and generator), `jev` (the Jev classifier), `sqlalchemy` (the SQL store), `yaml` (YAML configuration files).

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
    classifier=LiteLLMClassifier(config),           # Gemini Flash-Lite by default
    handlers=HandlerRegistry({"faq": GroundedAnswer(retriever, LiteLLMGenerator(), min_score=1.0)}),
    sink=my_channel_sink,                            # implements ReplySink
    store=InMemoryConversationStore(),
    notifier=my_notifier,                            # implements Notifier
    audit=JsonlAuditSink("audit.jsonl"),
)
record = pipeline.process(incoming_message)
```

A channel provides two things: a parser into `IncomingMessage`, and a `ReplySink` with `send_to_public` and `hold_for_review`.

## Development

```sh
uv sync
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pytest --cov
```

The suite is deterministic, makes no network calls, and keeps coverage at 90 percent or more.
See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the rules, which matter because this repository is public.

## Licence and origin

MIT.
Much of the core started as the inbound answer engine of the Vietnam Hearts volunteer platform, which is also MIT-licensed; that project's copyright notice is kept alongside this one, and [`NOTICE`](NOTICE) lists which modules came from it.
