"""What the bundle stores about a visitor, and what it does not serve to the internet."""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx

from tests.demo_e2e.bundle import Owner, Visitor, rails, until


def test_a_visitor_contact_holds_no_address_name_or_email(
    visitor: Callable[[], Visitor], owner: Owner
) -> None:
    person = visitor()
    person.say("Where is the shop?")
    until(person.replies)
    sender = owner.conversation(person.conversation_id or 0)["meta"]["sender"]
    stored = json.loads(
        rails(
            f"c = Contact.find({int(sender['id'])}); "
            "puts({email: c.email, phone: c.phone_number, attrs: c.additional_attributes}.to_json)"
        )
        .strip()
        .splitlines()[-1]
    )
    assert stored["email"] in (None, "")
    assert stored["phone"] in (None, "")
    assert not {"created_at_ip", "updated_at_ip", "city", "country"} & set(stored["attrs"] or {})


def test_the_widget_offers_no_uploads_and_uploads_are_refused(bundle: dict[str, str]) -> None:
    config = httpx.post(
        f"{bundle['CHAT_ORIGIN']}/api/v1/widget/config",
        params={"website_token": bundle["CHATWOOT_WEBSITE_TOKEN"]},
    ).json()
    assert "attachments" not in config["website_channel_config"]["enabled_features"]
    upload = httpx.post(
        f"{bundle['CHAT_ORIGIN']}/api/v1/widget/messages",
        params={"website_token": bundle["CHATWOOT_WEBSITE_TOKEN"]},
        files={"message[attachments][]": ("x.txt", b"hello", "text/plain")},
    )
    # Refused at the proxy and answered by the page server, which never reaches
    # Chatwoot: 404 for a GET, 501 for any other method.
    assert upload.status_code == 501


def test_only_the_widget_page_and_the_draft_tab_are_public(bundle: dict[str, str]) -> None:
    page = httpx.get(bundle["PAGE_ORIGIN"])
    assert page.status_code == 200
    assert "This is a demo." in page.text
    assert bundle["CHATWOOT_WEBSITE_TOKEN"] in page.text
    tab = httpx.get(f"{bundle['BOT_ORIGIN']}/tab")
    assert tab.status_code == 200
    assert f"frame-ancestors {bundle['CHAT_ORIGIN']}" in tab.headers["content-security-policy"]
    for path in ("/healthz", "/metrics", "/chatwoot/webhook/x", "/docs", "/openapi.json"):
        assert httpx.get(f"{bundle['BOT_ORIGIN']}{path}").status_code == 404, path
    for path in ("/super_admin", "/super_admin/sign_in", "/monitoring/sidekiq"):
        assert httpx.get(f"{bundle['CHAT_ORIGIN']}{path}").status_code == 404, path
    assert httpx.get(f"{bundle['PAGE_ORIGIN']}/compose.yaml").status_code == 404


def test_the_widget_may_be_framed_only_by_the_demo_page(bundle: dict[str, str]) -> None:
    widget = httpx.get(
        f"{bundle['CHAT_ORIGIN']}/widget",
        params={"website_token": bundle["CHATWOOT_WEBSITE_TOKEN"]},
    )
    assert widget.status_code == 200
    host = bundle["PAGE_ORIGIN"].split("://", 1)[1]
    assert f"frame-ancestors {host}" in widget.headers["content-security-policy"]


def test_sign_up_is_closed(bundle: dict[str, str]) -> None:
    response = httpx.post(
        f"{bundle['CHAT_ORIGIN']}/api/v1/accounts",
        json={"account_name": "x", "email": "someone@example.com", "password": "Aa1!aaaaaaaa"},
    )
    assert response.status_code in (401, 403, 404, 422)
