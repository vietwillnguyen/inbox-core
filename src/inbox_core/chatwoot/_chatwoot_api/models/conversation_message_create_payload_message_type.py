from typing import Literal

ConversationMessageCreatePayloadMessageType = Literal["incoming", "outgoing"]

CONVERSATION_MESSAGE_CREATE_PAYLOAD_MESSAGE_TYPE_VALUES: set[
    ConversationMessageCreatePayloadMessageType
] = {
    "incoming",
    "outgoing",
}


def check_conversation_message_create_payload_message_type(
    value: str,
) -> ConversationMessageCreatePayloadMessageType:
    if value in CONVERSATION_MESSAGE_CREATE_PAYLOAD_MESSAGE_TYPE_VALUES:
        return value
    raise TypeError(
        f"Unexpected value {value!r}. Expected one of {CONVERSATION_MESSAGE_CREATE_PAYLOAD_MESSAGE_TYPE_VALUES!r}"
    )
