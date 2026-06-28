import os
import sys

BOT_TOKEN        = os.getenv("BOT_TOKEN", "")
ADMIN_IDS        = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
DATABASE_URL     = os.getenv("DATABASE_URL", "")
FOOTBALL_API_KEY = os.getenv("FOOTBALL_API_KEY", "")  # از football-data.org

# بررسی متغیرهای ضروری — اگه نباشن، بات اصلاً شروع نمی‌کنه
_missing = [v for v in ("BOT_TOKEN", "DATABASE_URL") if not os.getenv(v)]
if _missing:
    sys.exit(f"❌ خطا: متغیرهای محیطی تنظیم نشدن: {', '.join(_missing)}\n"
             f"   در فایل .env یا تنظیمات سرور این متغیرها رو set کن.")

# جام جهانی ۲۰۲۶ — competition ID در football-data.org
WC_COMPETITION_ID = 2000

POINTS = {
    "exact":   10,
    "diff":     7,
    "winner":   5,
    "wrong":    2,
    "no_pred":  0,
}
