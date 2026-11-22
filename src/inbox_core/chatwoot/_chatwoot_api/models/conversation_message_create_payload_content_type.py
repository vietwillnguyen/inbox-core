from typing import Literal

ConversationMessageCreatePayloadContentType = Literal[
    "article", "cards", "form", "input_email", "input_select", "text"
]

CONVERSATION_MESSAGE_CREATE_PAYLOAD_CONTENT_TYPE_VALUES: set[
    ConversationMessageCreatePayloadContentType
] = {
    "article",
    "cards",
    "form",
    "input_email",
    "input_select",
    "text",
}


def check_conversation_message_create_payload_content_type(
    value: str,
) -> ConversationMessageCreatePayloadContentType:
    if value in CONVERSATION_MESSAGE_CREATE_PAYLOAD_CONTENT_TYPE_VALUES:
        return value
    raise TypeError(
        f"Unexpected value {value!r}. Expected one of {CONVERSATION_MESSAGE_CREATE_PAYLOAD_CONTENT_TYPE_VALUES!r}"
    )
