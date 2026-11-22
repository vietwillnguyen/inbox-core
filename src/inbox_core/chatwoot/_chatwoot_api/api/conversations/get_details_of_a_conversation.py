from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.conversation_show import ConversationShow
from ...models.data import Data
from typing import cast


def _get_kwargs(
    account_id: int,
    conversation_id: int,
) -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v1/accounts/{account_id}/conversations/{conversation_id}".format(
            account_id=quote(str(account_id), safe=""),
            conversation_id=quote(str(conversation_id), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ConversationShow | Data | None:
    if response.status_code == 200:
        response_200 = ConversationShow.from_dict(response.json())

        return response_200

    if response.status_code == 403:
        response_403 = Data.from_dict(response.json())

        return response_403

    if response.status_code == 404:
        response_404 = Data.from_dict(response.json())

        return response_404

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[ConversationShow | Data]:
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
) -> Response[ConversationShow | Data]:
    """Conversation Details

     Get all details regarding a conversation with all messages in the conversation

    Args:
        account_id (int):
        conversation_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ConversationShow | Data]
    """

    kwargs = _get_kwargs(
        account_id=account_id,
        conversation_id=conversation_id,
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
) -> ConversationShow | Data | None:
    """Conversation Details

     Get all details regarding a conversation with all messages in the conversation

    Args:
        account_id (int):
        conversation_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ConversationShow | Data
    """

    return sync_detailed(
        account_id=account_id,
        conversation_id=conversation_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    account_id: int,
    conversation_id: int,
    *,
    client: AuthenticatedClient,
) -> Response[ConversationShow | Data]:
    """Conversation Details

     Get all details regarding a conversation with all messages in the conversation

    Args:
        account_id (int):
        conversation_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ConversationShow | Data]
    """

    kwargs = _get_kwargs(
        account_id=account_id,
        conversation_id=conversation_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    account_id: int,
    conversation_id: int,
    *,
    client: AuthenticatedClient,
) -> ConversationShow | Data | None:
    """Conversation Details

     Get all details regarding a conversation with all messages in the conversation

    Args:
        account_id (int):
        conversation_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ConversationShow | Data
    """

    return (
        await asyncio_detailed(
            account_id=account_id,
            conversation_id=conversation_id,
            client=client,
        )
    ).parsed
