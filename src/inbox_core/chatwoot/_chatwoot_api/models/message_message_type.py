from typing import Literal

MessageMessageType = Literal[0, 1, 2, 3]

MESSAGE_MESSAGE_TYPE_VALUES: set[MessageMessageType] = {
    0,
    1,
    2,
    3,
}


def check_message_message_type(value: int) -> MessageMessageType:
    if value in MESSAGE_MESSAGE_TYPE_VALUES:
        return value
    raise TypeError(f"Unexpected value {value!r}. Expected one of {MESSAGE_MESSAGE_TYPE_VALUES!r}")
