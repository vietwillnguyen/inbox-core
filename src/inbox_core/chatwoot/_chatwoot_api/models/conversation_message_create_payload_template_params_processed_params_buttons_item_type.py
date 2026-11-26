from typing import Literal

ConversationMessageCreatePayloadTemplateParamsProcessedParamsButtonsItemType = Literal[
    "copy_code", "url"
]

CONVERSATION_MESSAGE_CREATE_PAYLOAD_TEMPLATE_PARAMS_PROCESSED_PARAMS_BUTTONS_ITEM_TYPE_VALUES: set[
    ConversationMessageCreatePayloadTemplateParamsProcessedParamsButtonsItemType
] = {
    "copy_code",
    "url",
}


def check_conversation_message_create_payload_template_params_processed_params_buttons_item_type(
    value: str,
) -> ConversationMessageCreatePayloadTemplateParamsProcessedParamsButtonsItemType:
    if (
        value
        in CONVERSATION_MESSAGE_CREATE_PAYLOAD_TEMPLATE_PARAMS_PROCESSED_PARAMS_BUTTONS_ITEM_TYPE_VALUES
    ):
        return value
    raise TypeError(
        f"Unexpected value {value!r}. Expected one of {CONVERSATION_MESSAGE_CREATE_PAYLOAD_TEMPLATE_PARAMS_PROCESSED_PARAMS_BUTTONS_ITEM_TYPE_VALUES!r}"
    )
