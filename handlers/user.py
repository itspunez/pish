from telegram import Update, InlineKeyboardButton as Btn, InlineKeyboardMarkup as Markup
from telegram.ext import ContextTypes, ConversationHandler

from database import (
    upsert_user, get_user, get_group_matches,
    get_all_matches, get_match, get_prediction,
    save_prediction, get_user_stats, leaderboard, get_user_rank
)
from wc_data import STAGE_LABEL, KNOCKOUT_ORDER
from utils import flag, tname, fmt_time, fmt_pred, make_display_name, parse_score
from maintenance import is_maintenance

PREDICT_INPUT = 10

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if is_maintenance():
        await update.message.reply_text("🔧 بات موقتاً در حال تعمیر است. به زودی برمی‌گردیم!")
        return
    u = update.effective_user
    existing = await get_user(u.id)
    lang = existing["lang"] if existing else None
    if not lang:
        await update.message.reply_text(
            "🌐 Choose your language / زبان خود را انتخاب کنید:",
            reply_markup=Markup([[
                Btn("🇮🇷 فارسی", callback_data="lang_fa"),
                Btn("🇬🇧 English", callback_data="lang_en"),
            ]]))
        return
    await upsert_user(u.id, make_display_name(u), lang)
    await _send_main(update.message.reply_text, u, lang)

async def cb_lang(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = query.data.split("_")[1]
    u = query.from_user
    await upsert_user(u.id, make_display_name(u), lang)
    await query.edit_message_text("✅ زبان ذخیره شد!" if lang=="fa" else "✅ Language saved!")
    await _send_main(query.message.reply_text, u, lang)

async def _send_main(send_fn, u, lang):
    name = u.first_name or "کاربر"
    if lang == "fa":
        text = (f"سلام {name}! 👋\n\n🏆 <b>بات پیش‌بینی جام جهانی ۲۰۲۶</b>\n\n"
                "🎯 نتیجه دقیق → <b>۱۰ امتیاز</b>\n"
                "📐 تفاضل گل درست → <b>۷ امتیاز</b>\n"
                "✔️ فقط برنده درست → <b>۵ امتیاز</b>\n"
                "❌ اشتباه (ولی شرکت کردی) → <b>۲ امتیاز</b>\n"
                "⭕ پیش‌بینی نکردی → <b>۰ امتیاز</b>")
    else:
        text = (f"Hello {name}! 👋\n\n🏆 <b>FIFA World Cup 2026 Prediction Bot</b>\n\n"
                "🎯 Exact score → <b>10 pts</b>\n"
                "📐 Correct goal diff → <b>7 pts</b>\n"
                "✔️ Correct winner only → <b>5 pts</b>\n"
                "❌ Wrong (participated) → <b>2 pts</b>\n"
                "⭕ No prediction → <b>0 pts</b>")
    kb = [
        [Btn("⚽ پیش‌بینی بازی‌ها" if lang=="fa" else "⚽ Predict Matches",
             callback_data="show_stages")],
        [Btn("📊 امتیاز من" if lang=="fa" else "📊 My Stats", callback_data="mystats"),
         Btn("🏆 جدول کل" if lang=="fa" else "🏆 Leaderboard", callback_data="leaderboard")],
        [Btn("🤝 لیگ‌های من" if lang=="fa" else "🤝 My Leagues", callback_data="leagues")],
        [Btn("🌐 تغییر زبان" if lang=="fa" else "🌐 Change Language", callback_data="changelang")],
    ]
    await send_fn(text, parse_mode="HTML", reply_markup=Markup(kb))

async def cb_show_stages(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = await get_user(query.from_user.id)
    if not user:
        await query.answer("اول /start بزن!", show_alert=True)
        return
    lang = user["lang"]
    kb = []

    all_group = await get_group_matches()
    open_group = [m for m in all_group if not m["is_locked"]]
    lbl = STAGE_LABEL["group"][lang]
    if open_group:
        kb.append([Btn(f"⚽ {lbl}  ({len(open_group)} باز)" if lang=="fa"
                       else f"⚽ {lbl}  ({len(open_group)} open)",
                       callback_data="stage_group")])
    elif all_group:
        kb.append([Btn(f"🔒 {lbl}", callback_data="locked_info")])

    kb.append([Btn("─────────────", callback_data="noop")])

    for stage in KNOCKOUT_ORDER:
        all_s = await get_all_matches(stage)
        open_s = [m for m in all_s if not m["is_locked"] and not m["is_finished"]]
        lbl = STAGE_LABEL[stage][lang]
        if open_s:
            kb.append([Btn(f"⚽ {lbl}  ({len(open_s)})", callback_data=f"stage_{stage}")])
        elif all_s:
            kb.append([Btn(f"🔒 {lbl}", callback_data="locked_info")])

    kb.append([Btn("🔙 برگشت" if lang=="fa" else "🔙 Back", callback_data="main")])
    await query.edit_message_text(
        "⚽ انتخاب مرحله:" if lang=="fa" else "⚽ Select stage:",
        reply_markup=Markup(kb))

async def cb_stage(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    stage = query.data.split("_",1)[1]
    user = await get_user(query.from_user.id)
    lang = user["lang"] if user else "fa"

    if stage == "group":
        await _show_round_selector(query, lang)
    else:
        matches = [m for m in await get_all_matches(stage)
                   if not m["is_locked"] and not m["is_finished"]]
        if not matches:
            await query.edit_message_text(
                "بازی‌ای موجود نیست." if lang=="fa" else "No matches available.",
                reply_markup=Markup([[Btn("🔙", callback_data="show_stages")]]))
            return
        lbl = STAGE_LABEL.get(stage,{}).get(lang, stage)
        await _show_knockout_list(query, lang, matches, lbl)

async def _show_round_selector(query, lang):
    all_group = await get_group_matches()
    rounds = {}
    for m in all_group:
        r = m["round_no"] or 1
        rounds.setdefault(r, {"open":0})
        if not m["is_locked"]:
            rounds[r]["open"] += 1

    round_names = {1:("دور اول","Round 1"), 2:("دور دوم","Round 2"), 3:("دور سوم","Round 3")}
    kb = []
    for r in sorted(rounds.keys()):
        open_c = rounds[r]["open"]
        lbl = round_names.get(r, (f"دور {r}", f"Round {r}"))[0 if lang=="fa" else 1]
        if open_c > 0:
            suffix = f" ({open_c} باز)" if lang=="fa" else f" ({open_c} open)"
            kb.append([Btn(f"⚽ {lbl}{suffix}", callback_data=f"round_{r}")])
        else:
            kb.append([Btn(f"🔒 {lbl}", callback_data="locked_info")])

    kb.append([Btn("🔙 برگشت" if lang=="fa" else "🔙 Back", callback_data="show_stages")])
    title = "⚽ <b>مرحله گروهی — انتخاب دور:</b>" if lang=="fa" \
            else "⚽ <b>Group Stage — Select Round:</b>"
    await query.edit_message_text(title, parse_mode="HTML", reply_markup=Markup(kb))

async def cb_round(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    round_no = int(query.data.split("_")[1])
    user = await get_user(query.from_user.id)
    lang = user["lang"] if user else "fa"
    ctx.user_data["current_round"] = round_no

    matches = await get_group_matches(round_no=round_no)
    groups = {}
    for m in matches:
        g = m["grp"] or "?"
        groups.setdefault(g, {"open":0})
        if not m["is_locked"]:
            groups[g]["open"] += 1

    round_names = {1:("دور اول","Round 1"), 2:("دور دوم","Round 2"), 3:("دور سوم","Round 3")}
    rname = round_names.get(round_no, (f"دور {round_no}", f"Round {round_no}"))[0 if lang=="fa" else 1]
    title = f"⚽ <b>{rname} — {'انتخاب گروه' if lang=='fa' else 'Select Group'}:</b>"

    kb = []
    row = []
    for g in sorted(groups.keys()):
        open_c = groups[g]["open"]
        lbl = (f"گروه {g} ({open_c})" if open_c > 0 else f"🔒 {g}") if lang=="fa" \
              else (f"Group {g} ({open_c})" if open_c > 0 else f"🔒 {g}")
        row.append(Btn(lbl, callback_data=f"grp_{round_no}_{g}"))
        if len(row) == 3:
            kb.append(row)
            row = []
    if row: kb.append(row)
    kb.append([Btn("🔙 برگشت" if lang=="fa" else "🔙 Back", callback_data="stage_group")])
    await query.edit_message_text(title, parse_mode="HTML", reply_markup=Markup(kb))

async def cb_group(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_")
    round_no = int(parts[1])
    grp = parts[2]
    user = await get_user(query.from_user.id)
    lang = user["lang"] if user else "fa"

    matches = await get_group_matches(round_no=round_no, grp=grp)
    round_names = {1:("دور اول","Round 1"), 2:("دور دوم","Round 2"), 3:("دور سوم","Round 3")}
    rname = round_names.get(round_no,(f"دور {round_no}",f"Round {round_no}"))[0 if lang=="fa" else 1]
    grp_lbl = f"گروه {grp}" if lang=="fa" else f"Group {grp}"
    txt = f"<b>⚽ {rname} — {grp_lbl}</b>\n\n"
    kb = []

    for m in matches:
        f1, f2 = flag(m["team1"]), flag(m["team2"])
        t1, t2 = tname(m["team1"],lang), tname(m["team2"],lang)
        time_str = fmt_time(m["match_time"], lang)
        if m["is_finished"]:
            txt += f"✅ {f1} {t1}  {m['result1']}-{m['result2']}  {t2} {f2}\n\n"
        elif m["is_locked"]:
            txt += f"🔒 {f1} {t1} vs {t2} {f2}\n🗓 {time_str}\n\n"
        else:
            txt += f"🟢 {f1} {t1} vs {t2} {f2}\n🗓 {time_str}\n\n"
            kb.append([Btn(f"{f1} {m['team1']} vs {m['team2']} {f2}",
                           callback_data=f"predict_{m['id']}")])

    kb.append([Btn("🔙 برگشت" if lang=="fa" else "🔙 Back", callback_data=f"round_{round_no}")])
    await query.edit_message_text(txt, parse_mode="HTML", reply_markup=Markup(kb))

async def _show_knockout_list(query, lang, matches, lbl):
    txt = f"<b>⚽ {lbl}</b>\n\n"
    kb = []
    for m in matches:
        f1, f2 = flag(m["team1"]), flag(m["team2"])
        t1, t2 = tname(m["team1"],lang), tname(m["team2"],lang)
        txt += f"{f1} {t1} vs {t2} {f2}\n🗓 {fmt_time(m['match_time'],lang)}\n\n"
        kb.append([Btn(f"{f1} {m['team1']} vs {m['team2']} {f2}",
                       callback_data=f"predict_{m['id']}")])
    kb.append([Btn("🔙 برگشت" if lang=="fa" else "🔙 Back", callback_data="show_stages")])
    await query.edit_message_text(txt, parse_mode="HTML", reply_markup=Markup(kb))

async def cb_predict_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    match_id = int(query.data.split("_")[1])
    m = await get_match(match_id)
    user = await get_user(query.from_user.id)
    lang = user["lang"] if user else "fa"

    if not m or m["is_locked"]:
        await query.answer("⛔ این بازی قفل شده!" if lang=="fa" else "⛔ Match is locked!", show_alert=True)
        return ConversationHandler.END

    ctx.user_data.update({"match_id":match_id,"lang":lang,
                          "stage":m["stage"],"grp":m["grp"],"round_no":m["round_no"]})

    f1, f2 = flag(m["team1"]), flag(m["team2"])
    t1, t2 = tname(m["team1"],lang), tname(m["team2"],lang)
    grp_txt = (f" | گروه {m['grp']}" if m["grp"] and lang=="fa"
               else f" | Group {m['grp']}" if m["grp"] else "")

    pred = await get_prediction(query.from_user.id, match_id)
    existing = ""
    if pred:
        existing = (f"✏️ پیش‌بینی فعلی:\n{fmt_pred(m['team1'],m['team2'],pred['pred1'],pred['pred2'],lang)}\n\n"
                    if lang=="fa" else
                    f"✏️ Current pick:\n{fmt_pred(m['team1'],m['team2'],pred['pred1'],pred['pred2'],lang)}\n\n")

    if lang == "fa":
        txt = (f"⚽ <b>{f1} {t1}  vs  {t2} {f2}</b>{grp_txt}\n"
               f"🗓 {fmt_time(m['match_time'],lang)}\n📍 {m['city']}\n\n"
               f"{existing}نتیجه رو بنویس:\n"
               f"فرمت: <code>گل تیم اول - گل تیم دوم</code>\n"
               f"مثال: <code>2-1</code>\n\n/cancel برای لغو")
    else:
        txt = (f"⚽ <b>{f1} {t1}  vs  {t2} {f2}</b>{grp_txt}\n"
               f"🗓 {fmt_time(m['match_time'],lang)}\n📍 {m['city']}\n\n"
               f"{existing}Enter score:\n"
               f"Format: <code>team1 - team2</code>\nExample: <code>2-1</code>\n\n/cancel to cancel")

    await query.edit_message_text(txt, parse_mode="HTML")
    return PREDICT_INPUT

async def handle_prediction_input(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    lang     = ctx.user_data.get("lang","fa")
    match_id = ctx.user_data.get("match_id")
    grp      = ctx.user_data.get("grp")
    round_no = ctx.user_data.get("round_no")

    score = parse_score(update.message.text)
    if not score:
        await update.message.reply_text(
            "❌ فرمت اشتباه! مثلاً: <code>2-1</code>" if lang=="fa"
            else "❌ Wrong format! e.g. <code>2-1</code>", parse_mode="HTML")
        return PREDICT_INPUT

    p1, p2 = score
    ok = await save_prediction(update.effective_user.id, match_id, p1, p2)
    if not ok:
        await update.message.reply_text("⛔ بازی همین الان قفل شد!" if lang=="fa" else "⛔ Match just locked!")
        return ConversationHandler.END

    m = await get_match(match_id)
    score_txt = fmt_pred(m["team1"], m["team2"], p1, p2, lang)
    next_m = await _get_next_unpredicted(update.effective_user.id, grp, round_no, match_id)
    next_grp = await _get_next_group(grp, round_no)

    txt = (f"✅ <b>ثبت شد!</b>\n\n{score_txt}\n\nتا شروع بازی می‌تونی عوض کنی 🔄"
           if lang=="fa" else
           f"✅ <b>Saved!</b>\n\n{score_txt}\n\nYou can change it until kickoff 🔄")

    kb = [[Btn("✏️ ویرایش" if lang=="fa" else "✏️ Edit", callback_data=f"predict_{match_id}")]]

    if next_m:
        nf1, nf2 = flag(next_m["team1"]), flag(next_m["team2"])
        kb.append([Btn(f"⏭ بعدی: {nf1} {next_m['team1']} vs {next_m['team2']} {nf2}",
                       callback_data=f"predict_{next_m['id']}")])

    if next_grp and not next_m:
        kb.append([Btn(f"➡️ گروه {next_grp}" if lang=="fa" else f"➡️ Group {next_grp}",
                       callback_data=f"grp_{round_no}_{next_grp}")])

    if grp and round_no:
        kb.append([Btn(f"📋 گروه {grp}" if lang=="fa" else f"📋 Group {grp}",
                       callback_data=f"grp_{round_no}_{grp}")])
    kb.append([Btn("⚽ مراحل" if lang=="fa" else "⚽ Stages", callback_data="show_stages")])
    kb.append([Btn("🏠 منو" if lang=="fa" else "🏠 Menu", callback_data="main")])

    await update.message.reply_text(txt, parse_mode="HTML", reply_markup=Markup(kb))
    return ConversationHandler.END

async def _get_next_unpredicted(user_id, grp, round_no, current_match_id):
    if not grp or not round_no: return None
    matches = await get_group_matches(round_no=round_no, grp=grp)
    for m in matches:
        if m["id"] == current_match_id or m["is_locked"]: continue
        pred = await get_prediction(user_id, m["id"])
        if not pred: return m
    return None

async def _get_next_group(current_grp, round_no):
    """گروه بعدی به ترتیب الفبا"""
    if not current_grp or not round_no: return None
    all_groups = sorted(set(m["grp"] for m in await get_group_matches(round_no=round_no)
                            if m["grp"] and not m["is_locked"]))
    if current_grp in all_groups:
        idx = all_groups.index(current_grp)
        if idx + 1 < len(all_groups):
            return all_groups[idx + 1]
    return None

async def cmd_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = await get_user(update.effective_user.id)
    lang = user["lang"] if user else "fa"
    msg = "❌ لغو شد." if lang == "fa" else "❌ Cancelled."
    await update.message.reply_text(msg)
    # بعد از لغو، منوی اصلی رو نشون بده
    if user:
        await _send_main(update.message.reply_text, update.effective_user, lang)
    return ConversationHandler.END

async def cb_mystats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = await get_user(query.from_user.id)
    if not user:
        await query.answer("اول /start بزن!", show_alert=True)
        return
    lang = user["lang"]
    stats = await get_user_stats(query.from_user.id)
    rank  = await get_user_rank(query.from_user.id)

    if lang == "fa":
        txt = (f"📊 <b>آمار {user['display_name']}</b>\n\n"
               f"⭐ کل امتیاز: <b>{stats['total']}</b>\n🏅 رتبه: <b>{rank}</b>\n\n"
               f"🎯 کل پیش‌بینی‌ها: {stats['total_preds']}\n"
               f"✅ بازی‌های تموم‌شده: {stats['finished']}\n\n"
               f"🏆 نتیجه دقیق (۱۰): {stats['exact_c']}\n"
               f"📐 تفاضل درست (۷): {stats['diff_c']}\n"
               f"✔️ برنده درست (۵): {stats['winner_c']}\n"
               f"❌ اشتباه (۲): {stats['wrong_c']}\n\n<b>آخرین ۵ پیش‌بینی:</b>")
    else:
        txt = (f"📊 <b>Stats: {user['display_name']}</b>\n\n"
               f"⭐ Total: <b>{stats['total']}</b>\n🏅 Rank: <b>{rank}</b>\n\n"
               f"🎯 Predictions: {stats['total_preds']}\n"
               f"✅ Finished: {stats['finished']}\n\n"
               f"🏆 Exact (10): {stats['exact_c']}\n"
               f"📐 Diff (7): {stats['diff_c']}\n"
               f"✔️ Winner (5): {stats['winner_c']}\n"
               f"❌ Wrong (2): {stats['wrong_c']}\n\n<b>Last 5 predictions:</b>")

    for p in stats["last5"]:
        f1, f2 = flag(p["team1"]), flag(p["team2"])
        pred_txt = f"{p['pred1']}-{p['pred2']}"
        if p["is_finished"]:
            txt += f"\n{f1} vs {f2}: <b>{pred_txt}</b> ({p['result1']}-{p['result2']}) → +{p['points']}pt"
        else:
            txt += f"\n{f1} vs {f2}: <b>{pred_txt}</b> ⏳"

    await query.edit_message_text(txt, parse_mode="HTML", reply_markup=Markup([
        [Btn("🔙 برگشت" if lang=="fa" else "🔙 Back", callback_data="main")]]))

async def cb_leaderboard(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = await get_user(query.from_user.id)
    lang = user["lang"] if user else "fa"
    rows = await leaderboard(50)

    medals = ["🥇","🥈","🥉"]
    title = "🏆 جدول امتیازات" if lang=="fa" else "🏆 Leaderboard"
    txt = f"<b>{title}</b>\n\n"
    for i, r in enumerate(rows):
        medal = medals[i] if i < 3 else f"{i+1}."
        exact = f" 🎯{r['exact_c']}" if r["exact_c"] else ""
        pts_lbl = "امتیاز" if lang=="fa" else "pts"
        txt += f"{medal} <b>{r['display_name']}</b> — {r['total']} {pts_lbl}{exact}\n"
    if not rows:
        txt += "هنوز کسی امتیاز نگرفته!" if lang=="fa" else "No scores yet!"
    if len(txt) > 4000: txt = txt[:3900] + "\n..."

    await query.edit_message_text(txt, parse_mode="HTML", reply_markup=Markup([
        [Btn("🔙 برگشت" if lang=="fa" else "🔙 Back", callback_data="main")]]))

async def cb_main(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = await get_user(query.from_user.id)
    lang = user["lang"] if user else "fa"
    await _send_main(query.edit_message_text, query.from_user, lang)

async def cb_changelang(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🌐 Choose language / انتخاب زبان:", reply_markup=Markup([[
        Btn("🇮🇷 فارسی", callback_data="lang_fa"),
        Btn("🇬🇧 English", callback_data="lang_en"),
    ]]))

async def cb_locked_info(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = await get_user(query.from_user.id)
    lang = user["lang"] if user else "fa"
    await query.answer(
        "🔒 همه بازی‌های این مرحله شروع شدن یا تموم شدن." if lang=="fa"
        else "🔒 All matches started or finished.", show_alert=True)

async def cb_noop(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
