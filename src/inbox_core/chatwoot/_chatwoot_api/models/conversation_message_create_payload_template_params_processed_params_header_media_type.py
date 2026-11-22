from typing import Literal

ConversationMessageCreatePayloadTemplateParamsProcessedParamsHeaderMediaType = Literal[
    "document", "image", "video"
]

CONVERSATION_MESSAGE_CREATE_PAYLOAD_TEMPLATE_PARAMS_PROCESSED_PARAMS_HEADER_MEDIA_TYPE_VALUES: set[
    ConversationMessageCreatePayloadTemplateParamsProcessedParamsHeaderMediaType
] = {
    "document",
    "image",
    "video",
}


def check_conversation_message_create_payload_template_params_processed_params_header_media_type(
    value: str,
) -> ConversationMessageCreatePayloadTemplateParamsProcessedParamsHeaderMediaType:
    if (
        value
        in CONVERSATION_MESSAGE_CREATE_PAYLOAD_TEMPLATE_PARAMS_PROCESSED_PARAMS_HEADER_MEDIA_TYPE_VALUES
    ):
        return value
    raise TypeError(
        f"Unexpected value {value!r}. Expected one of {CONVERSATION_MESSAGE_CREATE_PAYLOAD_TEMPLATE_PARAMS_PROCESSED_PARAMS_HEADER_MEDIA_TYPE_VALUES!r}"
    )
