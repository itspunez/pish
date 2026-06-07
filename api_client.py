"""
football-data.org API client
رایگان، معتبر، از ۲۰۱۳ فعاله
"""
import asyncio
import logging
import httpx
from config import FOOTBALL_API_KEY, WC_COMPETITION_ID
from wc_data import API_NAME_MAP

log = logging.getLogger(__name__)

BASE = "https://api.football-data.org/v4"
HEADERS = {"X-Auth-Token": FOOTBALL_API_KEY}

def normalize_team(name: str) -> str:
    return API_NAME_MAP.get(name, name)

async def get_match_result(api_match_id: int) -> dict | None:
    """
    نتیجه یک بازی رو از API بگیر
    برمیگردونه: {status, home_score, away_score, penalty_home, penalty_away}
    یا None اگه خطا داشت
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{BASE}/matches/{api_match_id}", headers=HEADERS)
            if r.status_code != 200:
                log.warning(f"API {r.status_code} for match {api_match_id}")
                return None
            data = r.json()
            score = data.get("score", {})
            status = data.get("status", "")

            ft = score.get("fullTime", {})
            pen = score.get("penalties", {})

            return {
                "status": status,  # FINISHED, IN_PLAY, etc
                "home_score": ft.get("home"),
                "away_score": ft.get("away"),
                "penalty_home": pen.get("home"),
                "penalty_away": pen.get("away"),
            }
    except Exception as e:
        log.error(f"API error match {api_match_id}: {e}")
        return None

async def get_competition_matches() -> list:
    """
    همه بازی‌های جام جهانی رو بگیر
    برای sync کردن api_id با match های دیتابیس
    """
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                f"{BASE}/competitions/{WC_COMPETITION_ID}/matches",
                headers=HEADERS)
            if r.status_code != 200:
                log.warning(f"API competition {r.status_code}")
                return []
            data = r.json()
            return data.get("matches", [])
    except Exception as e:
        log.error(f"API competition error: {e}")
        return []
