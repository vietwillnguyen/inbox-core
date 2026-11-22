"""Delivery: off, draft and auto modes, language gates, send caps, and one path to the public."""

from __future__ import annotations

import ast
import importlib
import inspect
import itertools
import pkgutil
import tomllib
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

import inbox_core
from inbox_core.config import ClientConfig, ConfigError, DeliveryPolicy
from inbox_core.delivery import (
    CapDecision,
    Delivery,
    DeliveryMode,
    DeliveryResult,
    InMemorySendCaps,
    ReleaseRefusedError,
    ReplySink,
    Route,
    SendCaps,
    choose_route,
    parse_mode,
)
from inbox_core.messages import OutboundReply
from tests.helpers import bike_config

ORIGIN = Path(__file__).parent / "fixtures" / "origin_table.toml"
PACKAGE_ROOT = Path(inbox_core.__file__).parent


def reply(language: str = "en", thread: str = "t-1") -> OutboundReply:
    return OutboundReply(
        thread_key=thread,
        in_reply_to="m-1",
        to_address="visitor@example.com",
        text="We open at 9.",
        language=language,
        kind="grounded_answer",
    )


@dataclass
class RecordingSink:
    sent: list[OutboundReply] = field(default_factory=list)
    held: list[OutboundReply] = field(default_factory=list)

    def send_to_public(self, reply: OutboundReply) -> str | None:
        self.sent.append(reply)
        return f"out-{len(self.sent)}"

    def hold_for_review(self, reply: OutboundReply) -> str | None:
        self.held.append(reply)
        return f"draft-{len(self.held)}"


@dataclass
class FixedCaps:
    allowed: bool = True
    recorded: list[tuple[str, str]] = field(default_factory=list)

    def allows(self, sender_key: str, thread_key: str) -> CapDecision:
        if self.allowed:
            return CapDecision.allow()
        return CapDecision.refuse("daily", "30 of 30 sent today")

    def record_send(self, sender_key: str, thread_key: str) -> None:
        self.recorded.append((sender_key, thread_key))


class TestParseMode:
    @pytest.mark.parametrize(("raw", "mode"), [("auto", "auto"), (" DRAFT ", "draft")])
    def test_reads_known_modes(self, raw: str, mode: str) -> None:
        assert parse_mode(raw) is DeliveryMode(mode)

    @pytest.mark.parametrize("raw", [None, "", "aut", "send", "on"])
    def test_anything_else_is_off(self, raw: str | None) -> None:
        assert parse_mode(raw) is DeliveryMode.OFF


class TestChooseRoute:
    AUTO = frozenset({"en"})

    def test_off_routes_nowhere(self) -> None:
        assert choose_route(DeliveryMode.OFF, "en", self.AUTO) == (Route.NONE, "delivery is off")

    def test_draft_always_holds(self) -> None:
        assert choose_route(DeliveryMode.DRAFT, "en", self.AUTO) == (Route.HOLD, "draft mode")

    def test_auto_sends_a_signed_off_language(self) -> None:
        assert choose_route(DeliveryMode.AUTO, "en", self.AUTO) == (Route.SEND, "")

    def test_auto_holds_a_language_not_signed_off(self) -> None:
        assert choose_route(DeliveryMode.AUTO, "es", self.AUTO) == (
            Route.HOLD,
            "language es is not signed off for automatic sending",
        )

    def test_auto_holds_a_reply_that_requires_approval(self) -> None:
        assert choose_route(DeliveryMode.AUTO, "en", self.AUTO, requires_approval=True) == (
            Route.HOLD,
            "the handler asked for approval",
        )


class TestDelivery:
    def build(self, mode: DeliveryMode, caps: SendCaps | None = None) -> tuple[Delivery, Any]:
        sink = RecordingSink()
        delivery = Delivery(
            sink, mode=mode, auto_languages=frozenset({"en"}), caps=caps or FixedCaps()
        )
        return delivery, sink

    def test_off_touches_no_sink_at_all(self) -> None:
        delivery, sink = self.build(DeliveryMode.OFF)
        result = delivery.deliver(reply(), sender_key="k")
        assert result == DeliveryResult(Route.NONE, "none", None, "delivery is off")
        assert sink.sent == []
        assert sink.held == []

    def test_draft_holds(self) -> None:
        delivery, sink = self.build(DeliveryMode.DRAFT)
        result = delivery.deliver(reply(), sender_key="k")
        assert result == DeliveryResult(Route.HOLD, "held", "draft-1", "draft mode")
        assert sink.sent == []

    def test_auto_sends_and_records_against_the_caps(self) -> None:
        caps = FixedCaps()
        delivery, _sink = self.build(DeliveryMode.AUTO, caps)
        result = delivery.deliver(reply(), sender_key="k")
        assert result == DeliveryResult(Route.SEND, "sent", "out-1", "")
        assert caps.recorded == [("k", "t-1")]

    def test_a_reached_cap_holds_instead_of_dropping(self) -> None:
        caps = FixedCaps(allowed=False)
        delivery, sink = self.build(DeliveryMode.AUTO, caps)
        result = delivery.deliver(reply(), sender_key="k")
        assert result.action == "held"
        assert result.held_because == "daily cap reached"
        assert sink.sent == []
        assert caps.recorded == []

    def test_a_failed_send_is_not_recorded_as_sent(self) -> None:
        class Failing(RecordingSink):
            def send_to_public(self, reply: OutboundReply) -> str | None:
                raise ConnectionError("down")

        caps = FixedCaps()
        delivery = Delivery(
            Failing(), mode=DeliveryMode.AUTO, auto_languages=frozenset({"en"}), caps=caps
        )
        with pytest.raises(ConnectionError):
            delivery.deliver(reply(), sender_key="k")
        assert caps.recorded == []

    def test_auto_languages_must_be_codes(self) -> None:
        with pytest.raises(ValueError, match="auto_languages"):
            Delivery(RecordingSink(), mode=DeliveryMode.AUTO, auto_languages="en", caps=FixedCaps())  # type: ignore[arg-type]

    def test_the_mode_is_readable(self) -> None:
        delivery, _ = self.build(DeliveryMode.DRAFT)
        assert delivery.mode is DeliveryMode.DRAFT


class TestTheOnlyPathToThePublic:
    """Exactly one code path in the package can send to the public."""

    def test_every_combination_sends_only_when_every_gate_allows(self) -> None:
        for mode, language, approval, allowed in itertools.product(
            DeliveryMode, ("en", "es", "other"), (False, True), (False, True)
        ):
            sink = RecordingSink()
            delivery = Delivery(
                sink, mode=mode, auto_languages=frozenset({"en"}), caps=FixedCaps(allowed)
            )
            delivery.deliver(reply(language), sender_key="k", requires_approval=approval)
            should_send = (
                mode is DeliveryMode.AUTO and language == "en" and not approval and allowed
            )
            assert bool(sink.sent) is should_send, (mode, language, approval, allowed)
            if mode is DeliveryMode.OFF:
                assert sink.held == [], "off must not even draft"
            if mode is DeliveryMode.DRAFT:
                assert sink.sent == [], "draft must never send"

    def test_the_sink_protocol_has_exactly_one_send_shaped_method(self) -> None:
        names = {name for name, _ in inspect.getmembers(ReplySink) if not name.startswith("_")}
        assert names == {"send_to_public", "hold_for_review"}

    def test_no_other_public_symbol_is_send_shaped(self) -> None:
        # Every public function and method in the package, walked from the
        # modules rather than listed by hand, so a new one cannot be missed.
        shaped = set()
        for module in iter_modules():
            for name, obj in vars(module).items():
                if name.startswith("_") or getattr(obj, "__module__", None) != module.__name__:
                    continue
                if send_shaped(name) and callable(obj) and not inspect.isclass(obj):
                    shaped.add(f"{module.__name__}.{name}")
                if inspect.isclass(obj):
                    for member, value in vars(obj).items():
                        method = isinstance(value, staticmethod | classmethod | property)
                        method = method or inspect.isfunction(value)
                        if method and not member.startswith("_") and send_shaped(member):
                            shaped.add(f"{module.__name__}.{obj.__name__}.{member}")
        # Implementing the protocol's method is expected (that is what a sink
        # is); any other send-shaped name is a second path and fails here. The
        # implementations inside the package are pinned too: the protocol
        # itself and the recording fake for tests. A real sink in the core
        # would show up here and need a deliberate decision.
        # DraftReview.send is the one deliberate exception: a person approving
        # a held draft. It reaches the public only through
        # Delivery.release_approved (pinned below), never through a sink.
        others = {name for name in shaped if not name.endswith(".send_to_public")}
        assert others == {"inbox_core.review.DraftReview.send"}
        assert shaped == {
            "inbox_core.delivery.ReplySink.send_to_public",
            "inbox_core.review.DraftReview.send",
            "inbox_core.testing.fakes.RecordingSink.send_to_public",
        }

    def test_send_to_public_is_called_from_exactly_one_place(self) -> None:
        calls = []
        for path in sorted(PACKAGE_ROOT.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "send_to_public"
                ):
                    calls.append((path.relative_to(PACKAGE_ROOT).as_posix(), enclosing(tree, node)))
        assert calls == [("delivery.py", "Delivery._send")]

    def test_the_one_call_site_is_reached_only_after_the_route_is_send(self) -> None:
        source = inspect.getsource(Delivery.deliver)
        assert source.index("Route.SEND") < source.index("self._send(")

    def test_only_deliver_and_release_approved_reach_the_call_site(self) -> None:
        # A person approving a held draft is the second, deliberate way to the
        # public. It still goes through Delivery._send, and refuses under off.
        tree = ast.parse(inspect.getsource(Delivery).lstrip())
        callers = sorted(
            enclosing(tree, node)
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "_send"
        )
        assert callers == ["Delivery.deliver", "Delivery.release_approved"]
        source = inspect.getsource(Delivery.release_approved)
        assert source.index("DeliveryMode.OFF") < source.index("self._send(")

    def test_release_approved_refuses_under_off_and_sends_otherwise(self) -> None:
        for mode in DeliveryMode:
            sink, caps = RecordingSink(), FixedCaps(allowed=False)
            delivery = Delivery(sink, mode=mode, auto_languages=frozenset(), caps=caps)
            if mode is DeliveryMode.OFF:
                with pytest.raises(ReleaseRefusedError):
                    delivery.release_approved(reply("es"), sender_key="s")
                assert sink.sent == []
                continue
            result = delivery.release_approved(reply("es"), sender_key="s")
            assert (result.action, result.provider_ref) == ("sent", "out-1")
            assert caps.recorded == [("s", "t-1")]


def send_shaped(name: str) -> bool:
    return name.lower().startswith(("send", "publish", "post", "deliver_to_public"))


def iter_modules() -> list[Any]:
    # Importing every module is safe without the optional SDKs: each adapter
    # imports its SDK only when it is used.
    modules = [inbox_core]
    for info in pkgutil.walk_packages(inbox_core.__path__, "inbox_core."):
        modules.append(importlib.import_module(info.name))
    return modules


def enclosing(tree: ast.AST, target: ast.AST) -> str:
    def walk(node: ast.AST, trail: tuple[str, ...]) -> str | None:
        for child in ast.iter_child_nodes(node):
            names = trail
            if isinstance(child, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
                names = (*trail, child.name)
            if child is target:
                return ".".join(names)
            found = walk(child, names)
            if found:
                return found
        return None

    return walk(tree, ()) or "<module>"


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


class TestInMemorySendCaps:
    def test_per_sender_cap_counts_threads_not_messages(self) -> None:
        caps = InMemorySendCaps(daily_cap=10, per_sender_cap=2, clock=Clock(datetime.now(UTC)))
        caps.record_send("k", "t1")
        caps.record_send("k", "t1")
        assert caps.allows("k", "t2").allowed
        caps.record_send("k", "t2")
        refused = caps.allows("k", "t3")
        assert refused == CapDecision.refuse(
            "per_sender", "2 of 2 conversations for this sender today"
        )
        assert caps.allows("k", "t1").allowed, "a thread already counted does not count again"
        assert caps.allows("other", "t9").allowed

    def test_daily_cap(self) -> None:
        caps = InMemorySendCaps(daily_cap=2, per_sender_cap=5, clock=Clock(datetime.now(UTC)))
        caps.record_send("a", "t1")
        caps.record_send("b", "t2")
        assert caps.allows("c", "t3") == CapDecision.refuse("daily", "2 of 2 sent today")

    def test_the_day_is_the_organisations_local_day(self) -> None:
        zone = ZoneInfo("Asia/Ho_Chi_Minh")
        clock = Clock(datetime(2026, 5, 1, 16, 30, tzinfo=UTC))  # 23:30 local
        caps = InMemorySendCaps(daily_cap=1, per_sender_cap=1, timezone=zone, clock=clock)
        caps.record_send("a", "t1")
        assert not caps.allows("b", "t2").allowed
        clock.now += timedelta(hours=1)  # 00:30 local the next day, still 1 May in UTC
        assert caps.allows("b", "t2").allowed
        assert caps.sent_today == 0

    def test_satisfies_the_protocol_and_bounds_are_positive(self) -> None:
        assert isinstance(InMemorySendCaps(), SendCaps)
        with pytest.raises(ValueError, match="positive"):
            InMemorySendCaps(daily_cap=0)

    def test_from_policy(self) -> None:
        policy = DeliveryPolicy(daily_send_cap=7, per_sender_daily_cap=3, timezone="Europe/Lisbon")
        caps = InMemorySendCaps.from_policy(policy)
        assert (caps.daily_cap, caps.per_sender_cap) == (7, 3)


class TestDeliveryPolicyConfig:
    def load(self, delivery: dict[str, Any]) -> ClientConfig:
        data = tomllib.loads(ORIGIN.read_text(encoding="utf-8"))
        data["delivery"] = delivery
        return ClientConfig.from_mapping(data)

    def test_defaults_are_off_and_nothing_auto_sends(self) -> None:
        policy = bike_config().delivery
        assert policy.mode is DeliveryMode.OFF
        assert policy.auto_languages == frozenset()
        assert policy.max_bot_replies_per_conversation == 1

    def test_loads_from_a_file(self) -> None:
        config = self.load(
            {
                "mode": "draft",
                "auto_languages": ["en"],
                "daily_send_cap": 10,
                "per_sender_daily_cap": 1,
                "max_bot_replies_per_conversation": 3,
                "timezone": "Asia/Ho_Chi_Minh",
                "holding": {"en": "A person will reply soon.", "vi": "Chúng tôi sẽ trả lời."},
            }
        )
        policy = config.delivery
        assert policy.mode is DeliveryMode.DRAFT
        assert policy.auto_languages == frozenset({"en"})
        assert config.holding_text("vi") == "Chúng tôi sẽ trả lời."
        assert policy.zone == ZoneInfo("Asia/Ho_Chi_Minh")

    @pytest.mark.parametrize(
        ("delivery", "problem"),
        [
            ({"mode": "aut"}, "mode"),
            ({"auto_languages": ["fr"]}, "auto_languages"),
            ({"auto_languages": "en"}, "auto_languages"),
            ({"daily_send_cap": 0}, "daily_send_cap"),
            ({"per_sender_daily_cap": True}, "per_sender_daily_cap"),
            ({"max_bot_replies_per_conversation": -1}, "max_bot_replies"),
            ({"timezone": "Mars/Olympus"}, "timezone"),
            ({"holding": {"fr": "Bonjour"}}, "holding"),
            ({"holding": {"en": " "}}, "holding"),
            ({"holding": "hi"}, "holding"),
            ({"colour": "blue"}, "colour"),
            ("off", "delivery must be a table"),
        ],
    )
    def test_bad_delivery_settings_are_refused(self, delivery: Any, problem: str) -> None:
        with pytest.raises(ConfigError, match=problem):
            self.load(delivery)

    def test_holding_falls_back_to_the_default_language(self) -> None:
        config = self.load({"holding": {"en": "A person will reply soon."}})
        assert config.holding_text("vi") == "A person will reply soon."
        assert config.holding_text("other") == "A person will reply soon."

    def test_no_holding_text_configured(self) -> None:
        assert self.load({}).holding_text("en") is None

    def test_holding_only_in_a_non_default_language(self) -> None:
        config = self.load({"holding": {"vi": "Chúng tôi sẽ trả lời."}})
        assert config.holding_text("en") is None


@pytest.mark.parametrize(
    ("kwargs", "problem"),
    [
        ({"mode": "auto"}, "delivery.mode"),
        ({"auto_languages": {"en"}}, "auto_languages"),
    ],
)
def test_delivery_policy_built_in_python_is_validated(kwargs: dict[str, Any], problem: str) -> None:
    with pytest.raises(ConfigError, match=problem):
        DeliveryPolicy(**kwargs)
