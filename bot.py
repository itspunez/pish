import logging
import asyncio

from telegram import Update
from telegram.ext import (
    ApplicationBuilder, ApplicationHandlerStop, CommandHandler, CallbackQueryHandler,
    MessageHandler, ConversationHandler, TypeHandler, ContextTypes, filters
)

from config import BOT_TOKEN, ADMIN_IDS
from maintenance import is_maintenance

from database import (init_db, bulk_insert_group_matches, bulk_insert_knockout_matches,
                      sync_match_schedules, sync_knockout_teams, close_pool, lock_due_matches)
from wc_data import GROUP_MATCHES, KNOCKOUT_MATCHES
from notifier import send_reminders, check_and_announce_results, sync_api_ids
from handlers.user import (
    cmd_start, cb_lang, cb_show_stages, cb_stage, cb_round, cb_group,
    cb_locked_info, cb_noop, cb_predict_start, handle_prediction_input,
    cmd_cancel, cb_mystats, cb_leaderboard, cb_main, cb_changelang,
    cb_boost, cb_advancement_start, cb_advancement_pick,
    PREDICT_INPUT
)
from handlers.admin import (
    cmd_admin, cb_adminpanel, cb_admin_list,
    cb_admin_result_start, admin_result_id, admin_result_score, admin_result_penalty,
    cb_admin_addmatch_start, admin_match_t1, admin_match_t2,
    admin_match_stage, admin_match_time, admin_match_city,
    cb_admin_editmatch_start, admin_edit_id, admin_edit_t1, admin_edit_t2,
    cb_admin_broadcast, cmd_sendall, cb_toggle_maintenance,
    cb_admin_lock_start, admin_lock_id,
    cmd_testfull, cmd_cleartestdata,
    cmd_cancel as admin_cancel,
    ADMIN_RESULT_ID, ADMIN_RESULT_SCORE, ADMIN_RESULT_PENALTY,
    ADMIN_MATCH_T1, ADMIN_MATCH_T2, ADMIN_MATCH_STAGE, ADMIN_MATCH_TIME, ADMIN_MATCH_CITY,
    ADMIN_EDIT_ID, ADMIN_EDIT_T1, ADMIN_EDIT_T2,
    ADMIN_LOCK_ID,
)
from handlers.league import (
    cb_leagues_menu, cb_lg_create, cb_lg_join, cb_lg_view,
    cb_lg_leave_ask, cb_lg_leave, cb_lg_delete_ask, cb_lg_delete,
    handle_league_name, handle_league_code,
    cmd_cancel as league_cancel,
    LEAGUE_NAME, LEAGUE_CODE,
)

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)

# ── Schedulers ─────────────────────────────────

async def main_scheduler(bot):
    """هر ۶۰ ثانیه: قفل بازی‌ها، یادآوری، چک نتایج."""
    while True:
        try:
            await lock_due_matches()
            await send_reminders(bot)
            await check_and_announce_results(bot)
        except Exception as e:
            log.error(f"Scheduler error: {e}")
        await asyncio.sleep(60)

async def api_sync_scheduler():
    """هر ۳۰ دقیقه: sync کردن api_id بازی‌ها (مهم برای بازی‌های حذفی که بعداً اضافه میشن)."""
    # اولین بار بعد ۱۰ ثانیه (برای استارت‌آپ)
    await asyncio.sleep(10)
    while True:
        try:
            await sync_api_ids()
        except Exception as e:
            log.error(f"API sync error: {e}")
        await asyncio.sleep(30 * 60)

# ── Conversations ──────────────────────────────

def predict_conv():
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(cb_predict_start, pattern=r"^predict_\d+$")],
        states={PREDICT_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_prediction_input)]},
        fallbacks=[
            CommandHandler("cancel", cmd_cancel),
            CommandHandler("start", cmd_start),
        ],
        per_user=True, per_chat=False,
        allow_reentry=True,
    )

def admin_result_conv():
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(cb_admin_result_start, pattern="^admin_result$")],
        states={
            ADMIN_RESULT_ID:      [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_result_id)],
            ADMIN_RESULT_SCORE:   [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_result_score)],
            ADMIN_RESULT_PENALTY: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_result_penalty)],
        },
        fallbacks=[
            CommandHandler("cancel", admin_cancel),
            CommandHandler("start", cmd_start),
        ],
        allow_reentry=True,
    )

def admin_addmatch_conv():
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(cb_admin_addmatch_start, pattern="^admin_addmatch$")],
        states={
            ADMIN_MATCH_T1:    [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_match_t1)],
            ADMIN_MATCH_T2:    [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_match_t2)],
            ADMIN_MATCH_STAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_match_stage)],
            ADMIN_MATCH_TIME:  [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_match_time)],
            ADMIN_MATCH_CITY:  [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_match_city)],
        },
        fallbacks=[
            CommandHandler("cancel", admin_cancel),
            CommandHandler("start", cmd_start),
        ],
        allow_reentry=True,
    )

def admin_editmatch_conv():
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(cb_admin_editmatch_start, pattern="^admin_editmatch$")],
        states={
            ADMIN_EDIT_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_edit_id)],
            ADMIN_EDIT_T1: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_edit_t1)],
            ADMIN_EDIT_T2: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_edit_t2)],
        },
        fallbacks=[
            CommandHandler("cancel", admin_cancel),
            CommandHandler("start", cmd_start),
        ],
        allow_reentry=True,
    )

def league_create_conv():
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(cb_lg_create, pattern="^lg_create$")],
        states={LEAGUE_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_league_name)]},
        fallbacks=[
            CommandHandler("cancel", league_cancel),
            CommandHandler("start", cmd_start),
        ],
        per_user=True, per_chat=False,
        allow_reentry=True,
    )

def league_join_conv():
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(cb_lg_join, pattern="^lg_join$")],
        states={LEAGUE_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_league_code)]},
        fallbacks=[
            CommandHandler("cancel", league_cancel),
            CommandHandler("start", cmd_start),
        ],
        per_user=True, per_chat=False,
        allow_reentry=True,
    )

# ── Maintenance gate ───────────────────────────

async def maintenance_gate(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """قبل از هر هندلر اجرا میشه. اگه بات در حالت تعمیر باشه و کاربر ادمین نباشه،
    پاسخ کوتاه می‌ده و جلوی پردازش بقیه هندلرها (شامل منوهای باز) رو می‌گیره."""
    if not is_maintenance():
        return
    user = update.effective_user
    if user and user.id in ADMIN_IDS:
        return  # ادمین‌ها بدون محدودیت
    try:
        if update.callback_query:
            await update.callback_query.answer(
                "🔧 بات موقتاً در حال تعمیر است.", show_alert=True)
        elif update.effective_message:
            await update.effective_message.reply_text(
                "🔧 بات موقتاً در حال تعمیر است. به زودی برمی‌گردیم!")
    except Exception:
        pass
    raise ApplicationHandlerStop

def admin_lock_conv():
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(cb_admin_lock_start, pattern="^admin_lock$")],
        states={
            ADMIN_LOCK_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_lock_id)],
        },
        fallbacks=[
            CommandHandler("cancel", admin_cancel),
            CommandHandler("start", cmd_start),
        ],
        allow_reentry=True,
    )

# ── Startup / Shutdown ─────────────────────────

async def post_init(app):
    await init_db()
    await bulk_insert_group_matches(GROUP_MATCHES)
    await bulk_insert_knockout_matches(KNOCKOUT_MATCHES)
    # هر بار استارت‌آپ: تاریخ/ساعت/شهر بازی‌های موجود رو از روی wc_data.py
    # هم‌گام کن. غیرتخریبی — پیش‌بینی‌ها و کاربرها دست نمیخورن.
    try:
        n = await sync_match_schedules(GROUP_MATCHES, KNOCKOUT_MATCHES)
        log.info("🕒 Schedule sync: %d match row(s) updated", n)
    except Exception as e:
        log.error("Schedule sync failed: %s", e)
    # آپدیت تیم‌های حذفی از placeholder به تیم واقعی
    try:
        n = await sync_knockout_teams(KNOCKOUT_MATCHES)
        log.info("🏟 Knockout teams sync: %d match row(s) updated", n)
    except Exception as e:
        log.error("Knockout teams sync failed: %s", e)
    log.info("✅ DB ready — %d group + %d knockout matches",
             len(GROUP_MATCHES), len(KNOCKOUT_MATCHES))
    # task ها رو نگه می‌داریم تا garbage collect نشن
    app.bot_data["main_task"] = asyncio.create_task(main_scheduler(app.bot))
    app.bot_data["sync_task"] = asyncio.create_task(api_sync_scheduler())
    log.info("✅ Schedulers started (main + api-sync every 30min)")

async def post_shutdown(app):
    for k in ("main_task", "sync_task"):
        t = app.bot_data.get(k)
        if t: t.cancel()
    await close_pool()
    log.info("✅ DB pool closed")

# ── Main ───────────────────────────────────────

def main():
    app = (ApplicationBuilder()
           .token(BOT_TOKEN)
           .post_init(post_init)
           .post_shutdown(post_shutdown)
           .build())

    # دروازه‌ی Maintenance — قبل از همه (group=-1) چک می‌کنه و جلوی بقیه رو می‌گیره
    app.add_handler(TypeHandler(Update, maintenance_gate), group=-1)

    app.add_handler(predict_conv())
    app.add_handler(admin_result_conv())
    app.add_handler(admin_addmatch_conv())
    app.add_handler(admin_editmatch_conv())
    app.add_handler(admin_lock_conv())
    app.add_handler(league_create_conv())
    app.add_handler(league_join_conv())

    app.add_handler(CommandHandler("start",         cmd_start))
    app.add_handler(CommandHandler("admin",         cmd_admin))
    app.add_handler(CommandHandler("sendall",       cmd_sendall))
    app.add_handler(CommandHandler("cancel",        cmd_cancel))
    app.add_handler(CommandHandler("testfull",      cmd_testfull))
    app.add_handler(CommandHandler("cleartestdata", cmd_cleartestdata))

    app.add_handler(CallbackQueryHandler(cb_lang,        pattern=r"^lang_"))
    app.add_handler(CallbackQueryHandler(cb_main,        pattern="^main$"))
    app.add_handler(CallbackQueryHandler(cb_changelang,  pattern="^changelang$"))
    app.add_handler(CallbackQueryHandler(cb_show_stages, pattern="^show_stages$"))
    app.add_handler(CallbackQueryHandler(cb_stage,       pattern=r"^stage_"))
    app.add_handler(CallbackQueryHandler(cb_round,       pattern=r"^round_\d+$"))
    app.add_handler(CallbackQueryHandler(cb_group,       pattern=r"^grp_"))
    app.add_handler(CallbackQueryHandler(cb_locked_info, pattern="^locked_info$"))
    app.add_handler(CallbackQueryHandler(cb_noop,        pattern="^noop$"))
    app.add_handler(CallbackQueryHandler(cb_mystats,     pattern="^mystats$"))
    app.add_handler(CallbackQueryHandler(cb_leaderboard, pattern="^leaderboard$"))
    # ── Boost & Advancement ──
    app.add_handler(CallbackQueryHandler(cb_boost,             pattern=r"^boost_\d+_\w+$"))
    app.add_handler(CallbackQueryHandler(cb_advancement_start, pattern=r"^adv_\d+$"))
    app.add_handler(CallbackQueryHandler(cb_advancement_pick,  pattern=r"^advpick_"))

    # ── League ──
    app.add_handler(CallbackQueryHandler(cb_leagues_menu,   pattern="^leagues$"))
    app.add_handler(CallbackQueryHandler(cb_lg_view,        pattern=r"^lg_view_\d+$"))
    app.add_handler(CallbackQueryHandler(cb_lg_leave_ask,   pattern=r"^lg_leaveask_\d+$"))
    app.add_handler(CallbackQueryHandler(cb_lg_leave,      pattern=r"^lg_leave_\d+$"))
    app.add_handler(CallbackQueryHandler(cb_lg_delete_ask,  pattern=r"^lg_delask_\d+$"))
    app.add_handler(CallbackQueryHandler(cb_lg_delete,      pattern=r"^lg_del_\d+$"))

    # ── Admin ──
    app.add_handler(CallbackQueryHandler(cb_adminpanel,         pattern="^adminpanel$"))
    app.add_handler(CallbackQueryHandler(cb_admin_list,         pattern="^admin_list$"))
    app.add_handler(CallbackQueryHandler(cb_admin_broadcast,    pattern="^admin_broadcast$"))
    app.add_handler(CallbackQueryHandler(cb_toggle_maintenance, pattern="^admin_toggle_maint$"))

    log.info("🚀 Bot starting...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
