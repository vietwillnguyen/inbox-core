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
