from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
    from ..models.inbox_auto_assignment_config import InboxAutoAssignmentConfig
    from ..models.inbox_working_hours_item import InboxWorkingHoursItem


T = TypeVar("T", bound="Inbox")


@_attrs_define
class Inbox:
    """
    Attributes:
        allow_messages_after_resolved (bool | Unset): Whether to allow messages after a conversation is resolved
        auto_assignment_config (InboxAutoAssignmentConfig | Unset): Configuration settings for auto assignment
        avatar_url (str | Unset): The avatar image of the inbox
        bot_name (None | str | Unset): Telegram bot name associated with the inbox
        branded_email_layout (None | str | Unset): Liquid HTML layout for branded email replies. Available to
            administrators for Email inbox show/update responses.
        business_id (None | str | Unset): TikTok business ID associated with the inbox
        business_name (None | str | Unset): Business name associated with the inbox
        callback_webhook_url (None | str | Unset): Webhook URL for callbacks
        channel_id (float | Unset): ID of the channel this inbox belongs to
        channel_type (str | Unset): The type of the inbox
        csat_survey_enabled (bool | Unset): The flag to enable CSAT survey
        email (None | str | Unset): Email address associated with the inbox
        enable_auto_assignment (bool | Unset): The flag which shows whether Auto Assignment is enabled or not
        enable_email_collect (bool | Unset): The flag to enable collecting email from contacts
        greeting_enabled (bool | Unset): The flag which shows whether greeting is enabled
        greeting_message (None | str | Unset): A greeting message when the user starts the conversation
        hmac_mandatory (bool | None | Unset): Whether HMAC verification is mandatory
        id (float | Unset): ID of the inbox
        inbox_identifier (None | str | Unset): Public identifier associated with an API inbox
        instagram_id (None | str | Unset): Instagram account ID associated with the inbox
        line_channel_id (None | str | Unset): LINE channel ID associated with the inbox
        lock_to_single_conversation (bool | Unset): Whether to lock a contact to a single conversation
        medium (str | Unset): Medium of communication (e.g., sms, email)
        messaging_service_sid (None | str | Unset): Messaging service SID for SMS providers
        name (str | Unset): The name of the inbox
        out_of_office_message (None | str | Unset): Message to show when agents are out of office
        page_id (None | str | Unset): Facebook Page ID associated with the inbox
        phone_number (None | str | Unset): Phone number associated with the inbox
        profile_id (None | str | Unset): X profile ID associated with the inbox
        provider (None | str | Unset): Provider of the channel
        provider_name (None | str | Unset): Provider username or page name associated with the social inbox
        reply_time (None | str | Unset): Expected reply time
        selected_feature_flags (list[str] | None | Unset): Selected feature flags for the inbox
        sender_name_type (str | Unset): Type of sender name to display (e.g., friendly)
        timezone (str | Unset): Timezone configuration for the inbox
        web_widget_script (None | str | Unset): Script used to load the website widget
        website_token (None | str | Unset): Website Token
        website_url (None | str | Unset): Website URL
        welcome_tagline (None | str | Unset): Welcome tagline to be displayed on the widget
        welcome_title (None | str | Unset): Welcome title to be displayed on the widget
        widget_color (None | str | Unset): Widget Color used for customization of the widget
        working_hours (list[InboxWorkingHoursItem] | Unset): Configuration for working hours of the inbox
        working_hours_enabled (bool | Unset): The flag which shows whether working hours feature is enabled
    """

    allow_messages_after_resolved: bool | Unset = UNSET
    auto_assignment_config: InboxAutoAssignmentConfig | Unset = UNSET
    avatar_url: str | Unset = UNSET
    bot_name: None | str | Unset = UNSET
    branded_email_layout: None | str | Unset = UNSET
    business_id: None | str | Unset = UNSET
    business_name: None | str | Unset = UNSET
    callback_webhook_url: None | str | Unset = UNSET
    channel_id: float | Unset = UNSET
    channel_type: str | Unset = UNSET
    csat_survey_enabled: bool | Unset = UNSET
    email: None | str | Unset = UNSET
    enable_auto_assignment: bool | Unset = UNSET
    enable_email_collect: bool | Unset = UNSET
    greeting_enabled: bool | Unset = UNSET
    greeting_message: None | str | Unset = UNSET
    hmac_mandatory: bool | None | Unset = UNSET
    id: float | Unset = UNSET
    inbox_identifier: None | str | Unset = UNSET
    instagram_id: None | str | Unset = UNSET
    line_channel_id: None | str | Unset = UNSET
    lock_to_single_conversation: bool | Unset = UNSET
    medium: str | Unset = UNSET
    messaging_service_sid: None | str | Unset = UNSET
    name: str | Unset = UNSET
    out_of_office_message: None | str | Unset = UNSET
    page_id: None | str | Unset = UNSET
    phone_number: None | str | Unset = UNSET
    profile_id: None | str | Unset = UNSET
    provider: None | str | Unset = UNSET
    provider_name: None | str | Unset = UNSET
    reply_time: None | str | Unset = UNSET
    selected_feature_flags: list[str] | None | Unset = UNSET
    sender_name_type: str | Unset = UNSET
    timezone: str | Unset = UNSET
    web_widget_script: None | str | Unset = UNSET
    website_token: None | str | Unset = UNSET
    website_url: None | str | Unset = UNSET
    welcome_tagline: None | str | Unset = UNSET
    welcome_title: None | str | Unset = UNSET
    widget_color: None | str | Unset = UNSET
    working_hours: list[InboxWorkingHoursItem] | Unset = UNSET
    working_hours_enabled: bool | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.inbox_auto_assignment_config import InboxAutoAssignmentConfig  # noqa: PLC0415
        from ..models.inbox_working_hours_item import InboxWorkingHoursItem  # noqa: PLC0415

        allow_messages_after_resolved = self.allow_messages_after_resolved

        auto_assignment_config: dict[str, Any] | Unset = UNSET
        if not isinstance(self.auto_assignment_config, Unset):
            auto_assignment_config = self.auto_assignment_config.to_dict()

        avatar_url = self.avatar_url

        bot_name: None | str | Unset
        if isinstance(self.bot_name, Unset):
            bot_name = UNSET
        else:
            bot_name = self.bot_name

        branded_email_layout: None | str | Unset
        if isinstance(self.branded_email_layout, Unset):
            branded_email_layout = UNSET
        else:
            branded_email_layout = self.branded_email_layout

        business_id: None | str | Unset
        if isinstance(self.business_id, Unset):
            business_id = UNSET
        else:
            business_id = self.business_id

        business_name: None | str | Unset
        if isinstance(self.business_name, Unset):
            business_name = UNSET
        else:
            business_name = self.business_name

        callback_webhook_url: None | str | Unset
        if isinstance(self.callback_webhook_url, Unset):
            callback_webhook_url = UNSET
        else:
            callback_webhook_url = self.callback_webhook_url

        channel_id = self.channel_id

        channel_type = self.channel_type

        csat_survey_enabled = self.csat_survey_enabled

        email: None | str | Unset
        if isinstance(self.email, Unset):
            email = UNSET
        else:
            email = self.email

        enable_auto_assignment = self.enable_auto_assignment

        enable_email_collect = self.enable_email_collect

        greeting_enabled = self.greeting_enabled

        greeting_message: None | str | Unset
        if isinstance(self.greeting_message, Unset):
            greeting_message = UNSET
        else:
            greeting_message = self.greeting_message

        hmac_mandatory: bool | None | Unset
        if isinstance(self.hmac_mandatory, Unset):
            hmac_mandatory = UNSET
        else:
            hmac_mandatory = self.hmac_mandatory

        id = self.id

        inbox_identifier: None | str | Unset
        if isinstance(self.inbox_identifier, Unset):
            inbox_identifier = UNSET
        else:
            inbox_identifier = self.inbox_identifier

        instagram_id: None | str | Unset
        if isinstance(self.instagram_id, Unset):
            instagram_id = UNSET
        else:
            instagram_id = self.instagram_id

        line_channel_id: None | str | Unset
        if isinstance(self.line_channel_id, Unset):
            line_channel_id = UNSET
        else:
            line_channel_id = self.line_channel_id

        lock_to_single_conversation = self.lock_to_single_conversation

        medium = self.medium

        messaging_service_sid: None | str | Unset
        if isinstance(self.messaging_service_sid, Unset):
            messaging_service_sid = UNSET
        else:
            messaging_service_sid = self.messaging_service_sid

        name = self.name

        out_of_office_message: None | str | Unset
        if isinstance(self.out_of_office_message, Unset):
            out_of_office_message = UNSET
        else:
            out_of_office_message = self.out_of_office_message

        page_id: None | str | Unset
        if isinstance(self.page_id, Unset):
            page_id = UNSET
        else:
            page_id = self.page_id

        phone_number: None | str | Unset
        if isinstance(self.phone_number, Unset):
            phone_number = UNSET
        else:
            phone_number = self.phone_number

        profile_id: None | str | Unset
        if isinstance(self.profile_id, Unset):
            profile_id = UNSET
        else:
            profile_id = self.profile_id

        provider: None | str | Unset
        if isinstance(self.provider, Unset):
            provider = UNSET
        else:
            provider = self.provider

        provider_name: None | str | Unset
        if isinstance(self.provider_name, Unset):
            provider_name = UNSET
        else:
            provider_name = self.provider_name

        reply_time: None | str | Unset
        if isinstance(self.reply_time, Unset):
            reply_time = UNSET
        else:
            reply_time = self.reply_time

        selected_feature_flags: list[str] | None | Unset
        if isinstance(self.selected_feature_flags, Unset):
            selected_feature_flags = UNSET
        elif isinstance(self.selected_feature_flags, list):
            selected_feature_flags = self.selected_feature_flags

        else:
            selected_feature_flags = self.selected_feature_flags

        sender_name_type = self.sender_name_type

        timezone = self.timezone

        web_widget_script: None | str | Unset
        if isinstance(self.web_widget_script, Unset):
            web_widget_script = UNSET
        else:
            web_widget_script = self.web_widget_script

        website_token: None | str | Unset
        if isinstance(self.website_token, Unset):
            website_token = UNSET
        else:
            website_token = self.website_token

        website_url: None | str | Unset
        if isinstance(self.website_url, Unset):
            website_url = UNSET
        else:
            website_url = self.website_url

        welcome_tagline: None | str | Unset
        if isinstance(self.welcome_tagline, Unset):
            welcome_tagline = UNSET
        else:
            welcome_tagline = self.welcome_tagline

        welcome_title: None | str | Unset
        if isinstance(self.welcome_title, Unset):
            welcome_title = UNSET
        else:
            welcome_title = self.welcome_title

        widget_color: None | str | Unset
        if isinstance(self.widget_color, Unset):
            widget_color = UNSET
        else:
            widget_color = self.widget_color

        working_hours: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.working_hours, Unset):
            working_hours = []
            for working_hours_item_data in self.working_hours:
                working_hours_item = working_hours_item_data.to_dict()
                working_hours.append(working_hours_item)

        working_hours_enabled = self.working_hours_enabled

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if allow_messages_after_resolved is not UNSET:
            field_dict["allow_messages_after_resolved"] = allow_messages_after_resolved
        if auto_assignment_config is not UNSET:
            field_dict["auto_assignment_config"] = auto_assignment_config
        if avatar_url is not UNSET:
            field_dict["avatar_url"] = avatar_url
        if bot_name is not UNSET:
            field_dict["bot_name"] = bot_name
        if branded_email_layout is not UNSET:
            field_dict["branded_email_layout"] = branded_email_layout
        if business_id is not UNSET:
            field_dict["business_id"] = business_id
        if business_name is not UNSET:
            field_dict["business_name"] = business_name
        if callback_webhook_url is not UNSET:
            field_dict["callback_webhook_url"] = callback_webhook_url
        if channel_id is not UNSET:
            field_dict["channel_id"] = channel_id
        if channel_type is not UNSET:
            field_dict["channel_type"] = channel_type
        if csat_survey_enabled is not UNSET:
            field_dict["csat_survey_enabled"] = csat_survey_enabled
        if email is not UNSET:
            field_dict["email"] = email
        if enable_auto_assignment is not UNSET:
            field_dict["enable_auto_assignment"] = enable_auto_assignment
        if enable_email_collect is not UNSET:
            field_dict["enable_email_collect"] = enable_email_collect
        if greeting_enabled is not UNSET:
            field_dict["greeting_enabled"] = greeting_enabled
        if greeting_message is not UNSET:
            field_dict["greeting_message"] = greeting_message
        if hmac_mandatory is not UNSET:
            field_dict["hmac_mandatory"] = hmac_mandatory
        if id is not UNSET:
            field_dict["id"] = id
        if inbox_identifier is not UNSET:
            field_dict["inbox_identifier"] = inbox_identifier
        if instagram_id is not UNSET:
            field_dict["instagram_id"] = instagram_id
        if line_channel_id is not UNSET:
            field_dict["line_channel_id"] = line_channel_id
        if lock_to_single_conversation is not UNSET:
            field_dict["lock_to_single_conversation"] = lock_to_single_conversation
        if medium is not UNSET:
            field_dict["medium"] = medium
        if messaging_service_sid is not UNSET:
            field_dict["messaging_service_sid"] = messaging_service_sid
        if name is not UNSET:
            field_dict["name"] = name
        if out_of_office_message is not UNSET:
            field_dict["out_of_office_message"] = out_of_office_message
        if page_id is not UNSET:
            field_dict["page_id"] = page_id
        if phone_number is not UNSET:
            field_dict["phone_number"] = phone_number
        if profile_id is not UNSET:
            field_dict["profile_id"] = profile_id
        if provider is not UNSET:
            field_dict["provider"] = provider
        if provider_name is not UNSET:
            field_dict["provider_name"] = provider_name
        if reply_time is not UNSET:
            field_dict["reply_time"] = reply_time
        if selected_feature_flags is not UNSET:
            field_dict["selected_feature_flags"] = selected_feature_flags
        if sender_name_type is not UNSET:
            field_dict["sender_name_type"] = sender_name_type
        if timezone is not UNSET:
            field_dict["timezone"] = timezone
        if web_widget_script is not UNSET:
            field_dict["web_widget_script"] = web_widget_script
        if website_token is not UNSET:
            field_dict["website_token"] = website_token
        if website_url is not UNSET:
            field_dict["website_url"] = website_url
        if welcome_tagline is not UNSET:
            field_dict["welcome_tagline"] = welcome_tagline
        if welcome_title is not UNSET:
            field_dict["welcome_title"] = welcome_title
        if widget_color is not UNSET:
            field_dict["widget_color"] = widget_color
        if working_hours is not UNSET:
            field_dict["working_hours"] = working_hours
        if working_hours_enabled is not UNSET:
            field_dict["working_hours_enabled"] = working_hours_enabled

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.inbox_auto_assignment_config import InboxAutoAssignmentConfig  # noqa: PLC0415
        from ..models.inbox_working_hours_item import InboxWorkingHoursItem  # noqa: PLC0415

        d = dict(src_dict)
        allow_messages_after_resolved = d.pop("allow_messages_after_resolved", UNSET)

        _auto_assignment_config = d.pop("auto_assignment_config", UNSET)
        auto_assignment_config: InboxAutoAssignmentConfig | Unset
        if isinstance(_auto_assignment_config, Unset):
            auto_assignment_config = UNSET
        else:
            auto_assignment_config = InboxAutoAssignmentConfig.from_dict(_auto_assignment_config)

        avatar_url = d.pop("avatar_url", UNSET)

        def _parse_bot_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        bot_name = _parse_bot_name(d.pop("bot_name", UNSET))

        def _parse_branded_email_layout(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        branded_email_layout = _parse_branded_email_layout(d.pop("branded_email_layout", UNSET))

        def _parse_business_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        business_id = _parse_business_id(d.pop("business_id", UNSET))

        def _parse_business_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        business_name = _parse_business_name(d.pop("business_name", UNSET))

        def _parse_callback_webhook_url(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        callback_webhook_url = _parse_callback_webhook_url(d.pop("callback_webhook_url", UNSET))

        channel_id = d.pop("channel_id", UNSET)

        channel_type = d.pop("channel_type", UNSET)

        csat_survey_enabled = d.pop("csat_survey_enabled", UNSET)

        def _parse_email(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        email = _parse_email(d.pop("email", UNSET))

        enable_auto_assignment = d.pop("enable_auto_assignment", UNSET)

        enable_email_collect = d.pop("enable_email_collect", UNSET)

        greeting_enabled = d.pop("greeting_enabled", UNSET)

        def _parse_greeting_message(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        greeting_message = _parse_greeting_message(d.pop("greeting_message", UNSET))

        def _parse_hmac_mandatory(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        hmac_mandatory = _parse_hmac_mandatory(d.pop("hmac_mandatory", UNSET))

        id = d.pop("id", UNSET)

        def _parse_inbox_identifier(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        inbox_identifier = _parse_inbox_identifier(d.pop("inbox_identifier", UNSET))

        def _parse_instagram_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        instagram_id = _parse_instagram_id(d.pop("instagram_id", UNSET))

        def _parse_line_channel_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        line_channel_id = _parse_line_channel_id(d.pop("line_channel_id", UNSET))

        lock_to_single_conversation = d.pop("lock_to_single_conversation", UNSET)

        medium = d.pop("medium", UNSET)

        def _parse_messaging_service_sid(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        messaging_service_sid = _parse_messaging_service_sid(d.pop("messaging_service_sid", UNSET))

        name = d.pop("name", UNSET)

        def _parse_out_of_office_message(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        out_of_office_message = _parse_out_of_office_message(d.pop("out_of_office_message", UNSET))

        def _parse_page_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        page_id = _parse_page_id(d.pop("page_id", UNSET))

        def _parse_phone_number(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        phone_number = _parse_phone_number(d.pop("phone_number", UNSET))

        def _parse_profile_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        profile_id = _parse_profile_id(d.pop("profile_id", UNSET))

        def _parse_provider(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        provider = _parse_provider(d.pop("provider", UNSET))

        def _parse_provider_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        provider_name = _parse_provider_name(d.pop("provider_name", UNSET))

        def _parse_reply_time(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        reply_time = _parse_reply_time(d.pop("reply_time", UNSET))

        def _parse_selected_feature_flags(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                selected_feature_flags_type_0 = cast(list[str], data)

                return selected_feature_flags_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        selected_feature_flags = _parse_selected_feature_flags(
            d.pop("selected_feature_flags", UNSET)
        )

        sender_name_type = d.pop("sender_name_type", UNSET)

        timezone = d.pop("timezone", UNSET)

        def _parse_web_widget_script(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        web_widget_script = _parse_web_widget_script(d.pop("web_widget_script", UNSET))

        def _parse_website_token(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        website_token = _parse_website_token(d.pop("website_token", UNSET))

        def _parse_website_url(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        website_url = _parse_website_url(d.pop("website_url", UNSET))

        def _parse_welcome_tagline(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        welcome_tagline = _parse_welcome_tagline(d.pop("welcome_tagline", UNSET))

        def _parse_welcome_title(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        welcome_title = _parse_welcome_title(d.pop("welcome_title", UNSET))

        def _parse_widget_color(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        widget_color = _parse_widget_color(d.pop("widget_color", UNSET))

        _working_hours = d.pop("working_hours", UNSET)
        working_hours: list[InboxWorkingHoursItem] | Unset = UNSET
        if _working_hours is not UNSET:
            working_hours = []
            for working_hours_item_data in _working_hours:
                working_hours_item = InboxWorkingHoursItem.from_dict(working_hours_item_data)

                working_hours.append(working_hours_item)

        working_hours_enabled = d.pop("working_hours_enabled", UNSET)

        inbox = cls(
            allow_messages_after_resolved=allow_messages_after_resolved,
            auto_assignment_config=auto_assignment_config,
            avatar_url=avatar_url,
            bot_name=bot_name,
            branded_email_layout=branded_email_layout,
            business_id=business_id,
            business_name=business_name,
            callback_webhook_url=callback_webhook_url,
            channel_id=channel_id,
            channel_type=channel_type,
            csat_survey_enabled=csat_survey_enabled,
            email=email,
            enable_auto_assignment=enable_auto_assignment,
            enable_email_collect=enable_email_collect,
            greeting_enabled=greeting_enabled,
            greeting_message=greeting_message,
            hmac_mandatory=hmac_mandatory,
            id=id,
            inbox_identifier=inbox_identifier,
            instagram_id=instagram_id,
            line_channel_id=line_channel_id,
            lock_to_single_conversation=lock_to_single_conversation,
            medium=medium,
            messaging_service_sid=messaging_service_sid,
            name=name,
            out_of_office_message=out_of_office_message,
            page_id=page_id,
            phone_number=phone_number,
            profile_id=profile_id,
            provider=provider,
            provider_name=provider_name,
            reply_time=reply_time,
            selected_feature_flags=selected_feature_flags,
            sender_name_type=sender_name_type,
            timezone=timezone,
            web_widget_script=web_widget_script,
            website_token=website_token,
            website_url=website_url,
            welcome_tagline=welcome_tagline,
            welcome_title=welcome_title,
            widget_color=widget_color,
            working_hours=working_hours,
            working_hours_enabled=working_hours_enabled,
        )

        inbox.additional_properties = d
        return inbox

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
