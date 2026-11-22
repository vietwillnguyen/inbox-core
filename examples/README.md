# Examples

The worked example is the **Brambleford Tool Library**, a made-up volunteer-run library that lends tools in a made-up town.
Nothing in it describes a real organisation, place or person, and every address in it ends in `.example`.

It ships inside the package, in [`src/inbox_core/examples/tool_library/`](../src/inbox_core/examples/tool_library/), so the demo command works from an installed wheel as well as from a checkout:

- `client.toml`: nine categories (two auto-answerable, four that always go to a senior person), English and Spanish, a membership template, draft mode with English signed off for automatic sending.
- `knowledge.md`: thirty knowledge entries, each with Spanish keywords so a Spanish question finds the English entry.
- `golden.toml`: forty-three messages across every category in both languages, plus multi-topic, money-mention and unsupported-language cases; the loader checks every expected tier against `derive_tier`.

Run a message through the whole pipeline and see the audit record:

```sh
uv run python -m inbox_core.examples.demo "What are your opening hours?"
uv run python -m inbox_core.examples.demo --mode auto "¿Dónde está la biblioteca?"
uv run python -m inbox_core.examples.demo --mode auto "The ladder slipped and I hurt my wrist"
```

Without `--model` it uses a keyword stand-in for the classifier and returns the best knowledge entry verbatim; neither is a model.
With `--model gemini/gemini-3.5-flash-lite` (and `inbox-core[litellm]` installed and a key in the environment) it uses a real model for both.

Score the golden set against a real model:

```sh
uv run python -m inbox_core.evals triage \
    --config src/inbox_core/examples/tool_library/client.toml \
    --golden src/inbox_core/examples/tool_library/golden.toml \
    --require-every-language --out docs/evidence/triage-gemini-flash-lite.json
```
