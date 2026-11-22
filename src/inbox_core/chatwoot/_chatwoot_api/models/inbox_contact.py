from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset


T = TypeVar("T", bound="InboxContact")


@_attrs_define
class InboxContact:
    """
    Attributes:
        avatar_url (str | Unset): The avatar image of the inbox
        channel_id (float | Unset): The ID of the channel
        channel_type (str | Unset): The type of the inbox
        id (float | Unset): ID of the inbox
        name (str | Unset): The name of the inbox
        provider (str | Unset): The provider of the inbox
    """

    avatar_url: str | Unset = UNSET
    channel_id: float | Unset = UNSET
    channel_type: str | Unset = UNSET
    id: float | Unset = UNSET
    name: str | Unset = UNSET
    provider: str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        avatar_url = self.avatar_url

        channel_id = self.channel_id

        channel_type = self.channel_type

        id = self.id

        name = self.name

        provider = self.provider

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if avatar_url is not UNSET:
            field_dict["avatar_url"] = avatar_url
        if channel_id is not UNSET:
            field_dict["channel_id"] = channel_id
        if channel_type is not UNSET:
            field_dict["channel_type"] = channel_type
        if id is not UNSET:
            field_dict["id"] = id
        if name is not UNSET:
            field_dict["name"] = name
        if provider is not UNSET:
            field_dict["provider"] = provider

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        avatar_url = d.pop("avatar_url", UNSET)

        channel_id = d.pop("channel_id", UNSET)

        channel_type = d.pop("channel_type", UNSET)

        id = d.pop("id", UNSET)

        name = d.pop("name", UNSET)

        provider = d.pop("provider", UNSET)

        inbox_contact = cls(
            avatar_url=avatar_url,
            channel_id=channel_id,
            channel_type=channel_type,
            id=id,
            name=name,
            provider=provider,
        )

        inbox_contact.additional_properties = d
        return inbox_contact

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
