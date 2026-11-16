"""Additive learning schema shared by SQLite and Postgres."""


def learning_schema(backend):
    identity = "BIGSERIAL PRIMARY KEY" if backend == "postgres" else "INTEGER PRIMARY KEY"
    return """
CREATE TABLE IF NOT EXISTS learning_sessions (
    id __ID__, user_id TEXT NOT NULL, language TEXT NOT NULL,
    learned_on TEXT NOT NULL, title TEXT NOT NULL, teacher TEXT NOT NULL DEFAULT '',
    goal TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
    words TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS learning_rules (
    id __ID__, user_id TEXT NOT NULL, language TEXT NOT NULL,
    session_id BIGINT REFERENCES learning_sessions(id) ON DELETE SET NULL,
    title TEXT NOT NULL, explanation TEXT NOT NULL, example TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '', due_on TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS learning_tasks (
    id __ID__, user_id TEXT NOT NULL, language TEXT NOT NULL,
    session_id BIGINT REFERENCES learning_sessions(id) ON DELETE SET NULL,
    prompt TEXT NOT NULL, words TEXT NOT NULL DEFAULT '[]', rules TEXT NOT NULL DEFAULT '[]',
    sentence_count INTEGER NOT NULL DEFAULT 3, due_on TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','done')),
    draft TEXT NOT NULL DEFAULT '', revision INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS learning_attempts (
    id __ID__, user_id TEXT NOT NULL, task_id BIGINT NOT NULL REFERENCES learning_tasks(id),
    text TEXT NOT NULL, requirements TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS learning_corrections (
    id __ID__, user_id TEXT NOT NULL, attempt_id BIGINT NOT NULL REFERENCES learning_attempts(id),
    text TEXT NOT NULL, note TEXT NOT NULL DEFAULT '', author TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS learning_recalls (
    id __ID__, user_id TEXT NOT NULL, rule_id BIGINT NOT NULL REFERENCES learning_rules(id),
    response TEXT NOT NULL, rating TEXT NOT NULL CHECK(rating IN ('again','partly','recalled')),
    rule_snapshot TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS learning_families (
    id __ID__, user_id TEXT NOT NULL, language TEXT NOT NULL,
    item_id BIGINT REFERENCES lesson_items(id) ON DELETE SET NULL,
    title TEXT NOT NULL, forms TEXT NOT NULL DEFAULT '[]',
    revision INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL,
    UNIQUE(user_id,item_id)
);
CREATE TABLE IF NOT EXISTS learning_word_classes (
    user_id TEXT NOT NULL, item_id BIGINT NOT NULL REFERENCES lesson_items(id) ON DELETE CASCADE,
    category TEXT NOT NULL CHECK(category IN ('noun','adjective','imperative','verb','phrase','other')),
    PRIMARY KEY(user_id,item_id)
);
CREATE TABLE IF NOT EXISTS learning_receipts (
    user_id TEXT NOT NULL, request_id TEXT NOT NULL, digest TEXT NOT NULL,
    result TEXT NOT NULL, PRIMARY KEY(user_id,request_id)
);
CREATE INDEX IF NOT EXISTS idx_learning_sessions_owner ON learning_sessions(user_id,language,learned_on);
CREATE INDEX IF NOT EXISTS idx_learning_rules_owner ON learning_rules(user_id,language,due_on);
CREATE INDEX IF NOT EXISTS idx_learning_tasks_owner ON learning_tasks(user_id,language,status,due_on);
CREATE INDEX IF NOT EXISTS idx_learning_attempt_task ON learning_attempts(task_id,created_at);
CREATE INDEX IF NOT EXISTS idx_learning_correction_attempt ON learning_corrections(attempt_id,created_at);
CREATE INDEX IF NOT EXISTS idx_learning_recall_rule ON learning_recalls(rule_id,created_at);
""".replace("__ID__", identity)
