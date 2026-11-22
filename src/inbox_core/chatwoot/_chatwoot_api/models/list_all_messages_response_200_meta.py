from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast
import datetime

if TYPE_CHECKING:
    from ..models.agent import Agent
    from ..models.contact import Contact
    from ..models.list_all_messages_response_200_meta_additional_attributes import (
        ListAllMessagesResponse200MetaAdditionalAttributes,
    )


T = TypeVar("T", bound="ListAllMessagesResponse200Meta")


@_attrs_define
class ListAllMessagesResponse200Meta:
    """
    Attributes:
        additional_attributes (ListAllMessagesResponse200MetaAdditionalAttributes | Unset):
        agent_last_seen_at (datetime.datetime | None | Unset):
        assignee (Agent | Unset):
        assignee_last_seen_at (datetime.datetime | None | Unset):
        contact (Contact | Unset):
        labels (list[str] | Unset):
    """

    additional_attributes: ListAllMessagesResponse200MetaAdditionalAttributes | Unset = UNSET
    agent_last_seen_at: datetime.datetime | None | Unset = UNSET
    assignee: Agent | Unset = UNSET
    assignee_last_seen_at: datetime.datetime | None | Unset = UNSET
    contact: Contact | Unset = UNSET
    labels: list[str] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.agent import Agent  # noqa: PLC0415
        from ..models.contact import Contact  # noqa: PLC0415
        from ..models.list_all_messages_response_200_meta_additional_attributes import (
            ListAllMessagesResponse200MetaAdditionalAttributes,
        )  # noqa: PLC0415

        additional_attributes: dict[str, Any] | Unset = UNSET
        if not isinstance(self.additional_attributes, Unset):
            additional_attributes = self.additional_attributes.to_dict()

        agent_last_seen_at: None | str | Unset
        if isinstance(self.agent_last_seen_at, Unset):
            agent_last_seen_at = UNSET
        elif isinstance(self.agent_last_seen_at, datetime.datetime):
            agent_last_seen_at = self.agent_last_seen_at.isoformat()
        else:
            agent_last_seen_at = self.agent_last_seen_at

        assignee: dict[str, Any] | Unset = UNSET
        if not isinstance(self.assignee, Unset):
            assignee = self.assignee.to_dict()

        assignee_last_seen_at: None | str | Unset
        if isinstance(self.assignee_last_seen_at, Unset):
            assignee_last_seen_at = UNSET
        elif isinstance(self.assignee_last_seen_at, datetime.datetime):
            assignee_last_seen_at = self.assignee_last_seen_at.isoformat()
        else:
            assignee_last_seen_at = self.assignee_last_seen_at

        contact: dict[str, Any] | Unset = UNSET
        if not isinstance(self.contact, Unset):
            contact = self.contact.to_dict()

        labels: list[str] | Unset = UNSET
        if not isinstance(self.labels, Unset):
            labels = self.labels

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if additional_attributes is not UNSET:
            field_dict["additional_attributes"] = additional_attributes
        if agent_last_seen_at is not UNSET:
            field_dict["agent_last_seen_at"] = agent_last_seen_at
        if assignee is not UNSET:
            field_dict["assignee"] = assignee
        if assignee_last_seen_at is not UNSET:
            field_dict["assignee_last_seen_at"] = assignee_last_seen_at
        if contact is not UNSET:
            field_dict["contact"] = contact
        if labels is not UNSET:
            field_dict["labels"] = labels

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.agent import Agent  # noqa: PLC0415
        from ..models.contact import Contact  # noqa: PLC0415
        from ..models.list_all_messages_response_200_meta_additional_attributes import (
            ListAllMessagesResponse200MetaAdditionalAttributes,
        )  # noqa: PLC0415

        d = dict(src_dict)
        _additional_attributes = d.pop("additional_attributes", UNSET)
        additional_attributes: ListAllMessagesResponse200MetaAdditionalAttributes | Unset
        if isinstance(_additional_attributes, Unset):
            additional_attributes = UNSET
        else:
            additional_attributes = ListAllMessagesResponse200MetaAdditionalAttributes.from_dict(
                _additional_attributes
            )

        def _parse_agent_last_seen_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                agent_last_seen_at_type_0 = datetime.datetime.fromisoformat(data)

                return agent_last_seen_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        agent_last_seen_at = _parse_agent_last_seen_at(d.pop("agent_last_seen_at", UNSET))

        _assignee = d.pop("assignee", UNSET)
        assignee: Agent | Unset
        if isinstance(_assignee, Unset):
            assignee = UNSET
        else:
            assignee = Agent.from_dict(_assignee)

        def _parse_assignee_last_seen_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                assignee_last_seen_at_type_0 = datetime.datetime.fromisoformat(data)

                return assignee_last_seen_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        assignee_last_seen_at = _parse_assignee_last_seen_at(d.pop("assignee_last_seen_at", UNSET))

        _contact = d.pop("contact", UNSET)
        contact: Contact | Unset
        if isinstance(_contact, Unset):
            contact = UNSET
        else:
            contact = Contact.from_dict(_contact)

        labels = cast(list[str], d.pop("labels", UNSET))

        list_all_messages_response_200_meta = cls(
            additional_attributes=additional_attributes,
            agent_last_seen_at=agent_last_seen_at,
            assignee=assignee,
            assignee_last_seen_at=assignee_last_seen_at,
            contact=contact,
            labels=labels,
        )

        list_all_messages_response_200_meta.additional_properties = d
        return list_all_messages_response_200_meta

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
