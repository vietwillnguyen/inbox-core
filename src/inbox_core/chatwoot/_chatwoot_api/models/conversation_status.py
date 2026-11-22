from typing import Literal

ConversationStatus = Literal["open", "pending", "resolved", "snoozed"]

CONVERSATION_STATUS_VALUES: set[ConversationStatus] = {
    "open",
    "pending",
    "resolved",
    "snoozed",
}


def check_conversation_status(value: str) -> ConversationStatus:
    if value in CONVERSATION_STATUS_VALUES:
        return value
    raise TypeError(f"Unexpected value {value!r}. Expected one of {CONVERSATION_STATUS_VALUES!r}")
