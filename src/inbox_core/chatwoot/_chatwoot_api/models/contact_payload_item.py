from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
    from ..models.contact_inboxes import ContactInboxes
    from ..models.contact_payload_item_additional_attributes import (
        ContactPayloadItemAdditionalAttributes,
    )
    from ..models.contact_payload_item_custom_attributes import ContactPayloadItemCustomAttributes


T = TypeVar("T", bound="ContactPayloadItem")


@_attrs_define
class ContactPayloadItem:
    """
    Attributes:
        additional_attributes (ContactPayloadItemAdditionalAttributes | Unset): The object containing additional
            attributes related to the contact
        availability_status (str | Unset): The availability status of the contact
        blocked (bool | Unset): Whether the contact is blocked
        contact_inboxes (list[ContactInboxes] | Unset):
        created_at (int | Unset): The created at of the contact
        custom_attributes (ContactPayloadItemCustomAttributes | Unset): The custom attributes of the contact Example:
            {'attribute_key': 'attribute_value', 'signed_up_at': 'dd/mm/yyyy'}.
        email (str | Unset): The email address of the contact
        id (int | Unset): The ID of the contact
        identifier (str | Unset): The identifier of the contact
        last_activity_at (int | Unset): The last activity at of the contact
        name (str | Unset): The name of the contact
        phone_number (str | Unset): The phone number of the contact
        thumbnail (str | Unset): The thumbnail of the contact
    """

    additional_attributes: ContactPayloadItemAdditionalAttributes | Unset = UNSET
    availability_status: str | Unset = UNSET
    blocked: bool | Unset = UNSET
    contact_inboxes: list[ContactInboxes] | Unset = UNSET
    created_at: int | Unset = UNSET
    custom_attributes: ContactPayloadItemCustomAttributes | Unset = UNSET
    email: str | Unset = UNSET
    id: int | Unset = UNSET
    identifier: str | Unset = UNSET
    last_activity_at: int | Unset = UNSET
    name: str | Unset = UNSET
    phone_number: str | Unset = UNSET
    thumbnail: str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.contact_inboxes import ContactInboxes  # noqa: PLC0415
        from ..models.contact_payload_item_additional_attributes import (
            ContactPayloadItemAdditionalAttributes,
        )  # noqa: PLC0415
        from ..models.contact_payload_item_custom_attributes import (
            ContactPayloadItemCustomAttributes,
        )  # noqa: PLC0415

        additional_attributes: dict[str, Any] | Unset = UNSET
        if not isinstance(self.additional_attributes, Unset):
            additional_attributes = self.additional_attributes.to_dict()

        availability_status = self.availability_status

        blocked = self.blocked

        contact_inboxes: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.contact_inboxes, Unset):
            contact_inboxes = []
            for contact_inboxes_item_data in self.contact_inboxes:
                contact_inboxes_item = contact_inboxes_item_data.to_dict()
                contact_inboxes.append(contact_inboxes_item)

        created_at = self.created_at

        custom_attributes: dict[str, Any] | Unset = UNSET
        if not isinstance(self.custom_attributes, Unset):
            custom_attributes = self.custom_attributes.to_dict()

        email = self.email

        id = self.id

        identifier = self.identifier

        last_activity_at = self.last_activity_at

        name = self.name

        phone_number = self.phone_number

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
        if contact_inboxes is not UNSET:
            field_dict["contact_inboxes"] = contact_inboxes
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
        from ..models.contact_inboxes import ContactInboxes  # noqa: PLC0415
        from ..models.contact_payload_item_additional_attributes import (
            ContactPayloadItemAdditionalAttributes,
        )  # noqa: PLC0415
        from ..models.contact_payload_item_custom_attributes import (
            ContactPayloadItemCustomAttributes,
        )  # noqa: PLC0415

        d = dict(src_dict)
        _additional_attributes = d.pop("additional_attributes", UNSET)
        additional_attributes: ContactPayloadItemAdditionalAttributes | Unset
        if isinstance(_additional_attributes, Unset):
            additional_attributes = UNSET
        else:
            additional_attributes = ContactPayloadItemAdditionalAttributes.from_dict(
                _additional_attributes
            )

        availability_status = d.pop("availability_status", UNSET)

        blocked = d.pop("blocked", UNSET)

        _contact_inboxes = d.pop("contact_inboxes", UNSET)
        contact_inboxes: list[ContactInboxes] | Unset = UNSET
        if _contact_inboxes is not UNSET:
            contact_inboxes = []
            for contact_inboxes_item_data in _contact_inboxes:
                contact_inboxes_item = ContactInboxes.from_dict(contact_inboxes_item_data)

                contact_inboxes.append(contact_inboxes_item)

        created_at = d.pop("created_at", UNSET)

        _custom_attributes = d.pop("custom_attributes", UNSET)
        custom_attributes: ContactPayloadItemCustomAttributes | Unset
        if isinstance(_custom_attributes, Unset):
            custom_attributes = UNSET
        else:
            custom_attributes = ContactPayloadItemCustomAttributes.from_dict(_custom_attributes)

        email = d.pop("email", UNSET)

        id = d.pop("id", UNSET)

        identifier = d.pop("identifier", UNSET)

        last_activity_at = d.pop("last_activity_at", UNSET)

        name = d.pop("name", UNSET)

        phone_number = d.pop("phone_number", UNSET)

        thumbnail = d.pop("thumbnail", UNSET)

        contact_payload_item = cls(
            additional_attributes=additional_attributes,
            availability_status=availability_status,
            blocked=blocked,
            contact_inboxes=contact_inboxes,
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

        contact_payload_item.additional_properties = d
        return contact_payload_item

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
