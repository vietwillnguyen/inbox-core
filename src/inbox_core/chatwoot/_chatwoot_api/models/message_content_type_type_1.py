from typing import Literal

MessageContentTypeType1 = Literal[
    "article",
    "cards",
    "form",
    "incoming_email",
    "input_csat",
    "input_email",
    "input_select",
    "input_text",
    "input_textarea",
    "integrations",
    "sticker",
    "text",
    "voice_call",
]

MESSAGE_CONTENT_TYPE_TYPE_1_VALUES: set[MessageContentTypeType1] = {
    "article",
    "cards",
    "form",
    "incoming_email",
    "input_csat",
    "input_email",
    "input_select",
    "input_text",
    "input_textarea",
    "integrations",
    "sticker",
    "text",
    "voice_call",
}


def check_message_content_type_type_1(value: str) -> MessageContentTypeType1:
    if value in MESSAGE_CONTENT_TYPE_TYPE_1_VALUES:
        return value
    raise TypeError(
        f"Unexpected value {value!r}. Expected one of {MESSAGE_CONTENT_TYPE_TYPE_1_VALUES!r}"
    )
