from typing import Literal

MessageStatusType2Type1 = Literal["delivered", "failed", "read", "sent"]

MESSAGE_STATUS_TYPE_2_TYPE_1_VALUES: set[MessageStatusType2Type1] = {
    "delivered",
    "failed",
    "read",
    "sent",
}


def check_message_status_type_2_type_1(value: str) -> MessageStatusType2Type1:
    if value in MESSAGE_STATUS_TYPE_2_TYPE_1_VALUES:
        return value
    raise TypeError(
        f"Unexpected value {value!r}. Expected one of {MESSAGE_STATUS_TYPE_2_TYPE_1_VALUES!r}"
    )
