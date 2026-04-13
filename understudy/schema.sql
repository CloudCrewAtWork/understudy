-- Understudy schema. Single source of truth.
-- Encrypt with SQLCipher: PRAGMA key = '...' must be set on connection.

PRAGMA user_version = 1;
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS trajectories (
    id            TEXT PRIMARY KEY,
    task_name     TEXT NOT NULL,
    target_kind   TEXT NOT NULL CHECK (target_kind IN ('browser', 'macos')),
    started_at    TEXT NOT NULL,
    finished_at   TEXT,
    success       INTEGER,
    step_count    INTEGER NOT NULL DEFAULT 0,
    notes         TEXT,
    -- JSONL of steps lives on disk at trajectories/<id>.jsonl;
    -- this row is the index plus metadata.
    file_path     TEXT NOT NULL UNIQUE
);

CREATE INDEX IF NOT EXISTS idx_trajectories_task ON trajectories(task_name);
CREATE INDEX IF NOT EXISTS idx_trajectories_started ON trajectories(started_at);

CREATE TABLE IF NOT EXISTS recipes (
    id              TEXT PRIMARY KEY,
    task_name       TEXT NOT NULL,
    target_kind     TEXT NOT NULL CHECK (target_kind IN ('browser', 'macos')),
    source_traj_id  TEXT NOT NULL REFERENCES trajectories(id) ON DELETE CASCADE,
    induced_by      TEXT NOT NULL,         -- model id, e.g. claude-sonnet-4-5
    created_at      TEXT NOT NULL,
    edited_at       TEXT,
    recipe_json     TEXT NOT NULL,         -- the parameterized recipe document
    is_active       INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_recipes_task ON recipes(task_name);

CREATE TABLE IF NOT EXISTS replays (
    id           TEXT PRIMARY KEY,
    recipe_id    TEXT NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
    started_at   TEXT NOT NULL,
    finished_at  TEXT,
    success      INTEGER,
    steps_total  INTEGER,
    steps_done   INTEGER,
    cost_usd     REAL,
    tokens_in    INTEGER,
    tokens_out   INTEGER,
    error_class  TEXT,
    params_json  TEXT NOT NULL,            -- inputs supplied for this run
    log_path     TEXT
);

CREATE INDEX IF NOT EXISTS idx_replays_recipe ON replays(recipe_id);
CREATE INDEX IF NOT EXISTS idx_replays_started ON replays(started_at);

-- Audit log for security-sensitive events: HITL approvals, denials, rotation, wipes.
CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,
    event       TEXT NOT NULL,
    detail_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(ts);
