"""Opt-in paid smoke test for the real Agents SDK boundary."""

import json
import os
from uuid import uuid4

import pytest

from math_research_agent.config import load_config
from math_research_agent.db import Database
from math_research_agent.model_gateway import OpenAIModelGateway
from math_research_agent.paths import Paths
from math_research_agent.schemas import EditorOutput


@pytest.mark.live
@pytest.mark.skipif(
    os.getenv("RUN_OPENAI_SMOKE_TEST") != "1",
    reason="set RUN_OPENAI_SMOKE_TEST=1 to authorize a paid OpenAI request",
)
@pytest.mark.asyncio
async def test_real_api_returns_and_audits_structured_output(tmp_path) -> None:
    db = Database.initialize(tmp_path, "live-smoke", "Live smoke")
    gateway = OpenAIModelGateway(db, Paths(tmp_path), load_config())

    result = await gateway.run_structured(
        role="editor",
        input_text=json.dumps(
            {
                "raw_content": "A theorem has assumptions and a conclusion.",
                "kind": "smoke_test",
                "editor_mode": "aggressive",
                "immutable_metadata": {},
            }
        ),
        output_type=EditorOutput,
        action_key=f"live-smoke:{uuid4().hex}",
    )

    assert isinstance(result.output, EditorOutput)
    assert result.output.edited_content.strip()
    row = db.one("SELECT status,raw_output_path FROM model_runs WHERE id=?", (result.run_id,))
    assert row == {"status": "COMPLETED", "raw_output_path": result.raw_path}
