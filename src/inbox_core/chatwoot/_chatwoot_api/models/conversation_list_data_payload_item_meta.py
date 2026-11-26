from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
    from ..models.conversation_list_data_payload_item_meta_sender import (
        ConversationListDataPayloadItemMetaSender,
    )
    from ..models.user import User


T = TypeVar("T", bound="ConversationListDataPayloadItemMeta")


@_attrs_define
class ConversationListDataPayloadItemMeta:
    """
    Attributes:
        assignee (User | Unset):
        channel (str | Unset): Channel Type
        hmac_verified (bool | Unset): Whether the hmac is verified
        sender (ConversationListDataPayloadItemMetaSender | Unset):
    """

    assignee: User | Unset = UNSET
    channel: str | Unset = UNSET
    hmac_verified: bool | Unset = UNSET
    sender: ConversationListDataPayloadItemMetaSender | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.conversation_list_data_payload_item_meta_sender import (
            ConversationListDataPayloadItemMetaSender,
        )  # noqa: PLC0415
        from ..models.user import User  # noqa: PLC0415

        assignee: dict[str, Any] | Unset = UNSET
        if not isinstance(self.assignee, Unset):
            assignee = self.assignee.to_dict()

        channel = self.channel

        hmac_verified = self.hmac_verified

        sender: dict[str, Any] | Unset = UNSET
        if not isinstance(self.sender, Unset):
            sender = self.sender.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if assignee is not UNSET:
            field_dict["assignee"] = assignee
        if channel is not UNSET:
            field_dict["channel"] = channel
        if hmac_verified is not UNSET:
            field_dict["hmac_verified"] = hmac_verified
        if sender is not UNSET:
            field_dict["sender"] = sender

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.conversation_list_data_payload_item_meta_sender import (
            ConversationListDataPayloadItemMetaSender,
        )  # noqa: PLC0415
        from ..models.user import User  # noqa: PLC0415

        d = dict(src_dict)
        _assignee = d.pop("assignee", UNSET)
        assignee: User | Unset
        if isinstance(_assignee, Unset):
            assignee = UNSET
        else:
            assignee = User.from_dict(_assignee)

        channel = d.pop("channel", UNSET)

        hmac_verified = d.pop("hmac_verified", UNSET)

        _sender = d.pop("sender", UNSET)
        sender: ConversationListDataPayloadItemMetaSender | Unset
        if isinstance(_sender, Unset):
            sender = UNSET
        else:
            sender = ConversationListDataPayloadItemMetaSender.from_dict(_sender)

        conversation_list_data_payload_item_meta = cls(
            assignee=assignee,
            channel=channel,
            hmac_verified=hmac_verified,
            sender=sender,
        )

        conversation_list_data_payload_item_meta.additional_properties = d
        return conversation_list_data_payload_item_meta

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
