# Design notes

This file records the decisions behind the public interface, one section per part of the core.
It is the place to look before changing a shape that clients depend on.

## Message shapes: what is core and what is channel-specific

`IncomingMessage` and `OutboundReply` came from an email-first engine.
The originals carried `rfc_message_id`, `references`, `headers` and `label_ids` on every message, and a web chat channel had to fill those with stand-ins.

The rule used to split them is one question: does anything in the core read the field?

| Field | Core reads it for | Where it lives |
|---|---|---|
| `channel`, `thread_key`, `provider_message_id` | dedupe, grouping, the audit record | core |
| `sender_key` | send caps and the flood guard | core |
| `sender_address` | addressing the reply (never logged, stored only encrypted) | core |
| `text`, `subject` | the classifier, the handler, the privacy sweep | core (`subject` defaults to empty for channels without one) |
| `received_at` | ordering and windows | core, timezone-aware when present |
| `rfc_message_id`, `references` | email threading only | `channels.email.EmailDetails` |
| `headers`, `label_ids` | email guards (auto-replies, newsletters) only | `channels.email.EmailDetails` |
| reply `subject`, reply `references` | email threading only | `channels.email.EmailReplyDetails` |

A channel attaches its own frozen `ChannelExtension` subclass, and its own guards and sinks read it back with `message.extension_as(EmailDetails)`.
The core never imports a channel module.

Two changes beyond the split:

- Content fields (`text`, `subject`, `sender_address`, `to_address`) are hidden from `repr`, so logging or raising with a message object cannot leak what it says.
- Required ids are checked when the message is built, and `received_at` must be timezone-aware, so a naive datetime never enters the core.

The adapter protocol is split by capability.
`ChannelAdapter` is only a name and `parse`, because a webhook channel never polls; `PollingChannel` adds `list_new`, and `Labeller` adds `label`.
Sending is not on any adapter: it goes through `ReplySink`, so the one path to the public stays in the delivery module.

## Triage: the category table is configuration

The origin engine hard-coded its category table, executive set and language list as module constants, so a second organisation could not use it without editing it.
Here the table is a `TriagePolicy` built from a TOML or YAML file or in Python, and the four tier rules in `inbox_core.triage.derive_tier` read it.

Each category says three things:

- `auto_answer`: whether it may ever be answered without a person (default false).
- `escalates_to`: `needs_admin`, `needs_executive` or `skip` (default `needs_admin`).
- `description`: what the classifier is shown.

The policy also sets `confidence_threshold`, the supported `languages` (code to name, first is the default) and `fallback_category`, which the audit records when the classifier is unavailable.

Validation refuses, and reports all at once:

- any auto-answerable category when there is no confidence threshold;
- a threshold that is not a finite number in (0, 1];
- an unknown tier, or `escalates_to = "auto_answer"`;
- an auto-answerable category that escalates anywhere but `needs_admin` (rule 1 or 2 would make the flag meaningless);
- duplicate or malformed category names, empty descriptions;
- no languages, malformed codes, or the reserved code `other`;
- a fallback category that is missing, auto-answered or skipped, since a failed classifier must reach a person;
- unknown keys and wrong types in a file, so a typo such as `auto_anwser` fails loudly instead of being ignored.

### Equivalence with the origin

`tests/test_triage_equivalence.py` loads `tests/fixtures/origin_table.toml`, a config equivalent to the origin's table, and compares `derive_tier` with a verbatim copy of the origin's function (`tests/reference/origin_policy.py`) over the whole input space, derived in the test rather than taken from the spike:

- 12 categories: the origin's 11 plus one the table does not list;
- 4 languages: `en`, `vi`, the origin's `other`, and an arbitrary unsupported code;
- confidences: a 0 to 1 grid in steps of 0.05, plus each threshold and the nearest floats either side of it;
- both values of each of the two booleans;
- 6 thresholds: 0.3, 0.55, 0.6, 0.7, 0.9 and 1.0.

That is 26,304 combinations, and the tiers are identical for all of them.
The spike's 528 was one threshold, four confidences and the enum languages only.

One deliberate difference, found while deriving the space: the origin compares `confidence < threshold`, which is false for NaN, so a NaN confidence on an auto-answerable category was auto-answered.
`derive_tier` treats any non-finite confidence as not confident, and the classifier validators reject it before it gets that far.
The test `test_nan_is_a_deliberate_difference` pins both behaviours.

Reasons produced by `escalation_reason` contain only category names from the table, language codes that match the code pattern, and numbers, so a classifier that returns free text in a field cannot push it into an audit record.

## Classifiers

`TriageClassifier` is one method, `classify(message) -> TriageSignals`, which raises `TriageUnavailable` rather than guessing.

- `adapters.litellm.LiteLLMClassifier` makes one JSON-schema call through LiteLLM.
  The default model is Gemini Flash-Lite (`gemini/gemini-3.5-flash-lite`); `model` changes it and `api_base` points it at a LiteLLM gateway.
- `adapters.jev.JevClassifier` asks the same four questions through Jev's `system_one`.
  `typesafe_sdk` is imported only by `JevClassifier.from_api_key`, so the extra is optional in practice and not only on paper.
- `shadow.ShadowingClassifier` runs a decider and a shadow; only the decider's answer is used.
- `triage.RetryingClassifier` wraps any classifier with a bounded number of attempts and a backoff, and turns every exception, not only `TriageUnavailable`, into `TriageUnavailable` carrying the exception's type name only.

Both adapters validate the model's answer with the same `signals_from_payload`, which checks it against the client's table and refuses a category or language the table does not list, a non-numeric or non-finite confidence, and non-boolean flags.
Its error messages name the field and the message id, never the value, because a model can echo the message into any field.

Prompts are rendered from the configuration by `prompts.render_triage_prompts`: the organisation's name and summary, each category's description, a seriousness order derived from the table (executive, then person-handled, then auto-answerable), and the language list.
The prompt module contains no organisation's name, and a test checks that.
The classifier is shown the subject and the body only, never the sender, and the system prompt tells the model the message is data, not instructions.

## Guards

A guard is one method, `check(message) -> GuardVerdict | None`, run before any model sees the message.
A verdict either drops the message (`drop`) or sends it to a person without classifying it (`hand_off`).

The core ships three channel-neutral guards:

- `EmptyMessageGuard` drops a message with no text and no subject.
- `OversizeGuard` hands a very long message to a person; it is not dropped, because a long message may be the important one.
- `SenderFloodGuard` drops messages from one sender beyond a limit within a sliding window, counted by `sender_key` and forgotten when the window passes.

The extension point for channel-specific guards is the same `Guard` protocol.
A channel guard reads its own extension, for example `message.extension_as(EmailDetails).headers`, and is passed to the pipeline after `default_guards()`.
`tests/test_guards.py` includes an email auto-reply guard written that way.
A guard that raises fails closed to `hand_off`, and its reason keeps only the exception's type name.
Verdict reasons are capped at 120 characters and must be fixed phrases, because they reach the audit record.

## Handlers

A handler is a named step chosen by category from a `HandlerRegistry`.
The pipeline calls it only for a message whose tier is `auto_answer`, with one `HandlerRequest` (the message, the triage decision and the client config), and gets back one `HandlerResult`: a reply to deliver, or a hand-off to a person with a short reason.
A handler never sends and never sets a tier; delivery, caps and escalation stay in the pipeline, so every handler inherits them.
A handler that raises is treated as a hand-off.

Built-ins:

- `GroundedAnswer(retriever, generator, min_score=...)` retrieves passages, keeps those scoring at least `min_score`, and asks the generator to answer from them only.
  It returns the ids and titles of the passages it used as `sources`, and hands off when nothing clears the threshold, when the generator returns the refusal sentinel or nothing, and when retrieval or generation fails.
  The reply text is the generator's alone and never names its sources.
- `Template(texts)` returns fixed text the client wrote, by language, and hands off rather than answer in a language it has no text for.
  `Template.from_config` reads a `[templates.<name>]` table from the client config.
- `HandOff()` always hands off; it is the registry's default for any category without a handler.

### Sources: tracked for staff, not shown to the public

A reply's sources travel beside its text, never in it.
On every channel and in every delivery mode, the text sent to the public, or held as a draft for a person to approve, has no source ids, titles or "Source:" line.
So an approved draft cannot carry one into the sent message either, unless the person reviewing it types one.
The sources are kept for staff in three places:

- the audit record's `sources` (ids), for every answered or held reply;
- the held draft, which the store keeps with its source ids and which the Chatwoot draft tab lists with their titles;
- a staff-only note through the channel's hand-off actions: the review note of a held draft, and, once an answer is sent automatically, a note with purpose `answered` naming each source's id and title.

The `answered` note is best effort and comes after the answer: a failure is logged by exception type, recorded as `source_note` in `handoff_failures`, and the answer stands.
Nothing labels, assigns or opens an answered conversation.

A client that wants the public to see the sources sets `show_sources = true` in `[delivery]` (off by default); the pipeline then adds "Source: <id> <title>; ..." to the reply text, and the staff records are unchanged.
The groundedness evaluation judges the handler's text against the knowledge entries named in its `sources`, so it does not depend on the text naming them.

`InMemoryRetriever` is BM25 over titles, keywords and text, with no embeddings and no network, for tests, demos and small knowledge bases.
`load_markdown_knowledge` reads `## <id> <title>` sections, each optionally starting with a `Keywords:` line, which is how an English entry can be found by a question in another language.
`ExtractiveGenerator` returns the best passage verbatim; `adapters.litellm.LiteLLMGenerator` asks a model, under instructions rendered from the client config.

### How future handlers fit without changing the protocol

Neither of these is built; this is how they would plug in.

- **A tool-calling action handler** (the "read" and "propose" rungs of the actions ladder) is a `Handler` whose constructor receives its tool client, for example an MCP client scoped to the few operations it needs, so credentials live in the handler instance and never in the request.
  On the read rung it looks something up and returns `HandlerResult.reply(...)` with `tags=("tool:order_lookup",)`, so the audit records which tool ran without recording what it returned.
  On the propose rung it returns its proposal with `requires_approval=True`, which makes delivery hold it for a person in every mode, auto included.
  The third rung, acting alone, needs an allow list and caps of its own and is deliberately out of scope.
- **A vertical handler** (such as drafting a quote from stock) is the same: a `Handler` registered for its category, holding its own dependencies, returning a reply, usually with `requires_approval=True`.

New context a handler might need later, such as the conversation so far, is added to `HandlerRequest` as a field with a default, so existing handlers keep working.

## Delivery

`choose_route(mode, language, auto_languages, requires_approval=...)` is a pure table:

| Mode | Route |
|---|---|
| `off` | nowhere: nothing is sent and nothing is drafted |
| `draft` | held for review |
| `auto` | sent, unless the language is not signed off for automatic sending or the handler asked for approval, in which case held |

`Delivery.deliver` then applies the caps to a `send` route; a reached cap holds the reply rather than dropping it.
The caps are a `SendCaps` protocol: a daily cap and a per-sender cap counted in conversations, over the organisation's local day.
`InMemorySendCaps` counts per process; a deployment that restarts or runs more than one process counts from its store.

A channel implements `ReplySink` with two methods, `send_to_public` and `hold_for_review`.
The guarantee that there is exactly one code path to the public is enforced by `tests/test_delivery.py` in three ways:

- every combination of mode, language, approval and cap state is driven through `Delivery` against a recording sink, and `send_to_public` is called only when all four allow it; `off` reaches neither method and `draft` never reaches `send_to_public`;
- every public function and method in every module of the package is walked, and the only send-shaped name is `ReplySink.send_to_public`;
- the package source is parsed, and the only call of `send_to_public` anywhere is in `Delivery._send`, which `deliver` reaches only after the route is `send`.

The delivery section of the configuration defaults to the safe settings: mode `off`, no language signed off for automatic sending, a daily cap of 30, two conversations per sender per day, one bot reply per conversation, and UTC.
An unknown mode in a configuration file is an error; `parse_mode`, for runtime settings such as an environment variable, reads anything unknown as `off`.

### Held drafts and the acceptance rate

A held reply is a draft waiting for a person, and its text is the outbound row's encrypted content.
`Pipeline.drafts` is an `inbox_core.review.DraftReview` over the pipeline's store and delivery:

- `pending(conversation_id)` lists drafts with the decision behind them: category, tier, confidence, classifier, sources and `held_because`, which the store now keeps.
- `send(draft_id, reviewer=..., text=None)` sends a draft as written or edited.
  It first claims the draft with an atomic compare-and-set (`held` to `reviewing`, one conditional `UPDATE` in SQL), so it is sent at most once across clicks, tabs and processes.
  The send goes through `Delivery.release_approved`, a second, deliberate way into `Delivery._send`: it refuses under `off` and otherwise sends, without the mode, language and cap gates, because those stop the assistant acting alone and a person approving a specific text is what they defer to.
  The send is still counted against the caps for later automatic replies.
  A send that raises is marked `failed` and never retried, because it may or may not have reached the public.
- `discard` and `expire_before(cutoff)` close a draft without sending it.
- `outcomes(start, end)` counts `sent_as_written`, `sent_edited`, `discarded` and `expired` by when they were resolved.
  `acceptance_rate` is sent as written over all resolved drafts, and `sent_rate` counts edited sends too.
  A whitespace-only change counts as written.

Reviewers are stored as identifiers such as `chatwoot-user:5`, never names or addresses, because the skeleton outlives the content.
The source-walk tests pin `DraftReview.send` as the only send-shaped public name besides the sinks, and pin that it reaches the public only through `release_approved`.

## The conversation record

`ConversationStore` is one protocol with two implementations: `store.memory.InMemoryConversationStore` in the core, and `store.sqlalchemy.SqlAlchemyConversationStore` behind the `sqlalchemy` extra.
`tests/test_store.py` runs the same contract against both.

Properties every implementation keeps:

- **Handled, not seen.** `record_inbound` writes and commits the row before any side effect, so a crash cannot produce a second reply.
  `is_handled` reads `handled_at`, which `mark_handled` sets only at a terminal state.
  A row without it is a message that was seen and not finished, and it is retried.
  Skipping on the row's existence is the silent-drop bug the origin documented; do not.
- **An outbound attempt is recorded before delivery.**
  `begin_outbound` writes a `pending` row linked to the inbound row, and `finish_outbound` records what delivery did.
  On a retry the pipeline sees the earlier attempt and does not deliver twice; if the attempt never finished, it hands off rather than guess whether the reply went out.
- **Naive UTC.** Every timestamp is stored and returned as a naive datetime in UTC.
  Any bound compared against one must go through `as_naive_utc` first, because an aware bound silently matches nothing; that bug once made every send cap read as untouched in the origin.
  Days are decided in the organisation's timezone and then converted.
- **No plaintext.** With a `FieldCipher`, inbound subject, text and sender address, and outbound reply text, are stored encrypted, each bound to its column as associated data.
  Without a cipher, no content is stored at all.
- **Delete content, keep the skeleton.** `erase_conversation` and `erase_sender` remove the encrypted content and set `content_erased_at`, and keep the rows, because dedupe, the caps and the metrics read them.

### Retention

`ConversationStore.erase_content_before(cutoff)` deletes the content of every message created before the cutoff and keeps the rows, like the other erase methods.
`inbox_core.retention.run_retention(store, days=N)` is the job: it first expires held drafts older than the cutoff (recorded as `expired` by reviewer `retention`), so nobody can approve a reply to a message whose text is going, and then erases the content.
`python -m inbox_core.retention --database-url URL --days N` runs it once against a SQL store and prints a report of numbers only; erasing needs no encryption key.

`StoreSendCaps` counts the day's sends from the store, so caps survive a restart and hold across processes.

### Encryption

`inbox_core.crypto` is AES-256-GCM from the `cryptography` library, with key ids for rotation: the first key in the setting encrypts, every key decrypts, and `reencrypt` moves a value to the newest key.
The token format, `<scheme>:v1:<key id>:<base64url(nonce || ciphertext || tag)>`, is the same as the parallel Vietnam Hearts storage work, and the scheme prefix is a parameter, so a cipher built with `scheme="vhenc"` reads tokens written there when the associated-data contexts match.
Errors name the setting, the key id and caller-supplied ids, never key material or plaintext.

## The pipeline

`Pipeline.process(message)` takes one message through these steps and always returns exactly one `AuditRecord`:

1. Dedupe: a handled message is a `duplicate` and nothing else happens.
2. Record: the conversation and the inbound row are written before any side effect; a conversation a person owns is `left_for_person`.
3. Guard: `dropped`, or straight to a person unclassified.
4. Triage: the classifier with bounded retries (default 3 attempts, backoff 0.5 s then 2 s); still unavailable means `needs_admin` with the fallback category.
5. Handle and deliver: only `auto_answer`, only within the per-conversation reply cap, and only while delivery is not `off`.
6. Hand off: the holding message (through the same delivery rules), the notifier, then the pause, then `handled`.

Decisions are `duplicate`, `left_for_person`, `dropped`, `skipped`, `answered`, `answer_held`, `handed_off` and `incomplete`.

### Concurrency: one worker per conversation

Two deliveries for one conversation, whether two different messages or the same message delivered twice, must not produce two replies.
The guarantee: at most one `Pipeline.process` call works on a given conversation at a time.

- Each call takes the conversation's lease in the store (`acquire_lease`) before it reads or changes anything in that conversation, then re-reads under the lease: a message another worker finished meanwhile is a `duplicate`, and the reply count and status are current.
- In memory the lease is a dictionary entry under the store's lock, so it holds across threads in one process.
  In SQL it is one conditional `UPDATE` on `inbox_conversations` (`lease_owner`, `lease_expires_at`), so it holds across processes sharing the database; `tests/test_concurrency.py` proves both with real threads and with two spawned processes over one SQLite file.
- A call waits up to `lease_wait` seconds (default 10); if it still cannot get the lease it returns `busy` with nothing done and the message unhandled, for the caller to retry.
- A lease expires after `lease_ttl` (default 120 seconds) so a crashed worker does not block a conversation forever.
  It is renewed immediately before every delivery, and a call that has lost it delivers nothing and is `incomplete`.

What is not guaranteed: lease expiry is read from each worker's clock, so workers on different machines need synchronised clocks, and a worker that stalls for longer than `lease_ttl` between its renewal and the send itself (one network call) could overlap a successor.
Set `lease_ttl` well above the slowest classifier-plus-handler time, retries included.

### Schema changes in this version

Pre-release tables need these columns added: `inbox_conversations.lease_owner` (string 64) and `lease_expires_at` (datetime), and `inbox_messages.held_because` (string 128), `review_outcome` (string 32), `reviewed_by` (string 64) and `reviewed_at` (datetime, indexed).
`create_schema` creates them for a new database; there is no migration tool in the package.

### A person replied

`Pipeline.person_replied(channel, thread_key, sender_key, message_id=...)` is the entry point for "a person replied in this conversation".
It sets the conversation to `paused_manual`, the stronger of the two paused states, and returns an audit record with decision `person_replied`.
Every later message there is `left_for_person`, without a classifier call, until `Pipeline.resume(channel, thread_key)` gives it back; a hand-off never overrides it.
A message already being processed when the person replies checks the conversation again right before it delivers anything (an answer or a holding message) and before it hands off, and then stays silent: it is marked handled as `left_for_person`, with nothing sent and nobody notified.

It fails closed in three specific ways:

- A handler that declines or raises, a delivery that fails, delivery being off, and the reply cap all become a hand-off, never a silent drop.
- If the notifier fails, the message is `incomplete`: not marked handled, so it is retried, and the conversation is not paused, so the retry is not mistaken for "a person owns this".
- Any unexpected error is caught, reported to the notifier as `internal error (<type>)`, and left unhandled for a retry.

A failed holding message does not stop the hand-off; a holding message or answer whose earlier attempt did not finish is never repeated.

### Hand-off side effects

A shared inbox such as Chatwoot can do four things when a person must act: add an internal note only staff see, label the conversation, assign it, and open it in a person's queue.
`inbox_core.handoff.HandOffActions` is that protocol, passed to the pipeline as `handoff_actions`.
The pipeline calls it for a hand-off (purpose `hand_off`) and for a drafted reply held for review (purpose `review`), in a fixed order: holding message, note, labels, assign, open, notifier, pause.
After an answer is sent automatically it calls only `add_internal_note` (purpose `answered`), with the answer's sources; see "Sources" above.

- The note, the labels and the assignment are best effort: a failure is logged by exception type and named in the audit record's `handoff_failures`, and the hand-off continues.
- Opening is what puts the conversation in front of a person, so failing to open fails closed: the message is `incomplete` and retried, and the retry neither repeats the holding message nor counts its own earlier reply against the per-conversation cap.
- The note and labels are composed by the core from fixed phrases, category and tier names, source ids and the titles the client gave those entries, and numbers (`handoff_note`, `handoff_labels`), so posting them cannot copy what the visitor wrote.
- Holding a draft for review does not pause the conversation and does not call the notifier; it is not a hand-off.
  The draft counts as the conversation's bot reply, so with the default cap of one the next message is handed off.

The audit record holds the channel, thread and message ids, the conversation id, category, tier, confidence, classifier, decision, reason, handler, mode, delivery outcome, the reason a reply was held, source ids, the guard and the handler's tags.
It holds no text, subject or address, and the reasons are built from fixed phrases, category names and numbers.

### The privacy sweep

`inbox_core.testing.privacy.run_privacy_sweep(build, corpus, caplog)` is the origin's privacy test turned into a helper any client can run against its own corpus and wiring.
`build(notifier, audit)` returns the client's pipeline with the sweep's recording notifier and audit sink wired in.
The sweep drives the corpus through it, then fails if any sender address, any subject of ten or more characters, or any line of text of twenty or more characters appears in a captured log record (message, arguments and formatted traceback), an escaped exception, a notifier payload or an audit record.
It also fails if nothing was logged or audited, because a sweep over silence proves nothing.

Logs are captured with `testing.logs.attached_caplog`, which hangs pytest's handler directly on the named loggers.
pytest 9 attaches to loggers that are already non-propagating when a test starts, but not to one that becomes non-propagating later, such as one a logger factory builds on first use; `tests/test_testing_logs.py` pins that trap and shows the helper capturing it.
`tests/test_privacy_sweep.py` shows the sweep catching a logged body, a logged address, content inside a logged traceback, a non-propagating client logger, content smuggled into a handler's reason (which reaches both the notifier and the audit), and an escaped exception.

The sweep is also available as a fixture with `pytest_plugins = ["inbox_core.testing.pytest_plugin"]`.

## Evaluation

`inbox_core.evals` carries the origin's three evaluation questions over to any client:

- **May this classifier decide?** `evaluate_triage` scores a classifier against a golden set; the gate is 100 percent recall on `needs_executive` with no case left unclassified, because a missed sensitive message is not compensated for by accuracy elsewhere.
- **Are the answers grounded?** `evaluate_groundedness` answers every `auto_answer` case with a handler and has a judge grade it on two separate questions: is every claim supported by the context, and does it state anything forbidden.
  A refusal counts against correctness, and a judge whose output cannot be read is never a pass.
- **Where should the thresholds sit?** `sweep_triage_threshold` re-derives tiers at each confidence threshold from one pass of classifier calls; `sweep_answer_threshold` shows what each retrieval-score gate would have let through.

A golden set is a TOML or YAML list of cases validated against the client's config.
`expected_tier` is never trusted as written: it is recomputed with `derive_tier` from the case's expected signals at confidence 1.0, so a golden set cannot drift from the policy it measures.
Every `auto_answer` case needs `must_mention` facts, or the judge has nothing to check.

The runners take their model-backed parts as arguments, so they are tested in CI with fakes; `python -m inbox_core.evals` builds the real LiteLLM ones on demand, and its tests inject a fake completion so the whole command runs offline.

## The Chatwoot connection

`inbox_core.chatwoot` is installed with the `chatwoot` extra and is the only part of the package that brings a web framework; the core never imports it, and a test checks that in a fresh interpreter.
[`chatwoot.md`](chatwoot.md) is the operator's guide; this section records the decisions.

- **Generated, not hand-written.** The service's own HTTP surface is `src/inbox_core/chatwoot/openapi.yaml`; its models and a router that delegates every operation to a `ServiceApi` interface are generated by fastapi-code-generator with a template in `codegen/service`.
  The Chatwoot client is generated by openapi-python-client from Chatwoot's spec at the pinned tag, cut to the operations the connection calls, with an overlay for what Chatwoot serves but its spec omits.
  `scripts/generate.py --check` runs in CI.
- **Signature first, then Chatwoot's own copy.** Chatwoot v4.19.1 signs agent-bot webhooks, so the HMAC is the authenticity check.
  The service then re-reads the conversation with the bot token (the only read a bot token is allowed) and, when the message is the latest, acts on Chatwoot's copy of it.
- **The store is the review queue.** `ChatwootReplySink.hold_for_review` sends nothing; the held reply is already the outbound row's encrypted content, the review hand-off opens the conversation, and the draft tab reads and resolves drafts through `DraftReview`.
  The service therefore requires an encryption key.
- **One more send path, pinned.** The tab's send operation (`ServiceApi.send_draft`, `ChatwootService.send_draft`) and the sink's transport (`ChatwootApi.send_message`) are send-shaped names the delivery tests list explicitly; `tests/chatwoot/test_send_paths.py` checks that the transport is called only from the sink's `send_to_public`, that the tab reaches the public only through `DraftReview.send`, and that the service-level fallback holding message goes through `Delivery.deliver`.
- **Never 429 or 500 to Chatwoot.** Chatwoot logs a retried webhook's whole payload at `warn`, so every verified webhook is answered 200 and handled in the background, and validation errors are answered with fixed phrases instead of FastAPI's input echo.
