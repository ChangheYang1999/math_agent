"""Narrow editor capability: text in, text and warnings out, no state authority."""

from __future__ import annotations

import json
import re
from typing import Any

from .schemas import EditorOutput


class EditorFailure(RuntimeError):
    pass


class EditorService:
    def __init__(self, gateway: Any):
        self.gateway = gateway

    async def edit(
        self, *, key: str, content: str, kind: str, mode: str, metadata: dict[str, str]
    ) -> Any:
        result = await self.gateway.run_structured(
            role="editor",
            action_key=f"edit:{key}",
            output_type=EditorOutput,
            input_text=json.dumps(
                {
                    "raw_content": content,
                    "kind": kind,
                    "editor_mode": mode,
                    "immutable_metadata": metadata,
                },
                ensure_ascii=False,
            ),
            metadata=metadata,
        )
        if not result.output.edited_content.strip():
            raise EditorFailure("Editor returned empty canonical content")
        pattern = r"\b(?:[IBR]-\d{6,}|Q-\d{6,}\.\d+)\b"
        before = set(re.findall(pattern, content))
        after = set(re.findall(pattern, result.output.edited_content))
        if before != after:
            raise EditorFailure("Editor changed canonical identifiers in prose")
        return result
