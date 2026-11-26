from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.toggle_status_of_a_conversation_response_200_payload_current_status import (
    check_toggle_status_of_a_conversation_response_200_payload_current_status,
)
from ..models.toggle_status_of_a_conversation_response_200_payload_current_status import (
    ToggleStatusOfAConversationResponse200PayloadCurrentStatus,
)
from ..types import UNSET, Unset
from typing import cast


T = TypeVar("T", bound="ToggleStatusOfAConversationResponse200Payload")


@_attrs_define
class ToggleStatusOfAConversationResponse200Payload:
    """
    Attributes:
        conversation_id (float | Unset):
        current_status (ToggleStatusOfAConversationResponse200PayloadCurrentStatus | Unset):
        success (bool | Unset):
    """

    conversation_id: float | Unset = UNSET
    current_status: ToggleStatusOfAConversationResponse200PayloadCurrentStatus | Unset = UNSET
    success: bool | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        conversation_id = self.conversation_id

        current_status: str | Unset = UNSET
        if not isinstance(self.current_status, Unset):
            current_status = self.current_status

        success = self.success

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if conversation_id is not UNSET:
            field_dict["conversation_id"] = conversation_id
        if current_status is not UNSET:
            field_dict["current_status"] = current_status
        if success is not UNSET:
            field_dict["success"] = success

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        conversation_id = d.pop("conversation_id", UNSET)

        _current_status = d.pop("current_status", UNSET)
        current_status: ToggleStatusOfAConversationResponse200PayloadCurrentStatus | Unset
        if isinstance(_current_status, Unset):
            current_status = UNSET
        else:
            current_status = (
                check_toggle_status_of_a_conversation_response_200_payload_current_status(
                    _current_status
                )
            )

        success = d.pop("success", UNSET)

        toggle_status_of_a_conversation_response_200_payload = cls(
            conversation_id=conversation_id,
            current_status=current_status,
            success=success,
        )

        toggle_status_of_a_conversation_response_200_payload.additional_properties = d
        return toggle_status_of_a_conversation_response_200_payload

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
