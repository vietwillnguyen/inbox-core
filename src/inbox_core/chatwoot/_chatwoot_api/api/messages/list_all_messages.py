from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.data import Data
from ...models.list_all_messages_response_200 import ListAllMessagesResponse200
from ...types import UNSET, Unset
from typing import cast


def _get_kwargs(
    account_id: int,
    conversation_id: int,
    *,
    after: int | Unset = UNSET,
    before: int | Unset = UNSET,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["after"] = after

    params["before"] = before

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v1/accounts/{account_id}/conversations/{conversation_id}/messages".format(
            account_id=quote(str(account_id), safe=""),
            conversation_id=quote(str(conversation_id), safe=""),
        ),
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Data | ListAllMessagesResponse200 | None:
    if response.status_code == 200:
        response_200 = ListAllMessagesResponse200.from_dict(response.json())

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
) -> Response[Data | ListAllMessagesResponse200]:
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
    after: int | Unset = UNSET,
    before: int | Unset = UNSET,
) -> Response[Data | ListAllMessagesResponse200]:
    """Get messages

     List all messages of a conversation

    Args:
        account_id (int):
        conversation_id (int):
        after (int | Unset):
        before (int | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Data | ListAllMessagesResponse200]
    """

    kwargs = _get_kwargs(
        account_id=account_id,
        conversation_id=conversation_id,
        after=after,
        before=before,
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
    after: int | Unset = UNSET,
    before: int | Unset = UNSET,
) -> Data | ListAllMessagesResponse200 | None:
    """Get messages

     List all messages of a conversation

    Args:
        account_id (int):
        conversation_id (int):
        after (int | Unset):
        before (int | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Data | ListAllMessagesResponse200
    """

    return sync_detailed(
        account_id=account_id,
        conversation_id=conversation_id,
        client=client,
        after=after,
        before=before,
    ).parsed


async def asyncio_detailed(
    account_id: int,
    conversation_id: int,
    *,
    client: AuthenticatedClient,
    after: int | Unset = UNSET,
    before: int | Unset = UNSET,
) -> Response[Data | ListAllMessagesResponse200]:
    """Get messages

     List all messages of a conversation

    Args:
        account_id (int):
        conversation_id (int):
        after (int | Unset):
        before (int | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Data | ListAllMessagesResponse200]
    """

    kwargs = _get_kwargs(
        account_id=account_id,
        conversation_id=conversation_id,
        after=after,
        before=before,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    account_id: int,
    conversation_id: int,
    *,
    client: AuthenticatedClient,
    after: int | Unset = UNSET,
    before: int | Unset = UNSET,
) -> Data | ListAllMessagesResponse200 | None:
    """Get messages

     List all messages of a conversation

    Args:
        account_id (int):
        conversation_id (int):
        after (int | Unset):
        before (int | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Data | ListAllMessagesResponse200
    """

    return (
        await asyncio_detailed(
            account_id=account_id,
            conversation_id=conversation_id,
            client=client,
            after=after,
            before=before,
        )
    ).parsed
