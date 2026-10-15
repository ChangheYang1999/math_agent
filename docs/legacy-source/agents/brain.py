from math_research_agent.agents.base import RoleDescriptor
from math_research_agent.schemas import BrainOutput

BRAIN_ROLE = RoleDescriptor(name="brain", prompt_filename="brain.md", output_schema=BrainOutput)
