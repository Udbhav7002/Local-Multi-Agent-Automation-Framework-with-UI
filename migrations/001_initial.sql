CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    status TEXT,
    result TEXT,
    steps_executed TEXT,
    created_at TEXT,
    updated_at TEXT
);
