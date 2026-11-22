from typing import Literal

ConversationMessageCreatePayloadTemplateParamsContentMode = Literal["raw_template", "rendered"]

CONVERSATION_MESSAGE_CREATE_PAYLOAD_TEMPLATE_PARAMS_CONTENT_MODE_VALUES: set[
    ConversationMessageCreatePayloadTemplateParamsContentMode
] = {
    "raw_template",
    "rendered",
}


def check_conversation_message_create_payload_template_params_content_mode(
    value: str,
) -> ConversationMessageCreatePayloadTemplateParamsContentMode:
    if value in CONVERSATION_MESSAGE_CREATE_PAYLOAD_TEMPLATE_PARAMS_CONTENT_MODE_VALUES:
        return value
    raise TypeError(
        f"Unexpected value {value!r}. Expected one of {CONVERSATION_MESSAGE_CREATE_PAYLOAD_TEMPLATE_PARAMS_CONTENT_MODE_VALUES!r}"
    )
