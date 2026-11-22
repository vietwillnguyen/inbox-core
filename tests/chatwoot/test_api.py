"""The Chatwoot API wrapper: request shapes, authorization and error mapping."""

from __future__ import annotations

import json

import httpx
import pytest

from inbox_core.chatwoot.api import ChatwootApi, ChatwootError
from tests.chatwoot.fake import ACCOUNT, ADMIN_TOKEN, AGENT_TOKEN, BOT_TOKEN, FakeChatwoot


def api(fake: FakeChatwoot, token: str = BOT_TOKEN) -> ChatwootApi:
    return ChatwootApi("http://chatwoot.test/", ACCOUNT, token, transport=fake.transport())


def recording(status: int = 200, body: object = None) -> tuple[list[httpx.Request], ChatwootApi]:
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, json=body if body is not None else {})

    return seen, ChatwootApi(
        "http://chatwoot.test", ACCOUNT, BOT_TOKEN, transport=httpx.MockTransport(handle)
    )


def test_requests_use_the_api_access_token_header_and_the_account() -> None:
    seen, client = recording(body={"id": 9})
    assert client.send_message(4, "Hello") == "9"
    (request,) = seen
    assert request.headers["api_access_token"] == BOT_TOKEN
    assert "authorization" not in request.headers
    assert request.url.path == "/api/v1/accounts/1/conversations/4/messages"
    assert json.loads(request.content) == {
        "content": "Hello",
        "message_type": "outgoing",
        "private": False,
    }


def test_a_private_note_is_private() -> None:
    seen, client = recording(body={"id": 9})
    client.add_private_note(4, "Staff only")
    assert json.loads(seen[0].content)["private"] is True


def test_a_message_without_an_id_returns_none() -> None:
    _, client = recording(body={})
    assert client.send_message(4, "Hello") is None


def test_open_assign_and_label() -> None:
    fake = FakeChatwoot()
    fake.conversation(4)
    fake.conversations[4]["labels"] = ["vip"]
    client = api(fake)
    client.open_conversation(4)
    client.assign(4, 5)
    client.add_labels(4, ("handoff", "vip"))
    assert fake.writes == [
        ("status", 4, "open"),
        ("assign", 4, 5),
        ("labels", 4, ["vip", "handoff"]),
    ]


def test_get_conversation_reads_its_facts() -> None:
    fake = FakeChatwoot()
    fake.conversation(4, inbox=2, contact=77)
    facts = api(fake).get_conversation(4)
    assert (facts.id, facts.account_id, facts.inbox_id, facts.status, facts.contact_id) == (
        4,
        ACCOUNT,
        2,
        "pending",
        77,
    )


def test_find_message_returns_the_api_view_or_none() -> None:
    fake = FakeChatwoot()
    fake.conversation(4)
    fake.message(10, 4, "Hi there")
    fake.message(11, 4, "From staff", message_type=1, sender_type="User")
    client = api(fake)
    found = client.find_message(4, 11)
    assert found is not None
    assert (found.message_type, found.sender_type, found.private, found.content) == (
        "outgoing",
        "User",
        False,
        "From staff",
    )
    assert "From staff" not in repr(found)
    assert client.find_message(4, 12) is None


def test_profile_and_inboxes_are_asked_with_the_agents_own_token() -> None:
    fake = FakeChatwoot()
    client = api(fake)
    profile = client.profile(AGENT_TOKEN)
    assert (profile.id, profile.roles) == (5, {ACCOUNT: "agent"})
    assert "Example Agent" not in repr(profile)
    assert client.inbox_ids(AGENT_TOKEN) == frozenset({1})


def test_listing_deleting_and_contacts() -> None:
    fake = FakeChatwoot()
    for n in range(30):
        fake.conversation(n + 1, contact=100 + n % 2)
    admin = api(fake, ADMIN_TOKEN)
    first, second = admin.list_conversations(1), admin.list_conversations(2)
    assert (len(first), len(second), admin.list_conversations(3)) == (25, 5, ())
    assert first[0].contact_id == 100
    assert first[0].last_activity_at.year == 2023
    admin.delete_conversation(1)
    assert admin.contact_conversation_count(100) == 14
    admin.delete_contact(100)
    assert 100 not in fake.contacts


def test_deleting_needs_an_administrator() -> None:
    fake = FakeChatwoot()
    fake.conversation(1)
    with pytest.raises(ChatwootError) as caught:
        api(fake, AGENT_TOKEN).delete_conversation(1)
    assert caught.value.status == 401
    with pytest.raises(ChatwootError):
        api(fake, AGENT_TOKEN).delete_contact(50)


@pytest.mark.parametrize(
    ("status", "body"),
    [(404, {"error": "Resource could not be found"}), (500, {}), (422, {"error": "message text"})],
)
def test_errors_name_the_operation_and_status_never_the_body(status: int, body: object) -> None:
    _, client = recording(status, body)
    with pytest.raises(ChatwootError) as caught:
        client.send_message(4, "Hello")
    assert str(caught.value) == f"chatwoot send message failed (HTTP {status})"
    assert "message text" not in str(caught.value)


def test_no_connection_is_status_zero() -> None:
    fake = FakeChatwoot(down=True)
    with pytest.raises(ChatwootError) as caught:
        api(fake).open_conversation(1)
    assert caught.value.status == 0


@pytest.mark.parametrize(
    ("call", "body"),
    [
        (lambda c: c.get_conversation(4), {"inbox_id": "x"}),
        (lambda c: c.get_conversation(4), {"status": "archived"}),
        (lambda c: c.find_message(4, 1), {"meta": {}}),
        (lambda c: c.profile("t"), {"name": "no id"}),
        (lambda c: c.inbox_ids("t"), {}),
        (lambda c: c.list_conversations(1), {}),
    ],
)
def test_a_response_of_the_wrong_shape_is_an_error(call: object, body: object) -> None:
    _, client = recording(200, body)
    with pytest.raises(ChatwootError):
        call(client)  # type: ignore[operator]


def test_a_listing_without_a_payload_is_empty_and_odd_rows_are_skipped() -> None:
    _, client = recording(200, {"data": {"meta": {}}})
    assert client.list_conversations(1) == ()
    _, client = recording(
        200, {"data": {"payload": [{"id": 3}, {"id": 4, "created_at": 1700000000}]}}
    )
    (only,) = client.list_conversations(1)
    assert (only.id, only.contact_id) == (4, None)


def test_contact_conversations_without_a_payload_is_zero() -> None:
    _, client = recording(200, {})
    assert client.contact_conversation_count(3) == 0


def test_repr_holds_no_token() -> None:
    assert BOT_TOKEN not in repr(api(FakeChatwoot()))
