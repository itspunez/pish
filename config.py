import os

BOT_TOKEN    = os.getenv("BOT_TOKEN", "")
ADMIN_IDS    = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
DATABASE_URL = os.getenv("DATABASE_URL", "")

POINTS = {
    "exact":   10,
    "diff":     7,
    "winner":   5,
    "wrong":    2,
    "no_pred":  0,
}
