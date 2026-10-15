from math_research_agent.agents.base import RoleDescriptor
from math_research_agent.schemas import ProbeAssessment, ProbeFormulation

PROBE_MANAGER_ROLE = RoleDescriptor(
    name="probe_manager",
    prompt_filename="probe_manager.md",
    output_schema=ProbeFormulation,
    secondary_output_schema=ProbeAssessment,
)
