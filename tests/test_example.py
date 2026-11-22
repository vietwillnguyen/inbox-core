"""The worked example: a made-up tool library, its golden set, and the demo command."""

from __future__ import annotations

import dataclasses
import io
import json
import sys

import pytest

from inbox_core.evals.golden import as_incoming, load_golden_set
from inbox_core.evals.runners import evaluate_triage
from inbox_core.examples import demo
from inbox_core.examples.demo import (
    EXAMPLE_DIR,
    KeywordClassifier,
    build_pipeline,
    example_config,
    example_knowledge,
)
from inbox_core.messages import IncomingMessage, make_sender_key
from inbox_core.pipeline import AuditSink, Notifier, Pipeline
from inbox_core.testing.fakes import RecordingSink
from inbox_core.testing.privacy import run_privacy_sweep


def golden() -> tuple:  # type: ignore[type-arg]
    return load_golden_set(
        EXAMPLE_DIR / "golden.toml", example_config(), require_every_language=True
    )


class TestTheExampleData:
    def test_the_config_loads(self) -> None:
        config = example_config()
        assert config.organisation.name == "Brambleford Tool Library"
        assert set(config.triage.languages) == {"en", "es"}
        assert len(config.triage.categories) == 9

    def test_about_thirty_knowledge_entries(self) -> None:
        assert len(example_knowledge()) == 30

    def test_the_golden_set_is_valid_in_both_languages(self) -> None:
        cases = golden()
        assert len(cases) >= 40
        assert {case.language for case in cases} == {"en", "es", "other"}

    def test_the_data_holds_only_made_up_addresses(self) -> None:
        import re

        for name in ("client.toml", "knowledge.md", "golden.toml"):
            text = (EXAMPLE_DIR / name).read_text(encoding="utf-8")
            for host in re.findall(r"[\w.-]+\.(?:com|org|net|io|uk|dev)\b", text):
                pytest.fail(f"{name} names a real-looking domain: {host}")
            for address in re.findall(r"[\w.+-]+@[\w.-]+", text):
                assert address.rstrip(".").endswith(".example"), address


class TestTheKeywordClassifier:
    def test_it_passes_the_executive_gate_on_the_golden_set(self) -> None:
        # The keyword stand-in is not a model and is not accurate, but it must
        # never let a sensitive message through on the example's own golden set.
        metrics = evaluate_triage(KeywordClassifier(), golden(), example_config().triage)
        assert metrics.passes_executive_gate(), metrics.missed_executive

    @pytest.mark.parametrize(
        "text",
        [
            "I want to make a complaint about how a volunteer spoke to me.",
            "Can you send me the workshop dates? Se you soon, Mi",
        ],
    )
    def test_common_english_words_are_not_read_as_spanish(self, text: str) -> None:
        found = KeywordClassifier().classify(message_with(text))
        assert found.language == "en"

    def test_spanish_is_still_spanish(self) -> None:
        found = KeywordClassifier().classify(message_with("Quiero hacerme socia de la biblioteca"))
        assert found.language == "es"


def message_with(text: str) -> IncomingMessage:
    return IncomingMessage(
        channel="web",
        thread_key="t",
        provider_message_id="m",
        sender_key=make_sender_key("visitor@example.com"),
        sender_address="visitor@example.com",
        text=text,
    )


def run(*argv: str) -> tuple[int, str]:
    out = io.StringIO()
    code = demo.main(list(argv), stdout=out)
    return code, out.getvalue()


class TestTheDemoCommand:
    def test_draft_mode_holds_an_english_answer(self) -> None:
        code, printed = run("What are your opening hours?")
        assert code == 0
        record = json.loads(printed.split("audit record:\n", 1)[1])
        assert record["decision"] == "answer_held"
        assert record["sources"] == ["TL-01"]
        assert "held for review" in printed

    def test_auto_mode_sends_english_and_holds_spanish(self) -> None:
        code, printed = run("--mode", "auto", "What are your opening hours?")
        assert code == 0
        assert '"decision": "answered"' in printed
        code, printed = run("--mode", "auto", "Hola, ¿qué horario tienen los sábados?")
        assert code == 0
        assert '"decision": "answer_held"' in printed
        assert "language es is not signed off" in printed

    def test_membership_uses_the_template(self) -> None:
        code, printed = run("--mode", "auto", "How do I become a member?")
        assert code == 0
        assert '"handler": "membership"' in printed
        assert "photo ID" in printed

    def test_a_damage_report_is_handed_off(self) -> None:
        code, printed = run("--mode", "auto", "The ladder slipped and I hurt my wrist")
        assert code == 0
        assert '"decision": "handed_off"' in printed
        assert '"tier": "needs_executive"' in printed
        assert "escalation:" in printed

    def test_the_model_path_runs_offline_with_a_stand_in_for_litellm(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import types

        def completion(**kwargs: object) -> dict[str, object]:
            if "response_format" in kwargs:
                content = json.dumps(
                    {
                        "category": "faq",
                        "language": "en",
                        "confidence": 0.9,
                        "asks_for_human": False,
                        "mentions_money_or_commitment": False,
                    }
                )
            else:
                content = "We are open on Wednesday evenings and Saturday mornings."
            return {"choices": [{"message": {"content": content}}]}

        module = types.ModuleType("litellm")
        module.completion = completion  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "litellm", module)
        code, printed = run("--mode", "auto", "--model", "gemini/test", "When are you open?")
        assert code == 0
        assert "Wednesday evenings" in printed
        assert '"classifier": "litellm:gemini/test"' in printed

    def test_the_model_path_without_litellm_explains_the_extra(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setitem(sys.modules, "litellm", None)
        assert demo.main(["--model", "gemini/x", "hello"]) == 2
        assert "inbox-core[litellm]" in capsys.readouterr().err


def test_the_example_passes_the_privacy_sweep(caplog: pytest.LogCaptureFixture) -> None:
    # One made-up sender per case, so the flood guard does not hide the other paths.
    corpus = [
        dataclasses.replace(
            as_incoming(case, channel="web"),
            sender_address=f"visitor{n}@mail.example",
            sender_key=make_sender_key(f"visitor{n}@mail.example"),
        )
        for n, case in enumerate(golden())
    ]

    def build(notifier: Notifier, audit: AuditSink) -> Pipeline:
        return build_pipeline(
            classifier=KeywordClassifier(), sink=RecordingSink(), notifier=notifier, audit=audit
        )

    report = run_privacy_sweep(build, corpus, caplog)
    assert report.processed == len(corpus)
    assert report.decisions["handed_off"] > 0
    assert report.decisions["answer_held"] > 0


EXPECTED_TOP_ENTRY = {
    "faq-en-hours": "TL-01",
    "faq-en-location": "TL-02",
    "faq-en-loan": "TL-07",
    "faq-en-ladder": "TL-13",
    "faq-en-repair-cafe": "TL-20",
    "faq-en-limit": "TL-10",
    "faq-es-hours": "TL-01",
    "faq-es-location": "TL-02",
    "faq-es-renew": "TL-08",
    "faq-es-protection": "TL-15",
    "faq-es-accessibility": "TL-23",
    "membership-en-join": {"TL-05", "TL-06"},
    "membership-en-eligibility": "TL-05",
    "membership-es-join": {"TL-05", "TL-06"},
    "membership-es-age": "TL-05",
}


def test_every_answerable_case_retrieves_the_entry_that_answers_it() -> None:
    from inbox_core.evals.golden import answerable_cases

    retriever = demo.example_retriever()
    cases = answerable_cases(golden())
    assert {case.id for case in cases} == set(EXPECTED_TOP_ENTRY)
    for case in cases:
        hits = retriever.search(f"{case.subject}\n{case.text}", limit=1)
        assert hits, case.id
        expected = EXPECTED_TOP_ENTRY[case.id]
        allowed = expected if isinstance(expected, set) else {expected}
        assert hits[0].entry.id in allowed, (case.id, hits[0].entry.id)
        assert hits[0].score >= demo.MIN_SCORE, (case.id, hits[0].score)


@pytest.mark.parametrize(
    ("question", "entry"),
    [
        ("Where is the library?", "TL-02"),
        ("When are you open?", "TL-01"),
        ("How do I get there by bus?", "TL-03"),
        ("Are you open on Sunday?", "TL-01"),
    ],
)
def test_everyday_questions_find_their_entry(question: str, entry: str) -> None:
    hits = demo.example_retriever().search(question, limit=1)
    assert hits[0].entry.id == entry
