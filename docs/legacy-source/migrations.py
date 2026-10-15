"""Versioned SQLite schema. Keep past migrations immutable after release."""

import sqlite3

SCHEMA = """
CREATE TABLE projects (
 id INTEGER PRIMARY KEY CHECK(id=1), slug TEXT UNIQUE NOT NULL, title TEXT NOT NULL,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 status TEXT NOT NULL DEFAULT 'ACTIVE', root_path TEXT NOT NULL);
CREATE TABLE counters(kind TEXT PRIMARY KEY,value INTEGER NOT NULL);
CREATE TABLE brain_cycles (
 id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL DEFAULT 1 REFERENCES projects(id),
 cycle_number INTEGER NOT NULL UNIQUE, status TEXT NOT NULL CHECK(status IN ('PENDING','RUNNING','COMPLETED','FAILED')),
 snapshot_report_id INTEGER, previous_checkpoint_report_id INTEGER,
 started_at TEXT DEFAULT CURRENT_TIMESTAMP, completed_at TEXT, raw_output_path TEXT,edited_output_path TEXT);
CREATE UNIQUE INDEX one_live_cycle ON brain_cycles(project_id) WHERE status IN ('PENDING','RUNNING');
CREATE TABLE insights (
 id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL DEFAULT 1 REFERENCES projects(id),
 public_id TEXT UNIQUE NOT NULL, summary TEXT NOT NULL, status TEXT NOT NULL
 CHECK(status IN ('ACTIVE','STRENGTHENED','WEAKENED','REFUTED','SUPERSEDED','ARCHIVED')),
 confidence TEXT, created_cycle_id INTEGER REFERENCES brain_cycles(id),updated_cycle_id INTEGER REFERENCES brain_cycles(id),
 parent_insight_id INTEGER REFERENCES insights(id), artifact_id TEXT,
 created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE branches (
 id INTEGER PRIMARY KEY,project_id INTEGER NOT NULL DEFAULT 1 REFERENCES projects(id),
 public_id TEXT UNIQUE NOT NULL,parent_insight_id INTEGER NOT NULL REFERENCES insights(id),
 status TEXT NOT NULL CHECK(status IN ('QUEUED','RUNNING','WAITING_FOR_SOLVER','WAITING_FOR_MANAGER','CONFIRMED','REFUTED','PARTIALLY_SUPPORTED','MODIFIED','TOO_HARD','ABANDONED','FAILED')),
 priority INTEGER NOT NULL DEFAULT 0,probe_round INTEGER NOT NULL DEFAULT 0,
 created_cycle_id INTEGER REFERENCES brain_cycles(id),proposal_index INTEGER,context_artifact_id TEXT,
 created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP,final_report_id INTEGER,
 UNIQUE(created_cycle_id,proposal_index));
CREATE TABLE probes (
 id INTEGER PRIMARY KEY, branch_id INTEGER NOT NULL REFERENCES branches(id),public_id TEXT UNIQUE NOT NULL,
 round_number INTEGER NOT NULL CHECK(round_number>0),status TEXT NOT NULL
 CHECK(status IN ('DRAFTED','EDITED','SOLVING','SOLVED','ASSESSED','FAILED')),
 verdict TEXT CHECK(verdict IN ('PROVED','DISPROVED','INCONCLUSIVE')),
 statement_edited_path TEXT,solver_raw_path TEXT,solver_edited_path TEXT,
 manager_assessment_raw_path TEXT,manager_assessment_edited_path TEXT,assessment_action TEXT,
 created_at TEXT DEFAULT CURRENT_TIMESTAMP,completed_at TEXT,UNIQUE(branch_id,round_number));
CREATE TRIGGER immutable_verdict BEFORE UPDATE OF verdict ON probes
 WHEN OLD.verdict IS NOT NULL AND NEW.verdict IS NOT OLD.verdict
 BEGIN SELECT RAISE(ABORT,'Historical Solver verdict is immutable'); END;
CREATE TABLE artifacts (
 id TEXT PRIMARY KEY,project_id INTEGER NOT NULL DEFAULT 1 REFERENCES projects(id),
 logical_key TEXT UNIQUE NOT NULL,kind TEXT NOT NULL,scope_type TEXT,scope_id TEXT,
 raw_path TEXT NOT NULL,edited_path TEXT,destination TEXT NOT NULL,editor_mode TEXT NOT NULL,
 content_sha256_raw TEXT NOT NULL,content_sha256_edited TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP,
 edited_at TEXT,model_run_id TEXT,editor_run_id TEXT,status TEXT NOT NULL,
 edit_attempts INTEGER NOT NULL DEFAULT 0,consistency_issues TEXT NOT NULL DEFAULT '[]',metadata_json TEXT NOT NULL DEFAULT '{}');
CREATE TRIGGER immutable_raw BEFORE UPDATE OF raw_path,content_sha256_raw ON artifacts
 BEGIN SELECT RAISE(ABORT,'Raw artifact ancestry is immutable'); END;
CREATE TABLE reports (
 id INTEGER PRIMARY KEY AUTOINCREMENT,project_id INTEGER NOT NULL DEFAULT 1 REFERENCES projects(id),
 public_id TEXT UNIQUE NOT NULL,branch_id INTEGER UNIQUE REFERENCES branches(id),insight_id INTEGER REFERENCES insights(id),
 kind TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'FINALIZED',raw_path TEXT,edited_path TEXT NOT NULL,
 created_at TEXT DEFAULT CURRENT_TIMESTAMP,finalized_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 processed_cycle_id INTEGER REFERENCES brain_cycles(id));
CREATE TRIGGER immutable_report BEFORE UPDATE OF edited_path,raw_path,finalized_at ON reports
 BEGIN SELECT RAISE(ABORT,'Finalized report is immutable; append a correction'); END;
CREATE TRIGGER processed_once BEFORE UPDATE OF processed_cycle_id ON reports
 WHEN OLD.processed_cycle_id IS NOT NULL AND NEW.processed_cycle_id IS NOT OLD.processed_cycle_id
 BEGIN SELECT RAISE(ABORT,'Report already processed'); END;
CREATE TABLE cycle_reports (
 cycle_id INTEGER NOT NULL REFERENCES brain_cycles(id),report_id INTEGER NOT NULL REFERENCES reports(id),
 PRIMARY KEY(cycle_id,report_id));
CREATE TABLE cycle_artifacts (
 cycle_id INTEGER NOT NULL REFERENCES brain_cycles(id),artifact_id TEXT NOT NULL REFERENCES artifacts(id),
 destination TEXT NOT NULL,append_only INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(cycle_id,destination));
CREATE TABLE insight_events (
 id INTEGER PRIMARY KEY,insight_id INTEGER NOT NULL REFERENCES insights(id),cycle_id INTEGER REFERENCES brain_cycles(id),
 status TEXT NOT NULL,artifact_id TEXT NOT NULL REFERENCES artifacts(id),created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE jobs (
 id INTEGER PRIMARY KEY,project_id INTEGER NOT NULL DEFAULT 1 REFERENCES projects(id),job_type TEXT NOT NULL,
 scope_type TEXT,scope_id TEXT,status TEXT NOT NULL DEFAULT 'QUEUED',priority INTEGER NOT NULL DEFAULT 0,
 attempts INTEGER NOT NULL DEFAULT 0,max_attempts INTEGER NOT NULL,
 lease_owner TEXT,lease_expires_at REAL,created_at TEXT DEFAULT CURRENT_TIMESTAMP,started_at TEXT,completed_at TEXT,error TEXT,
 UNIQUE(job_type,scope_type,scope_id));
CREATE UNIQUE INDEX one_live_strategic_job ON jobs(job_type) WHERE job_type IN ('BACKGROUND','BRAIN') AND status IN ('QUEUED','RUNNING','FAILED');
CREATE TABLE model_runs (
 id TEXT PRIMARY KEY,project_id INTEGER NOT NULL DEFAULT 1 REFERENCES projects(id),agent_role TEXT,scope_type TEXT,scope_id TEXT,
 action_key TEXT,model_name TEXT,reasoning_effort TEXT,prompt_hash TEXT,prompt_path TEXT,
 started_at TEXT DEFAULT CURRENT_TIMESTAMP,completed_at TEXT,input_tokens INTEGER,output_tokens INTEGER,total_tokens INTEGER,
 estimated_cost_usd REAL,reserved_cost_usd REAL DEFAULT 0,trace_id TEXT,status TEXT,error TEXT,raw_output_path TEXT,metadata_json TEXT);
CREATE UNIQUE INDEX cached_model_action ON model_runs(action_key) WHERE status='COMPLETED';
CREATE TABLE literature (
 id INTEGER PRIMARY KEY,reference_key TEXT UNIQUE NOT NULL,metadata_json TEXT NOT NULL,notes_artifact_id TEXT REFERENCES artifacts(id),
 pdf_path TEXT,pdf_sha256 TEXT,download_error TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE state_events (
 id INTEGER PRIMARY KEY,entity_type TEXT,entity_id TEXT,old_status TEXT,new_status TEXT,
 created_at TEXT DEFAULT CURRENT_TIMESTAMP);
"""


def migrate(connection: sqlite3.Connection) -> None:
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    if version > 1:
        raise RuntimeError("Database is newer than this application")
    if version == 0:
        try:
            connection.executescript(
                "BEGIN IMMEDIATE;\n" + SCHEMA + "\nPRAGMA user_version=1;\nCOMMIT;"
            )
        except BaseException:
            connection.rollback()
            raise
