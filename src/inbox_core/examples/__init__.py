"""A worked example: the made-up Brambleford Tool Library.

``tool_library/`` holds its configuration, about thirty knowledge entries and
a golden set of about forty messages in English and Spanish. Run a message
through the whole pipeline with::

    python -m inbox_core.examples.demo "What are your opening hours?"
    python -m inbox_core.examples.demo --mode auto "¿Dónde están?"
    python -m inbox_core.examples.demo --model gemini/gemini-3.5-flash-lite "..."

Nothing in it describes a real organisation, place or person.
"""

__all__: list[str] = []
