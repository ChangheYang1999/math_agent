from math_research_agent.agents.base import RoleDescriptor
from math_research_agent.schemas import SolverOutput

SOLVER_ROLE = RoleDescriptor(name="solver", prompt_filename="solver.md", output_schema=SolverOutput)
