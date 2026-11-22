from typing import Literal

AgentRole = Literal["administrator", "agent"]

AGENT_ROLE_VALUES: set[AgentRole] = {
    "administrator",
    "agent",
}


def check_agent_role(value: str) -> AgentRole:
    if value in AGENT_ROLE_VALUES:
        return value
    raise TypeError(f"Unexpected value {value!r}. Expected one of {AGENT_ROLE_VALUES!r}")
