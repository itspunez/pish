"""handlers/league.py — قابلیت لیگ خصوصی"""
from telegram import Update, InlineKeyboardButton as Btn, InlineKeyboardMarkup as Markup
from telegram.ext import ContextTypes, ConversationHandler

from database import (
    get_user, create_league, join_league_by_code,
    get_user_leagues, get_league, is_league_member,
    league_leaderboard, leave_league, delete_league, get_league_members,
)

# Conversation states (دور از بقیه نگه می‌داریم)
LEAGUE_NAME, LEAGUE_CODE = range(50, 52)

# ───────────────── منوی لیگ ─────────────────

async def cb_leagues_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = await get_user(query.from_user.id)
    if not user:
        await query.answer("اول /start بزن!", show_alert=True); return
    lang = user["lang"]
    leagues = await get_user_leagues(query.from_user.id)

    if lang == "fa":
        title = "🏆 <b>لیگ‌های من</b>\n\n"
        if leagues:
            title += "لیگ‌هایی که عضوشی:\n"
        else:
            title += "هنوز عضو هیچ لیگی نیستی.\nبا دوستات یه لیگ بساز یا با کد دعوت عضو شو!"
        new_btn = "➕ ساخت لیگ جدید"
        join_btn = "🔗 عضویت با کد"
        back_btn = "🔙 منوی اصلی"
    else:
        title = "🏆 <b>My Leagues</b>\n\n"
        if leagues:
            title += "Leagues you're in:\n"
        else:
            title += "You're not in any league yet.\nCreate one with friends or join with a code!"
        new_btn = "➕ Create League"
        join_btn = "🔗 Join with Code"
        back_btn = "🔙 Main Menu"

    kb = []
    for lg in leagues:
        crown = "👑 " if lg["is_owner"] else ""
        kb.append([Btn(f"{crown}{lg['name']} ({lg['member_count']})",
                       callback_data=f"lg_view_{lg['id']}")])
    kb.append([Btn(new_btn, callback_data="lg_create"),
               Btn(join_btn, callback_data="lg_join")])
    kb.append([Btn(back_btn, callback_data="main")])
    await query.edit_message_text(title, parse_mode="HTML", reply_markup=Markup(kb))

# ───────────────── ساخت لیگ ─────────────────

async def cb_lg_create(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = await get_user(query.from_user.id)
    lang = user["lang"] if user else "fa"
    ctx.user_data["lg_lang"] = lang
    txt = ("✏️ <b>اسم لیگ رو بنویس</b> (حداکثر ۵۰ حرف):\n\n/cancel برای لغو"
           if lang == "fa" else
           "✏️ <b>Send the league name</b> (max 50 chars):\n\n/cancel to cancel")
    await query.edit_message_text(txt, parse_mode="HTML")
    return LEAGUE_NAME

async def handle_league_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    lang = ctx.user_data.get("lg_lang", "fa")
    name = update.message.text.strip()
    if len(name) < 2:
        await update.message.reply_text(
            "اسم خیلی کوتاهه!" if lang == "fa" else "Name too short!")
        return LEAGUE_NAME

    league_id, code = await create_league(update.effective_user.id, name)
    if lang == "fa":
        txt = (f"✅ <b>لیگ ساخته شد!</b>\n\n"
               f"🏆 {name}\n\n"
               f"🔗 <b>کد دعوت:</b> <code>{code}</code>\n\n"
               f"این کد رو برای دوستات بفرست تا با زدن «عضویت با کد» وارد لیگ بشن.")
        view_btn = "📊 مشاهده لیگ"
        back_btn = "🏆 لیگ‌های من"
    else:
        txt = (f"✅ <b>League created!</b>\n\n"
               f"🏆 {name}\n\n"
               f"🔗 <b>Invite code:</b> <code>{code}</code>\n\n"
               f"Share this code with friends so they can join via «Join with Code».")
        view_btn = "📊 View League"
        back_btn = "🏆 My Leagues"
    await update.message.reply_text(txt, parse_mode="HTML", reply_markup=Markup([
        [Btn(view_btn, callback_data=f"lg_view_{league_id}")],
        [Btn(back_btn, callback_data="leagues")],
    ]))
    return ConversationHandler.END

# ───────────────── عضویت با کد ─────────────────

async def cb_lg_join(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = await get_user(query.from_user.id)
    lang = user["lang"] if user else "fa"
    ctx.user_data["lg_lang"] = lang
    txt = ("🔗 <b>کد دعوت رو وارد کن:</b>\n(مثلاً <code>X7K2P9</code>)\n\n/cancel برای لغو"
           if lang == "fa" else
           "🔗 <b>Enter the invite code:</b>\n(e.g. <code>X7K2P9</code>)\n\n/cancel to cancel")
    await query.edit_message_text(txt, parse_mode="HTML")
    return LEAGUE_CODE

async def handle_league_code(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    lang = ctx.user_data.get("lg_lang", "fa")
    code = update.message.text.strip()
    league, status = await join_league_by_code(update.effective_user.id, code)

    if status == "not_found":
        await update.message.reply_text(
            "❌ کد اشتباهه! دوباره تلاش کن یا /cancel" if lang == "fa"
            else "❌ Wrong code! Try again or /cancel")
        return LEAGUE_CODE
    if status == "already":
        msg = (f"ℹ️ تو الان عضو لیگ «{league['name']}» هستی!" if lang == "fa"
               else f"ℹ️ You're already in «{league['name']}»!")
    else:
        msg = (f"✅ به لیگ <b>{league['name']}</b> خوش اومدی!" if lang == "fa"
               else f"✅ Welcome to <b>{league['name']}</b>!")
    await update.message.reply_text(msg, parse_mode="HTML", reply_markup=Markup([
        [Btn("📊 مشاهده" if lang == "fa" else "📊 View",
             callback_data=f"lg_view_{league['id']}")],
        [Btn("🏆 لیگ‌های من" if lang == "fa" else "🏆 My Leagues", callback_data="leagues")],
    ]))
    return ConversationHandler.END

# ───────────────── مشاهده لیگ ─────────────────

async def cb_lg_view(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    league_id = int(query.data.split("_")[2])
    user = await get_user(query.from_user.id)
    lang = user["lang"] if user else "fa"

    if not await is_league_member(league_id, query.from_user.id):
        await query.answer("⛔ عضو این لیگ نیستی!" if lang == "fa" else "⛔ Not a member!",
                           show_alert=True)
        return

    lg = await get_league(league_id)
    if not lg:
        await query.edit_message_text("لیگ پیدا نشد!" if lang == "fa" else "League not found!")
        return
    is_owner = lg["owner_id"] == query.from_user.id

    rows = await league_leaderboard(league_id, 100)
    medals = ["🥇","🥈","🥉"]
    title = "🏆" if lang == "fa" else "🏆"

    if lang == "fa":
        txt = (f"{title} <b>{lg['name']}</b>\n"
               f"🔗 کد: <code>{lg['invite_code']}</code> | 👥 {len(rows)} عضو\n\n"
               f"<b>📊 رده‌بندی لیگ:</b>\n")
        empty = "هنوز کسی امتیازی نگرفته!"
    else:
        txt = (f"{title} <b>{lg['name']}</b>\n"
               f"🔗 Code: <code>{lg['invite_code']}</code> | 👥 {len(rows)} members\n\n"
               f"<b>📊 League Leaderboard:</b>\n")
        empty = "No scores yet!"

    me = query.from_user.id
    has_scores = False
    for i, r in enumerate(rows):
        if r["total"] > 0 or r["preds"] > 0:
            has_scores = True
        medal = medals[i] if i < 3 else f"{i+1}."
        me_mark = " 👈" if r["user_id"] == me else ""
        exact = f" 🎯{r['exact_c']}" if r["exact_c"] else ""
        pts_lbl = "امتیاز" if lang == "fa" else "pts"
        txt += f"{medal} <b>{r['display_name']}</b> — {r['total']} {pts_lbl}{exact}{me_mark}\n"
    if not has_scores:
        txt += f"<i>{empty}</i>\n"
    if len(txt) > 4000: txt = txt[:3900] + "\n..."

    kb = []
    if is_owner:
        kb.append([Btn("🗑 حذف لیگ" if lang == "fa" else "🗑 Delete League",
                       callback_data=f"lg_delask_{league_id}")])
    else:
        kb.append([Btn("🚪 خروج از لیگ" if lang == "fa" else "🚪 Leave League",
                       callback_data=f"lg_leaveask_{league_id}")])
    kb.append([Btn("🔄 بروزرسانی" if lang == "fa" else "🔄 Refresh",
                   callback_data=f"lg_view_{league_id}")])
    kb.append([Btn("🔙 لیگ‌های من" if lang == "fa" else "🔙 My Leagues",
                   callback_data="leagues")])
    await query.edit_message_text(txt, parse_mode="HTML", reply_markup=Markup(kb))

# ───────────────── خروج / حذف ─────────────────

async def cb_lg_leave_ask(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    league_id = int(query.data.split("_")[2])
    user = await get_user(query.from_user.id)
    lang = user["lang"] if user else "fa"
    txt = ("⚠️ مطمئنی می‌خوای از این لیگ بری؟ امتیازهات تو رده‌بندی کلی می‌مونه."
           if lang == "fa" else
           "⚠️ Sure you want to leave? Your overall score stays.")
    await query.edit_message_text(txt, reply_markup=Markup([
        [Btn("✅ بله، خروج" if lang == "fa" else "✅ Yes, leave",
             callback_data=f"lg_leave_{league_id}"),
         Btn("↩️ نه" if lang == "fa" else "↩️ No",
             callback_data=f"lg_view_{league_id}")],
    ]))

async def cb_lg_leave(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    league_id = int(query.data.split("_")[2])
    user = await get_user(query.from_user.id)
    lang = user["lang"] if user else "fa"
    lg = await get_league(league_id)
    if lg and lg["owner_id"] == query.from_user.id:
        await query.answer("سازنده نمی‌تونه خروج بزنه — حذف کن!" if lang == "fa"
                           else "Owner can't leave — delete instead!", show_alert=True)
        return
    await leave_league(league_id, query.from_user.id)
    await query.edit_message_text(
        "✅ از لیگ خارج شدی." if lang == "fa" else "✅ Left the league.",
        reply_markup=Markup([[Btn("🏆 لیگ‌های من" if lang == "fa" else "🏆 My Leagues",
                                  callback_data="leagues")]]))

async def cb_lg_delete_ask(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    league_id = int(query.data.split("_")[2])
    user = await get_user(query.from_user.id)
    lang = user["lang"] if user else "fa"
    txt = ("⚠️ <b>حذف لیگ غیرقابل بازگشته!</b>\nهمه اعضا حذف میشن (امتیاز کلی محفوظه)."
           if lang == "fa" else
           "⚠️ <b>Deleting is permanent!</b>\nAll members removed (overall scores stay).")
    await query.edit_message_text(txt, parse_mode="HTML", reply_markup=Markup([
        [Btn("🗑 آره حذف کن" if lang == "fa" else "🗑 Yes delete",
             callback_data=f"lg_del_{league_id}"),
         Btn("↩️ نه" if lang == "fa" else "↩️ No",
             callback_data=f"lg_view_{league_id}")],
    ]))

async def cb_lg_delete(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    league_id = int(query.data.split("_")[2])
    user = await get_user(query.from_user.id)
    lang = user["lang"] if user else "fa"
    ok = await delete_league(league_id, query.from_user.id)
    msg = ("✅ لیگ حذف شد." if lang == "fa" else "✅ League deleted.") if ok else \
          ("⛔ نمی‌تونی این لیگ رو حذف کنی." if lang == "fa" else "⛔ Can't delete this league.")
    await query.edit_message_text(msg, reply_markup=Markup([
        [Btn("🏆 لیگ‌های من" if lang == "fa" else "🏆 My Leagues", callback_data="leagues")]]))

# ───────────────── cancel ─────────────────

async def cmd_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = await get_user(update.effective_user.id)
    lang = user["lang"] if user else "fa"
    await update.message.reply_text("❌ لغو شد." if lang == "fa" else "❌ Cancelled.")
    return ConversationHandler.END
