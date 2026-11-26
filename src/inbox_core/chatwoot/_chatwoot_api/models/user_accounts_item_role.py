from typing import Literal

UserAccountsItemRole = Literal["administrator", "agent"]

USER_ACCOUNTS_ITEM_ROLE_VALUES: set[UserAccountsItemRole] = {
    "administrator",
    "agent",
}


def check_user_accounts_item_role(value: str) -> UserAccountsItemRole:
    if value in USER_ACCOUNTS_ITEM_ROLE_VALUES:
        return value
    raise TypeError(
        f"Unexpected value {value!r}. Expected one of {USER_ACCOUNTS_ITEM_ROLE_VALUES!r}"
    )
