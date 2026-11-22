from typing import Literal

MessageSenderTypeType1 = Literal["AgentBot", "Captain::Assistant", "Contact", "User"]

MESSAGE_SENDER_TYPE_TYPE_1_VALUES: set[MessageSenderTypeType1] = {
    "AgentBot",
    "Captain::Assistant",
    "Contact",
    "User",
}


def check_message_sender_type_type_1(value: str) -> MessageSenderTypeType1:
    if value in MESSAGE_SENDER_TYPE_TYPE_1_VALUES:
        return value
    raise TypeError(
        f"Unexpected value {value!r}. Expected one of {MESSAGE_SENDER_TYPE_TYPE_1_VALUES!r}"
    )
