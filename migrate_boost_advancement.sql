-- ──────────────────────────────────────────────────────────────────────────
-- Migration: اضافه کردن جداول بوستر و پیش‌بینی صعود
-- برای دیتابیس‌های موجود این فایل رو یه بار اجرا کن:
--   psql $DATABASE_URL -f migrate_boost_advancement.sql
-- ──────────────────────────────────────────────────────────────────────────

-- جدول بوستر ×۲ (هر کاربر در هر مرحله حذفی فقط یک بوستر)
CREATE TABLE IF NOT EXISTS boosts (
    id         SERIAL PRIMARY KEY,
    user_id    BIGINT NOT NULL REFERENCES users(user_id),
    match_id   INT    NOT NULL REFERENCES matches(id),
    stage      TEXT   NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, stage)
);
CREATE INDEX IF NOT EXISTS idx_boost_user  ON boosts(user_id);
CREATE INDEX IF NOT EXISTS idx_boost_match ON boosts(match_id);

-- جدول پیش‌بینی صعود (+۵ امتیاز اگه درست بود)
CREATE TABLE IF NOT EXISTS advancement_predictions (
    id         SERIAL PRIMARY KEY,
    user_id    BIGINT NOT NULL REFERENCES users(user_id),
    match_id   INT    NOT NULL REFERENCES matches(id),
    team       TEXT   NOT NULL,
    points     INT    DEFAULT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, match_id)
);
CREATE INDEX IF NOT EXISTS idx_adv_user  ON advancement_predictions(user_id);
CREATE INDEX IF NOT EXISTS idx_adv_match ON advancement_predictions(match_id);
