"""Handlers as a named, pluggable step, and the three built-ins."""

from __future__ import annotations

import types
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from inbox_core.adapters.litellm import LiteLLMGenerator
from inbox_core.config import ConfigError
from inbox_core.handlers import (
    ExtractiveGenerator,
    GenerationRequest,
    GroundedAnswer,
    Handler,
    HandlerRegistry,
    HandlerRequest,
    HandlerResult,
    HandOff,
    Source,
    Template,
)
from inbox_core.knowledge import (
    InMemoryRetriever,
    KnowledgeEntry,
    Passage,
    Retriever,
    load_markdown_knowledge,
)
from inbox_core.prompts import REFUSAL_SENTINEL, render_answer_instructions
from inbox_core.triage import TriageDecision
from tests.helpers import bike_config, message

CONFIG = bike_config()

ENTRIES = (
    KnowledgeEntry("KB-01", "Opening hours", "We are open Tuesday to Saturday, 9am to 6pm."),
    KnowledgeEntry(
        "KB-02",
        "Flat tyre repair",
        "We fix flat tyres while you wait, usually in twenty minutes.",
        keywords=("pinchazo", "rueda"),
    ),
    KnowledgeEntry("KB-03", "Location", "The workshop is next to the ferry terminal."),
)


def decision(category: str = "faq", language: str = "en") -> TriageDecision:
    return TriageDecision(category, language, 0.9, False, False, "test", tier="auto_answer")


def request(text: str = "When are you open on Saturday?", **kwargs: Any) -> HandlerRequest:
    return HandlerRequest(message=message(text), decision=decision(**kwargs), config=CONFIG)


@dataclass
class RecordingGenerator:
    reply: str = "We open at 9am on Saturdays."
    error: BaseException | None = None
    name: str = "recording"
    seen: list[GenerationRequest] = field(default_factory=list)

    def generate(self, request: GenerationRequest) -> str:
        self.seen.append(request)
        if self.error is not None:
            raise self.error
        return self.reply


class TestHandlerResult:
    def test_reply_and_hand_off_constructors(self) -> None:
        reply = HandlerResult.reply("t", "hello", sources=(Source("KB-1", "Hours", 1.0),))
        assert reply.outcome == "reply"
        assert "hello" not in repr(reply)
        hand_off = HandlerResult.hand_off("t", "nothing relevant")
        assert hand_off.outcome == "hand_off"
        assert hand_off.text == ""

    def test_a_reply_needs_text_and_a_hand_off_needs_a_reason(self) -> None:
        with pytest.raises(ValueError, match="text"):
            HandlerResult.reply("t", "  ")
        with pytest.raises(ValueError, match="reason"):
            HandlerResult.hand_off("t", "")

    def test_reasons_are_bounded_and_tags_are_identifiers(self) -> None:
        with pytest.raises(ValueError, match="reason"):
            HandlerResult.hand_off("t", "x" * 121)
        with pytest.raises(ValueError, match="tag"):
            HandlerResult.reply("t", "hi", tags=("tool: looked up order for a person",))
        assert HandlerResult.reply("t", "hi", tags=("tool:order_lookup",)).tags == (
            "tool:order_lookup",
        )

    def test_an_unknown_outcome_is_refused(self) -> None:
        with pytest.raises(ValueError, match="outcome"):
            HandlerResult(outcome="maybe", kind="t", reason="x")  # type: ignore[arg-type]


class TestRegistry:
    def test_a_category_gets_its_handler_and_everything_else_hands_off(self) -> None:
        template = Template({"en": "Book online."})
        registry = HandlerRegistry({"faq": template})
        assert registry.for_category("faq") is template
        assert isinstance(registry.for_category("booking"), HandOff)

    def test_a_custom_default(self) -> None:
        default = HandOff(reason="maintenance")
        assert HandlerRegistry({}, default=default).for_category("faq") is default

    def test_validate_refuses_an_unknown_category(self) -> None:
        with pytest.raises(ConfigError, match="'cakes'"):
            HandlerRegistry({"cakes": HandOff()}).validate(CONFIG)

    def test_validate_refuses_a_handler_that_could_never_run(self) -> None:
        with pytest.raises(ConfigError, match="never be auto-answered"):
            HandlerRegistry({"refund": Template({"en": "x"})}).validate(CONFIG)

    def test_validate_accepts_a_good_registry(self) -> None:
        HandlerRegistry({"faq": HandOff()}).validate(CONFIG)

    def test_built_ins_satisfy_the_protocol(self) -> None:
        for handler in (HandOff(), Template({"en": "x"}), grounded()):
            assert isinstance(handler, Handler)


class TestHandOff:
    def test_always_hands_off_with_its_reason(self) -> None:
        result = HandOff(reason="answered by a person this month").handle(request())
        assert result == HandlerResult.hand_off("hand_off", "answered by a person this month")


class TestTemplate:
    def test_chooses_the_text_for_the_message_language(self) -> None:
        template = Template({"en": "Join online.", "es": "Únete en línea."}, name="membership")
        result = template.handle(request(language="es"))
        assert result == HandlerResult.reply("membership", "Únete en línea.")

    def test_hands_off_rather_than_answering_in_the_wrong_language(self) -> None:
        result = Template({"en": "Join online."}).handle(request(language="es"))
        assert result.outcome == "hand_off"
        assert result.reason == "no template text for language es"

    def test_needs_at_least_one_non_empty_text(self) -> None:
        with pytest.raises(ValueError, match="text"):
            Template({})
        with pytest.raises(ValueError, match="text"):
            Template({"en": " "})

    def test_validate_against_config_languages(self) -> None:
        with pytest.raises(ConfigError, match="'fr'"):
            Template({"fr": "Bonjour"}).validate(CONFIG)
        Template({"en": "x"}).validate(CONFIG)

    def test_from_config(self) -> None:
        config = bike_config()
        config = type(config)(
            organisation=config.organisation,
            triage=config.triage,
            templates={"membership": {"en": "Join online."}},
        )
        assert Template.from_config(config, "membership").handle(request()).text == "Join online."
        with pytest.raises(ConfigError, match="no template named 'missing'"):
            Template.from_config(config, "missing")


def grounded(generator: Any = None, **kwargs: Any) -> GroundedAnswer:
    return GroundedAnswer(
        InMemoryRetriever(ENTRIES),
        generator if generator is not None else RecordingGenerator(),
        min_score=kwargs.pop("min_score", 0.5),
        **kwargs,
    )


class TestGroundedAnswer:
    def test_answers_from_retrieved_passages_and_returns_its_sources(self) -> None:
        generator = RecordingGenerator()
        result = grounded(generator).handle(request("What are your opening hours on Saturday?"))
        assert result.outcome == "reply"
        assert result.kind == "grounded_answer"
        assert result.text == "We open at 9am on Saturdays."
        assert [source.id for source in result.sources] == ["KB-01"]
        sent = generator.seen[0]
        assert [passage.entry.id for passage in sent.passages] == ["KB-01"]
        assert sent.language == "en"
        assert sent.language_name == "English"
        assert "Example Bike Workshop" in sent.instructions

    def test_refuses_when_nothing_scores_above_the_threshold(self) -> None:
        generator = RecordingGenerator()
        result = grounded(generator).handle(request("Do you sell pianos?"))
        assert result == HandlerResult.hand_off(
            "grounded_answer", "no knowledge entry scored at least 0.50"
        )
        assert generator.seen == []

    def test_refuses_when_the_generator_says_the_context_is_insufficient(self) -> None:
        generator = RecordingGenerator(reply=f"  {REFUSAL_SENTINEL} ")
        result = grounded(generator).handle(request("What are your opening hours?"))
        assert result.reason == "the generator found the context insufficient"

    def test_refuses_an_empty_generation(self) -> None:
        result = grounded(RecordingGenerator(reply="")).handle(request("opening hours"))
        assert result.outcome == "hand_off"

    def test_a_generator_failure_hands_off_with_its_type_only(self) -> None:
        generator = RecordingGenerator(error=TimeoutError("echo: opening hours please"))
        result = grounded(generator).handle(request("opening hours"))
        assert result.reason == "generator recording failed (TimeoutError)"

    def test_a_retriever_failure_hands_off(self) -> None:
        class Broken:
            def search(self, query: str, *, limit: int) -> list[Passage]:
                raise OSError("index missing")

        result = GroundedAnswer(Broken(), RecordingGenerator(), min_score=0.1).handle(request())
        assert result.reason == "retrieval failed (OSError)"

    def test_cites_sources_when_asked(self) -> None:
        result = grounded(cite=True).handle(request("opening hours on Saturday"))
        assert result.text.endswith("Source: KB-01 Opening hours")

    def test_spanish_keywords_find_an_english_entry(self) -> None:
        result = grounded().handle(request("Tengo un pinchazo en la rueda", language="es"))
        assert [source.id for source in result.sources] == ["KB-02"]

    def test_limit_and_threshold_must_be_sensible(self) -> None:
        with pytest.raises(ValueError, match="limit"):
            grounded(limit=0)
        with pytest.raises(ValueError, match="min_score"):
            grounded(min_score=-1)


class TestExtractiveGenerator:
    def test_returns_the_top_passage_verbatim(self) -> None:
        passages = (Passage(ENTRIES[0], 2.0), Passage(ENTRIES[1], 1.0))
        text = ExtractiveGenerator().generate(
            GenerationRequest("q", "", passages, "en", "English", "rules")
        )
        assert text == ENTRIES[0].text

    def test_refuses_with_no_passages(self) -> None:
        text = ExtractiveGenerator().generate(GenerationRequest("q", "", (), "en", "English", ""))
        assert text == REFUSAL_SENTINEL


class TestInMemoryRetriever:
    def test_ranks_by_relevance_and_respects_the_limit(self) -> None:
        hits = InMemoryRetriever(ENTRIES).search("flat tyre repair while I wait", limit=2)
        assert hits[0].entry.id == "KB-02"
        assert len(hits) <= 2
        assert all(isinstance(hit, Passage) for hit in hits)
        assert isinstance(InMemoryRetriever(ENTRIES), Retriever)

    def test_irrelevant_queries_score_zero_and_are_not_returned(self) -> None:
        assert InMemoryRetriever(ENTRIES).search("piano lessons", limit=3) == []

    def test_an_empty_corpus_returns_nothing(self) -> None:
        assert InMemoryRetriever(()).search("anything", limit=3) == []

    def test_duplicate_ids_are_refused(self) -> None:
        with pytest.raises(ValueError, match="KB-01"):
            InMemoryRetriever((ENTRIES[0], ENTRIES[0]))

    def test_deterministic_tie_break(self) -> None:
        twins = (KnowledgeEntry("B", "same", "words"), KnowledgeEntry("A", "same", "words"))
        assert [hit.entry.id for hit in InMemoryRetriever(twins).search("same", limit=2)] == [
            "B",
            "A",
        ]


class TestMarkdownKnowledge:
    def test_loads_sections_with_ids_titles_and_keywords(self, tmp_path: Path) -> None:
        path = tmp_path / "kb.md"
        path.write_text(
            "# Example knowledge\n\nIntro text is ignored.\n\n"
            "## KB-01 Opening hours\nKeywords: horario, abierto\nOpen 9 to 6.\n\n"
            "## KB-02 Location\nNext to the ferry.\n",
            encoding="utf-8",
        )
        entries = load_markdown_knowledge(path)
        assert entries == (
            KnowledgeEntry("KB-01", "Opening hours", "Open 9 to 6.", ("horario", "abierto")),
            KnowledgeEntry("KB-02", "Location", "Next to the ferry."),
        )
        assert "Open 9" not in repr(entries[0])

    @pytest.mark.parametrize(
        ("body", "problem"),
        [
            ("## KB-01 Hours\nA\n## KB-01 Again\nB\n", "duplicate"),
            ("## KB-01\nNo title\n", "title"),
            ("## KB-01 Hours\n\n", "empty"),
            ("# nothing here\n", "no entries"),
        ],
    )
    def test_refuses_malformed_files(self, tmp_path: Path, body: str, problem: str) -> None:
        path = tmp_path / "kb.md"
        path.write_text(body, encoding="utf-8")
        with pytest.raises(ValueError, match=problem):
            load_markdown_knowledge(path)


class TestAnswerInstructions:
    def test_rendered_for_the_organisation_and_language(self) -> None:
        text = render_answer_instructions(CONFIG, "es")
        assert "Example Bike Workshop" in text
        assert "reply in Spanish" in text
        assert REFUSAL_SENTINEL in text

    def test_an_unsupported_language_replies_in_the_default(self) -> None:
        assert "reply in English" in render_answer_instructions(CONFIG, "other")


@dataclass
class FakeCompletion:
    content: str | None = "Open 9 to 6."
    error: BaseException | None = None
    calls: list[dict[str, Any]] = field(default_factory=list)

    def __call__(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return {"choices": [{"message": {"content": self.content}}]}


class TestLiteLLMGenerator:
    def generation(self) -> GenerationRequest:
        return GenerationRequest(
            question="When do you open?",
            subject="Hours",
            passages=(Passage(ENTRIES[0], 1.5),),
            language="en",
            language_name="English",
            instructions="RULES",
        )

    def test_sends_instructions_context_and_question(self) -> None:
        fake = FakeCompletion()
        generator = LiteLLMGenerator(
            model="gemini/x", completion=fake, api_base="http://gw.example"
        )
        assert generator.generate(self.generation()) == "Open 9 to 6."
        assert generator.name == "litellm:gemini/x"
        call = fake.calls[0]
        system, user = call["messages"]
        assert system["content"].startswith("RULES")
        assert "[KB-01] Opening hours" in system["content"]
        assert user["content"] == "Subject: Hours\n\nWhen do you open?"
        assert call["api_base"] == "http://gw.example"
        assert call["temperature"] == 0

    def test_no_content_reads_as_a_refusal(self) -> None:
        generator = LiteLLMGenerator(completion=FakeCompletion(content=None))
        assert generator.generate(self.generation()) == REFUSAL_SENTINEL

    def test_without_litellm_explains_the_extra(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import sys

        monkeypatch.setitem(sys.modules, "litellm", None)
        with pytest.raises(ImportError, match=r"inbox-core\[litellm\]"):
            LiteLLMGenerator()

    def test_object_responses_and_api_key(self) -> None:
        ns = types.SimpleNamespace
        calls: list[dict[str, Any]] = []

        def completion(**kwargs: Any) -> Any:
            calls.append(kwargs)
            return ns(choices=[ns(message=ns(content="ok"))])

        assert LiteLLMGenerator(completion=completion, api_key="k").generate(self.generation())
        assert calls[0]["api_key"] == "k"


def test_a_generation_without_a_subject_sends_the_question_alone() -> None:
    fake = FakeCompletion()
    generation = GenerationRequest("When?", "", (Passage(ENTRIES[0], 1.0),), "en", "English", "R")
    LiteLLMGenerator(completion=fake).generate(generation)
    assert fake.calls[0]["messages"][1]["content"] == "When?"
