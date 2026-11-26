from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
    from ..models.conversation_list_data_payload_item_meta_sender_additional_attributes import (
        ConversationListDataPayloadItemMetaSenderAdditionalAttributes,
    )
    from ..models.conversation_list_data_payload_item_meta_sender_custom_attributes import (
        ConversationListDataPayloadItemMetaSenderCustomAttributes,
    )


T = TypeVar("T", bound="ConversationListDataPayloadItemMetaSender")


@_attrs_define
class ConversationListDataPayloadItemMetaSender:
    """
    Attributes:
        additional_attributes (ConversationListDataPayloadItemMetaSenderAdditionalAttributes | Unset): The additional
            attributes of the sender
        availability_status (str | Unset): The availability status of the sender
        blocked (bool | Unset): Whether the sender is blocked
        created_at (float | Unset): The created at of the sender
        custom_attributes (ConversationListDataPayloadItemMetaSenderCustomAttributes | Unset): The custom attributes of
            the sender
        email (None | str | Unset): The email of the sender
        id (float | Unset): ID fo the sender
        identifier (None | str | Unset): The identifier of the sender
        last_activity_at (float | Unset): The last activity at of the sender
        name (str | Unset): The name of the sender
        phone_number (None | str | Unset): The phone number of the sender
        thumbnail (None | str | Unset): Avatar URL of the contact
    """

    additional_attributes: ConversationListDataPayloadItemMetaSenderAdditionalAttributes | Unset = (
        UNSET
    )
    availability_status: str | Unset = UNSET
    blocked: bool | Unset = UNSET
    created_at: float | Unset = UNSET
    custom_attributes: ConversationListDataPayloadItemMetaSenderCustomAttributes | Unset = UNSET
    email: None | str | Unset = UNSET
    id: float | Unset = UNSET
    identifier: None | str | Unset = UNSET
    last_activity_at: float | Unset = UNSET
    name: str | Unset = UNSET
    phone_number: None | str | Unset = UNSET
    thumbnail: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.conversation_list_data_payload_item_meta_sender_additional_attributes import (
            ConversationListDataPayloadItemMetaSenderAdditionalAttributes,
        )  # noqa: PLC0415
        from ..models.conversation_list_data_payload_item_meta_sender_custom_attributes import (
            ConversationListDataPayloadItemMetaSenderCustomAttributes,
        )  # noqa: PLC0415

        additional_attributes: dict[str, Any] | Unset = UNSET
        if not isinstance(self.additional_attributes, Unset):
            additional_attributes = self.additional_attributes.to_dict()

        availability_status = self.availability_status

        blocked = self.blocked

        created_at = self.created_at

        custom_attributes: dict[str, Any] | Unset = UNSET
        if not isinstance(self.custom_attributes, Unset):
            custom_attributes = self.custom_attributes.to_dict()

        email: None | str | Unset
        if isinstance(self.email, Unset):
            email = UNSET
        else:
            email = self.email

        id = self.id

        identifier: None | str | Unset
        if isinstance(self.identifier, Unset):
            identifier = UNSET
        else:
            identifier = self.identifier

        last_activity_at = self.last_activity_at

        name = self.name

        phone_number: None | str | Unset
        if isinstance(self.phone_number, Unset):
            phone_number = UNSET
        else:
            phone_number = self.phone_number

        thumbnail: None | str | Unset
        if isinstance(self.thumbnail, Unset):
            thumbnail = UNSET
        else:
            thumbnail = self.thumbnail

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if additional_attributes is not UNSET:
            field_dict["additional_attributes"] = additional_attributes
        if availability_status is not UNSET:
            field_dict["availability_status"] = availability_status
        if blocked is not UNSET:
            field_dict["blocked"] = blocked
        if created_at is not UNSET:
            field_dict["created_at"] = created_at
        if custom_attributes is not UNSET:
            field_dict["custom_attributes"] = custom_attributes
        if email is not UNSET:
            field_dict["email"] = email
        if id is not UNSET:
            field_dict["id"] = id
        if identifier is not UNSET:
            field_dict["identifier"] = identifier
        if last_activity_at is not UNSET:
            field_dict["last_activity_at"] = last_activity_at
        if name is not UNSET:
            field_dict["name"] = name
        if phone_number is not UNSET:
            field_dict["phone_number"] = phone_number
        if thumbnail is not UNSET:
            field_dict["thumbnail"] = thumbnail

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.conversation_list_data_payload_item_meta_sender_additional_attributes import (
            ConversationListDataPayloadItemMetaSenderAdditionalAttributes,
        )  # noqa: PLC0415
        from ..models.conversation_list_data_payload_item_meta_sender_custom_attributes import (
            ConversationListDataPayloadItemMetaSenderCustomAttributes,
        )  # noqa: PLC0415

        d = dict(src_dict)
        _additional_attributes = d.pop("additional_attributes", UNSET)
        additional_attributes: ConversationListDataPayloadItemMetaSenderAdditionalAttributes | Unset
        if isinstance(_additional_attributes, Unset):
            additional_attributes = UNSET
        else:
            additional_attributes = (
                ConversationListDataPayloadItemMetaSenderAdditionalAttributes.from_dict(
                    _additional_attributes
                )
            )

        availability_status = d.pop("availability_status", UNSET)

        blocked = d.pop("blocked", UNSET)

        created_at = d.pop("created_at", UNSET)

        _custom_attributes = d.pop("custom_attributes", UNSET)
        custom_attributes: ConversationListDataPayloadItemMetaSenderCustomAttributes | Unset
        if isinstance(_custom_attributes, Unset):
            custom_attributes = UNSET
        else:
            custom_attributes = ConversationListDataPayloadItemMetaSenderCustomAttributes.from_dict(
                _custom_attributes
            )

        def _parse_email(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        email = _parse_email(d.pop("email", UNSET))

        id = d.pop("id", UNSET)

        def _parse_identifier(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        identifier = _parse_identifier(d.pop("identifier", UNSET))

        last_activity_at = d.pop("last_activity_at", UNSET)

        name = d.pop("name", UNSET)

        def _parse_phone_number(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        phone_number = _parse_phone_number(d.pop("phone_number", UNSET))

        def _parse_thumbnail(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        thumbnail = _parse_thumbnail(d.pop("thumbnail", UNSET))

        conversation_list_data_payload_item_meta_sender = cls(
            additional_attributes=additional_attributes,
            availability_status=availability_status,
            blocked=blocked,
            created_at=created_at,
            custom_attributes=custom_attributes,
            email=email,
            id=id,
            identifier=identifier,
            last_activity_at=last_activity_at,
            name=name,
            phone_number=phone_number,
            thumbnail=thumbnail,
        )

        conversation_list_data_payload_item_meta_sender.additional_properties = d
        return conversation_list_data_payload_item_meta_sender

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
