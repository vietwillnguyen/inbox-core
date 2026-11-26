from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.conversation_status import check_conversation_status
from ..models.conversation_status import ConversationStatus
from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
    from ..models.contact_conversations_response_payload_item_meta import (
        ContactConversationsResponsePayloadItemMeta,
    )
    from ..models.conversation_additional_attributes import ConversationAdditionalAttributes
    from ..models.conversation_applied_sla import ConversationAppliedSla
    from ..models.conversation_custom_attributes import ConversationCustomAttributes
    from ..models.conversation_sla_events_item import ConversationSlaEventsItem
    from ..models.message import Message


T = TypeVar("T", bound="ContactConversationsResponsePayloadItem")


@_attrs_define
class ContactConversationsResponsePayloadItem:
    """
    Attributes:
        account_id (float | Unset): Account Id
        additional_attributes (ConversationAdditionalAttributes | Unset): The object containing additional attributes
            related to the conversation
        agent_last_seen_at (float | Unset): The last activity at of the agent
        applied_sla (ConversationAppliedSla | Unset): The applied SLA
        assignee_last_seen_at (float | Unset): The last activity at of the assignee
        can_reply (bool | Unset): Whether the conversation can be replied to
        contact_last_seen_at (float | Unset): The last activity at of the contact
        created_at (float | Unset): The time at which conversation was created
        custom_attributes (ConversationCustomAttributes | Unset): The object to save custom attributes for conversation,
            accepts custom attributes key and value
        first_reply_created_at (float | None | Unset): The time at which the first reply was created
        id (float | Unset): ID of the conversation
        inbox_id (float | Unset): ID of the inbox
        labels (list[str] | Unset): The labels of the conversation
        last_activity_at (float | Unset): The last activity at of the conversation
        last_non_activity_message (Message | None | Unset): The last non activity message
        messages (list[Message] | Unset):
        muted (bool | Unset): Whether the conversation is muted
        priority (None | str | Unset): The priority of the conversation
        sla_events (list[ConversationSlaEventsItem] | Unset):
        sla_policy_id (float | None | Unset): The ID of the SLA policy
        snoozed_until (float | None | Unset): The time at which the conversation will be unmuted
        status (ConversationStatus | Unset): The status of the conversation
        timestamp (float | Unset): The time at which conversation was created
        unread_count (float | Unset): The number of unread messages
        updated_at (float | Unset): The time at which conversation was updated
        uuid (str | Unset): UUID of the conversation
        waiting_since (float | None | Unset): The time at which the conversation was waiting
        meta (ContactConversationsResponsePayloadItemMeta | Unset):
    """

    account_id: float | Unset = UNSET
    additional_attributes: ConversationAdditionalAttributes | Unset = UNSET
    agent_last_seen_at: float | Unset = UNSET
    applied_sla: ConversationAppliedSla | Unset = UNSET
    assignee_last_seen_at: float | Unset = UNSET
    can_reply: bool | Unset = UNSET
    contact_last_seen_at: float | Unset = UNSET
    created_at: float | Unset = UNSET
    custom_attributes: ConversationCustomAttributes | Unset = UNSET
    first_reply_created_at: float | None | Unset = UNSET
    id: float | Unset = UNSET
    inbox_id: float | Unset = UNSET
    labels: list[str] | Unset = UNSET
    last_activity_at: float | Unset = UNSET
    last_non_activity_message: Message | None | Unset = UNSET
    messages: list[Message] | Unset = UNSET
    muted: bool | Unset = UNSET
    priority: None | str | Unset = UNSET
    sla_events: list[ConversationSlaEventsItem] | Unset = UNSET
    sla_policy_id: float | None | Unset = UNSET
    snoozed_until: float | None | Unset = UNSET
    status: ConversationStatus | Unset = UNSET
    timestamp: float | Unset = UNSET
    unread_count: float | Unset = UNSET
    updated_at: float | Unset = UNSET
    uuid: str | Unset = UNSET
    waiting_since: float | None | Unset = UNSET
    meta: ContactConversationsResponsePayloadItemMeta | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.contact_conversations_response_payload_item_meta import (
            ContactConversationsResponsePayloadItemMeta,
        )  # noqa: PLC0415
        from ..models.conversation_additional_attributes import ConversationAdditionalAttributes  # noqa: PLC0415
        from ..models.conversation_applied_sla import ConversationAppliedSla  # noqa: PLC0415
        from ..models.conversation_custom_attributes import ConversationCustomAttributes  # noqa: PLC0415
        from ..models.conversation_sla_events_item import ConversationSlaEventsItem  # noqa: PLC0415
        from ..models.message import Message  # noqa: PLC0415

        account_id = self.account_id

        additional_attributes: dict[str, Any] | Unset = UNSET
        if not isinstance(self.additional_attributes, Unset):
            additional_attributes = self.additional_attributes.to_dict()

        agent_last_seen_at = self.agent_last_seen_at

        applied_sla: dict[str, Any] | Unset = UNSET
        if not isinstance(self.applied_sla, Unset):
            applied_sla = self.applied_sla.to_dict()

        assignee_last_seen_at = self.assignee_last_seen_at

        can_reply = self.can_reply

        contact_last_seen_at = self.contact_last_seen_at

        created_at = self.created_at

        custom_attributes: dict[str, Any] | Unset = UNSET
        if not isinstance(self.custom_attributes, Unset):
            custom_attributes = self.custom_attributes.to_dict()

        first_reply_created_at: float | None | Unset
        if isinstance(self.first_reply_created_at, Unset):
            first_reply_created_at = UNSET
        else:
            first_reply_created_at = self.first_reply_created_at

        id = self.id

        inbox_id = self.inbox_id

        labels: list[str] | Unset = UNSET
        if not isinstance(self.labels, Unset):
            labels = self.labels

        last_activity_at = self.last_activity_at

        last_non_activity_message: dict[str, Any] | None | Unset
        if isinstance(self.last_non_activity_message, Unset):
            last_non_activity_message = UNSET
        elif isinstance(self.last_non_activity_message, Message):
            last_non_activity_message = self.last_non_activity_message.to_dict()
        else:
            last_non_activity_message = self.last_non_activity_message

        messages: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.messages, Unset):
            messages = []
            for messages_item_data in self.messages:
                messages_item = messages_item_data.to_dict()
                messages.append(messages_item)

        muted = self.muted

        priority: None | str | Unset
        if isinstance(self.priority, Unset):
            priority = UNSET
        else:
            priority = self.priority

        sla_events: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.sla_events, Unset):
            sla_events = []
            for sla_events_item_data in self.sla_events:
                sla_events_item = sla_events_item_data.to_dict()
                sla_events.append(sla_events_item)

        sla_policy_id: float | None | Unset
        if isinstance(self.sla_policy_id, Unset):
            sla_policy_id = UNSET
        else:
            sla_policy_id = self.sla_policy_id

        snoozed_until: float | None | Unset
        if isinstance(self.snoozed_until, Unset):
            snoozed_until = UNSET
        else:
            snoozed_until = self.snoozed_until

        status: str | Unset = UNSET
        if not isinstance(self.status, Unset):
            status = self.status

        timestamp = self.timestamp

        unread_count = self.unread_count

        updated_at = self.updated_at

        uuid = self.uuid

        waiting_since: float | None | Unset
        if isinstance(self.waiting_since, Unset):
            waiting_since = UNSET
        else:
            waiting_since = self.waiting_since

        meta: dict[str, Any] | Unset = UNSET
        if not isinstance(self.meta, Unset):
            meta = self.meta.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if account_id is not UNSET:
            field_dict["account_id"] = account_id
        if additional_attributes is not UNSET:
            field_dict["additional_attributes"] = additional_attributes
        if agent_last_seen_at is not UNSET:
            field_dict["agent_last_seen_at"] = agent_last_seen_at
        if applied_sla is not UNSET:
            field_dict["applied_sla"] = applied_sla
        if assignee_last_seen_at is not UNSET:
            field_dict["assignee_last_seen_at"] = assignee_last_seen_at
        if can_reply is not UNSET:
            field_dict["can_reply"] = can_reply
        if contact_last_seen_at is not UNSET:
            field_dict["contact_last_seen_at"] = contact_last_seen_at
        if created_at is not UNSET:
            field_dict["created_at"] = created_at
        if custom_attributes is not UNSET:
            field_dict["custom_attributes"] = custom_attributes
        if first_reply_created_at is not UNSET:
            field_dict["first_reply_created_at"] = first_reply_created_at
        if id is not UNSET:
            field_dict["id"] = id
        if inbox_id is not UNSET:
            field_dict["inbox_id"] = inbox_id
        if labels is not UNSET:
            field_dict["labels"] = labels
        if last_activity_at is not UNSET:
            field_dict["last_activity_at"] = last_activity_at
        if last_non_activity_message is not UNSET:
            field_dict["last_non_activity_message"] = last_non_activity_message
        if messages is not UNSET:
            field_dict["messages"] = messages
        if muted is not UNSET:
            field_dict["muted"] = muted
        if priority is not UNSET:
            field_dict["priority"] = priority
        if sla_events is not UNSET:
            field_dict["sla_events"] = sla_events
        if sla_policy_id is not UNSET:
            field_dict["sla_policy_id"] = sla_policy_id
        if snoozed_until is not UNSET:
            field_dict["snoozed_until"] = snoozed_until
        if status is not UNSET:
            field_dict["status"] = status
        if timestamp is not UNSET:
            field_dict["timestamp"] = timestamp
        if unread_count is not UNSET:
            field_dict["unread_count"] = unread_count
        if updated_at is not UNSET:
            field_dict["updated_at"] = updated_at
        if uuid is not UNSET:
            field_dict["uuid"] = uuid
        if waiting_since is not UNSET:
            field_dict["waiting_since"] = waiting_since
        if meta is not UNSET:
            field_dict["meta"] = meta

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.contact_conversations_response_payload_item_meta import (
            ContactConversationsResponsePayloadItemMeta,
        )  # noqa: PLC0415
        from ..models.conversation_additional_attributes import ConversationAdditionalAttributes  # noqa: PLC0415
        from ..models.conversation_applied_sla import ConversationAppliedSla  # noqa: PLC0415
        from ..models.conversation_custom_attributes import ConversationCustomAttributes  # noqa: PLC0415
        from ..models.conversation_sla_events_item import ConversationSlaEventsItem  # noqa: PLC0415
        from ..models.message import Message  # noqa: PLC0415

        d = dict(src_dict)
        account_id = d.pop("account_id", UNSET)

        _additional_attributes = d.pop("additional_attributes", UNSET)
        additional_attributes: ConversationAdditionalAttributes | Unset
        if isinstance(_additional_attributes, Unset):
            additional_attributes = UNSET
        else:
            additional_attributes = ConversationAdditionalAttributes.from_dict(
                _additional_attributes
            )

        agent_last_seen_at = d.pop("agent_last_seen_at", UNSET)

        _applied_sla = d.pop("applied_sla", UNSET)
        applied_sla: ConversationAppliedSla | Unset
        if isinstance(_applied_sla, Unset):
            applied_sla = UNSET
        else:
            applied_sla = ConversationAppliedSla.from_dict(_applied_sla)

        assignee_last_seen_at = d.pop("assignee_last_seen_at", UNSET)

        can_reply = d.pop("can_reply", UNSET)

        contact_last_seen_at = d.pop("contact_last_seen_at", UNSET)

        created_at = d.pop("created_at", UNSET)

        _custom_attributes = d.pop("custom_attributes", UNSET)
        custom_attributes: ConversationCustomAttributes | Unset
        if isinstance(_custom_attributes, Unset):
            custom_attributes = UNSET
        else:
            custom_attributes = ConversationCustomAttributes.from_dict(_custom_attributes)

        def _parse_first_reply_created_at(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        first_reply_created_at = _parse_first_reply_created_at(
            d.pop("first_reply_created_at", UNSET)
        )

        id = d.pop("id", UNSET)

        inbox_id = d.pop("inbox_id", UNSET)

        labels = cast(list[str], d.pop("labels", UNSET))

        last_activity_at = d.pop("last_activity_at", UNSET)

        def _parse_last_non_activity_message(data: object) -> Message | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                last_non_activity_message_type_0 = Message.from_dict(data)

                return last_non_activity_message_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(Message | None | Unset, data)

        last_non_activity_message = _parse_last_non_activity_message(
            d.pop("last_non_activity_message", UNSET)
        )

        _messages = d.pop("messages", UNSET)
        messages: list[Message] | Unset = UNSET
        if _messages is not UNSET:
            messages = []
            for messages_item_data in _messages:
                messages_item = Message.from_dict(messages_item_data)

                messages.append(messages_item)

        muted = d.pop("muted", UNSET)

        def _parse_priority(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        priority = _parse_priority(d.pop("priority", UNSET))

        _sla_events = d.pop("sla_events", UNSET)
        sla_events: list[ConversationSlaEventsItem] | Unset = UNSET
        if _sla_events is not UNSET:
            sla_events = []
            for sla_events_item_data in _sla_events:
                sla_events_item = ConversationSlaEventsItem.from_dict(sla_events_item_data)

                sla_events.append(sla_events_item)

        def _parse_sla_policy_id(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        sla_policy_id = _parse_sla_policy_id(d.pop("sla_policy_id", UNSET))

        def _parse_snoozed_until(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        snoozed_until = _parse_snoozed_until(d.pop("snoozed_until", UNSET))

        _status = d.pop("status", UNSET)
        status: ConversationStatus | Unset
        if isinstance(_status, Unset):
            status = UNSET
        else:
            status = check_conversation_status(_status)

        timestamp = d.pop("timestamp", UNSET)

        unread_count = d.pop("unread_count", UNSET)

        updated_at = d.pop("updated_at", UNSET)

        uuid = d.pop("uuid", UNSET)

        def _parse_waiting_since(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        waiting_since = _parse_waiting_since(d.pop("waiting_since", UNSET))

        _meta = d.pop("meta", UNSET)
        meta: ContactConversationsResponsePayloadItemMeta | Unset
        if isinstance(_meta, Unset):
            meta = UNSET
        else:
            meta = ContactConversationsResponsePayloadItemMeta.from_dict(_meta)

        contact_conversations_response_payload_item = cls(
            account_id=account_id,
            additional_attributes=additional_attributes,
            agent_last_seen_at=agent_last_seen_at,
            applied_sla=applied_sla,
            assignee_last_seen_at=assignee_last_seen_at,
            can_reply=can_reply,
            contact_last_seen_at=contact_last_seen_at,
            created_at=created_at,
            custom_attributes=custom_attributes,
            first_reply_created_at=first_reply_created_at,
            id=id,
            inbox_id=inbox_id,
            labels=labels,
            last_activity_at=last_activity_at,
            last_non_activity_message=last_non_activity_message,
            messages=messages,
            muted=muted,
            priority=priority,
            sla_events=sla_events,
            sla_policy_id=sla_policy_id,
            snoozed_until=snoozed_until,
            status=status,
            timestamp=timestamp,
            unread_count=unread_count,
            updated_at=updated_at,
            uuid=uuid,
            waiting_since=waiting_since,
            meta=meta,
        )

        contact_conversations_response_payload_item.additional_properties = d
        return contact_conversations_response_payload_item

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
