from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
    from ..models.conversation_message_create_payload_template_params_processed_params_body import (
        ConversationMessageCreatePayloadTemplateParamsProcessedParamsBody,
    )
    from ..models.conversation_message_create_payload_template_params_processed_params_buttons_item import (
        ConversationMessageCreatePayloadTemplateParamsProcessedParamsButtonsItem,
    )
    from ..models.conversation_message_create_payload_template_params_processed_params_header import (
        ConversationMessageCreatePayloadTemplateParamsProcessedParamsHeader,
    )


T = TypeVar("T", bound="ConversationMessageCreatePayloadTemplateParamsProcessedParams")


@_attrs_define
class ConversationMessageCreatePayloadTemplateParamsProcessedParams:
    """Processed template parameters organized by component type

    Attributes:
        body (ConversationMessageCreatePayloadTemplateParamsProcessedParamsBody | Unset): Body component parameters with
            variable placeholders Example: {'1': 'Visa', '2': 'Nike', '3': 'Bill'}.
        buttons (list[ConversationMessageCreatePayloadTemplateParamsProcessedParamsButtonsItem] | Unset): Button
            component parameters for interactive templates
        header (ConversationMessageCreatePayloadTemplateParamsProcessedParamsHeader | Unset): Header component
            parameters for media templates
    """

    body: ConversationMessageCreatePayloadTemplateParamsProcessedParamsBody | Unset = UNSET
    buttons: (
        list[ConversationMessageCreatePayloadTemplateParamsProcessedParamsButtonsItem] | Unset
    ) = UNSET
    header: ConversationMessageCreatePayloadTemplateParamsProcessedParamsHeader | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.conversation_message_create_payload_template_params_processed_params_body import (
            ConversationMessageCreatePayloadTemplateParamsProcessedParamsBody,
        )  # noqa: PLC0415
        from ..models.conversation_message_create_payload_template_params_processed_params_buttons_item import (
            ConversationMessageCreatePayloadTemplateParamsProcessedParamsButtonsItem,
        )  # noqa: PLC0415
        from ..models.conversation_message_create_payload_template_params_processed_params_header import (
            ConversationMessageCreatePayloadTemplateParamsProcessedParamsHeader,
        )  # noqa: PLC0415

        body: dict[str, Any] | Unset = UNSET
        if not isinstance(self.body, Unset):
            body = self.body.to_dict()

        buttons: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.buttons, Unset):
            buttons = []
            for buttons_item_data in self.buttons:
                buttons_item = buttons_item_data.to_dict()
                buttons.append(buttons_item)

        header: dict[str, Any] | Unset = UNSET
        if not isinstance(self.header, Unset):
            header = self.header.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if body is not UNSET:
            field_dict["body"] = body
        if buttons is not UNSET:
            field_dict["buttons"] = buttons
        if header is not UNSET:
            field_dict["header"] = header

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.conversation_message_create_payload_template_params_processed_params_body import (
            ConversationMessageCreatePayloadTemplateParamsProcessedParamsBody,
        )  # noqa: PLC0415
        from ..models.conversation_message_create_payload_template_params_processed_params_buttons_item import (
            ConversationMessageCreatePayloadTemplateParamsProcessedParamsButtonsItem,
        )  # noqa: PLC0415
        from ..models.conversation_message_create_payload_template_params_processed_params_header import (
            ConversationMessageCreatePayloadTemplateParamsProcessedParamsHeader,
        )  # noqa: PLC0415

        d = dict(src_dict)
        _body = d.pop("body", UNSET)
        body: ConversationMessageCreatePayloadTemplateParamsProcessedParamsBody | Unset
        if isinstance(_body, Unset):
            body = UNSET
        else:
            body = ConversationMessageCreatePayloadTemplateParamsProcessedParamsBody.from_dict(
                _body
            )

        _buttons = d.pop("buttons", UNSET)
        buttons: (
            list[ConversationMessageCreatePayloadTemplateParamsProcessedParamsButtonsItem] | Unset
        ) = UNSET
        if _buttons is not UNSET:
            buttons = []
            for buttons_item_data in _buttons:
                buttons_item = ConversationMessageCreatePayloadTemplateParamsProcessedParamsButtonsItem.from_dict(
                    buttons_item_data
                )

                buttons.append(buttons_item)

        _header = d.pop("header", UNSET)
        header: ConversationMessageCreatePayloadTemplateParamsProcessedParamsHeader | Unset
        if isinstance(_header, Unset):
            header = UNSET
        else:
            header = ConversationMessageCreatePayloadTemplateParamsProcessedParamsHeader.from_dict(
                _header
            )

        conversation_message_create_payload_template_params_processed_params = cls(
            body=body,
            buttons=buttons,
            header=header,
        )

        conversation_message_create_payload_template_params_processed_params.additional_properties = d
        return conversation_message_create_payload_template_params_processed_params

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
