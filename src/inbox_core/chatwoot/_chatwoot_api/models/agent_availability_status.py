from typing import Literal

AgentAvailabilityStatus = Literal["busy", "offline", "online"]

AGENT_AVAILABILITY_STATUS_VALUES: set[AgentAvailabilityStatus] = {
    "busy",
    "offline",
    "online",
}


def check_agent_availability_status(value: str) -> AgentAvailabilityStatus:
    if value in AGENT_AVAILABILITY_STATUS_VALUES:
        return value
    raise TypeError(
        f"Unexpected value {value!r}. Expected one of {AGENT_AVAILABILITY_STATUS_VALUES!r}"
    )
