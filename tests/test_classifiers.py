"""Classifier adapters, the shared validator, retries and shadow mode. Fakes only, no network."""

from __future__ import annotations

import json
import logging
import sys
import types
from dataclasses import dataclass, field
from typing import Any

import pytest

from inbox_core.adapters.jev import JevClassifier, build_questions
from inbox_core.adapters.litellm import DEFAULT_MODEL, LiteLLMClassifier
from inbox_core.messages import IncomingMessage
from inbox_core.shadow import ShadowingClassifier, agreement
from inbox_core.testing.logs import attached_caplog
from inbox_core.triage import (
    RetryingClassifier,
    TriageClassifier,
    TriageSignals,
    TriageUnavailable,
    signals_from_payload,
)
from tests.helpers import bike_config, message

CONFIG = bike_config()
SECRET_TEXT = "my bike was stolen outside the cafe on Elm Road"


def good_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "category": "faq",
        "language": "en",
        "confidence": 0.82,
        "asks_for_human": False,
        "mentions_money_or_commitment": False,
    }
    payload.update(overrides)
    return payload


class TestSignalsFromPayload:
    def read(self, payload: object) -> TriageSignals:
        return signals_from_payload(payload, CONFIG.triage, classifier="fake", message_id="m-1")

    def test_a_good_payload_becomes_signals(self) -> None:
        assert self.read(good_payload()) == TriageSignals("faq", "en", 0.82, False, False, "fake")

    def test_other_is_an_accepted_language(self) -> None:
        assert self.read(good_payload(language="other")).language == "other"

    @pytest.mark.parametrize(("value", "clamped"), [(1.7, 1.0), (-0.2, 0.0), (1, 1.0)])
    def test_confidence_is_clamped(self, value: float, clamped: float) -> None:
        assert self.read(good_payload(confidence=value)).confidence == clamped

    def test_a_numeric_string_confidence_is_read(self) -> None:
        assert self.read(good_payload(confidence="0.5")).confidence == 0.5

    @pytest.mark.parametrize(
        "payload",
        [
            [],
            "faq",
            good_payload(category="refund_please"),
            good_payload(category=None),
            good_payload(language="fr"),
            good_payload(confidence="very high"),
            good_payload(confidence=None),
            good_payload(confidence=True),
            good_payload(confidence=float("nan")),
            good_payload(confidence=float("inf")),
            good_payload(asks_for_human="no"),
            good_payload(mentions_money_or_commitment=1),
            {k: v for k, v in good_payload().items() if k != "confidence"},
        ],
    )
    def test_anything_malformed_is_unavailable(self, payload: object) -> None:
        with pytest.raises(TriageUnavailable) as caught:
            self.read(payload)
        assert "m-1" in str(caught.value)

    def test_an_unknown_category_value_is_not_echoed(self) -> None:
        with pytest.raises(TriageUnavailable) as caught:
            self.read(good_payload(category=SECRET_TEXT))
        assert "stolen" not in str(caught.value)


@dataclass
class FlakyClassifier:
    failures: list[BaseException]
    name: str = "flaky"
    calls: int = 0

    def classify(self, message: IncomingMessage) -> TriageSignals:
        self.calls += 1
        if self.failures:
            raise self.failures.pop(0)
        return TriageSignals("faq", "en", 0.9, False, False, self.name)


class TestRetryingClassifier:
    def test_succeeds_after_transient_failures_with_backoff(self) -> None:
        slept: list[float] = []
        inner = FlakyClassifier([TriageUnavailable("a"), TriageUnavailable("b")])
        retrying = RetryingClassifier(inner, attempts=3, backoff=(0.5, 2.0), sleep=slept.append)
        assert retrying.classify(message()).category == "faq"
        assert inner.calls == 3
        assert slept == [0.5, 2.0]
        assert retrying.name == "flaky"
        assert isinstance(retrying, TriageClassifier)

    def test_gives_up_after_the_bound(self) -> None:
        inner = FlakyClassifier([TriageUnavailable("x")] * 5)
        retrying = RetryingClassifier(inner, attempts=2, backoff=(0.1,), sleep=lambda _: None)
        with pytest.raises(TriageUnavailable, match="after 2 attempts"):
            retrying.classify(message())
        assert inner.calls == 2

    def test_reuses_the_last_backoff_step(self) -> None:
        slept: list[float] = []
        inner = FlakyClassifier([TriageUnavailable("x")] * 3)
        RetryingClassifier(inner, attempts=4, backoff=(1.0,), sleep=slept.append).classify(
            message()
        )
        assert slept == [1.0, 1.0, 1.0]

    def test_an_unexpected_exception_fails_closed_without_its_message(self) -> None:
        inner = FlakyClassifier([ValueError(SECRET_TEXT)] * 3)
        retrying = RetryingClassifier(inner, attempts=3, backoff=(), sleep=lambda _: None)
        with pytest.raises(TriageUnavailable) as caught:
            retrying.classify(message(message_id="m-9"))
        assert "stolen" not in str(caught.value)
        assert "ValueError" in str(caught.value)
        assert "m-9" in str(caught.value)

    def test_a_keyboard_interrupt_is_not_swallowed(self) -> None:
        inner = FlakyClassifier([KeyboardInterrupt()])
        with pytest.raises(KeyboardInterrupt):
            RetryingClassifier(inner, attempts=3, sleep=lambda _: None).classify(message())

    def test_at_least_one_attempt(self) -> None:
        with pytest.raises(ValueError, match="attempts"):
            RetryingClassifier(FlakyClassifier([]), attempts=0)


@dataclass
class FakeCompletion:
    content: Any = field(default_factory=lambda: json.dumps(good_payload()))
    as_object: bool = False
    error: BaseException | None = None
    calls: list[dict[str, Any]] = field(default_factory=list)

    def __call__(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        if self.as_object:
            msg = types.SimpleNamespace(content=self.content)
            return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])
        return {"choices": [{"message": {"content": self.content}}]}


class TestLiteLLMClassifier:
    def test_default_model_is_flash_lite_and_named(self) -> None:
        classifier = LiteLLMClassifier(CONFIG, completion=FakeCompletion())
        assert "flash-lite" in DEFAULT_MODEL
        assert classifier.name == f"litellm:{DEFAULT_MODEL}"

    def test_the_call_is_built_from_the_config(self) -> None:
        fake = FakeCompletion()
        classifier = LiteLLMClassifier(
            CONFIG,
            model="gateway/flash-lite",
            completion=fake,
            api_key="test-key",
            api_base="http://gateway.example",
            timeout=5.0,
        )
        signals = classifier.classify(message("Hi", subject="Hours"))
        assert signals.classifier == "litellm:gateway/flash-lite"

        call = fake.calls[0]
        assert call["model"] == "gateway/flash-lite"
        assert call["temperature"] == 0
        assert call["api_key"] == "test-key"
        assert call["api_base"] == "http://gateway.example"
        assert call["timeout"] == 5.0
        schema = call["response_format"]["json_schema"]["schema"]
        assert schema["properties"]["category"]["enum"] == [
            "faq",
            "booking",
            "refund",
            "other",
            "automated",
        ]
        assert schema["properties"]["language"]["enum"] == ["en", "es", "other"]
        system, user = call["messages"]
        assert "Example Bike Workshop" in system["content"]
        assert json.loads(user["content"]) == {"subject": "Hours", "body": "Hi"}

    def test_key_and_base_are_omitted_when_unset(self) -> None:
        fake = FakeCompletion()
        LiteLLMClassifier(CONFIG, completion=fake).classify(message())
        assert "api_key" not in fake.calls[0]
        assert "api_base" not in fake.calls[0]

    def test_object_shaped_responses_are_read(self) -> None:
        fake = FakeCompletion(as_object=True)
        assert LiteLLMClassifier(CONFIG, completion=fake).classify(message()).category == "faq"

    @pytest.mark.parametrize(
        "fake",
        [
            FakeCompletion(content="not json"),
            FakeCompletion(content=None),
            FakeCompletion(content=json.dumps([1, 2])),
            FakeCompletion(content=json.dumps(good_payload(category="cake"))),
            FakeCompletion(
                content='{"category": "faq", "language": "en", "confidence": NaN, '
                '"asks_for_human": false, "mentions_money_or_commitment": false}'
            ),
        ],
    )
    def test_malformed_answers_are_unavailable(self, fake: FakeCompletion) -> None:
        with pytest.raises(TriageUnavailable):
            LiteLLMClassifier(CONFIG, completion=fake).classify(message())

    @pytest.mark.parametrize("response", [{"choices": []}, types.SimpleNamespace(choices=[])])
    def test_no_choices_is_unavailable(self, response: Any) -> None:
        with pytest.raises(TriageUnavailable, match="no choices"):
            LiteLLMClassifier(CONFIG, completion=lambda **_: response).classify(message())

    def test_a_transport_error_carries_its_type_and_never_its_message(self) -> None:
        fake = FakeCompletion(error=ConnectionError(f"echo of prompt: {SECRET_TEXT}"))
        with pytest.raises(TriageUnavailable) as caught:
            LiteLLMClassifier(CONFIG, completion=fake).classify(message(SECRET_TEXT))
        assert "ConnectionError" in str(caught.value)
        assert "stolen" not in str(caught.value)
        assert caught.value.__cause__ is None
        assert caught.value.__suppress_context__

    def test_without_litellm_installed_construction_explains_the_extra(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setitem(sys.modules, "litellm", None)
        with pytest.raises(ImportError, match=r"inbox-core\[litellm\]"):
            LiteLLMClassifier(CONFIG)

    def test_with_litellm_installed_its_completion_is_used(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = FakeCompletion()
        module = types.ModuleType("litellm")
        module.completion = fake  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "litellm", module)
        LiteLLMClassifier(CONFIG).classify(message())
        assert fake.calls


@dataclass
class FakeJevClient:
    response: Any = None
    error: BaseException | None = None
    calls: list[dict[str, Any]] = field(default_factory=list)
    closed: bool = False

    def system_one(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response

    def close(self) -> None:
        self.closed = True


def jev_response(
    category: str = "faq",
    confidence: Any = 0.91,
    language: str = "es",
    human: float = 0.2,
    money: float = 0.7,
) -> Any:
    ns = types.SimpleNamespace
    return ns(
        choices={
            "category": ns(choice=category, confidence=confidence),
            "language": ns(choice=language, confidence=0.99),
        },
        nouls={"asks_for_human": ns(noul=human), "mentions_money_or_commitment": ns(noul=money)},
    )


class TestJevClassifier:
    def test_questions_are_built_from_the_config(self) -> None:
        questions = build_questions(CONFIG)
        assert list(questions["category"]["criteria"]) == [
            "faq",
            "booking",
            "refund",
            "other",
            "automated",
        ]
        assert list(questions["language"]["criteria"]) == ["en", "es", "other"]
        assert "Example Bike Workshop" in questions["category"]["instructions"]
        assert questions["asks_for_human"]["type"] == "noul"

    def test_answers_become_signals(self) -> None:
        client = FakeJevClient(response=jev_response())
        signals = JevClassifier(CONFIG, client, model="jev-test").classify(message("Hola"))
        assert signals == TriageSignals("faq", "es", 0.91, False, True, "jev:jev-test")
        assert client.calls[0]["state"] == {"subject": "", "body": "Hola"}
        assert client.calls[0]["model"] == "jev-test"

    @pytest.mark.parametrize(
        "response",
        [
            jev_response(category="cake"),
            jev_response(language="fr"),
            jev_response(confidence="high"),
            jev_response(confidence=float("nan")),
            types.SimpleNamespace(choices={}, nouls={}),
            None,
        ],
    )
    def test_malformed_answers_are_unavailable(self, response: Any) -> None:
        with pytest.raises(TriageUnavailable):
            JevClassifier(CONFIG, FakeJevClient(response=response)).classify(message())

    def test_a_transport_error_carries_its_type_only(self) -> None:
        client = FakeJevClient(error=RuntimeError(SECRET_TEXT))
        with pytest.raises(TriageUnavailable) as caught:
            JevClassifier(CONFIG, client).classify(message(SECRET_TEXT))
        assert "RuntimeError" in str(caught.value)
        assert "stolen" not in str(caught.value)

    def test_close_is_passed_on(self) -> None:
        client = FakeJevClient()
        JevClassifier(CONFIG, client).close()
        assert client.closed
        JevClassifier(CONFIG, object()).close()  # a client without close is fine

    def test_from_api_key_without_the_sdk_explains_the_extra(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setitem(sys.modules, "typesafe_sdk", None)
        with pytest.raises(ImportError, match=r"inbox-core\[jev\]"):
            JevClassifier.from_api_key(CONFIG, "key")

    def test_from_api_key_with_the_sdk_builds_its_client(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        built: dict[str, Any] = {}

        class TypeSafeClient:
            def __init__(self, *, api_key: str, model: str) -> None:
                built.update(api_key=api_key, model=model)

        module = types.ModuleType("typesafe_sdk")
        module.TypeSafeClient = TypeSafeClient  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "typesafe_sdk", module)
        classifier = JevClassifier.from_api_key(CONFIG, "key", model="jev-x")
        assert built == {"api_key": "key", "model": "jev-x"}
        assert classifier.name == "jev:jev-x"


def test_optional_sdks_are_not_imported_by_the_adapters_or_the_package() -> None:
    # In a fresh interpreter: inside the test process another test may already
    # have imported one of these, which made this check pass or fail by order.
    import subprocess

    optional = (
        "litellm",
        "typesafe_sdk",
        "sqlalchemy",
        "fastapi",
        "starlette",
        "uvicorn",
        "httpx",
        "apprise",
    )
    probe = (
        "import sys, inbox_core, inbox_core.adapters.litellm, inbox_core.adapters.jev,"
        " inbox_core.adapters.apprise, inbox_core.notify, inbox_core.pipeline;"
        f"print(','.join(n for n in {optional!r} if n in sys.modules))"
    )
    found = subprocess.run(  # noqa: S603 - a fixed probe in this interpreter
        [sys.executable, "-c", probe], capture_output=True, text=True, check=True
    ).stdout.strip()
    assert found == ""


@dataclass
class FixedClassifier:
    signals: TriageSignals | None
    name: str = "fixed"

    def classify(self, message: IncomingMessage) -> TriageSignals:
        if self.signals is None:
            raise TriageUnavailable("down")
        return self.signals


class TestShadow:
    decided = TriageSignals("faq", "en", 0.9, False, False, "decider")
    other = TriageSignals("booking", "en", 0.4, False, True, "shadow")

    def test_the_decider_answers_and_the_shadow_is_out_of_band(self) -> None:
        shadowing = ShadowingClassifier(FixedClassifier(self.decided), FixedClassifier(self.other))
        assert shadowing.classify(message()) == self.decided
        assert shadowing.last_shadow == self.other
        assert shadowing.name == "fixed"

    def test_a_shadow_failure_is_logged_by_type_and_swallowed(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        shadowing = ShadowingClassifier(FixedClassifier(self.decided), FixedClassifier(None))
        with attached_caplog(caplog, "inbox_core.shadow"):
            assert shadowing.classify(message(message_id="m-5")) == self.decided
        assert shadowing.last_shadow is None
        assert "m-5" in caplog.text
        assert "TriageUnavailable" in caplog.text
        assert caplog.records[0].levelno == logging.WARNING

    def test_a_decider_failure_propagates(self) -> None:
        shadowing = ShadowingClassifier(FixedClassifier(None), FixedClassifier(self.other))
        with pytest.raises(TriageUnavailable):
            shadowing.classify(message())

    def test_no_shadow(self) -> None:
        shadowing = ShadowingClassifier(FixedClassifier(self.decided))
        shadowing.classify(message())
        assert shadowing.last_shadow is None

    def test_agreement_is_per_field(self) -> None:
        assert agreement(self.decided, None) == {}
        assert agreement(self.decided, self.other) == {
            "category": False,
            "language": True,
            "asks_for_human": True,
            "mentions_money_or_commitment": False,
        }
