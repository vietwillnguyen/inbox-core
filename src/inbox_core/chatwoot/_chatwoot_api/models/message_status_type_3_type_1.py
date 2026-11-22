from typing import Literal

MessageStatusType3Type1 = Literal["delivered", "failed", "read", "sent"]

MESSAGE_STATUS_TYPE_3_TYPE_1_VALUES: set[MessageStatusType3Type1] = {
    "delivered",
    "failed",
    "read",
    "sent",
}


def check_message_status_type_3_type_1(value: str) -> MessageStatusType3Type1:
    if value in MESSAGE_STATUS_TYPE_3_TYPE_1_VALUES:
        return value
    raise TypeError(
        f"Unexpected value {value!r}. Expected one of {MESSAGE_STATUS_TYPE_3_TYPE_1_VALUES!r}"
    )
