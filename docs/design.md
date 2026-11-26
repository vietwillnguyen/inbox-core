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

### Prices: a per-client setting, decided in code

Rule 1 sends any mention of money to `needs_executive`, so by default "how much is a service?" is never answered.
`[triage] prices` makes that a per-client choice, with three levels:

| `prices` | A plain price question | Everything else about money |
|---|---|---|
| `always_hand_off` (default) | `needs_executive`, never answered | `needs_executive` |
| `published_prices_only` | triaged like any other message, and answered | `needs_executive` |
| `draft_for_approval` | triaged like any other message; the reply is held for a person to approve | `needs_executive` |

At every level, the default included, a reply that states a price no passage it cites states is handed off as `needs_executive` (below).

Under the default, the classifier is not asked anything new, its prompt and JSON schema are byte for byte what they were, and a price question is `needs_executive` even if a classifier claims otherwise.
What does change under the default is the invented-price check: see "Owner decisions" below.

For the other two levels the classifier is asked a fifth question, `asks_listed_price`: is every mention of money only a question about what something usually costs, with no refund, discount, deal, dispute, payment problem, negotiation or custom quote?
It is a fact about the message, like the other four; `derive_tier` decides what follows.
`is_price_question` is true only when the client answers prices, the message mentions money and the classifier said yes; only then does rule 1 not escalate it for money, and rules 2 to 4 apply as for any message (so the category must be auto-answerable, the confidence high enough, and so on).
An executive category stays executive.
`signals_from_payload` requires the fifth answer as a boolean for such a client and ignores it for everyone else.

The model's discretion ends there.
After the handler writes the reply and before delivery, the pipeline runs `inbox_core.prices.check_prices` on the reply text against the passages the reply cites (each `Source.passage`, the entry's title and text; never stored or shown):

- A **figure** is an amount (digits with `,` or `.` separators) with a currency marker right before it (`£45`, `$1,200.50`, `USD 30`, `A$12`) or right after it (`45 euros`, `45 EUR`, `50.000đ`, `50p`), with at most one space between.
  It is stated when the same figure appears in a cited passage: the same marker (case aside, a plural word read as singular), on the same side, with the same digits written the same way.
  `£45` matches `£45` and `£ 45`, and not `£45.00`, `45 pounds`, `$45`, or the `£45` inside `£450`.
- A **lone marker** (a currency symbol, code or word not part of a figure, as "pounds" in "forty-five pounds") is stated only when the same marker appears in a cited passage. This is how a price written in words is caught.
- In a reply to a price question, a **bare number** ("a basic service is 45") is stated only when the same number appears in a cited passage.

Anything unstated is the fail-closed reading, and it is the same at every level: the message is handed off as `needs_executive` with the reason `the reply states a price that no knowledge entry it cites states`, and the reply is never delivered or held.
The check applies to every reply of every client, not only to price questions: a model that puts a price into an answer about opening hours is caught too.
Under `draft_for_approval` a reply that passes the check is still held with `a price needs approval` when it answers a price question or states a price.
The bare-number rule needs a price question, so it never applies under `always_hand_off`, where there are none.
A handler that cites nothing (a `Template`) cites no price, so a template that states one is handed off; write prices in the knowledge base instead.
The audit record's tags say `price:stated` or `price:unstated`; the figures themselves are not recorded.
`tests/test_price_setting.py` drives all three levels through the pipeline, including a generator that invents a price, writes one in words and answers with a bare number, and a non-price answer with an invented price under the default.

The golden set takes `expected_asks_listed_price`, which needs `expected_mentions_money`, and the expected tier is recomputed under the client's own `prices`, so a price case cannot pass validation under the wrong setting.

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

### Sources: tracked for staff, linked for the public only on request

A reply's sources travel beside its text, never in it.
On every channel and in every delivery mode, the text sent to the public, or held as a draft for a person to approve, never has a source id or title.
The sources are kept for staff in three places:

- the audit record's `sources` (ids), for every answered or held reply;
- the held draft, which the store keeps with its source ids and which the Chatwoot draft tab lists with their titles;
- a staff-only note through the channel's hand-off actions: the review note of a held draft, and, once an answer is sent automatically, a note with purpose `answered` naming each source's id and title.

The `answered` note is best effort and comes after the answer: a failure is logged by exception type, recorded as `source_note` in `handoff_failures`, and the answer stands.
Nothing labels, assigns or opens an answered conversation.

A knowledge entry may name the public page it is about, in a `URL:` line (see below) or `KnowledgeEntry(url=...)`.
The URL must be an absolute `https` URL with a host and no user name or password; anything else is refused when the knowledge is loaded, so a service with a bad URL does not start.
A client that wants the public to see where an answer comes from sets `show_sources = true` in `[delivery]` (off by default, per client).
The pipeline then ends a grounded reply with one line linking to the public pages of the sources it used, for example:

```text
The library is open on Wednesdays from 5pm to 8pm and on Saturdays from 10am to 2pm.

More: https://brambleford-tools.example/visit
```

Only sources with a URL are linked, each page once, in the order the sources came, separated by ", ".
Sources without a URL are never mentioned, and a reply whose sources have none gets no line at all.
An id or title is never shown, in any mode.
The words before the links are `More:` unless the client sets `[delivery.links_label]`, a table of language = label (one line, at most 40 characters), with the default language's label as the fallback.
The staff records are the same with the option on or off.

The line is added before delivery decides to send or hold, so it is the same rule for both paths.
A held draft's text therefore already ends with the line, and the reviewer sees exactly what will be sent and may edit or remove it; an approved draft is sent as the person approved it, with nothing appended after approval.
With the option off, a held draft has no line and approving it adds none.
Turning the option on or off affects replies written after the change; a draft already held keeps the text it was held with.
The groundedness evaluation judges the handler's text against the knowledge entries named in its `sources`, so it does not depend on the text naming them.

`InMemoryRetriever` is BM25 over titles, keywords and text, with no embeddings and no network, for tests, demos and small knowledge bases.
`load_markdown_knowledge` reads `## <id> <title>` sections, each optionally starting with a `Keywords:` line, which is how an English entry can be found by a question in another language, and a `URL:` line naming the entry's public page, in either order.
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
| `auto` | sent, unless the language is not signed off for automatic sending or approval is required, in which case held |

Approval is required when the handler asks for it (`requires_approval=True`), or when the message's category is listed in the configuration's `delivery.approval_categories`.
That list may name only categories that can be auto-answered, and it holds for every handler: the assistant drafts the reply and a person sends it.
The audit record says which: `the handler asked for approval`, or `category <name> needs approval`.

`Delivery.deliver` then applies the caps to a `send` route; a reached cap holds the reply rather than dropping it.
The caps are a `SendCaps` protocol: a daily cap and a per-sender cap counted in conversations, over the organisation's local day.
`InMemorySendCaps` counts per process; a deployment that restarts or runs more than one process counts from its store.

A channel implements `ReplySink` with two methods, `send_to_public` and `hold_for_review`.
The guarantee that there is exactly one code path to the public is enforced by `tests/test_delivery.py` in three ways:

- every combination of mode, language, approval and cap state is driven through `Delivery` against a recording sink, and `send_to_public` is called only when all four allow it; `off` reaches neither method and `draft` never reaches `send_to_public`;
- every public function and method in every module of the package is walked, and the only send-shaped name is `ReplySink.send_to_public`;
- the package source is parsed, and the only call of `send_to_public` anywhere is in `Delivery._send`, which `deliver` reaches only after the route is `send`.

The delivery section of the configuration defaults to the safe settings: mode `off`, no language signed off for automatic sending, a daily cap of 30, two conversations per sender per day, one bot reply per conversation, no category that needs approval, and UTC.
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
7. Notify: with `notifications`, a finished hand-off or held draft is announced, best effort (see "Notifications").

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
The reminder job adds one table, `inbox_reminders` (`key` string 160, primary key, and `created_at`); `create_schema` creates a missing table on an existing database too, so it needs no migration.

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
The pipeline calls it for a hand-off (purpose `hand_off`) and for a drafted reply held for review (purpose `review`), in a fixed order: holding message, note, labels, open, assign, notifier, pause.
The assignment comes after the opening because a shared inbox may not announce an assignment made before: Chatwoot does not notify one made while a conversation is pending, so the older order (assign, then open) told nobody; see "Owner decisions" below.
After an answer is sent automatically it calls only `add_internal_note` (purpose `answered`), with the answer's sources; see "Sources" above.

- The note, the labels and the assignment are best effort: a failure is logged by exception type and named in the audit record's `handoff_failures`, and the hand-off continues.
- Opening is what puts the conversation in front of a person, so failing to open fails closed: the message is `incomplete` and retried, nothing is assigned, and the retry neither repeats the holding message nor counts its own earlier reply against the per-conversation cap.
- The note and labels are composed by the core from fixed phrases, category and tier names, source ids and the titles the client gave those entries, and numbers (`handoff_note`, `handoff_labels`), so posting them cannot copy what the visitor wrote.
- Holding a draft for review does not pause the conversation and does not call the notifier; it is not a hand-off. With `notifications` it is announced as `draft_held`.
  The draft counts as the conversation's bot reply, so with the default cap of one the next message is handed off.

### Notifications

`notifier` (the `Notifier` protocol) is fail-closed by design: if a person cannot be told of a hand-off, the message is left unhandled and retried.
That stays as it was.
`inbox_core.notify` is a second, best-effort way to tell people, for what had no way before: a held draft, and a client with no shared inbox to notify its agents.
It is off unless the client config has a `[notifications]` section:

```toml
[notifications]
urls = ["ntfy://${NTFY_TOKEN}@ntfy.example/shop-alerts", "${INBOX_CORE_NOTIFY_URL}"]
events = ["hand_off", "draft_held", "reminder"]   # default: hand_off and draft_held
remind_after_minutes = 60                         # needs the reminder event, and the other way round
quiet_hours = { start = "22:00", end = "07:00" }  # in delivery.timezone; optional
link = "https://mail.example/#inbox/{thread_key}" # optional; {channel}, {thread_key}, {conversation_id}
```

- `urls` are [Apprise](https://github.com/caronc/apprise) URLs (BSD licence; the `notify` extra), so one line reaches any of the services Apprise supports.
  Every secret goes in a `${VARIABLE}` placeholder, filled from the environment when the notifier is built (`build_notifications`); validation refuses a URL with no placeholder at all, a password written into it, or a secret-named query value written into it, and names a URL by its position, never by what it holds.
  A variable that is not set stops start-up with its name.
  The filled-in URLs are kept only inside `adapters.apprise.AppriseTransport`, whose `repr` shows a count.
- `hand_off` is sent after a hand-off is finished (holding message, notifier, pause, handled); `draft_held` after a held draft is recorded.
- `reminder`: `run_reminders(store, notifications, config)` finds hand-offs still paused for a person (not `paused_manual`: someone replied) and drafts still `held`, older than `remind_after_minutes`, and reminds about each once.
  The store records each reminder with an atomic claim (`claim_reminder`, a new `inbox_reminders` table that `create_schema` adds to an older database), so two runners never both send it, and a failed send gives the claim back.
  `python -m inbox_core.notify --config client.toml --database-url URL` runs it once (and `python -m inbox_core.chatwoot remind` for the Chatwoot service); schedule it every few minutes.
- `quiet_hours` holds notifications back: nothing is sent, the audit record says `quiet`, and nothing is claimed, so the first reminder run after the quiet hours sends a reminder for anything still waiting. Set a reminder if you use quiet hours.

A notification is built by `Notification` from the event, the organisation's name, the category and tier, the pipeline's reason (cut to one line of 120 characters), a count of minutes and the link.
It has no field for the sender's text, subject, name, address or phone number, so it cannot carry them; `tests/test_notify.py` drives a message full of a name, an email address and a phone number through every notified path, and through a real Apprise to a JSON endpoint on 127.0.0.1, and finds none of it in what was sent.
`run_privacy_sweep(..., notifications=transport)` adds a client's own notifications to its sweep.

Failure never changes the reply path: an exception is logged by type, recorded as `notification` in `handoff_failures` and as `<event>:failed` in the audit record's `notifications`, and the reply, hand-off, pause and handled mark are exactly as without a notifier.
A transport method is `notify_staff`, deliberately not send-shaped: it never reaches the public, and the delivery source-walk test keeps it that way.

The audit record holds the channel, thread and message ids, the conversation id, category, tier, confidence, classifier, decision, reason, handler, mode, delivery outcome, the reason a reply was held, source ids, the guard, the handler's tags, the failed best-effort steps and the notifications attempted (`hand_off:sent`, `draft_held:quiet`, `hand_off:failed`).
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

## Owner decisions

Decisions the owner made on review, recorded here because each changes behaviour a client could see.

### The invented-price check runs for every client (behaviour change)

`check_prices` runs on every reply at every `triage.prices` level, including the default `always_hand_off`.
Any reply that states a price no passage it cites states is handed off as `needs_executive`, not sent or held.
This deliberately changes behaviour for existing clients, Vietnam Hearts included: before this version, under the default, an answer that happened to state a price (a model adding "parking is £5", or a client's template naming a fee) was sent; now it goes to a person.
A price that is written in the entry the answer cites is still sent.
A `Template` cites no entry, so a template that states a price now always hands off; move the price into the knowledge base.
The reason is that a wrong price is a commitment the organisation did not make, and the check is cheap and in code.

### The service opens a conversation before assigning it

The hand-off order is note, labels, open, assign (it was assign, then open).
Chatwoot does not notify an assignment made while a conversation is pending, so with the old order a Chatwoot client's `INBOX_CORE_ASSIGNEE_ID` was assigned silently and nobody was told.
Assigning is still best effort, and nothing is assigned when the opening fails.
The seed's automation rule stays as the alternative for a client that wants Chatwoot to choose the assignee; when both are configured the service's assignee wins, through the `inbox-core-assigns` label (see [chatwoot.md](chatwoot.md), "Telling a person").
The cost: with inbox auto-assignment on and an agent online, Chatwoot assigns that agent as the conversation opens and the service then reassigns it, so two people are notified; such a client should turn auto-assignment off.

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
