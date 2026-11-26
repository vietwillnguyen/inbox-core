from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.conversation_list import ConversationList
from ...models.conversation_list_assignee_type import check_conversation_list_assignee_type
from ...models.conversation_list_assignee_type import ConversationListAssigneeType
from ...models.conversation_list_status import check_conversation_list_status
from ...models.conversation_list_status import ConversationListStatus
from ...models.data import Data
from ...types import UNSET, Unset
from typing import cast


def _get_kwargs(
    account_id: int,
    *,
    assignee_type: ConversationListAssigneeType | Unset = "all",
    status: ConversationListStatus | Unset = "open",
    q: str | Unset = UNSET,
    inbox_id: int | Unset = UNSET,
    team_id: int | Unset = UNSET,
    labels: list[str] | Unset = UNSET,
    page: int | Unset = 1,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_assignee_type: str | Unset = UNSET
    if not isinstance(assignee_type, Unset):
        json_assignee_type = assignee_type

    params["assignee_type"] = json_assignee_type

    json_status: str | Unset = UNSET
    if not isinstance(status, Unset):
        json_status = status

    params["status"] = json_status

    params["q"] = q

    params["inbox_id"] = inbox_id

    params["team_id"] = team_id

    json_labels: list[str] | Unset = UNSET
    if not isinstance(labels, Unset):
        json_labels = labels

    params["labels"] = json_labels

    params["page"] = page

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v1/accounts/{account_id}/conversations".format(
            account_id=quote(str(account_id), safe=""),
        ),
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ConversationList | Data | None:
    if response.status_code == 200:
        response_200 = ConversationList.from_dict(response.json())

        return response_200

    if response.status_code == 400:
        response_400 = Data.from_dict(response.json())

        return response_400

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[ConversationList | Data]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    account_id: int,
    *,
    client: AuthenticatedClient,
    assignee_type: ConversationListAssigneeType | Unset = "all",
    status: ConversationListStatus | Unset = "open",
    q: str | Unset = UNSET,
    inbox_id: int | Unset = UNSET,
    team_id: int | Unset = UNSET,
    labels: list[str] | Unset = UNSET,
    page: int | Unset = 1,
) -> Response[ConversationList | Data]:
    """Conversations List

     List all the conversations with pagination

    Args:
        account_id (int):
        assignee_type (ConversationListAssigneeType | Unset):  Default: 'all'.
        status (ConversationListStatus | Unset):  Default: 'open'.
        q (str | Unset):
        inbox_id (int | Unset):
        team_id (int | Unset):
        labels (list[str] | Unset):
        page (int | Unset):  Default: 1.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ConversationList | Data]
    """

    kwargs = _get_kwargs(
        account_id=account_id,
        assignee_type=assignee_type,
        status=status,
        q=q,
        inbox_id=inbox_id,
        team_id=team_id,
        labels=labels,
        page=page,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    account_id: int,
    *,
    client: AuthenticatedClient,
    assignee_type: ConversationListAssigneeType | Unset = "all",
    status: ConversationListStatus | Unset = "open",
    q: str | Unset = UNSET,
    inbox_id: int | Unset = UNSET,
    team_id: int | Unset = UNSET,
    labels: list[str] | Unset = UNSET,
    page: int | Unset = 1,
) -> ConversationList | Data | None:
    """Conversations List

     List all the conversations with pagination

    Args:
        account_id (int):
        assignee_type (ConversationListAssigneeType | Unset):  Default: 'all'.
        status (ConversationListStatus | Unset):  Default: 'open'.
        q (str | Unset):
        inbox_id (int | Unset):
        team_id (int | Unset):
        labels (list[str] | Unset):
        page (int | Unset):  Default: 1.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ConversationList | Data
    """

    return sync_detailed(
        account_id=account_id,
        client=client,
        assignee_type=assignee_type,
        status=status,
        q=q,
        inbox_id=inbox_id,
        team_id=team_id,
        labels=labels,
        page=page,
    ).parsed


async def asyncio_detailed(
    account_id: int,
    *,
    client: AuthenticatedClient,
    assignee_type: ConversationListAssigneeType | Unset = "all",
    status: ConversationListStatus | Unset = "open",
    q: str | Unset = UNSET,
    inbox_id: int | Unset = UNSET,
    team_id: int | Unset = UNSET,
    labels: list[str] | Unset = UNSET,
    page: int | Unset = 1,
) -> Response[ConversationList | Data]:
    """Conversations List

     List all the conversations with pagination

    Args:
        account_id (int):
        assignee_type (ConversationListAssigneeType | Unset):  Default: 'all'.
        status (ConversationListStatus | Unset):  Default: 'open'.
        q (str | Unset):
        inbox_id (int | Unset):
        team_id (int | Unset):
        labels (list[str] | Unset):
        page (int | Unset):  Default: 1.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ConversationList | Data]
    """

    kwargs = _get_kwargs(
        account_id=account_id,
        assignee_type=assignee_type,
        status=status,
        q=q,
        inbox_id=inbox_id,
        team_id=team_id,
        labels=labels,
        page=page,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    account_id: int,
    *,
    client: AuthenticatedClient,
    assignee_type: ConversationListAssigneeType | Unset = "all",
    status: ConversationListStatus | Unset = "open",
    q: str | Unset = UNSET,
    inbox_id: int | Unset = UNSET,
    team_id: int | Unset = UNSET,
    labels: list[str] | Unset = UNSET,
    page: int | Unset = 1,
) -> ConversationList | Data | None:
    """Conversations List

     List all the conversations with pagination

    Args:
        account_id (int):
        assignee_type (ConversationListAssigneeType | Unset):  Default: 'all'.
        status (ConversationListStatus | Unset):  Default: 'open'.
        q (str | Unset):
        inbox_id (int | Unset):
        team_id (int | Unset):
        labels (list[str] | Unset):
        page (int | Unset):  Default: 1.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ConversationList | Data
    """

    return (
        await asyncio_detailed(
            account_id=account_id,
            client=client,
            assignee_type=assignee_type,
            status=status,
            q=q,
            inbox_id=inbox_id,
            team_id=team_id,
            labels=labels,
            page=page,
        )
    ).parsed
