from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset


T = TypeVar("T", bound="AssignAConversationBody")


@_attrs_define
class AssignAConversationBody:
    """
    Attributes:
        assignee_id (float | Unset): Id of the assignee user Example: 1.
        team_id (float | Unset): Id of the team. If the assignee_id is present, this param would be ignored Example: 1.
    """

    assignee_id: float | Unset = UNSET
    team_id: float | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        assignee_id = self.assignee_id

        team_id = self.team_id

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if assignee_id is not UNSET:
            field_dict["assignee_id"] = assignee_id
        if team_id is not UNSET:
            field_dict["team_id"] = team_id

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        assignee_id = d.pop("assignee_id", UNSET)

        team_id = d.pop("team_id", UNSET)

        assign_a_conversation_body = cls(
            assignee_id=assignee_id,
            team_id=team_id,
        )

        assign_a_conversation_body.additional_properties = d
        return assign_a_conversation_body

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
