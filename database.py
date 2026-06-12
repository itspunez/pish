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

async def set_result(match_id, r1, r2, penalty1=None, penalty2=None, force=False):
    """ثبت نتیجه + محاسبه امتیاز + تعیین برنده
    force=True → حتی اگه بازی finished باشه، نتیجه و امتیازها بازنویسی میشن (اصلاح)

    امتیازدهی همیشه بر اساس نتیجه ۹۰ دقیقه (r1, r2) انجام میشه.
    برای پر کردن جدول مراحل حذفی، اگه تساوی بود از پنالتی برنده مشخص میشه.
    """
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

            # برنده برای پر کردن بازی بعدی (جدول): اگه تساوی بود از پنالتی استفاده میشه
            if scoring_winner:
                bracket_winner = scoring_winner
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

            # پر کردن بازی بعدی با برنده جدول (bracket_winner)
            if bracket_winner and m["next_match_id"]:
                next_m = await conn.fetchrow(
                    "SELECT * FROM matches WHERE id=$1", m["next_match_id"])
                if next_m:
                    if not next_m["team1"] or next_m["team1"].startswith("TBD"):
                        await conn.execute(
                            "UPDATE matches SET team1=$1 WHERE id=$2",
                            bracket_winner, m["next_match_id"])
                    elif not next_m["team2"] or next_m["team2"].startswith("TBD"):
                        await conn.execute(
                            "UPDATE matches SET team2=$1 WHERE id=$2",
                            bracket_winner, m["next_match_id"])

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
                   COALESCE(SUM(p.points),0) AS total,
                   COUNT(p.id) AS preds,
                   COUNT(*) FILTER (WHERE p.points=10) AS exact_c
            FROM users u LEFT JOIN predictions p ON p.user_id=u.user_id
            GROUP BY u.user_id, u.display_name
            ORDER BY total DESC, preds DESC LIMIT $1
        """, limit)

async def get_user_rank(user_id):
    """رتبه کاربر در رده‌بندی کلی (سازگار با leaderboard — همه کاربرا، نه فقط کسانی که پیش‌بینی کردن)"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval("""
            SELECT rank FROM (
                SELECT u.user_id,
                       RANK() OVER (ORDER BY COALESCE(SUM(p.points),0) DESC) AS rank
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
                   COALESCE(SUM(p.points),0) AS total,
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
