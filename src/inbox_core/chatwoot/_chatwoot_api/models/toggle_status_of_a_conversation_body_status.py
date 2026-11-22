from typing import Literal

ToggleStatusOfAConversationBodyStatus = Literal["open", "pending", "resolved", "snoozed"]

TOGGLE_STATUS_OF_A_CONVERSATION_BODY_STATUS_VALUES: set[ToggleStatusOfAConversationBodyStatus] = {
    "open",
    "pending",
    "resolved",
    "snoozed",
}


def check_toggle_status_of_a_conversation_body_status(
    value: str,
) -> ToggleStatusOfAConversationBodyStatus:
    if value in TOGGLE_STATUS_OF_A_CONVERSATION_BODY_STATUS_VALUES:
        return value
    raise TypeError(
        f"Unexpected value {value!r}. Expected one of {TOGGLE_STATUS_OF_A_CONVERSATION_BODY_STATUS_VALUES!r}"
    )
