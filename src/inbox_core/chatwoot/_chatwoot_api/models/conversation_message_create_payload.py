from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.conversation_message_create_payload_content_type import (
    check_conversation_message_create_payload_content_type,
)
from ..models.conversation_message_create_payload_content_type import (
    ConversationMessageCreatePayloadContentType,
)
from ..models.conversation_message_create_payload_message_type import (
    check_conversation_message_create_payload_message_type,
)
from ..models.conversation_message_create_payload_message_type import (
    ConversationMessageCreatePayloadMessageType,
)
from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
    from ..models.conversation_message_create_payload_content_attributes import (
        ConversationMessageCreatePayloadContentAttributes,
    )
    from ..models.conversation_message_create_payload_template_params import (
        ConversationMessageCreatePayloadTemplateParams,
    )


T = TypeVar("T", bound="ConversationMessageCreatePayload")


@_attrs_define
class ConversationMessageCreatePayload:
    """
    Attributes:
        content (str): The content of the message Example: Hello, how can I help you?.
        campaign_id (int | Unset): The campaign id to which the message belongs Example: 1.
        content_attributes (ConversationMessageCreatePayloadContentAttributes | Unset): Attributes based on the content
            type. For `input_select`, provide an `items` array with
            `title`, `value`, and optional `description`. WhatsApp list messages use `description`
            as the row subtitle when present.
             Example: {'items': [{'description': 'Optional WhatsApp list row subtitle', 'title': 'Option 1', 'value':
            'option_1'}]}.
        content_type (ConversationMessageCreatePayloadContentType | Unset): Content type of the message Example: text.
        message_type (ConversationMessageCreatePayloadMessageType | Unset): The type of the message Example: outgoing.
        private (bool | Unset): Flag to identify if it is a private note Example: False.
        template_params (ConversationMessageCreatePayloadTemplateParams | Unset): WhatsApp template parameters for
            sending structured messages
    """

    content: str
    campaign_id: int | Unset = UNSET
    content_attributes: ConversationMessageCreatePayloadContentAttributes | Unset = UNSET
    content_type: ConversationMessageCreatePayloadContentType | Unset = UNSET
    message_type: ConversationMessageCreatePayloadMessageType | Unset = UNSET
    private: bool | Unset = UNSET
    template_params: ConversationMessageCreatePayloadTemplateParams | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.conversation_message_create_payload_content_attributes import (
            ConversationMessageCreatePayloadContentAttributes,
        )  # noqa: PLC0415
        from ..models.conversation_message_create_payload_template_params import (
            ConversationMessageCreatePayloadTemplateParams,
        )  # noqa: PLC0415

        content = self.content

        campaign_id = self.campaign_id

        content_attributes: dict[str, Any] | Unset = UNSET
        if not isinstance(self.content_attributes, Unset):
            content_attributes = self.content_attributes.to_dict()

        content_type: str | Unset = UNSET
        if not isinstance(self.content_type, Unset):
            content_type = self.content_type

        message_type: str | Unset = UNSET
        if not isinstance(self.message_type, Unset):
            message_type = self.message_type

        private = self.private

        template_params: dict[str, Any] | Unset = UNSET
        if not isinstance(self.template_params, Unset):
            template_params = self.template_params.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "content": content,
            }
        )
        if campaign_id is not UNSET:
            field_dict["campaign_id"] = campaign_id
        if content_attributes is not UNSET:
            field_dict["content_attributes"] = content_attributes
        if content_type is not UNSET:
            field_dict["content_type"] = content_type
        if message_type is not UNSET:
            field_dict["message_type"] = message_type
        if private is not UNSET:
            field_dict["private"] = private
        if template_params is not UNSET:
            field_dict["template_params"] = template_params

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.conversation_message_create_payload_content_attributes import (
            ConversationMessageCreatePayloadContentAttributes,
        )  # noqa: PLC0415
        from ..models.conversation_message_create_payload_template_params import (
            ConversationMessageCreatePayloadTemplateParams,
        )  # noqa: PLC0415

        d = dict(src_dict)
        content = d.pop("content")

        campaign_id = d.pop("campaign_id", UNSET)

        _content_attributes = d.pop("content_attributes", UNSET)
        content_attributes: ConversationMessageCreatePayloadContentAttributes | Unset
        if isinstance(_content_attributes, Unset):
            content_attributes = UNSET
        else:
            content_attributes = ConversationMessageCreatePayloadContentAttributes.from_dict(
                _content_attributes
            )

        _content_type = d.pop("content_type", UNSET)
        content_type: ConversationMessageCreatePayloadContentType | Unset
        if isinstance(_content_type, Unset):
            content_type = UNSET
        else:
            content_type = check_conversation_message_create_payload_content_type(_content_type)

        _message_type = d.pop("message_type", UNSET)
        message_type: ConversationMessageCreatePayloadMessageType | Unset
        if isinstance(_message_type, Unset):
            message_type = UNSET
        else:
            message_type = check_conversation_message_create_payload_message_type(_message_type)

        private = d.pop("private", UNSET)

        _template_params = d.pop("template_params", UNSET)
        template_params: ConversationMessageCreatePayloadTemplateParams | Unset
        if isinstance(_template_params, Unset):
            template_params = UNSET
        else:
            template_params = ConversationMessageCreatePayloadTemplateParams.from_dict(
                _template_params
            )

        conversation_message_create_payload = cls(
            content=content,
            campaign_id=campaign_id,
            content_attributes=content_attributes,
            content_type=content_type,
            message_type=message_type,
            private=private,
            template_params=template_params,
        )

        conversation_message_create_payload.additional_properties = d
        return conversation_message_create_payload

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
