from typing import Literal

ConversationMessageCreatePayloadTemplateParamsCategory = Literal[
    "ISSUE_RESOLUTION", "MARKETING", "SHIPPING_UPDATE", "TICKET_UPDATE", "UTILITY"
]

CONVERSATION_MESSAGE_CREATE_PAYLOAD_TEMPLATE_PARAMS_CATEGORY_VALUES: set[
    ConversationMessageCreatePayloadTemplateParamsCategory
] = {
    "ISSUE_RESOLUTION",
    "MARKETING",
    "SHIPPING_UPDATE",
    "TICKET_UPDATE",
    "UTILITY",
}


def check_conversation_message_create_payload_template_params_category(
    value: str,
) -> ConversationMessageCreatePayloadTemplateParamsCategory:
    if value in CONVERSATION_MESSAGE_CREATE_PAYLOAD_TEMPLATE_PARAMS_CATEGORY_VALUES:
        return value
    raise TypeError(
        f"Unexpected value {value!r}. Expected one of {CONVERSATION_MESSAGE_CREATE_PAYLOAD_TEMPLATE_PARAMS_CATEGORY_VALUES!r}"
    )
