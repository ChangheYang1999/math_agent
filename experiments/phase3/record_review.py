"""Read-only observations of the running, explicitly simulated review dashboard."""

import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import urlopen

root = Path(__file__).resolve().parent
label = sys.argv[1]
if not label.replace("_", "").isalnum():
    raise ValueError("Use a simple observation label")
with urlopen("http://127.0.0.1:8766/api/state", timeout=10) as response:
    state = json.load(response)
pending = [a for a in state["approvals"] if a["status"] == "PENDING"]
observation = {
    "observed_at": datetime.now(UTC).isoformat(),
    "classification": "REAL_LOCAL_DASHBOARD_WITH_OFFLINE_SIMULATED_TRANSPORT",
    "label": label,
    "pending": [
        {k: a[k] for k in ("id", "node_id", "round_id", "artifact_type", "version", "content_hash", "status")}
        for a in pending
    ],
    "leaf_turn_count": sum(t["id"].startswith("leaf:") for t in state.get("turns", [])),
    "review_messages": state.get("review_messages", []),
    "feedback": state.get("feedback", []),
    "state": state,
}
for item in pending:
    from urllib.parse import quote

    with urlopen("http://127.0.0.1:8766/review-original?id=" + quote(item["id"], safe=""), timeout=10) as response:
        raw = response.read()
    item["original_route_sha256"] = hashlib.sha256(raw).hexdigest()
    item["original_route_matches_hash"] = item["original_route_sha256"] == item["content_hash"]
with (root / ("review_" + label + ".json")).open("x") as file:
    json.dump(observation, file, indent=2, ensure_ascii=False)
    file.write("\n")
print(json.dumps({k: observation[k] for k in ("label", "pending", "leaf_turn_count")}))
