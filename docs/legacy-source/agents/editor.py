from math_research_agent.agents.base import RoleDescriptor
from math_research_agent.schemas import EditorOutput

EDITOR_ROLE = RoleDescriptor(name="editor", prompt_filename="editor.md", output_schema=EditorOutput)
