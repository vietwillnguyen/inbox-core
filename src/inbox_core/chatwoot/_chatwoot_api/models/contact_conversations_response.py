from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
    from ..models.contact_conversations_response_payload_item import (
        ContactConversationsResponsePayloadItem,
    )


T = TypeVar("T", bound="ContactConversationsResponse")


@_attrs_define
class ContactConversationsResponse:
    """
    Attributes:
        payload (list[ContactConversationsResponsePayloadItem] | Unset): List of conversations for the contact
    """

    payload: list[ContactConversationsResponsePayloadItem] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.contact_conversations_response_payload_item import (
            ContactConversationsResponsePayloadItem,
        )  # noqa: PLC0415

        payload: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.payload, Unset):
            payload = []
            for payload_item_data in self.payload:
                payload_item = payload_item_data.to_dict()
                payload.append(payload_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if payload is not UNSET:
            field_dict["payload"] = payload

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.contact_conversations_response_payload_item import (
            ContactConversationsResponsePayloadItem,
        )  # noqa: PLC0415

        d = dict(src_dict)
        _payload = d.pop("payload", UNSET)
        payload: list[ContactConversationsResponsePayloadItem] | Unset = UNSET
        if _payload is not UNSET:
            payload = []
            for payload_item_data in _payload:
                payload_item = ContactConversationsResponsePayloadItem.from_dict(payload_item_data)

                payload.append(payload_item)

        contact_conversations_response = cls(
            payload=payload,
        )

        contact_conversations_response.additional_properties = d
        return contact_conversations_response

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
