"""LiteLLM custom provider that serves inbox-core's stand-in model.

The gateway loads this file through ``custom_provider_map`` in config.yaml, so
the demo bundle runs end to end with no model key and no network: the
``stand-in`` model group answers from keyword rules and the retrieved passages
(``inbox_core.testing.standin_model``, mounted beside this file). It reports
token usage like a real provider, so the gateway prices its calls and the
daily spend cap is exercised exactly as it is for the real model.
"""

from __future__ import annotations

import os
from typing import Any

from litellm import CustomLLM
from litellm.types.utils import ModelResponse, Usage
from standin_model import StandInModel


def _tokens(text: str) -> int:
    return max(1, len(text) // 4)


class StandInProvider(CustomLLM):
    """Answers chat completions from the stand-in model's rules."""

    def __init__(self) -> None:
        super().__init__()
        self._model = StandInModel.from_file(
            os.environ.get("STANDIN_RULES", "/etc/litellm/standin.toml")
        )

    def _reply(self, messages: list[dict[str, Any]], response: ModelResponse) -> ModelResponse:
        text = self._model.complete(messages)
        prompt = _tokens("".join(str(m.get("content") or "") for m in messages))
        completion = _tokens(text)
        response.choices[0].message.content = text  # type: ignore[union-attr]
        response.choices[0].finish_reason = "stop"
        response.usage = Usage(  # type: ignore[attr-defined]
            prompt_tokens=prompt, completion_tokens=completion, total_tokens=prompt + completion
        )
        return response

    def completion(self, *args: Any, **kwargs: Any) -> ModelResponse:
        """One chat call, answered synchronously."""
        return self._reply(kwargs["messages"], kwargs["model_response"])

    async def acompletion(self, *args: Any, **kwargs: Any) -> ModelResponse:
        """One chat call, answered from the gateway's event loop."""
        return self._reply(kwargs["messages"], kwargs["model_response"])


standin = StandInProvider()
