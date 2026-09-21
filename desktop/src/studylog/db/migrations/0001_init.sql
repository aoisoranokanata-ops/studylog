-- StudyLog 母艦の初期スキーマ。
-- フェーズ2以降で使うテーブルもここで作り切る（転送処理が未作成のテーブルを踏まないようにするため）。
-- 共通の約束：
--   * id は UUID v4 の文字列
--   * 日時は UTC の ISO 8601（例 2026-09-20T05:30:00Z）
--   * deleted_at が NULL でない行は削除済みとして扱う（論理削除）
--   * CHECK 制約は書かない。整合はアプリ側（services/）で保証する
--     （ON DELETE SET NULL と CHECK が衝突して更新できなくなる事故を避けるため）

CREATE TABLE exams (
    id                 TEXT PRIMARY KEY,
    name               TEXT NOT NULL,
    color              TEXT NOT NULL DEFAULT '#4a6fa5',
    status             TEXT NOT NULL DEFAULT 'studying',  -- studying/taken/passed/failed/paused
    goal_note          TEXT NOT NULL DEFAULT '',
    goal_total_seconds INTEGER,
    sort_order         INTEGER NOT NULL DEFAULT 0,
    archived           INTEGER NOT NULL DEFAULT 0,
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL,
    deleted_at         TEXT
);

-- 年度ごとの試験日と結果
CREATE TABLE exam_sittings (
    id                       TEXT PRIMARY KEY,
    exam_id                  TEXT NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
    label                    TEXT NOT NULL DEFAULT '',        -- 例「2026年度」
    exam_date                TEXT,                            -- YYYY-MM-DD
    is_primary               INTEGER NOT NULL DEFAULT 0,      -- カウントダウンに使う回
    result_score             INTEGER,
    result_passed            INTEGER,                         -- 1=合格 0=不合格 NULL=未受験
    result_memo              TEXT NOT NULL DEFAULT '',
    certificate_received_on  TEXT,
    created_at               TEXT NOT NULL,
    updated_at               TEXT NOT NULL,
    deleted_at               TEXT
);

CREATE TABLE materials (
    id          TEXT PRIMARY KEY,
    exam_id     TEXT REFERENCES exams(id) ON DELETE SET NULL,
    name        TEXT NOT NULL,
    type        TEXT NOT NULL DEFAULT 'text',   -- text/drill/past/lecture/other
    unit_label  TEXT NOT NULL DEFAULT 'ページ',
    total       INTEGER NOT NULL DEFAULT 0,
    current     INTEGER NOT NULL DEFAULT 0,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    archived    INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    deleted_at  TEXT
);

CREATE TABLE subjects (
    id          TEXT PRIMARY KEY,
    exam_id     TEXT REFERENCES exams(id) ON DELETE SET NULL,
    parent_id   TEXT REFERENCES subjects(id) ON DELETE SET NULL,  -- 2階層まで
    name        TEXT NOT NULL,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    archived    INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    deleted_at  TEXT
);

CREATE TABLE sessions (
    id              TEXT PRIMARY KEY,
    exam_id         TEXT REFERENCES exams(id) ON DELETE SET NULL,
    material_id     TEXT REFERENCES materials(id) ON DELETE SET NULL,
    subject_id      TEXT REFERENCES subjects(id) ON DELETE SET NULL,
    quota_id        TEXT,
    unclassified    INTEGER NOT NULL DEFAULT 0,
    started_at      TEXT NOT NULL,
    ended_at        TEXT NOT NULL,
    active_seconds  INTEGER NOT NULL DEFAULT 0,
    study_date      TEXT NOT NULL,                  -- started_at に日付変更時刻を適用した学習日
    range_unit      TEXT,                           -- page/question
    range_from      INTEGER,
    range_to        INTEGER,
    correct         INTEGER,
    attempted       INTEGER,
    focus           INTEGER,                        -- 1〜5
    memo            TEXT NOT NULL DEFAULT '',
    entry_mode      TEXT NOT NULL DEFAULT 'timer',  -- timer/manual
    source          TEXT NOT NULL DEFAULT 'hub',    -- hub/satellite
    device_id       TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    deleted_at      TEXT
);

-- 計測中の状態（1行だけ。id は 'current' 固定）
CREATE TABLE timer_state (
    id                   TEXT PRIMARY KEY,
    exam_id              TEXT,
    material_id          TEXT,
    subject_id           TEXT,
    quota_id             TEXT,
    started_at           TEXT NOT NULL,              -- 計測全体の開始
    accumulated_seconds  INTEGER NOT NULL DEFAULT 0, -- 直前の一時停止までに確定した秒数
    resumed_at           TEXT,                       -- 稼働中の区間の開始（停止中は NULL）
    is_running           INTEGER NOT NULL DEFAULT 1,
    memo                 TEXT NOT NULL DEFAULT '',
    created_at           TEXT NOT NULL,
    updated_at           TEXT NOT NULL,
    deleted_at           TEXT
);

CREATE TABLE plans (
    id               TEXT PRIMARY KEY,
    date             TEXT NOT NULL,
    time_of_day      TEXT,
    exam_id          TEXT REFERENCES exams(id) ON DELETE SET NULL,
    material_id      TEXT REFERENCES materials(id) ON DELETE SET NULL,
    subject_id       TEXT REFERENCES subjects(id) ON DELETE SET NULL,
    title            TEXT NOT NULL DEFAULT '',
    planned_seconds  INTEGER NOT NULL DEFAULT 0,
    range_unit       TEXT,
    range_from       INTEGER,
    range_to         INTEGER,
    note             TEXT NOT NULL DEFAULT '',
    repeat_rule      TEXT,       -- none/daily/weekly:1,3,5
    repeat_from      TEXT,
    repeat_until     TEXT,
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL,
    deleted_at       TEXT
);

-- 子機に渡すノルマ
CREATE TABLE quotas (
    id                 TEXT PRIMARY KEY,
    plan_id            TEXT REFERENCES plans(id) ON DELETE SET NULL,
    date               TEXT NOT NULL,
    sort_order         INTEGER NOT NULL DEFAULT 0,
    exam_id            TEXT REFERENCES exams(id) ON DELETE SET NULL,
    material_id        TEXT REFERENCES materials(id) ON DELETE SET NULL,
    subject_id         TEXT REFERENCES subjects(id) ON DELETE SET NULL,
    title              TEXT NOT NULL DEFAULT '',
    target_seconds     INTEGER NOT NULL DEFAULT 0,
    range_unit         TEXT,
    range_from         INTEGER,
    range_to           INTEGER,
    note               TEXT NOT NULL DEFAULT '',
    status             TEXT NOT NULL DEFAULT 'none',  -- none/done/partial/skipped
    status_id          TEXT,                          -- 子機の quotaStatus.id（冪等判定用）
    status_updated_at  TEXT,
    sent_at            TEXT,
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL,
    deleted_at         TEXT
);

CREATE TABLE mistakes (
    id              TEXT PRIMARY KEY,
    session_id      TEXT REFERENCES sessions(id) ON DELETE SET NULL,
    exam_id         TEXT REFERENCES exams(id) ON DELETE SET NULL,
    material_id     TEXT REFERENCES materials(id) ON DELETE SET NULL,
    subject_id      TEXT REFERENCES subjects(id) ON DELETE SET NULL,
    question_ref    TEXT NOT NULL DEFAULT '',
    memo            TEXT NOT NULL DEFAULT '',
    answer_memo     TEXT NOT NULL DEFAULT '',       -- 正解・ポイント（母艦で追記する）
    reason          TEXT,                           -- knowledge/misread/careless/confusion/other
    review_stage    INTEGER NOT NULL DEFAULT 0,
    next_review_on  TEXT,
    consecutive_ok  INTEGER NOT NULL DEFAULT 0,
    mastery         TEXT NOT NULL DEFAULT 'unmastered',  -- unmastered/reviewing/mastered
    source          TEXT NOT NULL DEFAULT 'hub',
    device_id       TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    deleted_at      TEXT
);

CREATE TABLE review_results (
    id           TEXT PRIMARY KEY,
    mistake_id   TEXT NOT NULL,
    result       TEXT NOT NULL,        -- ok/ng
    reviewed_at  TEXT NOT NULL,
    source       TEXT NOT NULL DEFAULT 'hub',
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    deleted_at   TEXT
);

CREATE TABLE tasks (
    id          TEXT PRIMARY KEY,
    exam_id     TEXT REFERENCES exams(id) ON DELETE SET NULL,
    subject_id  TEXT REFERENCES subjects(id) ON DELETE SET NULL,
    content     TEXT NOT NULL,
    due_on      TEXT,
    priority    INTEGER NOT NULL DEFAULT 2,   -- 1=高 2=中 3=低
    done        INTEGER NOT NULL DEFAULT 0,
    done_at     TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    deleted_at  TEXT
);

CREATE TABLE weekly_goals (
    id            TEXT PRIMARY KEY,
    week_start    TEXT NOT NULL,
    exam_id       TEXT REFERENCES exams(id) ON DELETE CASCADE,  -- NULL は全体の目標
    goal_seconds  INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    deleted_at    TEXT
);

CREATE TABLE devices (
    id                TEXT PRIMARY KEY,      -- 子機の deviceId
    name              TEXT NOT NULL DEFAULT '',
    last_received_at  TEXT,
    last_package_id   TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    deleted_at        TEXT
);

-- 取り込み済みの上りパッケージ（下りの acks を作るための台帳）
CREATE TABLE imported_packages (
    id           TEXT PRIMARY KEY,           -- = package_id
    device_id    TEXT,
    imported_at  TEXT NOT NULL,
    included_ids TEXT NOT NULL DEFAULT '[]', -- JSON配列
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    deleted_at   TEXT
);

CREATE TABLE transfer_log (
    id           TEXT PRIMARY KEY,
    direction    TEXT NOT NULL,        -- down/up
    package_id   TEXT,
    occurred_at  TEXT NOT NULL,
    device_id    TEXT,
    variant      TEXT,                 -- full/lite/file/qr/text
    counts       TEXT NOT NULL DEFAULT '{}',  -- JSON
    result       TEXT NOT NULL DEFAULT 'ok',  -- ok/rejected/error
    message      TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    deleted_at   TEXT
);

CREATE TABLE settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE INDEX idx_sessions_study_date    ON sessions(study_date) WHERE deleted_at IS NULL;
CREATE INDEX idx_sessions_exam_date     ON sessions(exam_id, study_date) WHERE deleted_at IS NULL;
CREATE INDEX idx_sessions_quota         ON sessions(quota_id);
CREATE INDEX idx_sessions_unclassified  ON sessions(unclassified) WHERE deleted_at IS NULL;
CREATE INDEX idx_materials_exam         ON materials(exam_id);
CREATE INDEX idx_subjects_exam          ON subjects(exam_id);
CREATE INDEX idx_subjects_parent        ON subjects(parent_id);
CREATE INDEX idx_quotas_date            ON quotas(date) WHERE deleted_at IS NULL;
CREATE INDEX idx_mistakes_next_review   ON mistakes(next_review_on) WHERE deleted_at IS NULL;
CREATE INDEX idx_mistakes_exam          ON mistakes(exam_id);
CREATE INDEX idx_review_results_mistake ON review_results(mistake_id);
CREATE INDEX idx_tasks_due              ON tasks(due_on) WHERE deleted_at IS NULL;
CREATE INDEX idx_weekly_goals_week      ON weekly_goals(week_start);
CREATE INDEX idx_imported_at            ON imported_packages(imported_at);
CREATE INDEX idx_transfer_log_occurred  ON transfer_log(occurred_at);
