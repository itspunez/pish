import logging
import asyncio
from datetime import timedelta

from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ConversationHandler, filters
)

from config import BOT_TOKEN
from database import init_db, bulk_insert_group_matches, close_pool, lock_due_matches
from wc_data import GROUP_MATCHES
from notifier import send_reminders, check_and_announce_results, sync_api_ids
from handlers.user import (
    cmd_start, cb_lang, cb_show_stages, cb_stage, cb_round, cb_group,
    cb_locked_info, cb_noop, cb_predict_start, handle_prediction_input,
    cmd_cancel, cb_mystats, cb_leaderboard, cb_main, cb_changelang,
    PREDICT_INPUT
)
from handlers.admin import (
    cmd_admin, cb_adminpanel, cb_admin_list,
    cb_admin_result_start, admin_result_id, admin_result_score, admin_result_penalty,
    cb_admin_addmatch_start, admin_match_t1, admin_match_t2,
    admin_match_stage, admin_match_time, admin_match_city,
    cb_admin_editmatch_start, admin_edit_id, admin_edit_t1, admin_edit_t2,
    cb_admin_broadcast, cmd_sendall, cb_toggle_maintenance,
    cmd_testfull, cmd_cleartestdata,
    cmd_cancel as admin_cancel,
    ADMIN_RESULT_ID, ADMIN_RESULT_SCORE, ADMIN_RESULT_PENALTY,
    ADMIN_MATCH_T1, ADMIN_MATCH_T2, ADMIN_MATCH_STAGE, ADMIN_MATCH_TIME, ADMIN_MATCH_CITY,
    ADMIN_EDIT_ID, ADMIN_EDIT_T1, ADMIN_EDIT_T2,
)

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)

# ── Scheduler ─────────────────────────────────

async def scheduler(bot):
    """
    هر ۶۰ ثانیه:
    - بازی‌های شروع‌شده رو قفل کن
    - یادآوری ۱ ساعت قبل بفرست
    - نتایج بازی‌های تموم‌شده رو بگیر و اعلام کن
    """
    while True:
        try:
            await lock_due_matches()
            await send_reminders(bot)
            await check_and_announce_results(bot)
        except Exception as e:
            log.error(f"Scheduler error: {e}")
        await asyncio.sleep(60)

# ── Conversations ──────────────────────────────

def predict_conv():
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(cb_predict_start, pattern=r"^predict_\d+$")],
        states={PREDICT_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_prediction_input)]},
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        per_user=True, per_chat=False,
    )

def admin_result_conv():
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(cb_admin_result_start, pattern="^admin_result$")],
        states={
            ADMIN_RESULT_ID:      [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_result_id)],
            ADMIN_RESULT_SCORE:   [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_result_score)],
            ADMIN_RESULT_PENALTY: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_result_penalty)],
        },
        fallbacks=[CommandHandler("cancel", admin_cancel)],
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
        fallbacks=[CommandHandler("cancel", admin_cancel)],
    )

def admin_editmatch_conv():
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(cb_admin_editmatch_start, pattern="^admin_editmatch$")],
        states={
            ADMIN_EDIT_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_edit_id)],
            ADMIN_EDIT_T1: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_edit_t1)],
            ADMIN_EDIT_T2: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_edit_t2)],
        },
        fallbacks=[CommandHandler("cancel", admin_cancel)],
    )

# ── Startup / Shutdown ─────────────────────────

async def post_init(app):
    await init_db()
    await bulk_insert_group_matches(GROUP_MATCHES)
    log.info("✅ DB ready — %d group matches", len(GROUP_MATCHES))
    asyncio.create_task(scheduler(app.bot))
    log.info("✅ Scheduler started")
    asyncio.create_task(sync_api_ids())
    log.info("✅ API sync started")

async def post_shutdown(app):
    await close_pool()
    log.info("✅ DB pool closed")

# ── Main ───────────────────────────────────────

def main():
    app = (ApplicationBuilder()
           .token(BOT_TOKEN)
           .post_init(post_init)
           .post_shutdown(post_shutdown)
           .build())

    app.add_handler(predict_conv())
    app.add_handler(admin_result_conv())
    app.add_handler(admin_addmatch_conv())
    app.add_handler(admin_editmatch_conv())

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

    app.add_handler(CallbackQueryHandler(cb_adminpanel,         pattern="^adminpanel$"))
    app.add_handler(CallbackQueryHandler(cb_admin_list,         pattern="^admin_list$"))
    app.add_handler(CallbackQueryHandler(cb_admin_broadcast,    pattern="^admin_broadcast$"))
    app.add_handler(CallbackQueryHandler(cb_toggle_maintenance, pattern="^admin_toggle_maint$"))

    log.info("🚀 Bot starting...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
