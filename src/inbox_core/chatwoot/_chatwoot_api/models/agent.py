from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.agent_availability_status import AgentAvailabilityStatus
from ..models.agent_availability_status import check_agent_availability_status
from ..models.agent_role import AgentRole
from ..models.agent_role import check_agent_role
from ..types import UNSET, Unset
from typing import cast


T = TypeVar("T", bound="Agent")


@_attrs_define
class Agent:
    """
    Attributes:
        account_id (int | Unset):
        auto_offline (bool | Unset): Whether the agent is automatically marked offline when they are away.
        availability_status (AgentAvailabilityStatus | Unset): The effective availability status of the agent, derived
            from the configured availability, auto-offline setting, and current presence. To update an agent's configured
            availability, use the availability field in create or update requests.
        available_name (str | Unset): The available name of the agent
        confirmed (bool | Unset): Whether the agent has confirmed their email address.
        custom_role_id (int | None | Unset): The custom role id of the agent
        email (str | Unset): The email of the agent
        id (int | Unset):
        name (str | Unset): The name of the agent
        role (AgentRole | Unset): The role of the agent
        thumbnail (str | Unset): The thumbnail of the agent
    """

    account_id: int | Unset = UNSET
    auto_offline: bool | Unset = UNSET
    availability_status: AgentAvailabilityStatus | Unset = UNSET
    available_name: str | Unset = UNSET
    confirmed: bool | Unset = UNSET
    custom_role_id: int | None | Unset = UNSET
    email: str | Unset = UNSET
    id: int | Unset = UNSET
    name: str | Unset = UNSET
    role: AgentRole | Unset = UNSET
    thumbnail: str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        account_id = self.account_id

        auto_offline = self.auto_offline

        availability_status: str | Unset = UNSET
        if not isinstance(self.availability_status, Unset):
            availability_status = self.availability_status

        available_name = self.available_name

        confirmed = self.confirmed

        custom_role_id: int | None | Unset
        if isinstance(self.custom_role_id, Unset):
            custom_role_id = UNSET
        else:
            custom_role_id = self.custom_role_id

        email = self.email

        id = self.id

        name = self.name

        role: str | Unset = UNSET
        if not isinstance(self.role, Unset):
            role = self.role

        thumbnail = self.thumbnail

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if account_id is not UNSET:
            field_dict["account_id"] = account_id
        if auto_offline is not UNSET:
            field_dict["auto_offline"] = auto_offline
        if availability_status is not UNSET:
            field_dict["availability_status"] = availability_status
        if available_name is not UNSET:
            field_dict["available_name"] = available_name
        if confirmed is not UNSET:
            field_dict["confirmed"] = confirmed
        if custom_role_id is not UNSET:
            field_dict["custom_role_id"] = custom_role_id
        if email is not UNSET:
            field_dict["email"] = email
        if id is not UNSET:
            field_dict["id"] = id
        if name is not UNSET:
            field_dict["name"] = name
        if role is not UNSET:
            field_dict["role"] = role
        if thumbnail is not UNSET:
            field_dict["thumbnail"] = thumbnail

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        account_id = d.pop("account_id", UNSET)

        auto_offline = d.pop("auto_offline", UNSET)

        _availability_status = d.pop("availability_status", UNSET)
        availability_status: AgentAvailabilityStatus | Unset
        if isinstance(_availability_status, Unset):
            availability_status = UNSET
        else:
            availability_status = check_agent_availability_status(_availability_status)

        available_name = d.pop("available_name", UNSET)

        confirmed = d.pop("confirmed", UNSET)

        def _parse_custom_role_id(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        custom_role_id = _parse_custom_role_id(d.pop("custom_role_id", UNSET))

        email = d.pop("email", UNSET)

        id = d.pop("id", UNSET)

        name = d.pop("name", UNSET)

        _role = d.pop("role", UNSET)
        role: AgentRole | Unset
        if isinstance(_role, Unset):
            role = UNSET
        else:
            role = check_agent_role(_role)

        thumbnail = d.pop("thumbnail", UNSET)

        agent = cls(
            account_id=account_id,
            auto_offline=auto_offline,
            availability_status=availability_status,
            available_name=available_name,
            confirmed=confirmed,
            custom_role_id=custom_role_id,
            email=email,
            id=id,
            name=name,
            role=role,
            thumbnail=thumbnail,
        )

        agent.additional_properties = d
        return agent

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
