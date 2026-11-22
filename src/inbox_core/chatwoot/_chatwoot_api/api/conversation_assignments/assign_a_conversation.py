from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.assign_a_conversation_body import AssignAConversationBody
from ...models.data import Data
from ...models.user import User
from typing import cast


def _get_kwargs(
    account_id: int,
    conversation_id: int,
    *,
    body: AssignAConversationBody,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/accounts/{account_id}/conversations/{conversation_id}/assignments".format(
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
) -> Data | User | None:
    if response.status_code == 200:
        response_200 = User.from_dict(response.json())

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
) -> Response[Data | User]:
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
    body: AssignAConversationBody,
) -> Response[Data | User]:
    """Assign Conversation

     Assign a conversation to an agent or a team

    Args:
        account_id (int):
        conversation_id (int):
        body (AssignAConversationBody):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Data | User]
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
    body: AssignAConversationBody,
) -> Data | User | None:
    """Assign Conversation

     Assign a conversation to an agent or a team

    Args:
        account_id (int):
        conversation_id (int):
        body (AssignAConversationBody):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Data | User
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
    body: AssignAConversationBody,
) -> Response[Data | User]:
    """Assign Conversation

     Assign a conversation to an agent or a team

    Args:
        account_id (int):
        conversation_id (int):
        body (AssignAConversationBody):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Data | User]
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
    body: AssignAConversationBody,
) -> Data | User | None:
    """Assign Conversation

     Assign a conversation to an agent or a team

    Args:
        account_id (int):
        conversation_id (int):
        body (AssignAConversationBody):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Data | User
    """

    return (
        await asyncio_detailed(
            account_id=account_id,
            conversation_id=conversation_id,
            client=client,
            body=body,
        )
    ).parsed
