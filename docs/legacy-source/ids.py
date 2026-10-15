"""Canonical IDs are allocated only inside caller-owned transactions."""

import re
import sqlite3

PREFIXES = {"insight": "I", "branch": "B", "report": "R"}


def next_id(connection: sqlite3.Connection, kind: str) -> str:
    prefix = PREFIXES[kind]
    row = connection.execute(
        "INSERT INTO counters(kind,value) VALUES(?,1) "
        "ON CONFLICT(kind) DO UPDATE SET value=value+1 RETURNING value",
        (kind,),
    ).fetchone()
    return f"{prefix}-{row[0]:06d}"


def probe_id(branch_public_id: str, round_number: int) -> str:
    if not re.fullmatch(r"B-\d{6,}", branch_public_id) or round_number < 1:
        raise ValueError("Invalid branch ID or probe round")
    return f"Q-{branch_public_id[2:]}.{round_number}"
