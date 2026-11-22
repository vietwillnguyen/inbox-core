from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.user_role import check_user_role
from ..models.user_role import UserRole
from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
    from ..models.user_accounts_item import UserAccountsItem
    from ..models.user_custom_attributes import UserCustomAttributes
    from ..models.user_ui_settings import UserUiSettings


T = TypeVar("T", bound="User")


@_attrs_define
class User:
    """
    Attributes:
        access_token (str | Unset):
        account_id (float | Unset):
        accounts (list[UserAccountsItem] | Unset):
        available_name (str | Unset):
        avatar_url (str | Unset):
        confirmed (bool | Unset):
        custom_attributes (UserCustomAttributes | Unset): Available for users who are created through platform APIs and
            has custom attributes associated.
        display_name (None | str | Unset):
        email (str | Unset):
        hmac_identifier (str | Unset):
        id (float | Unset):
        inviter_id (float | None | Unset):
        message_signature (None | str | Unset):
        name (str | Unset):
        provider (str | Unset):
        pubsub_token (str | Unset):
        role (UserRole | Unset):
        type_ (None | str | Unset):
        ui_settings (UserUiSettings | Unset):
        uid (str | Unset):
    """

    access_token: str | Unset = UNSET
    account_id: float | Unset = UNSET
    accounts: list[UserAccountsItem] | Unset = UNSET
    available_name: str | Unset = UNSET
    avatar_url: str | Unset = UNSET
    confirmed: bool | Unset = UNSET
    custom_attributes: UserCustomAttributes | Unset = UNSET
    display_name: None | str | Unset = UNSET
    email: str | Unset = UNSET
    hmac_identifier: str | Unset = UNSET
    id: float | Unset = UNSET
    inviter_id: float | None | Unset = UNSET
    message_signature: None | str | Unset = UNSET
    name: str | Unset = UNSET
    provider: str | Unset = UNSET
    pubsub_token: str | Unset = UNSET
    role: UserRole | Unset = UNSET
    type_: None | str | Unset = UNSET
    ui_settings: UserUiSettings | Unset = UNSET
    uid: str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.user_accounts_item import UserAccountsItem  # noqa: PLC0415
        from ..models.user_custom_attributes import UserCustomAttributes  # noqa: PLC0415
        from ..models.user_ui_settings import UserUiSettings  # noqa: PLC0415

        access_token = self.access_token

        account_id = self.account_id

        accounts: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.accounts, Unset):
            accounts = []
            for accounts_item_data in self.accounts:
                accounts_item = accounts_item_data.to_dict()
                accounts.append(accounts_item)

        available_name = self.available_name

        avatar_url = self.avatar_url

        confirmed = self.confirmed

        custom_attributes: dict[str, Any] | Unset = UNSET
        if not isinstance(self.custom_attributes, Unset):
            custom_attributes = self.custom_attributes.to_dict()

        display_name: None | str | Unset
        if isinstance(self.display_name, Unset):
            display_name = UNSET
        else:
            display_name = self.display_name

        email = self.email

        hmac_identifier = self.hmac_identifier

        id = self.id

        inviter_id: float | None | Unset
        if isinstance(self.inviter_id, Unset):
            inviter_id = UNSET
        else:
            inviter_id = self.inviter_id

        message_signature: None | str | Unset
        if isinstance(self.message_signature, Unset):
            message_signature = UNSET
        else:
            message_signature = self.message_signature

        name = self.name

        provider = self.provider

        pubsub_token = self.pubsub_token

        role: str | Unset = UNSET
        if not isinstance(self.role, Unset):
            role = self.role

        type_: None | str | Unset
        if isinstance(self.type_, Unset):
            type_ = UNSET
        else:
            type_ = self.type_

        ui_settings: dict[str, Any] | Unset = UNSET
        if not isinstance(self.ui_settings, Unset):
            ui_settings = self.ui_settings.to_dict()

        uid = self.uid

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if access_token is not UNSET:
            field_dict["access_token"] = access_token
        if account_id is not UNSET:
            field_dict["account_id"] = account_id
        if accounts is not UNSET:
            field_dict["accounts"] = accounts
        if available_name is not UNSET:
            field_dict["available_name"] = available_name
        if avatar_url is not UNSET:
            field_dict["avatar_url"] = avatar_url
        if confirmed is not UNSET:
            field_dict["confirmed"] = confirmed
        if custom_attributes is not UNSET:
            field_dict["custom_attributes"] = custom_attributes
        if display_name is not UNSET:
            field_dict["display_name"] = display_name
        if email is not UNSET:
            field_dict["email"] = email
        if hmac_identifier is not UNSET:
            field_dict["hmac_identifier"] = hmac_identifier
        if id is not UNSET:
            field_dict["id"] = id
        if inviter_id is not UNSET:
            field_dict["inviter_id"] = inviter_id
        if message_signature is not UNSET:
            field_dict["message_signature"] = message_signature
        if name is not UNSET:
            field_dict["name"] = name
        if provider is not UNSET:
            field_dict["provider"] = provider
        if pubsub_token is not UNSET:
            field_dict["pubsub_token"] = pubsub_token
        if role is not UNSET:
            field_dict["role"] = role
        if type_ is not UNSET:
            field_dict["type"] = type_
        if ui_settings is not UNSET:
            field_dict["ui_settings"] = ui_settings
        if uid is not UNSET:
            field_dict["uid"] = uid

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.user_accounts_item import UserAccountsItem  # noqa: PLC0415
        from ..models.user_custom_attributes import UserCustomAttributes  # noqa: PLC0415
        from ..models.user_ui_settings import UserUiSettings  # noqa: PLC0415

        d = dict(src_dict)
        access_token = d.pop("access_token", UNSET)

        account_id = d.pop("account_id", UNSET)

        _accounts = d.pop("accounts", UNSET)
        accounts: list[UserAccountsItem] | Unset = UNSET
        if _accounts is not UNSET:
            accounts = []
            for accounts_item_data in _accounts:
                accounts_item = UserAccountsItem.from_dict(accounts_item_data)

                accounts.append(accounts_item)

        available_name = d.pop("available_name", UNSET)

        avatar_url = d.pop("avatar_url", UNSET)

        confirmed = d.pop("confirmed", UNSET)

        _custom_attributes = d.pop("custom_attributes", UNSET)
        custom_attributes: UserCustomAttributes | Unset
        if isinstance(_custom_attributes, Unset):
            custom_attributes = UNSET
        else:
            custom_attributes = UserCustomAttributes.from_dict(_custom_attributes)

        def _parse_display_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        display_name = _parse_display_name(d.pop("display_name", UNSET))

        email = d.pop("email", UNSET)

        hmac_identifier = d.pop("hmac_identifier", UNSET)

        id = d.pop("id", UNSET)

        def _parse_inviter_id(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        inviter_id = _parse_inviter_id(d.pop("inviter_id", UNSET))

        def _parse_message_signature(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        message_signature = _parse_message_signature(d.pop("message_signature", UNSET))

        name = d.pop("name", UNSET)

        provider = d.pop("provider", UNSET)

        pubsub_token = d.pop("pubsub_token", UNSET)

        _role = d.pop("role", UNSET)
        role: UserRole | Unset
        if isinstance(_role, Unset):
            role = UNSET
        else:
            role = check_user_role(_role)

        def _parse_type_(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        type_ = _parse_type_(d.pop("type", UNSET))

        _ui_settings = d.pop("ui_settings", UNSET)
        ui_settings: UserUiSettings | Unset
        if isinstance(_ui_settings, Unset):
            ui_settings = UNSET
        else:
            ui_settings = UserUiSettings.from_dict(_ui_settings)

        uid = d.pop("uid", UNSET)

        user = cls(
            access_token=access_token,
            account_id=account_id,
            accounts=accounts,
            available_name=available_name,
            avatar_url=avatar_url,
            confirmed=confirmed,
            custom_attributes=custom_attributes,
            display_name=display_name,
            email=email,
            hmac_identifier=hmac_identifier,
            id=id,
            inviter_id=inviter_id,
            message_signature=message_signature,
            name=name,
            provider=provider,
            pubsub_token=pubsub_token,
            role=role,
            type_=type_,
            ui_settings=ui_settings,
            uid=uid,
        )

        user.additional_properties = d
        return user

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
