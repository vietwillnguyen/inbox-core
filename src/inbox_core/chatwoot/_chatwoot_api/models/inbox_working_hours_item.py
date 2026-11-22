from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast


T = TypeVar("T", bound="InboxWorkingHoursItem")


@_attrs_define
class InboxWorkingHoursItem:
    """
    Attributes:
        close_hour (float | None | Unset): Hour when inbox closes (0-23)
        close_minutes (float | None | Unset): Minutes of the hour when inbox closes (0-59)
        closed_all_day (bool | Unset): Whether the inbox is closed for the entire day
        day_of_week (float | Unset): Day of the week (0-6, where 0 is Sunday)
        open_all_day (bool | Unset): Whether the inbox is open for the entire day
        open_hour (float | None | Unset): Hour when inbox opens (0-23)
        open_minutes (float | None | Unset): Minutes of the hour when inbox opens (0-59)
    """

    close_hour: float | None | Unset = UNSET
    close_minutes: float | None | Unset = UNSET
    closed_all_day: bool | Unset = UNSET
    day_of_week: float | Unset = UNSET
    open_all_day: bool | Unset = UNSET
    open_hour: float | None | Unset = UNSET
    open_minutes: float | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        close_hour: float | None | Unset
        if isinstance(self.close_hour, Unset):
            close_hour = UNSET
        else:
            close_hour = self.close_hour

        close_minutes: float | None | Unset
        if isinstance(self.close_minutes, Unset):
            close_minutes = UNSET
        else:
            close_minutes = self.close_minutes

        closed_all_day = self.closed_all_day

        day_of_week = self.day_of_week

        open_all_day = self.open_all_day

        open_hour: float | None | Unset
        if isinstance(self.open_hour, Unset):
            open_hour = UNSET
        else:
            open_hour = self.open_hour

        open_minutes: float | None | Unset
        if isinstance(self.open_minutes, Unset):
            open_minutes = UNSET
        else:
            open_minutes = self.open_minutes

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if close_hour is not UNSET:
            field_dict["close_hour"] = close_hour
        if close_minutes is not UNSET:
            field_dict["close_minutes"] = close_minutes
        if closed_all_day is not UNSET:
            field_dict["closed_all_day"] = closed_all_day
        if day_of_week is not UNSET:
            field_dict["day_of_week"] = day_of_week
        if open_all_day is not UNSET:
            field_dict["open_all_day"] = open_all_day
        if open_hour is not UNSET:
            field_dict["open_hour"] = open_hour
        if open_minutes is not UNSET:
            field_dict["open_minutes"] = open_minutes

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_close_hour(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        close_hour = _parse_close_hour(d.pop("close_hour", UNSET))

        def _parse_close_minutes(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        close_minutes = _parse_close_minutes(d.pop("close_minutes", UNSET))

        closed_all_day = d.pop("closed_all_day", UNSET)

        day_of_week = d.pop("day_of_week", UNSET)

        open_all_day = d.pop("open_all_day", UNSET)

        def _parse_open_hour(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        open_hour = _parse_open_hour(d.pop("open_hour", UNSET))

        def _parse_open_minutes(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        open_minutes = _parse_open_minutes(d.pop("open_minutes", UNSET))

        inbox_working_hours_item = cls(
            close_hour=close_hour,
            close_minutes=close_minutes,
            closed_all_day=closed_all_day,
            day_of_week=day_of_week,
            open_all_day=open_all_day,
            open_hour=open_hour,
            open_minutes=open_minutes,
        )

        inbox_working_hours_item.additional_properties = d
        return inbox_working_hours_item

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
