from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.conversation_message_create_payload_template_params_category import (
    check_conversation_message_create_payload_template_params_category,
)
from ..models.conversation_message_create_payload_template_params_category import (
    ConversationMessageCreatePayloadTemplateParamsCategory,
)
from ..models.conversation_message_create_payload_template_params_content_mode import (
    check_conversation_message_create_payload_template_params_content_mode,
)
from ..models.conversation_message_create_payload_template_params_content_mode import (
    ConversationMessageCreatePayloadTemplateParamsContentMode,
)
from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
    from ..models.conversation_message_create_payload_template_params_processed_params import (
        ConversationMessageCreatePayloadTemplateParamsProcessedParams,
    )


T = TypeVar("T", bound="ConversationMessageCreatePayloadTemplateParams")


@_attrs_define
class ConversationMessageCreatePayloadTemplateParams:
    """WhatsApp template parameters for sending structured messages

    Attributes:
        category (ConversationMessageCreatePayloadTemplateParamsCategory): Category of the template Example: UTILITY.
        language (str): Language code of the template (BCP 47 format) Example: en_US.
        name (str): Name of the WhatsApp template (must be approved in WhatsApp Business Manager) Example:
            purchase_receipt.
        processed_params (ConversationMessageCreatePayloadTemplateParamsProcessedParams): Processed template parameters
            organized by component type
        content_mode (ConversationMessageCreatePayloadTemplateParamsContentMode | Unset): Format of the top-level
            `content` field. Existing clients may send rendered
            content or omit this field. Set this to `raw_template` only when `content`
            contains the original template body placeholders.
             Default: 'rendered'.
    """

    category: ConversationMessageCreatePayloadTemplateParamsCategory
    language: str
    name: str
    processed_params: ConversationMessageCreatePayloadTemplateParamsProcessedParams
    content_mode: ConversationMessageCreatePayloadTemplateParamsContentMode | Unset = "rendered"
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.conversation_message_create_payload_template_params_processed_params import (
            ConversationMessageCreatePayloadTemplateParamsProcessedParams,
        )  # noqa: PLC0415

        category: str = self.category

        language = self.language

        name = self.name

        processed_params = self.processed_params.to_dict()

        content_mode: str | Unset = UNSET
        if not isinstance(self.content_mode, Unset):
            content_mode = self.content_mode

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "category": category,
                "language": language,
                "name": name,
                "processed_params": processed_params,
            }
        )
        if content_mode is not UNSET:
            field_dict["content_mode"] = content_mode

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.conversation_message_create_payload_template_params_processed_params import (
            ConversationMessageCreatePayloadTemplateParamsProcessedParams,
        )  # noqa: PLC0415

        d = dict(src_dict)
        category = check_conversation_message_create_payload_template_params_category(
            d.pop("category")
        )

        language = d.pop("language")

        name = d.pop("name")

        processed_params = ConversationMessageCreatePayloadTemplateParamsProcessedParams.from_dict(
            d.pop("processed_params")
        )

        _content_mode = d.pop("content_mode", UNSET)
        content_mode: ConversationMessageCreatePayloadTemplateParamsContentMode | Unset
        if isinstance(_content_mode, Unset):
            content_mode = UNSET
        else:
            content_mode = check_conversation_message_create_payload_template_params_content_mode(
                _content_mode
            )

        conversation_message_create_payload_template_params = cls(
            category=category,
            language=language,
            name=name,
            processed_params=processed_params,
            content_mode=content_mode,
        )

        conversation_message_create_payload_template_params.additional_properties = d
        return conversation_message_create_payload_template_params

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
