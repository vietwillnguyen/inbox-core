from typing import Literal

MessageContentTypeType2Type1 = Literal[
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

MESSAGE_CONTENT_TYPE_TYPE_2_TYPE_1_VALUES: set[MessageContentTypeType2Type1] = {
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


def check_message_content_type_type_2_type_1(value: str) -> MessageContentTypeType2Type1:
    if value in MESSAGE_CONTENT_TYPE_TYPE_2_TYPE_1_VALUES:
        return value
    raise TypeError(
        f"Unexpected value {value!r}. Expected one of {MESSAGE_CONTENT_TYPE_TYPE_2_TYPE_1_VALUES!r}"
    )
