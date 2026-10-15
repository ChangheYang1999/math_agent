from math_research_agent.agents.base import RoleDescriptor
from math_research_agent.schemas import BackgroundOutput

BACKGROUND_ROLE = RoleDescriptor(
    name="background",
    prompt_filename="background.md",
    output_schema=BackgroundOutput,
    supports_web_search=True,
)
