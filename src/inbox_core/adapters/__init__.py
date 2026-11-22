"""Adapters to model providers. Each one imports its SDK only when it is used.

- :mod:`inbox_core.adapters.litellm`: any model LiteLLM can reach, directly or
  through a LiteLLM gateway. Needs ``inbox-core[litellm]``.
- :mod:`inbox_core.adapters.jev`: the Jev classifier. Needs ``inbox-core[jev]``.
"""
