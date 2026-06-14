from telegram import Update, InlineKeyboardButton as Btn, InlineKeyboardMarkup as Markup
from telegram.ext import ContextTypes, ConversationHandler

from database import (get_all_matches, get_match, set_result, add_match,
                      update_match_teams, get_all_users, get_pool,
                      lock_match, unlock_match)
from config import ADMIN_IDS
from utils import flag, fmt_time, parse_score
from maintenance import is_maintenance, set_maintenance
from wc_data import STAGE_LABEL

ADMIN_RESULT_ID, ADMIN_RESULT_SCORE, ADMIN_RESULT_PENALTY = range(20, 23)
ADMIN_MATCH_T1, ADMIN_MATCH_T2, ADMIN_MATCH_STAGE, ADMIN_MATCH_TIME, ADMIN_MATCH_CITY = range(30, 35)
ADMIN_EDIT_ID, ADMIN_EDIT_T1, ADMIN_EDIT_T2 = range(40, 43)
ADMIN_LOCK_ID, = range(50, 51)

def is_admin(uid): return uid in ADMIN_IDS

async def cmd_admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔")
        return
    await _admin_menu(update.message.reply_text)

async def cb_adminpanel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id): return
    await _admin_menu(query.edit_message_text)

async def _admin_menu(send):
    maint = is_maintenance()
    maint_btn = "🟢 روشن کردن بات" if maint else "🔴 خاموش کردن بات"
    await send(
        "🛠 <b>Admin Panel</b>" + ("\n\n⚠️ بات در حالت Maintenance است!" if maint else ""),
        parse_mode="HTML",
        reply_markup=Markup([
            [Btn("📋 لیست بازی‌ها", callback_data="admin_list")],
            [Btn("✅ ثبت نتیجه دستی", callback_data="admin_result")],
            [Btn("🔒 قفل/باز کردن بازی", callback_data="admin_lock")],
            [Btn("➕ بازی جدید (حذفی)", callback_data="admin_addmatch")],
            [Btn("✏️ ویرایش تیم‌های حذفی", callback_data="admin_editmatch")],
            [Btn("📢 پیام همگانی", callback_data="admin_broadcast")],
            [Btn(maint_btn, callback_data="admin_toggle_maint")],
        ]))

async def cb_toggle_maintenance(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id): return
    new_state = not is_maintenance()
    set_maintenance(new_state)
    await query.answer("🔴 Maintenance ON" if new_state else "🟢 بات روشن شد!", show_alert=True)
    await _admin_menu(query.edit_message_text)

async def cb_admin_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id): return
    matches = await get_all_matches()
    if not matches:
        await query.edit_message_text("هنوز بازی‌ای نیست!")
        return
    stages_seen = {}
    for m in matches:
        stages_seen.setdefault(m["stage"],[]).append(m)
    txt = "📋 <b>همه بازی‌ها:</b>\n\n"
    for stage, ms in stages_seen.items():
        lbl = STAGE_LABEL.get(stage,{}).get("fa", stage)
        txt += f"<b>── {lbl} ──</b>\n"
        for m in ms:
            status = f"✅ {m['result1']}-{m['result2']}" if m["is_finished"] else ("🔒" if m["is_locked"] else "🟢")
            api = f" [api:{m['api_id']}]" if m["api_id"] else ""
            grp = f"[{m['grp']}] " if m["grp"] else ""
            txt += f"<code>#{m['id']}</code>{api} {grp}{flag(m['team1'])}{m['team1']} vs {m['team2']}{flag(m['team2'])} {status}\n"
        txt += "\n"
    if len(txt) > 4000: txt = txt[:3900] + "\n..."
    await query.edit_message_text(txt, parse_mode="HTML", reply_markup=Markup([
        [Btn("🔙 برگشت", callback_data="adminpanel")]]))

# ── ثبت نتیجه دستی (اضطراری) ─────────────────

async def cb_admin_result_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id): return ConversationHandler.END
    # حالا هم بازی‌های تموم‌نشده، هم تموم‌شده (برای اصلاح) قابل انتخاب‌اند
    matches = await get_all_matches()
    if not matches:
        await query.edit_message_text("هنوز بازی‌ای نیست!")
        return ConversationHandler.END
    txt = "شماره بازی (✏️ اصلاح هم ممکنه):\n\n"
    for m in matches[:40]:
        grp = f"[{m['grp']}] " if m["grp"] else ""
        if m["is_finished"]:
            status = f"✅ {m['result1']}-{m['result2']}"
        elif m["is_locked"]:
            status = "🔒"
        else:
            status = "🟢"
        txt += f"<code>#{m['id']}</code> {grp}{m['team1']} vs {m['team2']} {status}\n"
    await query.edit_message_text(txt + "\n/cancel لغو", parse_mode="HTML")
    return ADMIN_RESULT_ID

async def admin_result_id(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try: mid = int(update.message.text.strip().lstrip("#"))
    except ValueError:
        await update.message.reply_text("عدد بنویس:")
        return ADMIN_RESULT_ID
    m = await get_match(mid)
    if not m:
        await update.message.reply_text(f"#{mid} پیدا نشد!")
        return ADMIN_RESULT_ID
    ctx.user_data["result_mid"] = mid
    ctx.user_data["result_stage"] = m["stage"]
    await update.message.reply_text(
        f"<b>{flag(m['team1'])}{m['team1']} vs {m['team2']}{flag(m['team2'])}</b>\n\n"
        f"نتیجه ۹۰ دقیقه (مثلاً <code>2-1</code>):",
        parse_mode="HTML")
    return ADMIN_RESULT_SCORE

async def admin_result_score(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    score = parse_score(update.message.text)
    if not score:
        await update.message.reply_text("فرمت اشتباه! مثلاً: <code>2-1</code>", parse_mode="HTML")
        return ADMIN_RESULT_SCORE
    ctx.user_data["result_score"] = score
    stage = ctx.user_data.get("result_stage","group")
    r1, r2 = score
    # اگه حذفیه و مساوی، پنالتی بخواه
    if stage != "group" and r1 == r2:
        await update.message.reply_text(
            "مساوی شد! نتیجه پنالتی:\nمثلاً <code>4-2</code> (تیم اول - تیم دوم)\n"
            "اگه پنالتی نبود <code>-</code> بزن:", parse_mode="HTML")
        return ADMIN_RESULT_PENALTY
    # گروهی یا حذفی با برنده
    return await _finalize_result(update, ctx, None, None)

async def admin_result_penalty(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip()
    if txt == "-":
        return await _finalize_result(update, ctx, None, None)
    pen = parse_score(txt)
    if not pen:
        await update.message.reply_text("فرمت اشتباه! مثلاً: <code>4-2</code>", parse_mode="HTML")
        return ADMIN_RESULT_PENALTY
    return await _finalize_result(update, ctx, pen[0], pen[1])

async def _finalize_result(update, ctx, p1, p2):
    mid = ctx.user_data["result_mid"]
    r1, r2 = ctx.user_data["result_score"]
    m = await get_match(mid)
    was_finished = bool(m and m["is_finished"])
    count, winner, changed = await set_result(mid, r1, r2, p1, p2, force=True)

    action = "اصلاح شد" if was_finished else "ثبت شد"
    txt = (f"✅ <b>{action}!</b>\n\n"
           f"{flag(m['team1'])}{m['team1']}  <b>{r1}–{r2}</b>  {m['team2']}{flag(m['team2'])}\n")
    if p1 is not None:
        txt += f"ضربات پنالتی: {p1}-{p2}\n"
    if winner:
        txt += f"🏆 صعود کننده: {flag(winner)}{winner}\n"
    if was_finished:
        txt += f"\n🔧 <b>{len(changed)}</b> امتیاز تغییر کرد و به کاربرها اطلاع داده شد."
    else:
        txt += f"\n🎯 امتیاز <b>{count}</b> پیش‌بینی محاسبه شد!"

    await update.message.reply_text(txt, parse_mode="HTML", reply_markup=Markup([
        [Btn("✅ نتیجه دیگه", callback_data="admin_result"),
         Btn("🛠 پنل", callback_data="adminpanel")]]))

    # نوتیف به کاربرها
    m_fresh = await get_match(mid)
    try:
        if was_finished:
            # فقط به کسایی که امتیازشون عوض شد
            if changed:
                from notifier import announce_result_correction
                await announce_result_correction(
                    update.get_bot(), m_fresh, r1, r2, p1, p2, changed)
        else:
            # ثبت اولیه دستی → اعلام عمومی مثل حالت API
            from notifier import _announce_result
            from database import mark_result_sent
            await mark_result_sent(mid)
            await _announce_result(update.get_bot(), m_fresh, r1, r2, p1, p2, count, winner)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Manual result announce failed: {e}")

    return ConversationHandler.END

# ── بازی جدید حذفی ────────────────────────────

async def cb_admin_addmatch_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id): return ConversationHandler.END
    await query.edit_message_text(
        "نام تیم اول (انگلیسی):\nمثال: <code>France</code>\n\n/cancel لغو", parse_mode="HTML")
    return ADMIN_MATCH_T1

async def admin_match_t1(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["m_t1"] = update.message.text.strip()
    await update.message.reply_text("نام تیم دوم:")
    return ADMIN_MATCH_T2

async def admin_match_t2(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["m_t2"] = update.message.text.strip()
    await update.message.reply_text(
        "مرحله:\n<code>r32</code> | <code>r16</code> | <code>qf</code> | "
        "<code>sf</code> | <code>third</code> | <code>final</code>", parse_mode="HTML")
    return ADMIN_MATCH_STAGE

async def admin_match_stage(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    stage = update.message.text.strip().lower()
    if stage not in ["r32","r16","qf","sf","final","third"]:
        await update.message.reply_text("باید یکی از: r32 / r16 / qf / sf / third / final")
        return ADMIN_MATCH_STAGE
    ctx.user_data["m_stage"] = stage
    await update.message.reply_text("زمان (UTC):\n<code>2026-07-01 20:00</code>", parse_mode="HTML")
    return ADMIN_MATCH_TIME

async def admin_match_time(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    from datetime import datetime
    try: datetime.strptime(update.message.text.strip(), "%Y-%m-%d %H:%M")
    except ValueError:
        await update.message.reply_text("فرمت: <code>2026-07-01 20:00</code>", parse_mode="HTML")
        return ADMIN_MATCH_TIME
    ctx.user_data["m_time"] = update.message.text.strip()
    await update.message.reply_text("شهر (یا - برای خالی):")
    return ADMIN_MATCH_CITY

async def admin_match_city(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    city = update.message.text.strip()
    if city == "-": city = ""
    t1, t2 = ctx.user_data["m_t1"], ctx.user_data["m_t2"]
    stage, mtime = ctx.user_data["m_stage"], ctx.user_data["m_time"]
    mid = await add_match(stage, t1, t2, mtime, city)
    lbl = STAGE_LABEL.get(stage,{}).get("fa", stage)
    await update.message.reply_text(
        f"✅ بازی اضافه شد!\n\n<code>#{mid}</code> {flag(t1)}{t1} vs {t2}{flag(t2)}\n{mtime} UTC | {lbl}",
        parse_mode="HTML",
        reply_markup=Markup([[Btn("➕ بازی دیگه", callback_data="admin_addmatch"),
                              Btn("🛠 پنل", callback_data="adminpanel")]]))
    return ConversationHandler.END

# ── ویرایش تیم‌های حذفی ───────────────────────

async def cb_admin_editmatch_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id): return ConversationHandler.END
    stages = ["r32","r16","qf","sf","third","final"]
    matches = []
    for s in stages:
        matches.extend(await get_all_matches(s))
    if not matches:
        await query.edit_message_text("هنوز بازی حذفی اضافه نشده!", reply_markup=Markup([
            [Btn("🔙 برگشت", callback_data="adminpanel")]]))
        return ConversationHandler.END
    txt = "شماره بازی‌ای که می‌خوای تیم‌هاش رو ویرایش کنی:\n\n"
    for m in matches:
        lbl = STAGE_LABEL.get(m["stage"],{}).get("fa","")
        txt += f"<code>#{m['id']}</code> {lbl}: {m['team1']} vs {m['team2']}\n"
    await query.edit_message_text(txt + "\n/cancel لغو", parse_mode="HTML")
    return ADMIN_EDIT_ID

async def admin_edit_id(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try: mid = int(update.message.text.strip().lstrip("#"))
    except ValueError:
        await update.message.reply_text("عدد بنویس:")
        return ADMIN_EDIT_ID
    m = await get_match(mid)
    if not m or m["stage"] == "group":
        await update.message.reply_text("بازی پیدا نشد یا گروهیه!")
        return ADMIN_EDIT_ID
    ctx.user_data["edit_mid"] = mid
    await update.message.reply_text(
        f"فعلی: <b>{m['team1']} vs {m['team2']}</b>\n\nتیم اول جدید:", parse_mode="HTML")
    return ADMIN_EDIT_T1

async def admin_edit_t1(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["edit_t1"] = update.message.text.strip()
    await update.message.reply_text("تیم دوم جدید:")
    return ADMIN_EDIT_T2

async def admin_edit_t2(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    t1 = ctx.user_data["edit_t1"]
    t2 = update.message.text.strip()
    mid = ctx.user_data["edit_mid"]
    # هشدار: پیش‌بینی‌های قبلی پاک میشن چون تیم‌ها عوض شدن
    await update_match_teams(mid, t1, t2)
    m = await get_match(mid)
    lbl = STAGE_LABEL.get(m["stage"],{}).get("fa","")
    await update.message.reply_text(
        f"✅ ویرایش شد!\n{lbl}: <b>{flag(t1)}{t1} vs {t2}{flag(t2)}</b>\n\n"
        f"⚠️ پیش‌بینی‌های قبلی این بازی پاک شدن (چون تیم‌ها عوض شدن).\n"
        f"کاربرها می‌تونن دوباره پیش‌بینی کنن.",
        parse_mode="HTML",
        reply_markup=Markup([[Btn("✏️ ویرایش دیگه", callback_data="admin_editmatch"),
                              Btn("🛠 پنل", callback_data="adminpanel")]]))
    return ConversationHandler.END

# ── پیام همگانی ───────────────────────────────

async def cb_admin_broadcast(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id): return
    await query.edit_message_text(
        "برای پیام همگانی:\n\n<code>/sendall متن پیام</code>", parse_mode="HTML")

async def cmd_sendall(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    if not ctx.args:
        await update.message.reply_text("متن: /sendall پیام")
        return
    msg = " ".join(ctx.args)
    users = await get_all_users()
    ok = fail = 0
    for u in users:
        try:
            await ctx.bot.send_message(u["user_id"], f"📢 {msg}")
            ok += 1
        except Exception:
            fail += 1
    await update.message.reply_text(f"✅ ارسال شد: {ok} نفر\n❌ ناموفق: {fail} نفر")

# ── تست ──────────────────────────────────────

async def cmd_testfull(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔")
        return
    import random
    await update.message.reply_text("🧪 شروع تست...")
    pool = await get_pool()
    fake_users = [(100000001,"علی رضایی"),(100000002,"مریم احمدی"),
                  (100000003,"رضا کریمی"),(100000004,"سارا محمدی"),(100000005,"امیر حسینی")]
    async with pool.acquire() as conn:
        for uid, name in fake_users:
            await conn.execute("""
                INSERT INTO users(user_id,display_name,lang) VALUES($1,$2,'fa')
                ON CONFLICT(user_id) DO NOTHING
            """, uid, name)
    matches = await get_all_matches("group")
    async with pool.acquire() as conn:
        for m in matches:
            for uid, _ in fake_users:
                p1, p2 = random.randint(0,4), random.randint(0,4)
                await conn.execute("""
                    INSERT INTO predictions(user_id,match_id,pred1,pred2)
                    VALUES($1,$2,$3,$4)
                    ON CONFLICT(user_id,match_id) DO UPDATE SET pred1=$3,pred2=$4,points=NULL
                """, uid, m["id"], p1, p2)
    scored = 0
    for m in matches:
        if not m["is_finished"]:
            r1, r2 = random.randint(0,4), random.randint(0,4)
            await set_result(m["id"], r1, r2)
            scored += 1
    await update.message.reply_text(f"✅ {scored} بازی نتیجه گرفت\n🏆 جدول رو چک کن!")

async def cmd_cleartestdata(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔")
        return
    pool = await get_pool()
    fake_ids = [100000001,100000002,100000003,100000004,100000005]
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM predictions WHERE user_id=ANY($1::bigint[])", fake_ids)
        await conn.execute("DELETE FROM users WHERE user_id=ANY($1::bigint[])", fake_ids)
        await conn.execute("""
            UPDATE matches SET result1=NULL,result2=NULL,penalty1=NULL,penalty2=NULL,
            winner_team=NULL,is_locked=FALSE,is_finished=FALSE,
            notif_sent=FALSE,result_sent=FALSE WHERE stage='group'
        """)
    await update.message.reply_text("🧹 داده‌های تست پاک شد!")

async def cmd_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ لغو شد. برای شروع /start بزن.")
    return ConversationHandler.END


# ── قفل / باز کردن دستی بازی ─────────────────

async def cb_admin_lock_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return ConversationHandler.END
    matches = await get_all_matches()
    open_matches = [m for m in matches if not m["is_finished"]]
    if not open_matches:
        await query.edit_message_text("بازی بازی برای قفل/باز کردن نیست!", reply_markup=Markup([
            [Btn("🔙 برگشت", callback_data="adminpanel")]]))
        return ConversationHandler.END
    txt = "شماره بازی برای قفل/باز کردن:\n(🔒 = قفل، 🟢 = باز)\n\n"
    for m in open_matches[:50]:
        grp = f"[{m['grp']}] " if m["grp"] else ""
        status = "🔒" if m["is_locked"] else "🟢"
        txt += f"<code>#{m['id']}</code> {grp}{m['team1']} vs {m['team2']} {status}\n"
    await query.edit_message_text(txt + "\n/cancel لغو", parse_mode="HTML")
    return ADMIN_LOCK_ID

async def admin_lock_id(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        mid = int(update.message.text.strip().lstrip("#"))
    except ValueError:
        await update.message.reply_text("عدد بنویس:")
        return ADMIN_LOCK_ID
    m = await get_match(mid)
    if not m:
        await update.message.reply_text(f"#{mid} پیدا نشد!")
        return ADMIN_LOCK_ID
    if m["is_finished"]:
        await update.message.reply_text("این بازی تموم شده — نمی‌شه قفل/باز کرد.")
        return ConversationHandler.END
    if m["is_locked"]:
        ok = await unlock_match(mid)
        msg = "🟢 باز شد — کاربرها دوباره می‌تونن پیش‌بینی کنن." if ok else "خطا!"
    else:
        ok = await lock_match(mid)
        msg = "🔒 قفل شد — پیش‌بینی جدید ممکن نیست." if ok else "خطا!"
    await update.message.reply_text(
        f"<b>{flag(m['team1'])}{m['team1']} vs {m['team2']}{flag(m['team2'])}</b>\n{msg}",
        parse_mode="HTML",
        reply_markup=Markup([[Btn("🔒 بازی دیگه", callback_data="admin_lock"),
                              Btn("🛠 پنل", callback_data="adminpanel")]]))
    return ConversationHandler.END
