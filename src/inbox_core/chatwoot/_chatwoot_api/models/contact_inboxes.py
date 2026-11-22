from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
    from ..models.inbox_contact import InboxContact


T = TypeVar("T", bound="ContactInboxes")


@_attrs_define
class ContactInboxes:
    """
    Attributes:
        inbox (InboxContact | Unset):
        source_id (str | Unset): Contact Inbox Source Id
    """

    inbox: InboxContact | Unset = UNSET
    source_id: str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.inbox_contact import InboxContact  # noqa: PLC0415

        inbox: dict[str, Any] | Unset = UNSET
        if not isinstance(self.inbox, Unset):
            inbox = self.inbox.to_dict()

        source_id = self.source_id

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if inbox is not UNSET:
            field_dict["inbox"] = inbox
        if source_id is not UNSET:
            field_dict["source_id"] = source_id

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.inbox_contact import InboxContact  # noqa: PLC0415

        d = dict(src_dict)
        _inbox = d.pop("inbox", UNSET)
        inbox: InboxContact | Unset
        if isinstance(_inbox, Unset):
            inbox = UNSET
        else:
            inbox = InboxContact.from_dict(_inbox)

        source_id = d.pop("source_id", UNSET)

        contact_inboxes = cls(
            inbox=inbox,
            source_id=source_id,
        )

        contact_inboxes.additional_properties = d
        return contact_inboxes

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
