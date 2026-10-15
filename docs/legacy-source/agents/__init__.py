"""Typed role descriptors without application-level handoffs or persistence."""

from math_research_agent.agents.background import BACKGROUND_ROLE
from math_research_agent.agents.base import RoleDescriptor
from math_research_agent.agents.brain import BRAIN_ROLE
from math_research_agent.agents.editor import EDITOR_ROLE
from math_research_agent.agents.probe_manager import PROBE_MANAGER_ROLE
from math_research_agent.agents.solver import SOLVER_ROLE

ROLE_DESCRIPTORS: dict[str, RoleDescriptor] = {
    role.name: role
    for role in (BACKGROUND_ROLE, BRAIN_ROLE, PROBE_MANAGER_ROLE, SOLVER_ROLE, EDITOR_ROLE)
}

__all__ = [
    "BACKGROUND_ROLE",
    "BRAIN_ROLE",
    "EDITOR_ROLE",
    "PROBE_MANAGER_ROLE",
    "ROLE_DESCRIPTORS",
    "SOLVER_ROLE",
    "RoleDescriptor",
]
