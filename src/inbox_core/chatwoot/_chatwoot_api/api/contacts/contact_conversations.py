from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.contact_conversations_response import ContactConversationsResponse
from ...models.data import Data
from typing import cast


def _get_kwargs(
    account_id: int,
    id: float,
) -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v1/accounts/{account_id}/contacts/{id}/conversations".format(
            account_id=quote(str(account_id), safe=""),
            id=quote(str(id), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ContactConversationsResponse | Data | None:
    if response.status_code == 200:
        response_200 = ContactConversationsResponse.from_dict(response.json())

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
) -> Response[ContactConversationsResponse | Data]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    account_id: int,
    id: float,
    *,
    client: AuthenticatedClient,
) -> Response[ContactConversationsResponse | Data]:
    """Contact Conversations

     Get conversations associated with that contact

    Args:
        account_id (int):
        id (float):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ContactConversationsResponse | Data]
    """

    kwargs = _get_kwargs(
        account_id=account_id,
        id=id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    account_id: int,
    id: float,
    *,
    client: AuthenticatedClient,
) -> ContactConversationsResponse | Data | None:
    """Contact Conversations

     Get conversations associated with that contact

    Args:
        account_id (int):
        id (float):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ContactConversationsResponse | Data
    """

    return sync_detailed(
        account_id=account_id,
        id=id,
        client=client,
    ).parsed


async def asyncio_detailed(
    account_id: int,
    id: float,
    *,
    client: AuthenticatedClient,
) -> Response[ContactConversationsResponse | Data]:
    """Contact Conversations

     Get conversations associated with that contact

    Args:
        account_id (int):
        id (float):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ContactConversationsResponse | Data]
    """

    kwargs = _get_kwargs(
        account_id=account_id,
        id=id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    account_id: int,
    id: float,
    *,
    client: AuthenticatedClient,
) -> ContactConversationsResponse | Data | None:
    """Contact Conversations

     Get conversations associated with that contact

    Args:
        account_id (int):
        id (float):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ContactConversationsResponse | Data
    """

    return (
        await asyncio_detailed(
            account_id=account_id,
            id=id,
            client=client,
        )
    ).parsed
