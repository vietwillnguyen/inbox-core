from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.message_content_type_type_1 import check_message_content_type_type_1
from ..models.message_content_type_type_1 import MessageContentTypeType1
from ..models.message_content_type_type_2_type_1 import check_message_content_type_type_2_type_1
from ..models.message_content_type_type_2_type_1 import MessageContentTypeType2Type1
from ..models.message_content_type_type_3_type_1 import check_message_content_type_type_3_type_1
from ..models.message_content_type_type_3_type_1 import MessageContentTypeType3Type1
from ..models.message_message_type import check_message_message_type
from ..models.message_message_type import MessageMessageType
from ..models.message_sender_type_type_1 import check_message_sender_type_type_1
from ..models.message_sender_type_type_1 import MessageSenderTypeType1
from ..models.message_sender_type_type_2_type_1 import check_message_sender_type_type_2_type_1
from ..models.message_sender_type_type_2_type_1 import MessageSenderTypeType2Type1
from ..models.message_sender_type_type_3_type_1 import check_message_sender_type_type_3_type_1
from ..models.message_sender_type_type_3_type_1 import MessageSenderTypeType3Type1
from ..models.message_status_type_1 import check_message_status_type_1
from ..models.message_status_type_1 import MessageStatusType1
from ..models.message_status_type_2_type_1 import check_message_status_type_2_type_1
from ..models.message_status_type_2_type_1 import MessageStatusType2Type1
from ..models.message_status_type_3_type_1 import check_message_status_type_3_type_1
from ..models.message_status_type_3_type_1 import MessageStatusType3Type1
from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
    from ..models.message_additional_attributes import MessageAdditionalAttributes
    from ..models.message_attachment_type_0 import MessageAttachmentType0
    from ..models.message_content_attributes import MessageContentAttributes
    from ..models.message_conversation_type_0 import MessageConversationType0
    from ..models.message_external_source_ids import MessageExternalSourceIds
    from ..models.message_sender import MessageSender
    from ..models.message_sentiment_type_0 import MessageSentimentType0


T = TypeVar("T", bound="Message")


@_attrs_define
class Message:
    """
    Attributes:
        account_id (float | Unset): The ID of the account
        additional_attributes (MessageAdditionalAttributes | Unset): The additional attributes of the message
        attachment (MessageAttachmentType0 | None | Unset): The file object attached to the image
        content (str | Unset): The text content of the message
        content_attributes (MessageContentAttributes | Unset): The content attributes for each content_type
        content_type (MessageContentTypeType1 | MessageContentTypeType2Type1 | MessageContentTypeType3Type1 | None |
            Unset): The type of the template message
        conversation (MessageConversationType0 | None | Unset): The conversation object
        conversation_id (float | Unset): The ID of the conversation
        created_at (int | Unset): The time at which message was created
        external_source_ids (MessageExternalSourceIds | Unset): The external source IDs of the message
        id (float | Unset): The ID of the message
        inbox_id (float | Unset): The ID of the inbox
        message_type (MessageMessageType | Unset): The type of the message
        private (bool | Unset): The flags which shows whether the message is private or not
        processed_message_content (None | str | Unset): The processed message content
        sender (MessageSender | Unset): User/Agent/AgentBot object
        sender_id (float | None | Unset): The ID of the sender
        sender_type (MessageSenderTypeType1 | MessageSenderTypeType2Type1 | MessageSenderTypeType3Type1 | None | Unset):
            The type of the sender
        sentiment (MessageSentimentType0 | None | Unset): The sentiment of the message
        source_id (None | str | Unset): The source ID of the message
        status (MessageStatusType1 | MessageStatusType2Type1 | MessageStatusType3Type1 | None | Unset): The status of
            the message
        updated_at (int | str | Unset): The time at which message was updated
    """

    account_id: float | Unset = UNSET
    additional_attributes: MessageAdditionalAttributes | Unset = UNSET
    attachment: MessageAttachmentType0 | None | Unset = UNSET
    content: str | Unset = UNSET
    content_attributes: MessageContentAttributes | Unset = UNSET
    content_type: (
        MessageContentTypeType1
        | MessageContentTypeType2Type1
        | MessageContentTypeType3Type1
        | None
        | Unset
    ) = UNSET
    conversation: MessageConversationType0 | None | Unset = UNSET
    conversation_id: float | Unset = UNSET
    created_at: int | Unset = UNSET
    external_source_ids: MessageExternalSourceIds | Unset = UNSET
    id: float | Unset = UNSET
    inbox_id: float | Unset = UNSET
    message_type: MessageMessageType | Unset = UNSET
    private: bool | Unset = UNSET
    processed_message_content: None | str | Unset = UNSET
    sender: MessageSender | Unset = UNSET
    sender_id: float | None | Unset = UNSET
    sender_type: (
        MessageSenderTypeType1
        | MessageSenderTypeType2Type1
        | MessageSenderTypeType3Type1
        | None
        | Unset
    ) = UNSET
    sentiment: MessageSentimentType0 | None | Unset = UNSET
    source_id: None | str | Unset = UNSET
    status: (
        MessageStatusType1 | MessageStatusType2Type1 | MessageStatusType3Type1 | None | Unset
    ) = UNSET
    updated_at: int | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.message_additional_attributes import MessageAdditionalAttributes  # noqa: PLC0415
        from ..models.message_attachment_type_0 import MessageAttachmentType0  # noqa: PLC0415
        from ..models.message_content_attributes import MessageContentAttributes  # noqa: PLC0415
        from ..models.message_conversation_type_0 import MessageConversationType0  # noqa: PLC0415
        from ..models.message_external_source_ids import MessageExternalSourceIds  # noqa: PLC0415
        from ..models.message_sender import MessageSender  # noqa: PLC0415
        from ..models.message_sentiment_type_0 import MessageSentimentType0  # noqa: PLC0415

        account_id = self.account_id

        additional_attributes: dict[str, Any] | Unset = UNSET
        if not isinstance(self.additional_attributes, Unset):
            additional_attributes = self.additional_attributes.to_dict()

        attachment: dict[str, Any] | None | Unset
        if isinstance(self.attachment, Unset):
            attachment = UNSET
        elif isinstance(self.attachment, MessageAttachmentType0):
            attachment = self.attachment.to_dict()
        else:
            attachment = self.attachment

        content = self.content

        content_attributes: dict[str, Any] | Unset = UNSET
        if not isinstance(self.content_attributes, Unset):
            content_attributes = self.content_attributes.to_dict()

        content_type: None | str | Unset
        if isinstance(self.content_type, Unset):
            content_type = UNSET
        elif isinstance(self.content_type, str):
            content_type = self.content_type
        elif isinstance(self.content_type, str):
            content_type = self.content_type
        elif isinstance(self.content_type, str):
            content_type = self.content_type
        else:
            content_type = self.content_type

        conversation: dict[str, Any] | None | Unset
        if isinstance(self.conversation, Unset):
            conversation = UNSET
        elif isinstance(self.conversation, MessageConversationType0):
            conversation = self.conversation.to_dict()
        else:
            conversation = self.conversation

        conversation_id = self.conversation_id

        created_at = self.created_at

        external_source_ids: dict[str, Any] | Unset = UNSET
        if not isinstance(self.external_source_ids, Unset):
            external_source_ids = self.external_source_ids.to_dict()

        id = self.id

        inbox_id = self.inbox_id

        message_type: int | Unset = UNSET
        if not isinstance(self.message_type, Unset):
            message_type = self.message_type

        private = self.private

        processed_message_content: None | str | Unset
        if isinstance(self.processed_message_content, Unset):
            processed_message_content = UNSET
        else:
            processed_message_content = self.processed_message_content

        sender: dict[str, Any] | Unset = UNSET
        if not isinstance(self.sender, Unset):
            sender = self.sender.to_dict()

        sender_id: float | None | Unset
        if isinstance(self.sender_id, Unset):
            sender_id = UNSET
        else:
            sender_id = self.sender_id

        sender_type: None | str | Unset
        if isinstance(self.sender_type, Unset):
            sender_type = UNSET
        elif isinstance(self.sender_type, str):
            sender_type = self.sender_type
        elif isinstance(self.sender_type, str):
            sender_type = self.sender_type
        elif isinstance(self.sender_type, str):
            sender_type = self.sender_type
        else:
            sender_type = self.sender_type

        sentiment: dict[str, Any] | None | Unset
        if isinstance(self.sentiment, Unset):
            sentiment = UNSET
        elif isinstance(self.sentiment, MessageSentimentType0):
            sentiment = self.sentiment.to_dict()
        else:
            sentiment = self.sentiment

        source_id: None | str | Unset
        if isinstance(self.source_id, Unset):
            source_id = UNSET
        else:
            source_id = self.source_id

        status: None | str | Unset
        if isinstance(self.status, Unset):
            status = UNSET
        elif isinstance(self.status, str):
            status = self.status
        elif isinstance(self.status, str):
            status = self.status
        elif isinstance(self.status, str):
            status = self.status
        else:
            status = self.status

        updated_at: int | str | Unset
        if isinstance(self.updated_at, Unset):
            updated_at = UNSET
        else:
            updated_at = self.updated_at

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if account_id is not UNSET:
            field_dict["account_id"] = account_id
        if additional_attributes is not UNSET:
            field_dict["additional_attributes"] = additional_attributes
        if attachment is not UNSET:
            field_dict["attachment"] = attachment
        if content is not UNSET:
            field_dict["content"] = content
        if content_attributes is not UNSET:
            field_dict["content_attributes"] = content_attributes
        if content_type is not UNSET:
            field_dict["content_type"] = content_type
        if conversation is not UNSET:
            field_dict["conversation"] = conversation
        if conversation_id is not UNSET:
            field_dict["conversation_id"] = conversation_id
        if created_at is not UNSET:
            field_dict["created_at"] = created_at
        if external_source_ids is not UNSET:
            field_dict["external_source_ids"] = external_source_ids
        if id is not UNSET:
            field_dict["id"] = id
        if inbox_id is not UNSET:
            field_dict["inbox_id"] = inbox_id
        if message_type is not UNSET:
            field_dict["message_type"] = message_type
        if private is not UNSET:
            field_dict["private"] = private
        if processed_message_content is not UNSET:
            field_dict["processed_message_content"] = processed_message_content
        if sender is not UNSET:
            field_dict["sender"] = sender
        if sender_id is not UNSET:
            field_dict["sender_id"] = sender_id
        if sender_type is not UNSET:
            field_dict["sender_type"] = sender_type
        if sentiment is not UNSET:
            field_dict["sentiment"] = sentiment
        if source_id is not UNSET:
            field_dict["source_id"] = source_id
        if status is not UNSET:
            field_dict["status"] = status
        if updated_at is not UNSET:
            field_dict["updated_at"] = updated_at

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.message_additional_attributes import MessageAdditionalAttributes  # noqa: PLC0415
        from ..models.message_attachment_type_0 import MessageAttachmentType0  # noqa: PLC0415
        from ..models.message_content_attributes import MessageContentAttributes  # noqa: PLC0415
        from ..models.message_conversation_type_0 import MessageConversationType0  # noqa: PLC0415
        from ..models.message_external_source_ids import MessageExternalSourceIds  # noqa: PLC0415
        from ..models.message_sender import MessageSender  # noqa: PLC0415
        from ..models.message_sentiment_type_0 import MessageSentimentType0  # noqa: PLC0415

        d = dict(src_dict)
        account_id = d.pop("account_id", UNSET)

        _additional_attributes = d.pop("additional_attributes", UNSET)
        additional_attributes: MessageAdditionalAttributes | Unset
        if isinstance(_additional_attributes, Unset):
            additional_attributes = UNSET
        else:
            additional_attributes = MessageAdditionalAttributes.from_dict(_additional_attributes)

        def _parse_attachment(data: object) -> MessageAttachmentType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                attachment_type_0 = MessageAttachmentType0.from_dict(data)

                return attachment_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(MessageAttachmentType0 | None | Unset, data)

        attachment = _parse_attachment(d.pop("attachment", UNSET))

        content = d.pop("content", UNSET)

        _content_attributes = d.pop("content_attributes", UNSET)
        content_attributes: MessageContentAttributes | Unset
        if isinstance(_content_attributes, Unset):
            content_attributes = UNSET
        else:
            content_attributes = MessageContentAttributes.from_dict(_content_attributes)

        def _parse_content_type(
            data: object,
        ) -> (
            MessageContentTypeType1
            | MessageContentTypeType2Type1
            | MessageContentTypeType3Type1
            | None
            | Unset
        ):
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                content_type_type_1 = check_message_content_type_type_1(data)

                return content_type_type_1
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            try:
                if not isinstance(data, str):
                    raise TypeError()
                content_type_type_2_type_1 = check_message_content_type_type_2_type_1(data)

                return content_type_type_2_type_1
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            try:
                if not isinstance(data, str):
                    raise TypeError()
                content_type_type_3_type_1 = check_message_content_type_type_3_type_1(data)

                return content_type_type_3_type_1
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(
                MessageContentTypeType1
                | MessageContentTypeType2Type1
                | MessageContentTypeType3Type1
                | None
                | Unset,
                data,
            )

        content_type = _parse_content_type(d.pop("content_type", UNSET))

        def _parse_conversation(data: object) -> MessageConversationType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                conversation_type_0 = MessageConversationType0.from_dict(data)

                return conversation_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(MessageConversationType0 | None | Unset, data)

        conversation = _parse_conversation(d.pop("conversation", UNSET))

        conversation_id = d.pop("conversation_id", UNSET)

        created_at = d.pop("created_at", UNSET)

        _external_source_ids = d.pop("external_source_ids", UNSET)
        external_source_ids: MessageExternalSourceIds | Unset
        if isinstance(_external_source_ids, Unset):
            external_source_ids = UNSET
        else:
            external_source_ids = MessageExternalSourceIds.from_dict(_external_source_ids)

        id = d.pop("id", UNSET)

        inbox_id = d.pop("inbox_id", UNSET)

        _message_type = d.pop("message_type", UNSET)
        message_type: MessageMessageType | Unset
        if isinstance(_message_type, Unset):
            message_type = UNSET
        else:
            message_type = check_message_message_type(_message_type)

        private = d.pop("private", UNSET)

        def _parse_processed_message_content(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        processed_message_content = _parse_processed_message_content(
            d.pop("processed_message_content", UNSET)
        )

        _sender = d.pop("sender", UNSET)
        sender: MessageSender | Unset
        if isinstance(_sender, Unset):
            sender = UNSET
        else:
            sender = MessageSender.from_dict(_sender)

        def _parse_sender_id(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        sender_id = _parse_sender_id(d.pop("sender_id", UNSET))

        def _parse_sender_type(
            data: object,
        ) -> (
            MessageSenderTypeType1
            | MessageSenderTypeType2Type1
            | MessageSenderTypeType3Type1
            | None
            | Unset
        ):
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                sender_type_type_1 = check_message_sender_type_type_1(data)

                return sender_type_type_1
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            try:
                if not isinstance(data, str):
                    raise TypeError()
                sender_type_type_2_type_1 = check_message_sender_type_type_2_type_1(data)

                return sender_type_type_2_type_1
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            try:
                if not isinstance(data, str):
                    raise TypeError()
                sender_type_type_3_type_1 = check_message_sender_type_type_3_type_1(data)

                return sender_type_type_3_type_1
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(
                MessageSenderTypeType1
                | MessageSenderTypeType2Type1
                | MessageSenderTypeType3Type1
                | None
                | Unset,
                data,
            )

        sender_type = _parse_sender_type(d.pop("sender_type", UNSET))

        def _parse_sentiment(data: object) -> MessageSentimentType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                sentiment_type_0 = MessageSentimentType0.from_dict(data)

                return sentiment_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(MessageSentimentType0 | None | Unset, data)

        sentiment = _parse_sentiment(d.pop("sentiment", UNSET))

        def _parse_source_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        source_id = _parse_source_id(d.pop("source_id", UNSET))

        def _parse_status(
            data: object,
        ) -> MessageStatusType1 | MessageStatusType2Type1 | MessageStatusType3Type1 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                status_type_1 = check_message_status_type_1(data)

                return status_type_1
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            try:
                if not isinstance(data, str):
                    raise TypeError()
                status_type_2_type_1 = check_message_status_type_2_type_1(data)

                return status_type_2_type_1
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            try:
                if not isinstance(data, str):
                    raise TypeError()
                status_type_3_type_1 = check_message_status_type_3_type_1(data)

                return status_type_3_type_1
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(
                MessageStatusType1
                | MessageStatusType2Type1
                | MessageStatusType3Type1
                | None
                | Unset,
                data,
            )

        status = _parse_status(d.pop("status", UNSET))

        def _parse_updated_at(data: object) -> int | str | Unset:
            if isinstance(data, Unset):
                return data
            return cast(int | str | Unset, data)

        updated_at = _parse_updated_at(d.pop("updated_at", UNSET))

        message = cls(
            account_id=account_id,
            additional_attributes=additional_attributes,
            attachment=attachment,
            content=content,
            content_attributes=content_attributes,
            content_type=content_type,
            conversation=conversation,
            conversation_id=conversation_id,
            created_at=created_at,
            external_source_ids=external_source_ids,
            id=id,
            inbox_id=inbox_id,
            message_type=message_type,
            private=private,
            processed_message_content=processed_message_content,
            sender=sender,
            sender_id=sender_id,
            sender_type=sender_type,
            sentiment=sentiment,
            source_id=source_id,
            status=status,
            updated_at=updated_at,
        )

        message.additional_properties = d
        return message

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
