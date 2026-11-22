from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.data import Data
from typing import cast


def _get_kwargs(
    account_id: int,
    id: float,
) -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "delete",
        "url": "/api/v1/accounts/{account_id}/contacts/{id}".format(
            account_id=quote(str(account_id), safe=""),
            id=quote(str(id), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | Data | None:
    if response.status_code == 200:
        response_200 = cast(Any, None)
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
) -> Response[Any | Data]:
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
) -> Response[Any | Data]:
    """Delete Contact

     Delete a contact belonging to the account using ID

    Args:
        account_id (int):
        id (float):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | Data]
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
) -> Any | Data | None:
    """Delete Contact

     Delete a contact belonging to the account using ID

    Args:
        account_id (int):
        id (float):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | Data
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
) -> Response[Any | Data]:
    """Delete Contact

     Delete a contact belonging to the account using ID

    Args:
        account_id (int):
        id (float):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | Data]
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
) -> Any | Data | None:
    """Delete Contact

     Delete a contact belonging to the account using ID

    Args:
        account_id (int):
        id (float):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | Data
    """

    return (
        await asyncio_detailed(
            account_id=account_id,
            id=id,
            client=client,
        )
    ).parsed
