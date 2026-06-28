"""football-data.org API client"""
import asyncio
import logging
import time
import httpx
from config import FOOTBALL_API_KEY, WC_COMPETITION_ID
from wc_data import API_NAME_MAP

log = logging.getLogger(__name__)

BASE = "https://api.football-data.org/v4"
HEADERS = {"X-Auth-Token": FOOTBALL_API_KEY}

# ── Throttle ساده (۱۰ req/min در پلن رایگان)
_min_interval = 7.0   # حداقل ۷ ثانیه بین درخواست‌ها = ~8/min امن
_last_call = 0.0
_lock = asyncio.Lock()

async def _throttle():
    global _last_call
    async with _lock:
        now = time.monotonic()
        wait = _min_interval - (now - _last_call)
        if wait > 0:
            await asyncio.sleep(wait)
        _last_call = time.monotonic()

def normalize_team(name: str) -> str:
    return API_NAME_MAP.get(name, name)

async def _get(url: str, timeout: int = 10):
    await _throttle()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.get(url, headers=HEADERS)
            if r.status_code == 429:
                log.warning("API 429 rate-limited; backing off 60s")
                await asyncio.sleep(60)
                return None
            if r.status_code != 200:
                log.warning(f"API {r.status_code}: {url}")
                return None
            return r.json()
    except Exception as e:
        log.error(f"API error {url}: {e}")
        return None

async def get_match_result(api_match_id: int) -> dict | None:
    """نتیجه یک بازی.

    منطق امتیازدهی:
    - بازی گروهی: نتیجه ۹۰ دقیقه (regularTime یا fullTime اگه regularTime نباشه)
    - بازی حذفی: نتیجه ۹۰ دقیقه برای امتیاز (scoring)؛ اگه تساوی بود،
      نتیجه بعد از وقت اضافه (extraTime/fullTime) برای تعیین bracket_winner استفاده میشه
      و در صورت مساوی ماندن، ضربات پنالتی برنده رو مشخص می‌کنه.

    کلیدهای خروجی:
      home_score / away_score  → نتیجه ۹۰ دقیقه (مبنای محاسبه امتیاز)
      et_home / et_away        → نتیجه بعد از وقت اضافه (برای تعیین bracket_winner)
      penalty_home / penalty_away → ضربات پنالتی
      status                   → وضعیت بازی
    """
    data = await _get(f"{BASE}/matches/{api_match_id}")
    if not data:
        return None
    score = data.get("score", {})
    status = data.get("status", "")
    reg = score.get("regularTime") or {}
    et  = score.get("extraTime")   or {}
    ft  = score.get("fullTime")    or {}
    pen = score.get("penalties")   or {}

    # نتیجه ۹۰ دقیقه:
    #   اگه regularTime پر شده باشه (بازی‌های حذفی) → از regularTime
    #   وگرنه (بازی‌های گروهی) → از fullTime
    home_90 = reg.get("home") if reg.get("home") is not None else ft.get("home")
    away_90 = reg.get("away") if reg.get("away") is not None else ft.get("away")

    # نتیجه بعد از وقت اضافه:
    #   اگه extraTime وجود داشت → از extraTime
    #   وگرنه → از fullTime (که ممکنه شامل AET باشه)
    et_home = et.get("home") if et.get("home") is not None else ft.get("home")
    et_away = et.get("away") if et.get("away") is not None else ft.get("away")

    return {
        "status":       status,
        "home_score":   home_90,
        "away_score":   away_90,
        "et_home":      et_home,
        "et_away":      et_away,
        "penalty_home": pen.get("home"),
        "penalty_away": pen.get("away"),
    }

async def get_competition_matches() -> list:
    data = await _get(f"{BASE}/competitions/{WC_COMPETITION_ID}/matches", timeout=15)
    if not data:
        return []
    return data.get("matches", [])
