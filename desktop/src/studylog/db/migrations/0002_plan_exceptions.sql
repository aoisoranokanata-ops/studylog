-- 繰り返し予定の「この回だけ休む」を覚えておく表。
-- 予定そのものは plans に1行だけ持ち、表示のたびに繰り返しを展開する。
-- 例外はここに日付で記録する（同じ予定・同じ日は1件だけ）。

CREATE TABLE plan_exceptions (
    id          TEXT PRIMARY KEY,
    plan_id     TEXT NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
    date        TEXT NOT NULL,          -- YYYY-MM-DD
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    deleted_at  TEXT
);

CREATE UNIQUE INDEX idx_plan_exceptions_unique ON plan_exceptions(plan_id, date);
