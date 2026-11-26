from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.conversation_message_create_payload import ConversationMessageCreatePayload
from ...models.create_a_new_message_in_a_conversation_response_200 import (
    CreateANewMessageInAConversationResponse200,
)
from ...models.data import Data
from typing import cast


def _get_kwargs(
    account_id: int,
    conversation_id: int,
    *,
    body: ConversationMessageCreatePayload,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/accounts/{account_id}/conversations/{conversation_id}/messages".format(
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
) -> CreateANewMessageInAConversationResponse200 | Data | None:
    if response.status_code == 200:
        response_200 = CreateANewMessageInAConversationResponse200.from_dict(response.json())

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
) -> Response[CreateANewMessageInAConversationResponse200 | Data]:
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
    body: ConversationMessageCreatePayload,
) -> Response[CreateANewMessageInAConversationResponse200 | Data]:
    """ Create New Message

     Create a new message in the conversation.

    Use `application/json` for text messages and `multipart/form-data` when the
    message includes file attachments.

    ### Multipart attachment request

    Send files with the `attachments[]` form field. `curl -F` sets the
    `multipart/form-data` content type and boundary automatically.

    ```bash
    curl -X POST
    "https://app.chatwoot.com/api/v1/accounts/{account_id}/conversations/{conversation_id}/messages" \\
      -H "Authorization: Bearer <your-api-token>" \\
      -F "content=Here is the screenshot" \\
      -F "message_type=outgoing" \\
      -F "private=false" \\
      -F "attachments[]=@/path/to/screenshot.png"
    ```

    ## WhatsApp Template Messages

    For WhatsApp channels, you can send structured template messages using the `template_params` field.
    Templates must be pre-approved in WhatsApp Business Manager.

    By default, `content` is treated as the already-rendered transcript text for
    compatibility with existing API and mobile clients. To submit the original
    template body instead, set `template_params.content_mode` to `raw_template`;
    Chatwoot will substitute `processed_params.body` before saving the transcript.

    ### Example Templates

    **Text with Image Header:**
    ```json
    {
      "content": "Hi your order 121212 is confirmed. Please wait for further updates",
      "template_params": {
        "name": "order_confirmation",
        "category": "MARKETING",
        "language": "en",
        "processed_params": {
          "body": {
            "1": "121212"
          },
          "header": {
            "media_url": "https://picsum.photos/200/300",
            "media_type": "image"
          }
        }
      }
    }
    ```

    **Text with Copy Code Button:**
    ```json
    {
      "content": "Special offer! Get 30% off your next purchase. Use the code below",
      "template_params": {
        "name": "discount_coupon",
        "category": "MARKETING",
        "language": "en",
        "processed_params": {
          "body": {
            "discount_percentage": "30"
          },
          "buttons": [{
            "type": "copy_code",
            "parameter": "SAVE20"
          }]
        }
      }
    }
    ```

    Args:
        account_id (int):
        conversation_id (int):
        body (ConversationMessageCreatePayload):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CreateANewMessageInAConversationResponse200 | Data]
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
    body: ConversationMessageCreatePayload,
) -> CreateANewMessageInAConversationResponse200 | Data | None:
    """ Create New Message

     Create a new message in the conversation.

    Use `application/json` for text messages and `multipart/form-data` when the
    message includes file attachments.

    ### Multipart attachment request

    Send files with the `attachments[]` form field. `curl -F` sets the
    `multipart/form-data` content type and boundary automatically.

    ```bash
    curl -X POST
    "https://app.chatwoot.com/api/v1/accounts/{account_id}/conversations/{conversation_id}/messages" \\
      -H "Authorization: Bearer <your-api-token>" \\
      -F "content=Here is the screenshot" \\
      -F "message_type=outgoing" \\
      -F "private=false" \\
      -F "attachments[]=@/path/to/screenshot.png"
    ```

    ## WhatsApp Template Messages

    For WhatsApp channels, you can send structured template messages using the `template_params` field.
    Templates must be pre-approved in WhatsApp Business Manager.

    By default, `content` is treated as the already-rendered transcript text for
    compatibility with existing API and mobile clients. To submit the original
    template body instead, set `template_params.content_mode` to `raw_template`;
    Chatwoot will substitute `processed_params.body` before saving the transcript.

    ### Example Templates

    **Text with Image Header:**
    ```json
    {
      "content": "Hi your order 121212 is confirmed. Please wait for further updates",
      "template_params": {
        "name": "order_confirmation",
        "category": "MARKETING",
        "language": "en",
        "processed_params": {
          "body": {
            "1": "121212"
          },
          "header": {
            "media_url": "https://picsum.photos/200/300",
            "media_type": "image"
          }
        }
      }
    }
    ```

    **Text with Copy Code Button:**
    ```json
    {
      "content": "Special offer! Get 30% off your next purchase. Use the code below",
      "template_params": {
        "name": "discount_coupon",
        "category": "MARKETING",
        "language": "en",
        "processed_params": {
          "body": {
            "discount_percentage": "30"
          },
          "buttons": [{
            "type": "copy_code",
            "parameter": "SAVE20"
          }]
        }
      }
    }
    ```

    Args:
        account_id (int):
        conversation_id (int):
        body (ConversationMessageCreatePayload):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CreateANewMessageInAConversationResponse200 | Data
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
    body: ConversationMessageCreatePayload,
) -> Response[CreateANewMessageInAConversationResponse200 | Data]:
    """ Create New Message

     Create a new message in the conversation.

    Use `application/json` for text messages and `multipart/form-data` when the
    message includes file attachments.

    ### Multipart attachment request

    Send files with the `attachments[]` form field. `curl -F` sets the
    `multipart/form-data` content type and boundary automatically.

    ```bash
    curl -X POST
    "https://app.chatwoot.com/api/v1/accounts/{account_id}/conversations/{conversation_id}/messages" \\
      -H "Authorization: Bearer <your-api-token>" \\
      -F "content=Here is the screenshot" \\
      -F "message_type=outgoing" \\
      -F "private=false" \\
      -F "attachments[]=@/path/to/screenshot.png"
    ```

    ## WhatsApp Template Messages

    For WhatsApp channels, you can send structured template messages using the `template_params` field.
    Templates must be pre-approved in WhatsApp Business Manager.

    By default, `content` is treated as the already-rendered transcript text for
    compatibility with existing API and mobile clients. To submit the original
    template body instead, set `template_params.content_mode` to `raw_template`;
    Chatwoot will substitute `processed_params.body` before saving the transcript.

    ### Example Templates

    **Text with Image Header:**
    ```json
    {
      "content": "Hi your order 121212 is confirmed. Please wait for further updates",
      "template_params": {
        "name": "order_confirmation",
        "category": "MARKETING",
        "language": "en",
        "processed_params": {
          "body": {
            "1": "121212"
          },
          "header": {
            "media_url": "https://picsum.photos/200/300",
            "media_type": "image"
          }
        }
      }
    }
    ```

    **Text with Copy Code Button:**
    ```json
    {
      "content": "Special offer! Get 30% off your next purchase. Use the code below",
      "template_params": {
        "name": "discount_coupon",
        "category": "MARKETING",
        "language": "en",
        "processed_params": {
          "body": {
            "discount_percentage": "30"
          },
          "buttons": [{
            "type": "copy_code",
            "parameter": "SAVE20"
          }]
        }
      }
    }
    ```

    Args:
        account_id (int):
        conversation_id (int):
        body (ConversationMessageCreatePayload):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CreateANewMessageInAConversationResponse200 | Data]
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
    body: ConversationMessageCreatePayload,
) -> CreateANewMessageInAConversationResponse200 | Data | None:
    """ Create New Message

     Create a new message in the conversation.

    Use `application/json` for text messages and `multipart/form-data` when the
    message includes file attachments.

    ### Multipart attachment request

    Send files with the `attachments[]` form field. `curl -F` sets the
    `multipart/form-data` content type and boundary automatically.

    ```bash
    curl -X POST
    "https://app.chatwoot.com/api/v1/accounts/{account_id}/conversations/{conversation_id}/messages" \\
      -H "Authorization: Bearer <your-api-token>" \\
      -F "content=Here is the screenshot" \\
      -F "message_type=outgoing" \\
      -F "private=false" \\
      -F "attachments[]=@/path/to/screenshot.png"
    ```

    ## WhatsApp Template Messages

    For WhatsApp channels, you can send structured template messages using the `template_params` field.
    Templates must be pre-approved in WhatsApp Business Manager.

    By default, `content` is treated as the already-rendered transcript text for
    compatibility with existing API and mobile clients. To submit the original
    template body instead, set `template_params.content_mode` to `raw_template`;
    Chatwoot will substitute `processed_params.body` before saving the transcript.

    ### Example Templates

    **Text with Image Header:**
    ```json
    {
      "content": "Hi your order 121212 is confirmed. Please wait for further updates",
      "template_params": {
        "name": "order_confirmation",
        "category": "MARKETING",
        "language": "en",
        "processed_params": {
          "body": {
            "1": "121212"
          },
          "header": {
            "media_url": "https://picsum.photos/200/300",
            "media_type": "image"
          }
        }
      }
    }
    ```

    **Text with Copy Code Button:**
    ```json
    {
      "content": "Special offer! Get 30% off your next purchase. Use the code below",
      "template_params": {
        "name": "discount_coupon",
        "category": "MARKETING",
        "language": "en",
        "processed_params": {
          "body": {
            "discount_percentage": "30"
          },
          "buttons": [{
            "type": "copy_code",
            "parameter": "SAVE20"
          }]
        }
      }
    }
    ```

    Args:
        account_id (int):
        conversation_id (int):
        body (ConversationMessageCreatePayload):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CreateANewMessageInAConversationResponse200 | Data
     """

    return (
        await asyncio_detailed(
            account_id=account_id,
            conversation_id=conversation_id,
            client=client,
            body=body,
        )
    ).parsed
