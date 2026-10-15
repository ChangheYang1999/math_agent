"""Finite workflow states and their legal transitions."""

from __future__ import annotations

from enum import StrEnum
from types import MappingProxyType
from typing import Literal, TypeAlias

AgentRole: TypeAlias = Literal["background", "brain", "probe_manager", "solver", "editor"]
EditorMode: TypeAlias = Literal["aggressive", "proof_safe", "prompt"]
Priority: TypeAlias = Literal["low", "medium", "high"]


class BrainCycleStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class InsightStatus(StrEnum):
    ACTIVE = "ACTIVE"
    STRENGTHENED = "STRENGTHENED"
    WEAKENED = "WEAKENED"
    REFUTED = "REFUTED"
    SUPERSEDED = "SUPERSEDED"
    ARCHIVED = "ARCHIVED"


class BranchStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    WAITING_FOR_SOLVER = "WAITING_FOR_SOLVER"
    WAITING_FOR_MANAGER = "WAITING_FOR_MANAGER"
    CONFIRMED = "CONFIRMED"
    REFUTED = "REFUTED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    MODIFIED = "MODIFIED"
    TOO_HARD = "TOO_HARD"
    ABANDONED = "ABANDONED"
    FAILED = "FAILED"


class ProbeStatus(StrEnum):
    DRAFTED = "DRAFTED"
    EDITED = "EDITED"
    SOLVING = "SOLVING"
    SOLVED = "SOLVED"
    ASSESSED = "ASSESSED"
    FAILED = "FAILED"


class SolverVerdict(StrEnum):
    PROVED = "PROVED"
    DISPROVED = "DISPROVED"
    INCONCLUSIVE = "INCONCLUSIVE"


class JobStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


TERMINAL_BRANCH_STATES = frozenset(
    {
        BranchStatus.CONFIRMED,
        BranchStatus.REFUTED,
        BranchStatus.PARTIALLY_SUPPORTED,
        BranchStatus.MODIFIED,
        BranchStatus.TOO_HARD,
        BranchStatus.ABANDONED,
        BranchStatus.FAILED,
    }
)
TERMINAL_PROBE_STATES = frozenset({ProbeStatus.ASSESSED, ProbeStatus.FAILED})
TERMINAL_BRAIN_CYCLE_STATES = frozenset({BrainCycleStatus.COMPLETED, BrainCycleStatus.FAILED})
TERMINAL_JOB_STATES = frozenset({JobStatus.COMPLETED})

BRANCH_TRANSITIONS = MappingProxyType(
    {
        BranchStatus.QUEUED: frozenset(
            {BranchStatus.RUNNING, BranchStatus.ABANDONED, BranchStatus.FAILED}
        ),
        BranchStatus.RUNNING: frozenset(
            {
                BranchStatus.WAITING_FOR_SOLVER,
                BranchStatus.TOO_HARD,
                BranchStatus.ABANDONED,
                BranchStatus.FAILED,
            }
        ),
        BranchStatus.WAITING_FOR_SOLVER: frozenset(
            {BranchStatus.WAITING_FOR_MANAGER, BranchStatus.FAILED}
        ),
        BranchStatus.WAITING_FOR_MANAGER: frozenset(
            {
                BranchStatus.WAITING_FOR_SOLVER,
                BranchStatus.CONFIRMED,
                BranchStatus.REFUTED,
                BranchStatus.PARTIALLY_SUPPORTED,
                BranchStatus.MODIFIED,
                BranchStatus.TOO_HARD,
                BranchStatus.ABANDONED,
                BranchStatus.FAILED,
            }
        ),
        **{status: frozenset() for status in TERMINAL_BRANCH_STATES},
    }
)
PROBE_TRANSITIONS = MappingProxyType(
    {
        ProbeStatus.DRAFTED: frozenset({ProbeStatus.EDITED, ProbeStatus.FAILED}),
        ProbeStatus.EDITED: frozenset({ProbeStatus.SOLVING, ProbeStatus.FAILED}),
        ProbeStatus.SOLVING: frozenset({ProbeStatus.SOLVED, ProbeStatus.FAILED}),
        ProbeStatus.SOLVED: frozenset({ProbeStatus.ASSESSED, ProbeStatus.FAILED}),
        ProbeStatus.ASSESSED: frozenset(),
        ProbeStatus.FAILED: frozenset(),
    }
)
BRAIN_CYCLE_TRANSITIONS = MappingProxyType(
    {
        BrainCycleStatus.PENDING: frozenset({BrainCycleStatus.RUNNING, BrainCycleStatus.FAILED}),
        BrainCycleStatus.RUNNING: frozenset({BrainCycleStatus.COMPLETED, BrainCycleStatus.FAILED}),
        BrainCycleStatus.COMPLETED: frozenset(),
        BrainCycleStatus.FAILED: frozenset(),
    }
)
JOB_TRANSITIONS = MappingProxyType(
    {
        JobStatus.QUEUED: frozenset({JobStatus.RUNNING}),
        JobStatus.RUNNING: frozenset({JobStatus.QUEUED, JobStatus.COMPLETED, JobStatus.FAILED}),
        JobStatus.COMPLETED: frozenset(),
        JobStatus.FAILED: frozenset({JobStatus.QUEUED}),
    }
)


def is_legal_branch_transition(current: BranchStatus | str, target: BranchStatus | str) -> bool:
    try:
        return BranchStatus(target) in BRANCH_TRANSITIONS[BranchStatus(current)]
    except (KeyError, ValueError):
        return False


def is_legal_probe_transition(current: ProbeStatus | str, target: ProbeStatus | str) -> bool:
    try:
        return ProbeStatus(target) in PROBE_TRANSITIONS[ProbeStatus(current)]
    except (KeyError, ValueError):
        return False


def can_transition(current: StrEnum, target: StrEnum) -> bool:
    """Check the state machine selected by the concrete enum type.

    Requiring matching enum types matters because different ``StrEnum`` classes can contain the
    same textual value, such as ``QUEUED``.
    """

    if type(current) is not type(target):
        return False
    tables = {
        BrainCycleStatus: BRAIN_CYCLE_TRANSITIONS,
        BranchStatus: BRANCH_TRANSITIONS,
        ProbeStatus: PROBE_TRANSITIONS,
        JobStatus: JOB_TRANSITIONS,
    }
    table = tables.get(type(current))
    return table is not None and target in table[current]
