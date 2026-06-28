import asyncpg
import secrets
import string
from datetime import datetime
from config import DATABASE_URL
from utils import calc_points

_pool = None

async def get_pool():
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            DATABASE_URL, min_size=2, max_size=10,
            max_inactive_connection_lifetime=300,
        )
    return _pool

async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None

async def init_db():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id      BIGINT PRIMARY KEY,
            display_name TEXT NOT NULL,
            lang         TEXT DEFAULT 'fa',
            joined_at    TIMESTAMPTZ DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS matches (
            id           SERIAL PRIMARY KEY,
            api_id       INT DEFAULT NULL,
            grp          TEXT,
            round_no     INT DEFAULT NULL,
            stage        TEXT NOT NULL DEFAULT 'group',
            team1        TEXT NOT NULL,
            team2        TEXT NOT NULL,
            match_time   TIMESTAMPTZ NOT NULL,
            city         TEXT DEFAULT '',
            result1      INT DEFAULT NULL,
            result2      INT DEFAULT NULL,
            penalty1     INT DEFAULT NULL,
            penalty2     INT DEFAULT NULL,
            winner_team  TEXT DEFAULT NULL,
            is_locked    BOOLEAN DEFAULT FALSE,
            is_finished  BOOLEAN DEFAULT FALSE,
            notif_sent   BOOLEAN DEFAULT FALSE,
            result_sent  BOOLEAN DEFAULT FALSE,
            next_match_id INT DEFAULT NULL
        );

        CREATE TABLE IF NOT EXISTS predictions (
            id         SERIAL PRIMARY KEY,
            user_id    BIGINT NOT NULL REFERENCES users(user_id),
            match_id   INT    NOT NULL REFERENCES matches(id),
            pred1      INT NOT NULL,
            pred2      INT NOT NULL,
            points     INT DEFAULT NULL,
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(user_id, match_id)
        );

        CREATE TABLE IF NOT EXISTS leagues (
            id           SERIAL PRIMARY KEY,
            name         TEXT NOT NULL,
            owner_id     BIGINT NOT NULL REFERENCES users(user_id),
            invite_code  TEXT NOT NULL UNIQUE,
            created_at   TIMESTAMPTZ DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS league_members (
            league_id  INT NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
            user_id    BIGINT NOT NULL REFERENCES users(user_id),
            joined_at  TIMESTAMPTZ DEFAULT NOW(),
            PRIMARY KEY(league_id, user_id)
        );

        CREATE INDEX IF NOT EXISTS idx_pred_user      ON predictions(user_id);
        CREATE INDEX IF NOT EXISTS idx_pred_match     ON predictions(match_id);
        CREATE INDEX IF NOT EXISTS idx_match_stage    ON matches(stage);
        CREATE INDEX IF NOT EXISTS idx_match_time     ON matches(match_time);
        CREATE INDEX IF NOT EXISTS idx_match_finished ON matches(is_finished);
        CREATE INDEX IF NOT EXISTS idx_match_api_id   ON matches(api_id);
        CREATE INDEX IF NOT EXISTS idx_lm_user        ON league_members(user_id);
        CREATE INDEX IF NOT EXISTS idx_league_code    ON leagues(invite_code);

        -- ── BOOSTS ────────────────────────────────────────────────────────────
        -- هر کاربر در هر مرحله حذفی فقط یک بوستر ×۲ می‌تونه فعال کنه
        CREATE TABLE IF NOT EXISTS boosts (
            id         SERIAL PRIMARY KEY,
            user_id    BIGINT NOT NULL REFERENCES users(user_id),
            match_id   INT    NOT NULL REFERENCES matches(id),
            stage      TEXT   NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(user_id, stage)   -- فقط یه بار در هر مرحله
        );
        CREATE INDEX IF NOT EXISTS idx_boost_user  ON boosts(user_id);
        CREATE INDEX IF NOT EXISTS idx_boost_match ON boosts(match_id);

        -- ── ADVANCEMENT PREDICTIONS ────────────────────────────────────────────
        -- پیش‌بینی تیم صعودکننده در بازی‌های حذفی (+۵ امتیاز اگه درست بود)
        CREATE TABLE IF NOT EXISTS advancement_predictions (
            id         SERIAL PRIMARY KEY,
            user_id    BIGINT NOT NULL REFERENCES users(user_id),
            match_id   INT    NOT NULL REFERENCES matches(id),
            team       TEXT   NOT NULL,   -- نام تیمی که پیش‌بینی صعود کرده
            points     INT    DEFAULT NULL,
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(user_id, match_id)
        );
        CREATE INDEX IF NOT EXISTS idx_adv_user  ON advancement_predictions(user_id);
        CREATE INDEX IF NOT EXISTS idx_adv_match ON advancement_predictions(match_id);
        """)

async def bulk_insert_group_matches(matches: list):
    pool = await get_pool()
    async with pool.acquire() as conn:
        count = await conn.fetchval("SELECT COUNT(*) FROM matches WHERE stage='group'")
        if count > 0:
            return
        await conn.executemany("""
            INSERT INTO matches(grp, round_no, stage, team1, team2, match_time, city)
            VALUES($1, $2, 'group', $3, $4, $5, $6)
        """, [(m[0], m[1], m[2], m[3],
               datetime.fromisoformat(m[4]+":00+00:00"), m[5]) for m in matches])

async def bulk_insert_knockout_matches(matches: list):
    """درج بازی‌های مراحل حذفی (r32, r16, qf, sf, third, final).
    ایدمپوتنت: اگه از قبل برای اون مرحله ردیفی داشته باشیم، رد می‌شه.
    دیتا و پیش‌بینی‌های موجود رو دست نمی‌زنه."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        # گروه‌بندی بر اساس stage برای چک ایدمپوتنت
        by_stage = {}
        for m in matches:
            by_stage.setdefault(m[0], []).append(m)
        for stage, rows in by_stage.items():
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM matches WHERE stage=$1", stage)
            if count > 0:
                continue  # قبلاً درج شده، رد شو
            await conn.executemany("""
                INSERT INTO matches(api_id, stage, team1, team2, match_time, city)
                VALUES($1, $2, $3, $4, $5, $6)
            """, [(m[1], m[0], m[2], m[3],
                   datetime.fromisoformat(m[4]+":00+00:00"), m[5]) for m in rows])

async def sync_knockout_teams(knockout_matches: list) -> int:
    """آپدیت تیم‌ها و ساعت/شهر بازی‌های حذفی که هنوز placeholder دارن.
    فقط ردیف‌هایی آپدیت میشن که:
      - is_finished=FALSE (تموم نشده)
      - is_locked=FALSE (قفل نشده — یعنی هنوز شروع نشده)
      - تیم‌هاشون placeholder هستن (مثل 1A, 2B, W77)
    پیش‌بینی‌ها و امتیازها دست نمیخوره.
    """
    import re
    def is_placeholder(name):
        if not name: return True
        return bool(re.fullmatch(r"[1-3][A-L]+|W\d{1,3}|L\d{1,3}", name.strip()))

    pool = await get_pool()
    updated = 0
    async with pool.acquire() as conn:
        for m in knockout_matches:
            stage, match_no, t1, t2, utc_str, city = m
            new_dt = datetime.fromisoformat(utc_str + ":00+00:00")
            # آپدیت تیم‌ها + ساعت + شهر — فقط اگه هنوز placeholder هستن
            res = await conn.execute("""
                UPDATE matches
                   SET team1=$1, team2=$2, match_time=$3, city=$4,
                       is_locked=FALSE, notif_sent=FALSE
                 WHERE stage=$5
                   AND api_id=$6
                   AND is_finished=FALSE
                   AND is_locked=FALSE
                   AND (
                       team1 ~ '^[1-3][A-L]+$' OR team1 ~ '^[WL]\\d+$' OR
                       team2 ~ '^[1-3][A-L]+$' OR team2 ~ '^[WL]\\d+$'
                   )
            """, t1, t2, new_dt, city, stage, match_no)
            try:
                updated += int(res.split()[-1])
            except Exception:
                pass
        # بعد از آپدیت تیم‌ها، predictions قدیمی (برای placeholder) پاک میشن
        # چون prediction برای تیم placeholder بی‌معنیه — ولی اگه کسی
        # پیش‌بینی واقعی داشته باشه (تیم‌های واقعی) دست نمیخوره
        # (این حالت عملاً نمیتونه رخ بده چون save_prediction placeholder رو رد می‌کنه)
    return updated

async def sync_match_schedules(group_matches: list, knockout_matches: list):
    """به‌روزرسانی غیرتخریبی تاریخ/ساعت/شهر بازی‌ها از روی wc_data.py.
    فقط ستون‌های match_time و city به‌روز میشن. تیم‌ها، نتایج، پیش‌بینی‌ها
    و بقیه‌ی دیتا دست نخورده باقی می‌مونن. بازی‌های قفل‌شده یا تمام‌شده
    رد میشن تا یادآوری‌های ارسال‌شده دوباره ارسال نشن.
    خروجی: تعداد ردیف‌های آپدیت‌شده."""
    pool = await get_pool()
    updated = 0
    async with pool.acquire() as conn:
        # --- مرحله گروهی: تطابق بر اساس (grp, round_no, جفت تیم بدون توجه به ترتیب)
        for m in group_matches:
            grp, round_no, t1, t2, utc_str, city = m
            new_dt = datetime.fromisoformat(utc_str + ":00+00:00")
            res = await conn.execute("""
                UPDATE matches
                   SET match_time = $1, city = $2
                 WHERE stage = 'group'
                   AND grp = $3
                   AND round_no = $4
                   AND ((team1 = $5 AND team2 = $6) OR (team1 = $6 AND team2 = $5))
                   AND is_finished = FALSE
                   AND is_locked   = FALSE
                   AND (match_time IS DISTINCT FROM $1 OR COALESCE(city,'') IS DISTINCT FROM $2)
            """, new_dt, city, grp, round_no, t1, t2)
            try:
                updated += int(res.split()[-1])
            except Exception:
                pass

        # --- مراحل حذفی: تطابق بر اساس api_id (شماره بازی 73..104)
        for m in knockout_matches:
            stage, match_no, _t1, _t2, utc_str, city = m
            new_dt = datetime.fromisoformat(utc_str + ":00+00:00")
            res = await conn.execute("""
                UPDATE matches
                   SET match_time = $1, city = $2
                 WHERE stage   = $3
                   AND api_id  = $4
                   AND is_finished = FALSE
                   AND is_locked   = FALSE
                   AND (match_time IS DISTINCT FROM $1 OR COALESCE(city,'') IS DISTINCT FROM $2)
            """, new_dt, city, stage, match_no)
            try:
                updated += int(res.split()[-1])
            except Exception:
                pass

        # بعد از تغییر زمان، اگه بازی هنوز در آینده‌ست، یادآوری باید دوباره ارسال بشه
        await conn.execute("""
            UPDATE matches
               SET notif_sent = FALSE
             WHERE is_finished = FALSE
               AND is_locked   = FALSE
               AND notif_sent  = TRUE
               AND match_time > NOW() + INTERVAL '65 minutes'
        """)
    return updated

# ── USERS ─────────────────────────────────────


async def upsert_user(user_id, display_name, lang="fa"):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO users(user_id, display_name, lang)
            VALUES($1,$2,$3)
            ON CONFLICT(user_id) DO UPDATE SET display_name=EXCLUDED.display_name
        """, user_id, display_name, lang)

async def get_user(user_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM users WHERE user_id=$1", user_id)

async def get_all_users():
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch("SELECT user_id, lang FROM users")

# ── MATCHES ───────────────────────────────────

async def get_group_matches(round_no=None, grp=None):
    pool = await get_pool()
    async with pool.acquire() as conn:
        if round_no and grp:
            return await conn.fetch("""
                SELECT * FROM matches WHERE stage='group' AND round_no=$1 AND grp=$2
                ORDER BY match_time
            """, round_no, grp)
        elif round_no:
            return await conn.fetch("""
                SELECT * FROM matches WHERE stage='group' AND round_no=$1
                ORDER BY match_time
            """, round_no)
        elif grp:
            return await conn.fetch("""
                SELECT * FROM matches WHERE stage='group' AND grp=$1
                ORDER BY match_time
            """, grp)
        return await conn.fetch("SELECT * FROM matches WHERE stage='group' ORDER BY match_time")

async def get_all_matches(stage=None):
    pool = await get_pool()
    async with pool.acquire() as conn:
        if stage:
            return await conn.fetch("SELECT * FROM matches WHERE stage=$1 ORDER BY match_time", stage)
        return await conn.fetch("SELECT * FROM matches ORDER BY match_time")

async def get_match(match_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM matches WHERE id=$1", match_id)

async def get_matches_to_notify():
    """بازی‌هایی که نهایتاً ۶۵ دقیقه دیگه شروع میشن و نوتیف نرفته
    (پنجره بزرگ‌تر تا اگه scheduler چند دقیقه عقب افتاد، نوتیف از دست نره)"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch("""
            SELECT * FROM matches
            WHERE notif_sent = FALSE
              AND is_finished = FALSE
              AND match_time > NOW()
              AND match_time <= NOW() + INTERVAL '65 minutes'
        """)

async def get_matches_to_check_result():
    """بازی‌هایی که باید نتیجه‌شون چک بشه:
    از دقیقه ۹۰ به بعد شروع به polling میکنیم (هر ۶۰ ثانیه یه بار)
    تا وقتی API وضعیت FINISHED برگردونه.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch("""
            SELECT * FROM matches
            WHERE is_finished = FALSE
              AND is_locked = TRUE
              AND result_sent = FALSE
              AND match_time + INTERVAL '90 minutes' <= NOW()
        """)

async def lock_due_matches():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE matches SET is_locked=TRUE
            WHERE match_time <= NOW() AND is_locked=FALSE
        """)

async def lock_match(match_id: int) -> bool:
    """قفل دستی یک بازی توسط ادمین (بدون تموم کردن)"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE matches SET is_locked=TRUE WHERE id=$1 AND is_finished=FALSE RETURNING id",
            match_id)
        return row is not None

async def unlock_match(match_id: int) -> bool:
    """باز کردن دستی یک بازی توسط ادمین (فقط اگه تموم نشده)"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE matches SET is_locked=FALSE WHERE id=$1 AND is_finished=FALSE RETURNING id",
            match_id)
        return row is not None

async def add_match(stage, team1, team2, match_time_str, city="", next_match_id=None):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO matches(stage,team1,team2,match_time,city,next_match_id)
            VALUES($1,$2,$3,$4::timestamptz,$5,$6) RETURNING id
        """, stage, team1, team2, match_time_str+"+00", city, next_match_id)
        return row["id"]

async def update_match_teams(match_id, team1, team2):
    """عوض کردن تیم‌های یک بازی → پیش‌بینی‌های قبلی پاک میشن
    (چون تیم‌ها عوض شدن، پیش‌بینی برای تیم‌های قدیمی بی‌معنیه)"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("DELETE FROM predictions WHERE match_id=$1", match_id)
            await conn.execute("""
                UPDATE matches SET team1=$1, team2=$2,
                is_locked=FALSE, is_finished=FALSE,
                result1=NULL, result2=NULL, penalty1=NULL, penalty2=NULL,
                winner_team=NULL, result_sent=FALSE, notif_sent=FALSE
                WHERE id=$3
            """, team1, team2, match_id)

async def set_result(match_id, r1, r2, penalty1=None, penalty2=None, force=False,
                     et1=None, et2=None):
    """ثبت نتیجه + محاسبه امتیاز + تعیین برنده

    force=True → حتی اگه بازی finished باشه، نتیجه و امتیازها بازنویسی میشن (اصلاح)

    امتیازدهی همیشه بر اساس نتیجه ۹۰ دقیقه (r1, r2) انجام میشه.
    برای bracket_winner (پر کردن جدول):
      1. اگه بازی ۹۰ دقیقه برنده داشت → از r1/r2
      2. اگه تساوی بود و وقت اضافه داریم (et1/et2) → از نتیجه وقت اضافه
      3. اگه هنوز مساوی بود و پنالتی داریم (penalty1/penalty2) → از پنالتی
    """
    import re as _re
    def _is_placeholder(name):
        if not name: return True
        return bool(_re.fullmatch(r"[1-3][A-L]+|W\d{1,3}|L\d{1,3}", name.strip()))

    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            m = await conn.fetchrow("SELECT * FROM matches WHERE id=$1 FOR UPDATE", match_id)
            if not m:
                return 0, None, []
            if m["is_finished"] and not force:
                return 0, None, []

            # برنده برای امتیازدهی: فقط بر اساس ۹۰ دقیقه
            if r1 > r2:
                scoring_winner = m["team1"]
            elif r2 > r1:
                scoring_winner = m["team2"]
            else:
                scoring_winner = None  # تساوی → امتیاز تساوی

            # برنده برای bracket: ۹۰ دقیقه → وقت اضافه → پنالتی
            if scoring_winner:
                bracket_winner = scoring_winner
            elif et1 is not None and et2 is not None and et1 != et2:
                # وقت اضافه برنده داشت (مثلاً 1-1 → 2-1 بعد از AET)
                bracket_winner = m["team1"] if et1 > et2 else m["team2"]
            elif penalty1 is not None and penalty2 is not None:
                bracket_winner = m["team1"] if penalty1 > penalty2 else m["team2"]
            else:
                bracket_winner = None

            await conn.execute("""
                UPDATE matches
                SET result1=$1, result2=$2, penalty1=$3, penalty2=$4,
                    winner_team=$5, is_locked=TRUE, is_finished=TRUE
                WHERE id=$6
            """, r1, r2, penalty1, penalty2, bracket_winner, match_id)

            # محاسبه/بازمحاسبه امتیاز همه پیش‌بینی‌ها (نه فقط NULL)
            preds = await conn.fetch(
                "SELECT * FROM predictions WHERE match_id=$1", match_id)
            changed = []
            for p in preds:
                new_pts = calc_points(p["pred1"], p["pred2"], r1, r2)
                old_pts = p["points"]
                if old_pts != new_pts:
                    await conn.execute(
                        "UPDATE predictions SET points=$1 WHERE id=$2", new_pts, p["id"])
                    changed.append({
                        "user_id": p["user_id"],
                        "pred1": p["pred1"], "pred2": p["pred2"],
                        "old_pts": old_pts, "new_pts": new_pts,
                    })

            # پر کردن بازی بعدی با bracket_winner — هم next_match_id هم W{api_id}
            if bracket_winner:
                w_placeholder = f"W{m['api_id']}" if m["api_id"] else None
                l_placeholder = f"L{m['api_id']}" if m["api_id"] else None
                loser = m["team2"] if bracket_winner == m["team1"] else m["team1"]

                # روش ۱: next_match_id مستقیم (اگه ست شده باشه)
                if m["next_match_id"]:
                    next_m = await conn.fetchrow(
                        "SELECT * FROM matches WHERE id=$1", m["next_match_id"])
                    if next_m:
                        if _is_placeholder(next_m["team1"]):
                            await conn.execute(
                                "UPDATE matches SET team1=$1 WHERE id=$2",
                                bracket_winner, m["next_match_id"])
                        elif _is_placeholder(next_m["team2"]):
                            await conn.execute(
                                "UPDATE matches SET team2=$1 WHERE id=$2",
                                bracket_winner, m["next_match_id"])

                # روش ۲: جستجو بر اساس placeholder W{api_id} در همه بازی‌ها
                elif w_placeholder:
                    await conn.execute("""
                        UPDATE matches SET team1=$1
                        WHERE team1=$2 AND is_finished=FALSE
                    """, bracket_winner, w_placeholder)
                    await conn.execute("""
                        UPDATE matches SET team2=$1
                        WHERE team2=$2 AND is_finished=FALSE
                    """, bracket_winner, w_placeholder)

                # پر کردن بازی سوم (L placeholder) با بازنده
                if l_placeholder and loser:
                    await conn.execute("""
                        UPDATE matches SET team1=$1
                        WHERE team1=$2 AND is_finished=FALSE
                    """, loser, l_placeholder)
                    await conn.execute("""
                        UPDATE matches SET team2=$1
                        WHERE team2=$2 AND is_finished=FALSE
                    """, loser, l_placeholder)

            return len(preds), bracket_winner, changed


async def mark_notif_sent(match_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE matches SET notif_sent=TRUE WHERE id=$1", match_id)

async def mark_result_sent(match_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE matches SET result_sent=TRUE WHERE id=$1", match_id)

# ── PREDICTIONS ───────────────────────────────

async def save_prediction(user_id, match_id, p1, p2):
    """ثبت پیش‌بینی — فقط اگه قفل نباشه، هنوز شروع نشده و تیم‌ها مشخص شده باشن"""
    from wc_data import is_placeholder_team
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            m = await conn.fetchrow(
                "SELECT is_locked, match_time, team1, team2 FROM matches WHERE id=$1 FOR UPDATE",
                match_id)
            if not m or m["is_locked"]:
                return False
            # اگه تیم‌ها هنوز placeholder هستن (مثل 1A یا W77) پیش‌بینی مجاز نیست
            if is_placeholder_team(m["team1"]) or is_placeholder_team(m["team2"]):
                return False
            ok = await conn.fetchval(
                "SELECT match_time > NOW() FROM matches WHERE id=$1", match_id)
            if not ok:
                return False
            await conn.execute("""
                INSERT INTO predictions(user_id,match_id,pred1,pred2)
                VALUES($1,$2,$3,$4)
                ON CONFLICT(user_id,match_id) DO UPDATE
                  SET pred1=$3,pred2=$4,updated_at=NOW(),points=NULL
            """, user_id, match_id, p1, p2)
            return True

async def get_prediction(user_id, match_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM predictions WHERE user_id=$1 AND match_id=$2",
            user_id, match_id)

async def get_match_predictions(match_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT * FROM predictions WHERE match_id=$1", match_id)

async def count_exact_predictions(match_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT COUNT(*) FROM predictions WHERE match_id=$1 AND points=10",
            match_id) or 0

async def get_user_stats(user_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        total = await conn.fetchval(
            "SELECT COALESCE(SUM(points),0) FROM predictions WHERE user_id=$1",
            user_id) or 0
        counts = await conn.fetchrow("""
            SELECT
                COUNT(*) FILTER (WHERE points IS NOT NULL) AS finished,
                COUNT(*) FILTER (WHERE points=10)          AS exact_c,
                COUNT(*) FILTER (WHERE points=7)           AS diff_c,
                COUNT(*) FILTER (WHERE points=5)           AS winner_c,
                COUNT(*) FILTER (WHERE points=2)           AS wrong_c,
                COUNT(*)                                   AS total_preds
            FROM predictions WHERE user_id=$1
        """, user_id)
        last5 = await conn.fetch("""
            SELECT p.*,m.team1,m.team2,m.result1,m.result2,m.is_finished
            FROM predictions p JOIN matches m ON m.id=p.match_id
            WHERE p.user_id=$1 ORDER BY m.match_time DESC LIMIT 5
        """, user_id)
        return {
            "total": int(total),
            "finished": counts["finished"],
            "exact_c": counts["exact_c"],
            "diff_c": counts["diff_c"],
            "winner_c": counts["winner_c"],
            "wrong_c": counts["wrong_c"],
            "total_preds": counts["total_preds"],
            "last5": last5,
        }

async def leaderboard(limit=50):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch("""
            SELECT u.user_id, u.display_name,
                   COALESCE(SUM(p.points),0)
                   + COALESCE((SELECT SUM(a.points) FROM advancement_predictions a
                                WHERE a.user_id=u.user_id),0) AS total,
                   COUNT(p.id) AS preds,
                   COUNT(*) FILTER (WHERE p.points=10) AS exact_c
            FROM users u LEFT JOIN predictions p ON p.user_id=u.user_id
            GROUP BY u.user_id, u.display_name
            ORDER BY total DESC, preds DESC LIMIT $1
        """, limit)

async def get_user_rank(user_id):
    """رتبه کاربر در رده‌بندی کلی (شامل امتیاز صعود)"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval("""
            SELECT rank FROM (
                SELECT u.user_id,
                       RANK() OVER (ORDER BY
                           COALESCE(SUM(p.points),0)
                           + COALESCE((SELECT SUM(a.points) FROM advancement_predictions a
                                        WHERE a.user_id=u.user_id),0)
                       DESC) AS rank
                FROM users u LEFT JOIN predictions p ON p.user_id=u.user_id
                GROUP BY u.user_id
            ) t WHERE user_id=$1
        """, user_id) or 0

# ── LEAGUES ───────────────────────────────────

def _gen_invite_code(n=6):
    alphabet = string.ascii_uppercase + string.digits
    # حذف حروف گمراه‌کننده
    alphabet = alphabet.replace("O","").replace("0","").replace("I","").replace("1","")
    return "".join(secrets.choice(alphabet) for _ in range(n))

async def create_league(owner_id: int, name: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        # کد یکتا بساز
        for _ in range(10):
            code = _gen_invite_code()
            exists = await conn.fetchval("SELECT 1 FROM leagues WHERE invite_code=$1", code)
            if not exists:
                break
        row = await conn.fetchrow("""
            INSERT INTO leagues(name, owner_id, invite_code)
            VALUES($1,$2,$3) RETURNING id, invite_code
        """, name.strip()[:50], owner_id, code)
        await conn.execute("""
            INSERT INTO league_members(league_id, user_id) VALUES($1,$2)
            ON CONFLICT DO NOTHING
        """, row["id"], owner_id)
        return row["id"], row["invite_code"]

async def join_league_by_code(user_id: int, code: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        league = await conn.fetchrow(
            "SELECT * FROM leagues WHERE UPPER(invite_code)=UPPER($1)", code.strip())
        if not league:
            return None, "not_found"
        already = await conn.fetchval("""
            SELECT 1 FROM league_members WHERE league_id=$1 AND user_id=$2
        """, league["id"], user_id)
        if already:
            return league, "already"
        await conn.execute("""
            INSERT INTO league_members(league_id, user_id) VALUES($1,$2)
        """, league["id"], user_id)
        return league, "joined"

async def get_user_leagues(user_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch("""
            SELECT l.*, (l.owner_id=$1) AS is_owner,
                   (SELECT COUNT(*) FROM league_members WHERE league_id=l.id) AS member_count
            FROM leagues l
            JOIN league_members lm ON lm.league_id=l.id
            WHERE lm.user_id=$1
            ORDER BY l.created_at DESC
        """, user_id)

async def get_league(league_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM leagues WHERE id=$1", league_id)

async def is_league_member(league_id: int, user_id: int) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return bool(await conn.fetchval("""
            SELECT 1 FROM league_members WHERE league_id=$1 AND user_id=$2
        """, league_id, user_id))

async def league_leaderboard(league_id: int, limit=100):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch("""
            SELECT u.user_id, u.display_name,
                   COALESCE(SUM(p.points),0)
                   + COALESCE((SELECT SUM(a.points) FROM advancement_predictions a
                                WHERE a.user_id=u.user_id),0) AS total,
                   COUNT(p.id) AS preds,
                   COUNT(*) FILTER (WHERE p.points=10) AS exact_c
            FROM league_members lm
            JOIN users u ON u.user_id=lm.user_id
            LEFT JOIN predictions p ON p.user_id=u.user_id
            WHERE lm.league_id=$1
            GROUP BY u.user_id, u.display_name
            ORDER BY total DESC, preds DESC
            LIMIT $2
        """, league_id, limit)

async def leave_league(league_id: int, user_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            DELETE FROM league_members WHERE league_id=$1 AND user_id=$2
        """, league_id, user_id)

async def delete_league(league_id: int, owner_id: int) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        league = await conn.fetchrow("SELECT * FROM leagues WHERE id=$1", league_id)
        if not league or league["owner_id"] != owner_id:
            return False
        await conn.execute("DELETE FROM leagues WHERE id=$1", league_id)
        return True

async def get_league_members(league_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch("""
            SELECT u.user_id, u.display_name, u.lang
            FROM league_members lm JOIN users u ON u.user_id=lm.user_id
            WHERE lm.league_id=$1
        """, league_id)

# ── BOOSTS ─────────────────────────────────────

async def get_boost(user_id: int, stage: str):
    """بوستر کاربر در یک مرحله (یا None اگه نزده)"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM boosts WHERE user_id=$1 AND stage=$2",
            user_id, stage)

async def set_boost(user_id: int, match_id: int, stage: str) -> str:
    """ثبت/تغییر/حذف بوستر.
    قوانین:
    - اگه بازی مورد نظر قفل شده → 'locked' (نه ثبت، نه تغییر، نه حذف)
    - اگه بوست قبلی روی بازی قفل‌شده‌ست → 'prev_locked' (بوست قدیمی رو نمیشه عوض کرد)
    - اگه دوباره همون بازی باز رو زدی → 'removed' (toggle حذف)
    - اگه بوست قبلی داشتی روی بازی باز → 'changed' (انتقال)
    - اگه اولین باره → 'ok'
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # چک: بازی انتخابی قفل نباشه
            m = await conn.fetchrow(
                "SELECT is_locked FROM matches WHERE id=$1", match_id)
            if not m or m["is_locked"]:
                return "locked"

            existing = await conn.fetchrow(
                "SELECT b.*, mx.is_locked AS prev_locked "
                "FROM boosts b JOIN matches mx ON mx.id=b.match_id "
                "WHERE b.user_id=$1 AND b.stage=$2",
                user_id, stage)

            if existing:
                if existing["prev_locked"]:
                    # بازی قبلی شروع شده — نمیشه بوست رو جابجا یا حذف کرد
                    return "prev_locked"
                if existing["match_id"] == match_id:
                    # toggle: حذف بوست (فقط اگه بازی هنوز باز باشه)
                    await conn.execute(
                        "DELETE FROM boosts WHERE user_id=$1 AND stage=$2", user_id, stage)
                    return "removed"
                # انتقال بوست از بازی قبلی (باز) به بازی جدید (باز)
                await conn.execute("""
                    UPDATE boosts SET match_id=$1, created_at=NOW()
                    WHERE user_id=$2 AND stage=$3
                """, match_id, user_id, stage)
                return "changed"

            await conn.execute("""
                INSERT INTO boosts(user_id, match_id, stage) VALUES($1,$2,$3)
            """, user_id, match_id, stage)
            return "ok"

async def get_user_boosts(user_id: int):
    """همه بوست‌های کاربر"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT * FROM boosts WHERE user_id=$1", user_id)

async def get_match_boost_users(match_id: int):
    """کاربرایی که این بازی رو بوست کردن"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT user_id FROM boosts WHERE match_id=$1", match_id)

# ── ADVANCEMENT PREDICTIONS ────────────────────

async def save_advancement(user_id: int, match_id: int, team: str) -> str:
    """ثبت پیش‌بینی تیم صعودکننده.
    خروجی: 'ok' | 'locked' | 'invalid_team'"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            m = await conn.fetchrow(
                "SELECT is_locked, team1, team2 FROM matches WHERE id=$1 FOR UPDATE", match_id)
            if not m or m["is_locked"]:
                return "locked"
            if team not in (m["team1"], m["team2"]):
                return "invalid_team"
            await conn.execute("""
                INSERT INTO advancement_predictions(user_id, match_id, team)
                VALUES($1,$2,$3)
                ON CONFLICT(user_id, match_id) DO UPDATE
                  SET team=$3, points=NULL, updated_at=NOW()
            """, user_id, match_id, team)
            return "ok"

async def get_advancement(user_id: int, match_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM advancement_predictions WHERE user_id=$1 AND match_id=$2",
            user_id, match_id)

async def delete_advancement(user_id: int, match_id: int) -> bool:
    """حذف پیش‌بینی صعود — فقط اگه بازی قفل نشده باشه."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            m = await conn.fetchrow(
                "SELECT is_locked FROM matches WHERE id=$1 FOR UPDATE", match_id)
            if not m or m["is_locked"]:
                return False
            await conn.execute(
                "DELETE FROM advancement_predictions WHERE user_id=$1 AND match_id=$2",
                user_id, match_id)
            return True

async def score_advancements(match_id: int, winner_team: str) -> list:
    """بعد از مشخص شدن برنده، امتیاز پیش‌بینی صعود رو محاسبه کن (+۵ یا ۰)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        preds = await conn.fetch(
            "SELECT * FROM advancement_predictions WHERE match_id=$1", match_id)
        changed = []
        for p in preds:
            pts = 5 if p["team"] == winner_team else 0
            await conn.execute(
                "UPDATE advancement_predictions SET points=$1 WHERE id=$2", pts, p["id"])
            changed.append({"user_id": p["user_id"], "team": p["team"], "points": pts})
        return changed

async def apply_boosts_to_predictions(match_id: int) -> list:
    """بعد از محاسبه امتیاز پیش‌بینی، بوست‌های این بازی رو اعمال کن (ضربدر ۲).
    ایمن در برابر فراخوانی چندباره: امتیاز پایه رو از calc_points محاسبه میکنه،
    نه از مقدار فعلی جدول — پس دوباره صدا زدن تاثیر مضاعف ندارد.
    برمیگردونه لیست {user_id, old_pts, new_pts}"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        # ابتدا نتیجه بازی رو بگیر تا امتیاز پایه رو از calc_points بسازیم
        match = await conn.fetchrow(
            "SELECT result1, result2 FROM matches WHERE id=$1", match_id)
        if not match or match["result1"] is None:
            return []
        r1, r2 = match["result1"], match["result2"]

        boosted_users = await conn.fetch(
            "SELECT user_id FROM boosts WHERE match_id=$1", match_id)
        changed = []
        for b in boosted_users:
            uid = b["user_id"]
            pred = await conn.fetchrow(
                "SELECT * FROM predictions WHERE user_id=$1 AND match_id=$2", uid, match_id)
            if pred and pred["pred1"] is not None:
                # امتیاز پایه (بدون بوست) — همیشه یکسان صرف‌نظر از فراخوانی قبلی
                base_pts = calc_points(pred["pred1"], pred["pred2"], r1, r2)
                boosted_pts = base_pts * 2
                old_pts = pred["points"]  # برای نمایش در پیام
                await conn.execute(
                    "UPDATE predictions SET points=$1 WHERE user_id=$2 AND match_id=$3",
                    boosted_pts, uid, match_id)
                changed.append({"user_id": uid, "old_pts": old_pts, "new_pts": boosted_pts})
        return changed

async def get_user_knockout_stats(user_id: int):
    """آمار بوست‌ها و پیش‌بینی صعود کاربر"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        adv_total = await conn.fetchval(
            "SELECT COALESCE(SUM(points),0) FROM advancement_predictions WHERE user_id=$1",
            user_id) or 0
        adv_correct = await conn.fetchval(
            "SELECT COUNT(*) FROM advancement_predictions WHERE user_id=$1 AND points=5",
            user_id) or 0
        boost_count = await conn.fetchval(
            "SELECT COUNT(*) FROM boosts WHERE user_id=$1", user_id) or 0
        return {
            "adv_total": int(adv_total),
            "adv_correct": int(adv_correct),
            "boost_count": int(boost_count),
        }

async def get_leaderboard_total(user_id: int) -> int:
    """مجموع کل امتیاز کاربر: پیش‌بینی + صعود (بوست داخل predictions محاسبه شده)"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        pred_pts = await conn.fetchval(
            "SELECT COALESCE(SUM(points),0) FROM predictions WHERE user_id=$1",
            user_id) or 0
        adv_pts = await conn.fetchval(
            "SELECT COALESCE(SUM(points),0) FROM advancement_predictions WHERE user_id=$1",
            user_id) or 0
        return int(pred_pts) + int(adv_pts)
