from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.user_accounts_item_role import check_user_accounts_item_role
from ..models.user_accounts_item_role import UserAccountsItemRole
from ..types import UNSET, Unset
from typing import cast
import datetime

if TYPE_CHECKING:
    from ..models.user_accounts_item_custom_role_type_0 import UserAccountsItemCustomRoleType0


T = TypeVar("T", bound="UserAccountsItem")


@_attrs_define
class UserAccountsItem:
    """
    Attributes:
        active_at (datetime.datetime | None | Unset):
        auto_offline (bool | Unset):
        availability (str | Unset):
        availability_status (str | Unset):
        custom_role (None | Unset | UserAccountsItemCustomRoleType0):
        custom_role_id (float | None | Unset):
        id (float | Unset):
        name (str | Unset):
        permissions (list[str] | Unset):
        role (UserAccountsItemRole | Unset):
        status (str | Unset):
    """

    active_at: datetime.datetime | None | Unset = UNSET
    auto_offline: bool | Unset = UNSET
    availability: str | Unset = UNSET
    availability_status: str | Unset = UNSET
    custom_role: None | Unset | UserAccountsItemCustomRoleType0 = UNSET
    custom_role_id: float | None | Unset = UNSET
    id: float | Unset = UNSET
    name: str | Unset = UNSET
    permissions: list[str] | Unset = UNSET
    role: UserAccountsItemRole | Unset = UNSET
    status: str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.user_accounts_item_custom_role_type_0 import UserAccountsItemCustomRoleType0  # noqa: PLC0415

        active_at: None | str | Unset
        if isinstance(self.active_at, Unset):
            active_at = UNSET
        elif isinstance(self.active_at, datetime.datetime):
            active_at = self.active_at.isoformat()
        else:
            active_at = self.active_at

        auto_offline = self.auto_offline

        availability = self.availability

        availability_status = self.availability_status

        custom_role: dict[str, Any] | None | Unset
        if isinstance(self.custom_role, Unset):
            custom_role = UNSET
        elif isinstance(self.custom_role, UserAccountsItemCustomRoleType0):
            custom_role = self.custom_role.to_dict()
        else:
            custom_role = self.custom_role

        custom_role_id: float | None | Unset
        if isinstance(self.custom_role_id, Unset):
            custom_role_id = UNSET
        else:
            custom_role_id = self.custom_role_id

        id = self.id

        name = self.name

        permissions: list[str] | Unset = UNSET
        if not isinstance(self.permissions, Unset):
            permissions = self.permissions

        role: str | Unset = UNSET
        if not isinstance(self.role, Unset):
            role = self.role

        status = self.status

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if active_at is not UNSET:
            field_dict["active_at"] = active_at
        if auto_offline is not UNSET:
            field_dict["auto_offline"] = auto_offline
        if availability is not UNSET:
            field_dict["availability"] = availability
        if availability_status is not UNSET:
            field_dict["availability_status"] = availability_status
        if custom_role is not UNSET:
            field_dict["custom_role"] = custom_role
        if custom_role_id is not UNSET:
            field_dict["custom_role_id"] = custom_role_id
        if id is not UNSET:
            field_dict["id"] = id
        if name is not UNSET:
            field_dict["name"] = name
        if permissions is not UNSET:
            field_dict["permissions"] = permissions
        if role is not UNSET:
            field_dict["role"] = role
        if status is not UNSET:
            field_dict["status"] = status

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.user_accounts_item_custom_role_type_0 import UserAccountsItemCustomRoleType0  # noqa: PLC0415

        d = dict(src_dict)

        def _parse_active_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                active_at_type_0 = datetime.datetime.fromisoformat(data)

                return active_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        active_at = _parse_active_at(d.pop("active_at", UNSET))

        auto_offline = d.pop("auto_offline", UNSET)

        availability = d.pop("availability", UNSET)

        availability_status = d.pop("availability_status", UNSET)

        def _parse_custom_role(data: object) -> None | Unset | UserAccountsItemCustomRoleType0:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                custom_role_type_0 = UserAccountsItemCustomRoleType0.from_dict(data)

                return custom_role_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UserAccountsItemCustomRoleType0, data)

        custom_role = _parse_custom_role(d.pop("custom_role", UNSET))

        def _parse_custom_role_id(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        custom_role_id = _parse_custom_role_id(d.pop("custom_role_id", UNSET))

        id = d.pop("id", UNSET)

        name = d.pop("name", UNSET)

        permissions = cast(list[str], d.pop("permissions", UNSET))

        _role = d.pop("role", UNSET)
        role: UserAccountsItemRole | Unset
        if isinstance(_role, Unset):
            role = UNSET
        else:
            role = check_user_accounts_item_role(_role)

        status = d.pop("status", UNSET)

        user_accounts_item = cls(
            active_at=active_at,
            auto_offline=auto_offline,
            availability=availability,
            availability_status=availability_status,
            custom_role=custom_role,
            custom_role_id=custom_role_id,
            id=id,
            name=name,
            permissions=permissions,
            role=role,
            status=status,
        )

        user_accounts_item.additional_properties = d
        return user_accounts_item

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
