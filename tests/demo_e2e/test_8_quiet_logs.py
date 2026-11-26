"""No visitor text in any container's log: every path, then a search of every log."""

from __future__ import annotations

from collections.abc import Callable

from tests.demo_e2e.bundle import Visitor, compose, unique, until


def test_no_container_logs_what_visitors_wrote(visitor: Callable[[], Visitor]) -> None:
    phrases = {
        "answered": unique("What are your opening hours, asks"),
        "handed off": unique("Write me a poem about otters called"),
        "held for approval": unique("My brakes squeak, says"),
        "money": unique("I want my money back from"),
    }
    people = []
    for phrase in phrases.values():
        person = visitor()
        person.say(phrase)
        people.append(person)
    for person in people[:2]:
        until(person.replies)
    logs = compose("logs", "--no-color", timeout=240)
    assert logs.count("\n") > 50
    for path, phrase in phrases.items():
        token = phrase.rsplit(" ", 1)[1]
        assert token not in logs, f"the {path} path logged visitor text"
