from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.conversation_message_create_payload_template_params_processed_params_header_media_type import (
    check_conversation_message_create_payload_template_params_processed_params_header_media_type,
)
from ..models.conversation_message_create_payload_template_params_processed_params_header_media_type import (
    ConversationMessageCreatePayloadTemplateParamsProcessedParamsHeaderMediaType,
)
from ..types import UNSET, Unset
from typing import cast


T = TypeVar("T", bound="ConversationMessageCreatePayloadTemplateParamsProcessedParamsHeader")


@_attrs_define
class ConversationMessageCreatePayloadTemplateParamsProcessedParamsHeader:
    """Header component parameters for media templates

    Attributes:
        media_type (ConversationMessageCreatePayloadTemplateParamsProcessedParamsHeaderMediaType | Unset): Type of media
            for the header Example: document.
        media_url (str | Unset): Publicly accessible URL for IMAGE, VIDEO, or DOCUMENT headers Example:
            https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf.
    """

    media_type: (
        ConversationMessageCreatePayloadTemplateParamsProcessedParamsHeaderMediaType | Unset
    ) = UNSET
    media_url: str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        media_type: str | Unset = UNSET
        if not isinstance(self.media_type, Unset):
            media_type = self.media_type

        media_url = self.media_url

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if media_type is not UNSET:
            field_dict["media_type"] = media_type
        if media_url is not UNSET:
            field_dict["media_url"] = media_url

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        _media_type = d.pop("media_type", UNSET)
        media_type: (
            ConversationMessageCreatePayloadTemplateParamsProcessedParamsHeaderMediaType | Unset
        )
        if isinstance(_media_type, Unset):
            media_type = UNSET
        else:
            media_type = check_conversation_message_create_payload_template_params_processed_params_header_media_type(
                _media_type
            )

        media_url = d.pop("media_url", UNSET)

        conversation_message_create_payload_template_params_processed_params_header = cls(
            media_type=media_type,
            media_url=media_url,
        )

        conversation_message_create_payload_template_params_processed_params_header.additional_properties = d
        return conversation_message_create_payload_template_params_processed_params_header

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
