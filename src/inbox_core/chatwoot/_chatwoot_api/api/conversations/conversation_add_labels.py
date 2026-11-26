from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.conversation_add_labels_body import ConversationAddLabelsBody
from ...models.conversation_labels import ConversationLabels
from ...models.data import Data
from typing import cast


def _get_kwargs(
    account_id: int,
    conversation_id: int,
    *,
    body: ConversationAddLabelsBody,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/accounts/{account_id}/conversations/{conversation_id}/labels".format(
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
) -> ConversationLabels | Data | None:
    if response.status_code == 200:
        response_200 = ConversationLabels.from_dict(response.json())

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
) -> Response[ConversationLabels | Data]:
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
    body: ConversationAddLabelsBody,
) -> Response[ConversationLabels | Data]:
    """Add Labels

     Add labels to a conversation. Note that this API would overwrite the existing list of labels
    associated to the conversation.

    Args:
        account_id (int):
        conversation_id (int):
        body (ConversationAddLabelsBody):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ConversationLabels | Data]
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
    body: ConversationAddLabelsBody,
) -> ConversationLabels | Data | None:
    """Add Labels

     Add labels to a conversation. Note that this API would overwrite the existing list of labels
    associated to the conversation.

    Args:
        account_id (int):
        conversation_id (int):
        body (ConversationAddLabelsBody):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ConversationLabels | Data
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
    body: ConversationAddLabelsBody,
) -> Response[ConversationLabels | Data]:
    """Add Labels

     Add labels to a conversation. Note that this API would overwrite the existing list of labels
    associated to the conversation.

    Args:
        account_id (int):
        conversation_id (int):
        body (ConversationAddLabelsBody):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ConversationLabels | Data]
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
    body: ConversationAddLabelsBody,
) -> ConversationLabels | Data | None:
    """Add Labels

     Add labels to a conversation. Note that this API would overwrite the existing list of labels
    associated to the conversation.

    Args:
        account_id (int):
        conversation_id (int):
        body (ConversationAddLabelsBody):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ConversationLabels | Data
    """

    return (
        await asyncio_detailed(
            account_id=account_id,
            conversation_id=conversation_id,
            client=client,
            body=body,
        )
    ).parsed
