from typing import Literal

UserRole = Literal["administrator", "agent"]

USER_ROLE_VALUES: set[UserRole] = {
    "administrator",
    "agent",
}


def check_user_role(value: str) -> UserRole:
    if value in USER_ROLE_VALUES:
        return value
    raise TypeError(f"Unexpected value {value!r}. Expected one of {USER_ROLE_VALUES!r}")
