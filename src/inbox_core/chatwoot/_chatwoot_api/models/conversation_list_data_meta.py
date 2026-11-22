from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset


T = TypeVar("T", bound="ConversationListDataMeta")


@_attrs_define
class ConversationListDataMeta:
    """
    Attributes:
        all_count (float | Unset):
        assigned_count (float | Unset):
        mine_count (float | Unset):
        unassigned_count (float | Unset):
    """

    all_count: float | Unset = UNSET
    assigned_count: float | Unset = UNSET
    mine_count: float | Unset = UNSET
    unassigned_count: float | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        all_count = self.all_count

        assigned_count = self.assigned_count

        mine_count = self.mine_count

        unassigned_count = self.unassigned_count

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if all_count is not UNSET:
            field_dict["all_count"] = all_count
        if assigned_count is not UNSET:
            field_dict["assigned_count"] = assigned_count
        if mine_count is not UNSET:
            field_dict["mine_count"] = mine_count
        if unassigned_count is not UNSET:
            field_dict["unassigned_count"] = unassigned_count

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        all_count = d.pop("all_count", UNSET)

        assigned_count = d.pop("assigned_count", UNSET)

        mine_count = d.pop("mine_count", UNSET)

        unassigned_count = d.pop("unassigned_count", UNSET)

        conversation_list_data_meta = cls(
            all_count=all_count,
            assigned_count=assigned_count,
            mine_count=mine_count,
            unassigned_count=unassigned_count,
        )

        conversation_list_data_meta.additional_properties = d
        return conversation_list_data_meta

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
