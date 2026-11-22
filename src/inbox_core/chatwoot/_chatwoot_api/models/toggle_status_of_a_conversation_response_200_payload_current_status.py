from typing import Literal

ToggleStatusOfAConversationResponse200PayloadCurrentStatus = Literal[
    "open", "pending", "resolved", "snoozed"
]

TOGGLE_STATUS_OF_A_CONVERSATION_RESPONSE_200_PAYLOAD_CURRENT_STATUS_VALUES: set[
    ToggleStatusOfAConversationResponse200PayloadCurrentStatus
] = {
    "open",
    "pending",
    "resolved",
    "snoozed",
}


def check_toggle_status_of_a_conversation_response_200_payload_current_status(
    value: str,
) -> ToggleStatusOfAConversationResponse200PayloadCurrentStatus:
    if value in TOGGLE_STATUS_OF_A_CONVERSATION_RESPONSE_200_PAYLOAD_CURRENT_STATUS_VALUES:
        return value
    raise TypeError(
        f"Unexpected value {value!r}. Expected one of {TOGGLE_STATUS_OF_A_CONVERSATION_RESPONSE_200_PAYLOAD_CURRENT_STATUS_VALUES!r}"
    )
