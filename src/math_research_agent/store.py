"""Authoritative SQLite tree state. Model awaits never hold a transaction open."""

from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from .config import Config
from .paths import Paths
from .schemas import BootstrapResponse, ChildTask, ReportUpdate, concrete_prompt, require_english

SCHEMA = """
PRAGMA user_version=2;
CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE nodes(
 id TEXT PRIMARY KEY,parent_id TEXT REFERENCES nodes(id),goal TEXT NOT NULL,
 relative_weight REAL NOT NULL CHECK(relative_weight>=0 AND relative_weight<=1),
 status TEXT NOT NULL DEFAULT 'ACTIVE',runtime_state TEXT NOT NULL DEFAULT 'OK',
 research_state TEXT NOT NULL DEFAULT '',conversation_id TEXT,round_counter INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE UNIQUE INDEX one_root ON nodes((1)) WHERE parent_id IS NULL;
CREATE TABLE sessions(id TEXT PRIMARY KEY,node_id TEXT NOT NULL,model TEXT NOT NULL,url TEXT,
 bridge_session_id TEXT,bridge_client_id TEXT,bridge_model TEXT,bridge_effort TEXT,bridge_state TEXT,
 active INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE UNIQUE INDEX active_bridge_tab ON sessions(bridge_client_id)
 WHERE active=1 AND bridge_client_id IS NOT NULL;
CREATE UNIQUE INDEX active_bridge_chat ON sessions(bridge_session_id)
 WHERE active=1 AND bridge_session_id IS NOT NULL;
CREATE TABLE turns(id TEXT PRIMARY KEY,session_id TEXT NOT NULL REFERENCES sessions(id),
 prompt TEXT NOT NULL,raw_response TEXT,status TEXT NOT NULL DEFAULT 'PENDING',error TEXT,
 bridge_request_id TEXT,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE rounds(
 seq INTEGER PRIMARY KEY AUTOINCREMENT,id TEXT UNIQUE NOT NULL,node_id TEXT NOT NULL REFERENCES nodes(id),
 number INTEGER NOT NULL,previous_round_id TEXT REFERENCES rounds(id),kind TEXT NOT NULL DEFAULT 'research',
 task TEXT NOT NULL,prompt TEXT NOT NULL,prompt_version INTEGER NOT NULL DEFAULT 1,
 stage TEXT NOT NULL,report TEXT,report_accepted INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(node_id,number));
CREATE TABLE parent_responses(round_id TEXT PRIMARY KEY REFERENCES rounds(id),parent_id TEXT NOT NULL,
 payload TEXT NOT NULL,next_round_id TEXT NOT NULL REFERENCES rounds(id),source TEXT NOT NULL DEFAULT 'report',
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE artifacts(id TEXT PRIMARY KEY,node_id TEXT NOT NULL,round_id TEXT NOT NULL,
 artifact_type TEXT NOT NULL,version INTEGER NOT NULL,payload TEXT NOT NULL,content_hash TEXT NOT NULL,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,UNIQUE(round_id,artifact_type,version));
CREATE TABLE approvals(id TEXT PRIMARY KEY,node_id TEXT NOT NULL,round_id TEXT NOT NULL,
 artifact_type TEXT NOT NULL,payload TEXT NOT NULL,content_hash TEXT NOT NULL,version INTEGER NOT NULL,
 status TEXT NOT NULL DEFAULT 'PENDING',deferred INTEGER NOT NULL DEFAULT 0,
 decision TEXT,decided_at TEXT,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE feedback(id TEXT PRIMARY KEY,approval_id TEXT NOT NULL,node_id TEXT NOT NULL,
 round_id TEXT NOT NULL,original_comment TEXT NOT NULL,english_comment TEXT,
 status TEXT NOT NULL DEFAULT 'PENDING',response TEXT,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE review_messages(
 seq INTEGER PRIMARY KEY AUTOINCREMENT,id TEXT NOT NULL UNIQUE,approval_id TEXT NOT NULL,
 node_id TEXT NOT NULL,round_id TEXT NOT NULL,content_hash TEXT NOT NULL,version INTEGER NOT NULL,
 original_message TEXT NOT NULL,english_message TEXT,reply TEXT,display_reply TEXT,
 status TEXT NOT NULL DEFAULT 'PENDING',created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 completed_at TEXT);
CREATE TABLE messages(id TEXT PRIMARY KEY,sender_node_id TEXT NOT NULL,recipient_node_id TEXT NOT NULL,
 message TEXT NOT NULL,evidence_reference TEXT NOT NULL,reason TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'PENDING',
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE sections(id INTEGER PRIMARY KEY AUTOINCREMENT,node_id TEXT NOT NULL REFERENCES nodes(id),
 version INTEGER NOT NULL,body TEXT NOT NULL,claim_status TEXT NOT NULL,evidence_reference TEXT NOT NULL,
 independent_verification TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(node_id,version));
CREATE TABLE optional_jobs(id TEXT PRIMARY KEY,priority INTEGER NOT NULL,kind TEXT NOT NULL,
 actor_id TEXT NOT NULL,payload TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'PENDING',error TEXT,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE errors(id INTEGER PRIMARY KEY AUTOINCREMENT,node_id TEXT,operation TEXT NOT NULL,
 message TEXT NOT NULL,resolved INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE events(id INTEGER PRIMARY KEY AUTOINCREMENT,type TEXT NOT NULL,payload TEXT NOT NULL,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
"""


def migrate(c):
    """Upgrade Research Tree databases in place, leaving all existing rows intact."""
    version = c.execute("PRAGMA user_version").fetchone()[0]
    if version == 1:
        for name in (
            "bridge_session_id",
            "bridge_client_id",
            "bridge_model",
            "bridge_effort",
            "bridge_state",
        ):
            c.execute(f"ALTER TABLE sessions ADD COLUMN {name} TEXT")
        c.execute("ALTER TABLE turns ADD COLUMN bridge_request_id TEXT")
        c.execute(
            "CREATE UNIQUE INDEX active_bridge_tab ON sessions(bridge_client_id) "
            "WHERE active=1 AND bridge_client_id IS NOT NULL"
        )
        c.execute(
            "CREATE UNIQUE INDEX active_bridge_chat ON sessions(bridge_session_id) "
            "WHERE active=1 AND bridge_session_id IS NOT NULL"
        )
        c.execute(
            "CREATE TABLE review_messages("
            "seq INTEGER PRIMARY KEY AUTOINCREMENT,id TEXT NOT NULL UNIQUE,approval_id TEXT NOT NULL,"
            "node_id TEXT NOT NULL,round_id TEXT NOT NULL,content_hash TEXT NOT NULL,version INTEGER NOT NULL,"
            "original_message TEXT NOT NULL,english_message TEXT,reply TEXT,display_reply TEXT,"
            "status TEXT NOT NULL DEFAULT 'PENDING',created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,"
            "completed_at TEXT)"
        )
        c.execute("PRAGMA user_version=2")
        version = 2
    if version != 2:
        raise ValueError(f"Unsupported Research Tree schema version: {version}")


def encode(value) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return json.dumps(value, ensure_ascii=True, sort_keys=True)


def digest(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


def largest_remainder(weights: dict[str, float], total: int) -> dict[str, int]:
    if total < 0 or any(not math.isfinite(v) or v < 0 for v in weights.values()):
        raise ValueError("Invalid allocation")
    norm = sum(weights.values())
    if not norm:
        return {key: 0 for key in weights}
    quotas = {key: value / norm * total for key, value in weights.items()}
    result = {key: math.floor(q) for key, q in quotas.items()}
    order = sorted(weights, key=lambda key: (-(quotas[key] - result[key]), key))
    for key in order[: total - sum(result.values())]:
        result[key] += 1
    return result


class Store:
    def __init__(self, root: Path):
        self.root = Path(root).expanduser().resolve()
        self.path = self.root / "tree.db"
        if not self.path.is_file():
            if (self.root / "state.db").exists():
                raise ValueError(
                    "Legacy project preserved. Create a new Research Tree project; legacy databases are not migrated."
                )
            raise FileNotFoundError(f"Research Tree project does not exist: {self.root}")
        with self.transaction() as c:
            migrate(c)
        self.config = Config.model_validate(self.setting("config"))

    @classmethod
    def initialize(cls, root: Path, goal: str, config: Config | None = None) -> Store:
        require_english(goal)
        if not goal.strip():
            raise ValueError("An English mathematical goal is required")
        root = Path(root).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        if (root / "state.db").exists():
            raise ValueError("Existing legacy project preserved; choose a new project directory")
        with (root / "tree.db").open("xb"):
            pass
        cfg = config or Config()
        with sqlite3.connect(root / "tree.db") as c:
            c.executescript(SCHEMA)
            for key, val in {
                "config": cfg.model_dump(mode="json"),
                "project_status": "ACTIVE",
                "manual_review_enabled": cfg.manual_review_enabled,
                "report_dirty": True,
                "request_epoch": 0,
            }.items():
                c.execute("INSERT INTO settings VALUES(?,?)", (key, encode(val)))
            c.execute(
                "INSERT INTO nodes(id,parent_id,goal,relative_weight) VALUES(?,NULL,?,1)",
                ("root", goal.strip()),
            )
        store = cls(root)
        Paths(root).atomic_write(
            "project.yaml",
            "# Research Tree configuration is also persisted in tree.db.\n"
            + __import__("yaml").safe_dump(cfg.model_dump(mode="json")),
        )
        store.build_report()
        return store

    @contextmanager
    def connection(self):
        c = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys=ON")
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA busy_timeout=10000")
        try:
            yield c
        finally:
            c.close()

    @contextmanager
    def transaction(self):
        with self.connection() as c:
            c.execute("BEGIN IMMEDIATE")
            try:
                yield c
                c.commit()
            except BaseException:
                c.rollback()
                raise

    def query(self, sql, params=()):
        with self.connection() as c:
            return [dict(r) for r in c.execute(sql, params).fetchall()]

    def one(self, sql, params=()):
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def execute(self, sql, params=()):
        with self.transaction() as c:
            cur = c.execute(sql, params)
            return cur.lastrowid

    def setting(self, key, default=None):
        row = self.one("SELECT value FROM settings WHERE key=?", (key,))
        return json.loads(row["value"]) if row else default

    def set_setting(self, key, value):
        self.execute(
            "INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, encode(value)),
        )

    def event(self, event_type, payload, c=None):
        sql = "INSERT INTO events(type,payload) VALUES(?,?)"
        if c is not None:
            c.execute(sql, (event_type, encode(payload)))
        else:
            self.execute(sql, (event_type, encode(payload)))

    def node(self, node_id):
        row = self.one("SELECT * FROM nodes WHERE id=?", (node_id,))
        if not row:
            raise ValueError(f"Unknown node: {node_id}")
        return row

    def children(self, node_id):
        return self.query(
            "SELECT * FROM nodes WHERE parent_id=? ORDER BY created_at,id", (node_id,)
        )

    def is_internal(self, node_id):
        return node_id == "root" or bool(self.children(node_id))

    def active(self, node_id):
        node = self.node(node_id)
        return (
            node["status"] == "ACTIVE"
            and node["relative_weight"] > 0
            and (not node["parent_id"] or self.active(node["parent_id"]))
        )

    def artifact(self, c, node_id, round_id, artifact_type, payload, version=1):
        artifact_id = f"{round_id}:{artifact_type}:{version}"
        content_hash = digest(payload)
        c.execute(
            "INSERT INTO artifacts(id,node_id,round_id,artifact_type,version,payload,content_hash) VALUES(?,?,?,?,?,?,?)",
            (artifact_id, node_id, round_id, artifact_type, version, payload, content_hash),
        )
        review = json.loads(
            c.execute("SELECT value FROM settings WHERE key='manual_review_enabled'").fetchone()[0]
        )
        status = "PENDING" if review else "AUTO_APPROVED"
        c.execute(
            "INSERT INTO approvals(id,node_id,round_id,artifact_type,payload,content_hash,version,status,decision,decided_at) VALUES(?,?,?,?,?,?,?,?,?,CASE WHEN ? THEN CURRENT_TIMESTAMP ELSE NULL END)",
            (
                artifact_id,
                node_id,
                round_id,
                artifact_type,
                payload,
                content_hash,
                version,
                status,
                None if review else "auto",
                not review,
            ),
        )
        self.event(
            "approval_pending" if review else "auto_approval",
            {"artifact_id": artifact_id, "content_hash": content_hash},
            c,
        )
        return review

    def create_round(self, node_id, task, previous_round_id=None, kind="research", c=None):
        concrete_prompt(task)
        if c is None:
            with self.transaction() as connection:
                return self.create_round(node_id, task, previous_round_id, kind, connection)
        n = dict(c.execute("SELECT * FROM nodes WHERE id=?", (node_id,)).fetchone())
        if c.execute(
            "SELECT id FROM rounds WHERE node_id=? AND stage NOT IN ('RESPONDED','SUPERSEDED')",
            (node_id,),
        ).fetchone():
            raise ValueError("A leaf already has an unfinished round")
        if previous_round_id:
            old = c.execute(
                "SELECT * FROM rounds WHERE id=? AND node_id=?", (previous_round_id, node_id)
            ).fetchone()
            if not old or not old["report"]:
                raise ValueError("Previous leaf round must have a durable report")
        number = n["round_counter"] + 1
        round_id = f"{node_id}-r{number:06d}"
        from .scheduler import render_prompt
        from .schemas import LeafRoundReport

        prompt = render_prompt(
            "leaf_round",
            {
                "kind": "leaf",
                "node_id": node_id,
                "round_id": round_id,
                "goal": n["goal"],
                "task": task,
                "research_state": n["research_state"],
            },
            LeafRoundReport,
        )
        stage = (
            "PROMPT_APPROVAL"
            if self.artifact(c, node_id, round_id, "prompt", prompt)
            else "PROMPT_READY"
        )
        c.execute(
            "INSERT INTO rounds(id,node_id,number,previous_round_id,kind,task,prompt,stage) VALUES(?,?,?,?,?,?,?,?)",
            (round_id, node_id, number, previous_round_id, kind, task, prompt, stage),
        )
        c.execute(
            "UPDATE nodes SET round_counter=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (number, node_id),
        )
        self.event("prompt_stored", {"node_id": node_id, "round_id": round_id}, c)
        return round_id

    def revise_prompt(self, round_id, task, *, feedback_id=None, response=None):
        concrete_prompt(task)
        from .scheduler import render_prompt
        from .schemas import LeafRoundReport

        with self.transaction() as c:
            r = dict(c.execute("SELECT * FROM rounds WHERE id=?", (round_id,)).fetchone())
            if feedback_id:
                feedback = c.execute(
                    "SELECT * FROM feedback WHERE id=? AND round_id=?", (feedback_id, round_id)
                ).fetchone()
                if not feedback:
                    raise ValueError("Revision feedback does not belong to this round")
                if feedback["status"] == "COMPLETED":
                    return r["prompt_version"]
            if r["stage"] not in ("PROMPT_APPROVAL", "PROMPT_READY", "PROMPT_DISCUSSION"):
                raise ValueError("Cannot revise a prompt after dispatch")
            n = dict(c.execute("SELECT * FROM nodes WHERE id=?", (r["node_id"],)).fetchone())
            prompt = render_prompt(
                "leaf_round",
                {
                    "kind": "leaf",
                    "node_id": n["id"],
                    "round_id": r["id"],
                    "goal": n["goal"],
                    "task": task,
                    "research_state": n["research_state"],
                },
                LeafRoundReport,
            )
            version = r["prompt_version"] + 1
            c.execute(
                "UPDATE approvals SET status='SUPERSEDED' WHERE round_id=? AND artifact_type='prompt'",
                (round_id,),
            )
            review = self.artifact(c, n["id"], round_id, "prompt", prompt, version)
            c.execute(
                "UPDATE rounds SET task=?,prompt=?,prompt_version=?,stage=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (task, prompt, version, "PROMPT_APPROVAL" if review else "PROMPT_READY", round_id),
            )
            if feedback_id:
                c.execute(
                    "UPDATE feedback SET status='COMPLETED',response=? WHERE id=?",
                    (response if isinstance(response, str) else encode(response), feedback_id),
                )
            return version

    def _finish_optional(self, c, job_id=None, *, report_dirty=False):
        if job_id:
            c.execute("UPDATE optional_jobs SET status='COMPLETED' WHERE id=?", (job_id,))
        if report_dirty:
            c.execute("UPDATE settings SET value='true' WHERE key='report_dirty'")

    def split(self, node_id, children, *, actor_id=None, job_id=None):
        tasks = [x if isinstance(x, ChildTask) else ChildTask.model_validate(x) for x in children]
        BootstrapResponse(children=tasks)
        node = self.node(node_id)
        if actor_id is not None and actor_id not in (node_id, node["parent_id"]):
            raise ValueError("Only a node or its parent can authorize its split")
        with self.transaction() as c:
            if c.execute("SELECT id FROM nodes WHERE parent_id=?", (node_id,)).fetchone():
                raise ValueError("Use a child split or reweight for an existing internal node")
            capacity = self.allocation(c)[node_id]["leaf_capacity"]
            if len(tasks) > capacity:
                raise ValueError(
                    f"Split needs {len(tasks)} active leaf slots but this node has capacity {capacity}; "
                    "defer the split or change the parent's allocation"
                )
            shares = largest_remainder(
                {str(i): task.relative_weight for i, task in enumerate(tasks)}, capacity
            )
            if any(slots == 0 for slots in shares.values()):
                raise ValueError(
                    "Split weights leave a new task without leaf capacity; "
                    "defer the split or increase its allocated importance"
                )
            live = c.execute(
                "SELECT * FROM rounds WHERE node_id=? AND stage NOT IN ('RESPONDED','SUPERSEDED')",
                (node_id,),
            ).fetchone()
            if live:
                # A saved undispatched next prompt remains in immutable artifacts/history.
                if (
                    live["stage"] not in ("PROMPT_APPROVAL", "PROMPT_READY")
                    or not live["previous_round_id"]
                ):
                    raise ValueError("Finish the leaf report and parent response before splitting")
                if not c.execute(
                    "SELECT 1 FROM parent_responses WHERE round_id=?", (live["previous_round_id"],)
                ).fetchone():
                    raise ValueError("Missing mandatory parent response")
                c.execute("UPDATE rounds SET stage='SUPERSEDED' WHERE id=?", (live["id"],))
                c.execute(
                    "UPDATE approvals SET status='SUPERSEDED' WHERE round_id=? AND status='PENDING'",
                    (live["id"],),
                )
            if node_id != "root":
                c.execute("UPDATE sessions SET active=0 WHERE node_id=?", (node_id,))
                c.execute("UPDATE nodes SET conversation_id=NULL WHERE id=?", (node_id,))
                c.execute(
                    "INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    ("coordinator_ready:" + node_id, "false"),
                )
            ids = []
            for task in tasks:
                child_id = "n-" + uuid4().hex[:12]
                c.execute(
                    "INSERT INTO nodes(id,parent_id,goal,relative_weight) VALUES(?,?,?,?)",
                    (child_id, node_id, task.goal, task.relative_weight),
                )
                self.create_round(child_id, task.initial_prompt, c=c)
                ids.append(child_id)
            self.event("split", {"node_id": node_id, "children": ids}, c)
            self._finish_optional(c, job_id, report_dirty=True)
        return ids

    def reweight(self, parent_id, weights, *, job_id=None):
        children = self.children(parent_id)
        if set(weights) != {n["id"] for n in children}:
            raise ValueError("Reweight must include every sibling atomically")
        if (
            any(not math.isfinite(w) or w < 0 or w > 1 for w in weights.values())
            or abs(sum(weights.values()) - 1) > 1e-8
        ):
            raise ValueError("Sibling weights must be finite, nonnegative and sum to one")
        if any(n["status"] != "ACTIVE" and weights[n["id"]] > 0 for n in children):
            raise ValueError("Inactive children cannot receive active weight; resume them first")
        with self.transaction() as c:
            previous = {n["id"]: n["relative_weight"] for n in children}
            for node in children:
                weight = weights[node["id"]]
                c.execute(
                    "UPDATE nodes SET relative_weight=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (weight, node["id"]),
                )
            self.event(
                "reweight", {"parent_id": parent_id, "previous": previous, "weights": weights}, c
            )
            self._finish_optional(c, job_id)

    def set_node_status(self, node_id, status, *, job_id=None):
        if status not in ("ACTIVE", "PAUSED", "COMPLETED", "ABANDONED"):
            raise ValueError("Invalid node status")
        node = self.node(node_id)
        with self.transaction() as c:
            if status == "ACTIVE" and node["status"] != "ACTIVE" and node["relative_weight"] == 0:
                history = c.execute(
                    "SELECT payload FROM events WHERE type='node_status' ORDER BY id DESC"
                ).fetchall()
                former = next(
                    (
                        json.loads(h["payload"]).get("previous_weight", 0)
                        for h in history
                        if json.loads(h["payload"]).get("node_id") == node_id
                        and json.loads(h["payload"]).get("previous_weight", 0) > 0
                    ),
                    0.5,
                )
                c.execute("UPDATE nodes SET relative_weight=? WHERE id=?", (former, node_id))
            c.execute(
                "UPDATE nodes SET status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (status, node_id),
            )
            if node["parent_id"]:
                siblings = [
                    dict(x)
                    for x in c.execute(
                        "SELECT * FROM nodes WHERE parent_id=?", (node["parent_id"],)
                    )
                ]
                active = [x for x in siblings if x["status"] == "ACTIVE"]
                total = sum(x["relative_weight"] for x in active)
                if active:
                    for s in siblings:
                        share = (
                            (s["relative_weight"] / total if total else 1 / len(active))
                            if s["status"] == "ACTIVE"
                            else 0
                        )
                        c.execute("UPDATE nodes SET relative_weight=? WHERE id=?", (share, s["id"]))
            self.event(
                "node_status",
                {"node_id": node_id, "status": status, "previous_weight": node["relative_weight"]},
                c,
            )
            self._finish_optional(c, job_id, report_dirty=True)

    def allocation(self, c=None):
        """Weighted upper limits and actual useful leaves; idle capacity is normal."""
        rows = (
            self.query("SELECT * FROM nodes ORDER BY id")
            if c is None
            else [dict(row) for row in c.execute("SELECT * FROM nodes ORDER BY id")]
        )
        lookup = {n["id"]: n for n in rows}
        children = {n["id"]: [] for n in rows}
        for n in rows:
            if n["parent_id"]:
                children[n["parent_id"]].append(n)
        result = {}

        def visit(n, absolute, slots, anc_active):
            active = anc_active and n["status"] == "ACTIVE" and n["relative_weight"] > 0
            slots = slots if active else 0
            kids = children[n["id"]]
            result[n["id"]] = {
                **n,
                "absolute_weight": absolute,
                "leaf_capacity": slots,
                # Compatibility with saved/dashboard v0.2 consumers.
                "target_leaves": slots,
                "role": "Extra High internal" if kids or n["id"] == "root" else "Pro leaf",
                "children_ids": [x["id"] for x in kids],
                "effective_active": active,
            }
            shares = {k["id"]: k["relative_weight"] if k["status"] == "ACTIVE" else 0 for k in kids}
            targets = largest_remainder(shares, slots)
            count = 0
            for k in kids:
                visit(k, absolute * k["relative_weight"], targets[k["id"]], active)
                count += result[k["id"]]["active_leaves"]
            result[n["id"]]["active_leaves"] = (
                count if kids else (int(active and slots > 0) if n["id"] != "root" else 0)
            )
            unused = max(0, slots - result[n["id"]]["active_leaves"])
            result[n["id"]]["unused_capacity"] = unused
            result[n["id"]]["underfilled"] = unused

        visit(lookup["root"], 1.0, self.config.target_active_leaves, True)
        return result

    def update_section(self, actor_id, update, *, job_id=None):
        update = update if isinstance(update, ReportUpdate) else ReportUpdate.model_validate(update)
        if update.node_id != actor_id:
            raise ValueError("An agent may update only its own report section")
        self.node(actor_id)
        if not update.significant:
            return False
        if update.claim_status == "VERIFIED" and not update.independent_verification.strip():
            raise ValueError(
                "Verified claims require a recorded independent verification reference"
            )
        with self.transaction() as c:
            version = c.execute(
                "SELECT COALESCE(MAX(version),0)+1 FROM sections WHERE node_id=?", (actor_id,)
            ).fetchone()[0]
            c.execute(
                "INSERT INTO sections(node_id,version,body,claim_status,evidence_reference,independent_verification) VALUES(?,?,?,?,?,?)",
                (
                    actor_id,
                    version,
                    update.body,
                    update.claim_status,
                    update.evidence_reference,
                    update.independent_verification,
                ),
            )
            self.event("section_updated", {"node_id": actor_id, "version": version}, c)
            self._finish_optional(c, job_id, report_dirty=True)
        return True

    def build_report(self):
        lines = [
            "# Research Report",
            "",
            "Model-proposed claims are not independently verified unless an explicit verification reference is recorded.",
            "",
        ]

        def visit(node, depth, number):
            title = f"{number} {' '.join(node['goal'].split())} [{node['status']}]"
            lines.extend(
                [
                    f'<a id="{node["id"]}"></a>',
                    f"{'#' * min(depth + 1, 6)} {title}",
                    "",
                    f"Node: `{node['id']}`",
                    "",
                ]
            )
            section = self.one(
                "SELECT * FROM sections WHERE node_id=? ORDER BY version DESC LIMIT 1",
                (node["id"],),
            )
            if section:
                lines.extend(
                    [
                        f"Claim status: **{section['claim_status']}**",
                        "",
                        re.sub(r"^#{1,6}\s+(.+)$", r"**\1**", section["body"], flags=re.MULTILINE),
                        "",
                        f"Evidence: {section['evidence_reference']}",
                        "",
                    ]
                )
                if section["independent_verification"]:
                    lines.extend(
                        [f"Independent verification: {section['independent_verification']}", ""]
                    )
            else:
                lines.extend(["No significant findings published yet.", ""])
            for i, child in enumerate(self.children(node["id"]), 1):
                visit(child, depth + 1, f"{number}.{i}")

        visit(self.node("root"), 1, "1")
        content = "\n".join(lines)
        Paths(self.root).atomic_write("RESEARCH_REPORT.md", content)
        self.set_setting("report_dirty", False)
        return content
