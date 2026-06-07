import os

BOT_TOKEN      = os.getenv("BOT_TOKEN", "")
ADMIN_IDS      = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
DATABASE_URL   = os.getenv("DATABASE_URL", "")
FOOTBALL_API_KEY = os.getenv("FOOTBALL_API_KEY", "")  # از football-data.org

# جام جهانی ۲۰۲۶ — competition ID در football-data.org
WC_COMPETITION_ID = 2000

POINTS = {
    "exact":   10,
    "diff":     7,
    "winner":   5,
    "wrong":    2,
    "no_pred":  0,
}
