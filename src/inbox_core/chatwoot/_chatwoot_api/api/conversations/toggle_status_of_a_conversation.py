from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.data import Data
from ...models.toggle_status_of_a_conversation_body import ToggleStatusOfAConversationBody
from ...models.toggle_status_of_a_conversation_response_200 import (
    ToggleStatusOfAConversationResponse200,
)
from typing import cast


def _get_kwargs(
    account_id: int,
    conversation_id: int,
    *,
    body: ToggleStatusOfAConversationBody,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/accounts/{account_id}/conversations/{conversation_id}/toggle_status".format(
            account_id=quote(str(account_id), safe=""),
            conversation_id=quote(str(conversation_id), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Data | ToggleStatusOfAConversationResponse200 | None:
    if response.status_code == 200:
        response_200 = ToggleStatusOfAConversationResponse200.from_dict(response.json())

        return response_200

    if response.status_code == 401:
        response_401 = Data.from_dict(response.json())

        return response_401

    if response.status_code == 404:
        response_404 = Data.from_dict(response.json())

        return response_404

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[Data | ToggleStatusOfAConversationResponse200]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    account_id: int,
    conversation_id: int,
    *,
    client: AuthenticatedClient,
    body: ToggleStatusOfAConversationBody,
) -> Response[Data | ToggleStatusOfAConversationResponse200]:
    """Toggle Status

     Toggle the status of a conversation. Pass `status` to explicitly set the
    conversation state. Use `snoozed` along with `snoozed_until` to snooze a
    conversation until a specific time. If `snoozed_until` is omitted, the
    conversation is snoozed until the next reply from the contact. Regardless
    of the value provided, snoozed conversations always reopen on the next
    reply from the contact.

    Args:
        account_id (int):
        conversation_id (int):
        body (ToggleStatusOfAConversationBody):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Data | ToggleStatusOfAConversationResponse200]
    """

    kwargs = _get_kwargs(
        account_id=account_id,
        conversation_id=conversation_id,
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    account_id: int,
    conversation_id: int,
    *,
    client: AuthenticatedClient,
    body: ToggleStatusOfAConversationBody,
) -> Data | ToggleStatusOfAConversationResponse200 | None:
    """Toggle Status

     Toggle the status of a conversation. Pass `status` to explicitly set the
    conversation state. Use `snoozed` along with `snoozed_until` to snooze a
    conversation until a specific time. If `snoozed_until` is omitted, the
    conversation is snoozed until the next reply from the contact. Regardless
    of the value provided, snoozed conversations always reopen on the next
    reply from the contact.

    Args:
        account_id (int):
        conversation_id (int):
        body (ToggleStatusOfAConversationBody):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Data | ToggleStatusOfAConversationResponse200
    """

    return sync_detailed(
        account_id=account_id,
        conversation_id=conversation_id,
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    account_id: int,
    conversation_id: int,
    *,
    client: AuthenticatedClient,
    body: ToggleStatusOfAConversationBody,
) -> Response[Data | ToggleStatusOfAConversationResponse200]:
    """Toggle Status

     Toggle the status of a conversation. Pass `status` to explicitly set the
    conversation state. Use `snoozed` along with `snoozed_until` to snooze a
    conversation until a specific time. If `snoozed_until` is omitted, the
    conversation is snoozed until the next reply from the contact. Regardless
    of the value provided, snoozed conversations always reopen on the next
    reply from the contact.

    Args:
        account_id (int):
        conversation_id (int):
        body (ToggleStatusOfAConversationBody):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Data | ToggleStatusOfAConversationResponse200]
    """

    kwargs = _get_kwargs(
        account_id=account_id,
        conversation_id=conversation_id,
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    account_id: int,
    conversation_id: int,
    *,
    client: AuthenticatedClient,
    body: ToggleStatusOfAConversationBody,
) -> Data | ToggleStatusOfAConversationResponse200 | None:
    """Toggle Status

     Toggle the status of a conversation. Pass `status` to explicitly set the
    conversation state. Use `snoozed` along with `snoozed_until` to snooze a
    conversation until a specific time. If `snoozed_until` is omitted, the
    conversation is snoozed until the next reply from the contact. Regardless
    of the value provided, snoozed conversations always reopen on the next
    reply from the contact.

    Args:
        account_id (int):
        conversation_id (int):
        body (ToggleStatusOfAConversationBody):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Data | ToggleStatusOfAConversationResponse200
    """

    return (
        await asyncio_detailed(
            account_id=account_id,
            conversation_id=conversation_id,
            client=client,
            body=body,
        )
    ).parsed
