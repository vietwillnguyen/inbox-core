from typing import Literal

ConversationListStatus = Literal["all", "open", "pending", "resolved", "snoozed"]

CONVERSATION_LIST_STATUS_VALUES: set[ConversationListStatus] = {
    "all",
    "open",
    "pending",
    "resolved",
    "snoozed",
}


def check_conversation_list_status(value: str) -> ConversationListStatus:
    if value in CONVERSATION_LIST_STATUS_VALUES:
        return value
    raise TypeError(
        f"Unexpected value {value!r}. Expected one of {CONVERSATION_LIST_STATUS_VALUES!r}"
    )
