from typing import Literal

ConversationListAssigneeType = Literal["all", "assigned", "me", "unassigned"]

CONVERSATION_LIST_ASSIGNEE_TYPE_VALUES: set[ConversationListAssigneeType] = {
    "all",
    "assigned",
    "me",
    "unassigned",
}


def check_conversation_list_assignee_type(value: str) -> ConversationListAssigneeType:
    if value in CONVERSATION_LIST_ASSIGNEE_TYPE_VALUES:
        return value
    raise TypeError(
        f"Unexpected value {value!r}. Expected one of {CONVERSATION_LIST_ASSIGNEE_TYPE_VALUES!r}"
    )
