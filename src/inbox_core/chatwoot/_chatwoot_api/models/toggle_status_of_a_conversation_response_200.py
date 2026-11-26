from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
    from ..models.toggle_status_of_a_conversation_response_200_meta import (
        ToggleStatusOfAConversationResponse200Meta,
    )
    from ..models.toggle_status_of_a_conversation_response_200_payload import (
        ToggleStatusOfAConversationResponse200Payload,
    )


T = TypeVar("T", bound="ToggleStatusOfAConversationResponse200")


@_attrs_define
class ToggleStatusOfAConversationResponse200:
    """
    Attributes:
        meta (ToggleStatusOfAConversationResponse200Meta | Unset):
        payload (ToggleStatusOfAConversationResponse200Payload | Unset):
    """

    meta: ToggleStatusOfAConversationResponse200Meta | Unset = UNSET
    payload: ToggleStatusOfAConversationResponse200Payload | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.toggle_status_of_a_conversation_response_200_meta import (
            ToggleStatusOfAConversationResponse200Meta,
        )  # noqa: PLC0415
        from ..models.toggle_status_of_a_conversation_response_200_payload import (
            ToggleStatusOfAConversationResponse200Payload,
        )  # noqa: PLC0415

        meta: dict[str, Any] | Unset = UNSET
        if not isinstance(self.meta, Unset):
            meta = self.meta.to_dict()

        payload: dict[str, Any] | Unset = UNSET
        if not isinstance(self.payload, Unset):
            payload = self.payload.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if meta is not UNSET:
            field_dict["meta"] = meta
        if payload is not UNSET:
            field_dict["payload"] = payload

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.toggle_status_of_a_conversation_response_200_meta import (
            ToggleStatusOfAConversationResponse200Meta,
        )  # noqa: PLC0415
        from ..models.toggle_status_of_a_conversation_response_200_payload import (
            ToggleStatusOfAConversationResponse200Payload,
        )  # noqa: PLC0415

        d = dict(src_dict)
        _meta = d.pop("meta", UNSET)
        meta: ToggleStatusOfAConversationResponse200Meta | Unset
        if isinstance(_meta, Unset):
            meta = UNSET
        else:
            meta = ToggleStatusOfAConversationResponse200Meta.from_dict(_meta)

        _payload = d.pop("payload", UNSET)
        payload: ToggleStatusOfAConversationResponse200Payload | Unset
        if isinstance(_payload, Unset):
            payload = UNSET
        else:
            payload = ToggleStatusOfAConversationResponse200Payload.from_dict(_payload)

        toggle_status_of_a_conversation_response_200 = cls(
            meta=meta,
            payload=payload,
        )

        toggle_status_of_a_conversation_response_200.additional_properties = d
        return toggle_status_of_a_conversation_response_200

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
