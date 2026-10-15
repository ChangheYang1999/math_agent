"""Declarative role bindings; orchestration and persistence live elsewhere."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel


@dataclass(frozen=True, slots=True)
class RoleDescriptor:
    name: str
    prompt_filename: str
    output_schema: type[BaseModel]
    supports_web_search: bool = False
    secondary_output_schema: type[BaseModel] | None = None
