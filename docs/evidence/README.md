# Evidence

Scored summaries of real-model runs belong here: numbers, category names and case ids only, never keys, message text or raw provider responses.

**No real-model run has been recorded yet.**
The test suite uses fakes only, so the model path (classification and generation through LiteLLM) is unproven.

To produce the first summary, with `inbox-core[litellm]` installed and `GEMINI_API_KEY` set in the environment:

```sh
uv run python -m inbox_core.evals triage \
    --config src/inbox_core/examples/tool_library/client.toml \
    --golden src/inbox_core/examples/tool_library/golden.toml \
    --require-every-language --out docs/evidence/triage-gemini-flash-lite.json

uv run python -m inbox_core.evals groundedness \
    --config src/inbox_core/examples/tool_library/client.toml \
    --golden src/inbox_core/examples/tool_library/golden.toml \
    --knowledge src/inbox_core/examples/tool_library/knowledge.md \
    --out docs/evidence/groundedness-gemini-flash-lite.json
```

Read the JSON before committing it.
