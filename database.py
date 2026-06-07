import asyncpg
from datetime import datetime
from config import DATABASE_URL
from utils import calc_points

_pool = None

async def get_pool():
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
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
            id          SERIAL PRIMARY KEY,
            grp         TEXT,
            round_no    INT DEFAULT NULL,
            stage       TEXT NOT NULL DEFAULT 'group',
            team1       TEXT NOT NULL,
            team2       TEXT NOT NULL,
            match_time  TIMESTAMPTZ NOT NULL,
            city        TEXT DEFAULT '',
            result1     INT DEFAULT NULL,
            result2     INT DEFAULT NULL,
            is_locked   BOOLEAN DEFAULT FALSE,
            is_finished BOOLEAN DEFAULT FALSE
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
        CREATE INDEX IF NOT EXISTS idx_pred_user   ON predictions(user_id);
        CREATE INDEX IF NOT EXISTS idx_match_stage ON matches(stage);
        CREATE INDEX IF NOT EXISTS idx_match_time  ON matches(match_time);
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
        return await conn.fetch("SELECT user_id FROM users")

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
        return await conn.fetch("""
            SELECT * FROM matches WHERE stage='group' ORDER BY match_time
        """)

async def get_all_matches(stage=None):
    pool = await get_pool()
    async with pool.acquire() as conn:
        if stage:
            return await conn.fetch(
                "SELECT * FROM matches WHERE stage=$1 ORDER BY match_time", stage)
        return await conn.fetch("SELECT * FROM matches ORDER BY match_time")

async def get_match(match_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM matches WHERE id=$1", match_id)

async def add_match(stage, team1, team2, match_time, city=""):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO matches(stage,team1,team2,match_time,city)
            VALUES($1,$2,$3,$4::timestamptz,$5) RETURNING id
        """, stage, team1, team2, match_time+"+00", city)
        return row["id"]

async def update_match_teams(match_id, team1, team2):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE matches SET team1=$1, team2=$2,
            is_locked=FALSE, is_finished=FALSE,
            result1=NULL, result2=NULL
            WHERE id=$3
        """, team1, team2, match_id)

async def lock_due_matches():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE matches SET is_locked=TRUE
            WHERE match_time <= NOW() AND is_locked=FALSE
        """)

async def set_result(match_id, r1, r2):
    pool = await get_pool()
    async with pool.acquire() as conn:
        m = await conn.fetchrow("SELECT * FROM matches WHERE id=$1", match_id)
        if not m or m["is_finished"]: return 0
        await conn.execute("""
            UPDATE matches SET result1=$1,result2=$2,is_locked=TRUE,is_finished=TRUE
            WHERE id=$3
        """, r1, r2, match_id)
        preds = await conn.fetch(
            "SELECT * FROM predictions WHERE match_id=$1 AND points IS NULL", match_id)
        for p in preds:
            pts = calc_points(p["pred1"], p["pred2"], r1, r2)
            await conn.execute("UPDATE predictions SET points=$1 WHERE id=$2", pts, p["id"])
        return len(preds)

# ── PREDICTIONS ───────────────────────────────

async def save_prediction(user_id, match_id, p1, p2):
    pool = await get_pool()
    async with pool.acquire() as conn:
        m = await conn.fetchrow("SELECT is_locked FROM matches WHERE id=$1", match_id)
        if not m or m["is_locked"]: return False
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
            "SELECT * FROM predictions WHERE user_id=$1 AND match_id=$2", user_id, match_id)

async def get_user_stats(user_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        total = await conn.fetchval(
            "SELECT COALESCE(SUM(points),0) FROM predictions WHERE user_id=$1", user_id) or 0
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
        return {"total":int(total),"finished":counts["finished"],
                "exact_c":counts["exact_c"],"diff_c":counts["diff_c"],
                "winner_c":counts["winner_c"],"wrong_c":counts["wrong_c"],
                "total_preds":counts["total_preds"],"last5":last5}

async def leaderboard(limit=50):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch("""
            SELECT u.user_id, u.display_name,
                   COALESCE(SUM(p.points),0) AS total,
                   COUNT(p.id) AS preds,
                   COUNT(*) FILTER (WHERE p.points=10) AS exact_c
            FROM users u LEFT JOIN predictions p ON p.user_id=u.user_id
            GROUP BY u.user_id,u.display_name
            ORDER BY total DESC, preds DESC LIMIT $1
        """, limit)

async def get_user_rank(user_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval("""
            SELECT rank FROM (
                SELECT user_id, RANK() OVER (ORDER BY COALESCE(SUM(points),0) DESC) AS rank
                FROM predictions GROUP BY user_id
            ) t WHERE user_id=$1
        """, user_id) or 0
