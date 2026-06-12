"""notifier.py — یادآوری، اعلام نتایج، اعلام اصلاح نتیجه"""
import asyncio
import logging

from telegram import Bot, InlineKeyboardButton as Btn, InlineKeyboardMarkup as Markup

from database import (
    get_matches_to_notify, get_matches_to_check_result,
    get_match, get_prediction, get_all_users, get_user,
    set_result, mark_notif_sent, mark_result_sent,
    count_exact_predictions, get_pool
)
from api_client import get_match_result
from utils import flag, tname, fmt_time
from wc_data import KNOCKOUT_STAGES, STAGE_LABEL

log = logging.getLogger(__name__)

# ── یادآوری ─────────────────────────────────

async def send_reminders(bot: Bot):
    matches = await get_matches_to_notify()
    for m in matches:
        await _send_reminder_for_match(bot, m)
        await mark_notif_sent(m["id"])
        await asyncio.sleep(0.1)

async def _send_reminder_for_match(bot: Bot, m):
    users = await get_all_users()
    f1, f2 = flag(m["team1"]), flag(m["team2"])
    for u in users:
        try:
            lang = u["lang"]
            t1 = tname(m["team1"], lang); t2 = tname(m["team2"], lang)
            time_str = fmt_time(m["match_time"], lang)
            pred = await get_prediction(u["user_id"], m["id"])

            if lang == "fa":
                header = "⏰ <b>به‌زودی بازی شروع میشه!</b>\n\n"
                match_txt = f"{f1} {t1}\n{f2} {t2}\n🗓 {time_str}\n\n"
                if pred:
                    pred_txt = (f"✏️ پیش‌بینی فعلیت:\n"
                                f"{f1} {t1}: {pred['pred1']}\n"
                                f"{f2} {t2}: {pred['pred2']}\n\n"
                                f"تا شروع بازی می‌تونی تغییر بدی!")
                    btn_lbl = "✏️ تغییر پیش‌بینی"
                else:
                    pred_txt = "⚠️ <b>هنوز پیش‌بینی نکردی!</b>"
                    btn_lbl = "⚽ پیش‌بینی کن"
            else:
                header = "⏰ <b>Match starts soon!</b>\n\n"
                match_txt = f"{f1} {t1}\n{f2} {t2}\n🗓 {time_str}\n\n"
                if pred:
                    pred_txt = (f"✏️ Your current pick:\n"
                                f"{f1} {t1}: {pred['pred1']}\n"
                                f"{f2} {t2}: {pred['pred2']}\n\n"
                                f"You can change until kickoff!")
                    btn_lbl = "✏️ Change prediction"
                else:
                    pred_txt = "⚠️ <b>You haven't predicted yet!</b>"
                    btn_lbl = "⚽ Predict now"

            kb = Markup([[Btn(btn_lbl, callback_data=f"predict_{m['id']}")]])
            await bot.send_message(u["user_id"], header + match_txt + pred_txt,
                                   parse_mode="HTML", reply_markup=kb)
            await asyncio.sleep(0.05)
        except Exception as e:
            log.warning(f"Reminder to {u['user_id']}: {e}")

# ── چک کردن و اعلام نتایج ───────────────────

async def check_and_announce_results(bot: Bot):
    matches = await get_matches_to_check_result()
    for m in matches:
        if m["stage"] == "group":
            await _handle_group_result(bot, m)
        else:
            await _handle_knockout_result(bot, m)
        await asyncio.sleep(1)

async def _handle_group_result(bot: Bot, m):
    if not m["api_id"]:
        log.warning(f"Match {m['id']} ({m['team1']} vs {m['team2']}) has no api_id")
        return
    result = await get_match_result(m["api_id"])
    # اگه بازی هنوز تموم نشده، این دور رد میکنیم — دور بعدی دوباره چک میشه
    if not result or result["status"] not in ("FINISHED", "FT", "AET", "PEN"):
        return
    if result["home_score"] is None:
        return
    r1, r2 = result["home_score"], result["away_score"]
    count, _, _ = await set_result(m["id"], r1, r2)
    await mark_result_sent(m["id"])
    await _announce_result(bot, m, r1, r2, None, None, count)

async def _handle_knockout_result(bot: Bot, m):
    if not m["api_id"]:
        log.warning(f"Knockout match {m['id']} ({m['team1']} vs {m['team2']}) has no api_id")
        return
    result = await get_match_result(m["api_id"])
    # اگه بازی هنوز تموم نشده (در حال بازی یا وقت اضافه)، این دور رد میکنیم
    if not result or result["status"] not in ("FINISHED", "FT", "AET", "PEN"):
        return
    # نتیجه ۹۰ دقیقه — برای امتیازدهی فقط این مهمه
    r1 = result["home_score"]
    r2 = result["away_score"]
    if r1 is None:
        return
    # پنالتی رو فقط برای نمایش (اعلام برنده) نگه میداریم، نه امتیازدهی
    p1 = result.get("penalty_home")
    p2 = result.get("penalty_away")
    # set_result با نتیجه ۹۰ دقیقه — اگه تساوی بود امتیاز تساوی میگیره (درست)
    count, winner, _ = await set_result(m["id"], r1, r2, p1, p2)
    await mark_result_sent(m["id"])
    await _announce_result(bot, m, r1, r2, p1, p2, count, winner)

async def _announce_result(bot: Bot, m, r1, r2, p1, p2, pred_count, winner=None):
    users = await get_all_users()
    f1, f2 = flag(m["team1"]), flag(m["team2"])
    exact_count = await count_exact_predictions(m["id"])
    is_knockout = m["stage"] in KNOCKOUT_STAGES

    for u in users:
        try:
            lang = u["lang"]
            t1 = tname(m["team1"], lang); t2 = tname(m["team2"], lang)
            if lang == "fa":
                txt = "🏁 <b>پایان بازی</b>\n\n"
                txt += f"{f1} {t1}: {r1}\n{f2} {t2}: {r2}\n"
                if p1 is not None and p2 is not None:
                    txt += f"\n⚽ ضربات پنالتی: {t1} {p1} — {p2} {t2}\n"
                if winner and is_knockout:
                    txt += f"\n🏆 صعود کننده: {flag(winner)} {tname(winner, lang)}\n"
            else:
                txt = "🏁 <b>Full Time</b>\n\n"
                txt += f"{f1} {t1}: {r1}\n{f2} {t2}: {r2}\n"
                if p1 is not None and p2 is not None:
                    txt += f"\n⚽ Penalties: {t1} {p1} — {p2} {t2}\n"
                if winner and is_knockout:
                    txt += f"\n🏆 Winner: {flag(winner)} {tname(winner, lang)}\n"

            pred = await get_prediction(u["user_id"], m["id"])
            txt += "\n"
            if pred and pred["points"] is not None:
                pts = pred["points"]
                if lang == "fa":
                    txt += (f"پیش‌بینی تو: {pred['pred1']}-{pred['pred2']}\n"
                            f"امتیاز این بازی: <b>+{pts}</b> {'🎯' if pts==10 else '✅' if pts>=5 else '❌'}\n")
                else:
                    txt += (f"Your pick: {pred['pred1']}-{pred['pred2']}\n"
                            f"Points: <b>+{pts}</b> {'🎯' if pts==10 else '✅' if pts>=5 else '❌'}\n")
            elif lang == "fa":
                txt += "پیش‌بینی نکرده بودی — ۰ امتیاز\n"
            else:
                txt += "No prediction — 0 points\n"

            if lang == "fa":
                txt += f"\n🎯 <b>{exact_count}</b> نفر نتیجه رو دقیق زدن"
            else:
                txt += f"\n🎯 <b>{exact_count}</b> players got it exactly right"

            await bot.send_message(u["user_id"], txt, parse_mode="HTML")
            await asyncio.sleep(0.05)
        except Exception as e:
            log.warning(f"Result announce to {u['user_id']}: {e}")

# ── اعلام اصلاح نتیجه ─────────────────────────

async def announce_result_correction(bot: Bot, m, r1, r2, p1, p2, changed: list):
    """بعد از اصلاح نتیجه توسط ادمین، فقط به کسایی که امتیازشون عوض شده پیام بفرست"""
    f1, f2 = flag(m["team1"]), flag(m["team2"])
    for ch in changed:
        try:
            u = await get_user(ch["user_id"])
            if not u: continue
            lang = u["lang"]
            t1 = tname(m["team1"], lang); t2 = tname(m["team2"], lang)
            delta = ch["new_pts"] - (ch["old_pts"] or 0)
            sign = "+" if delta >= 0 else ""
            if lang == "fa":
                txt = ("🔧 <b>نتیجه یک بازی اصلاح شد</b>\n\n"
                       f"{f1} {t1}  <b>{r1}-{r2}</b>  {t2} {f2}\n")
                if p1 is not None:
                    txt += f"پنالتی: {p1}-{p2}\n"
                txt += (f"\nپیش‌بینی تو: {ch['pred1']}-{ch['pred2']}\n"
                        f"امتیاز قبلی: {ch['old_pts'] or 0}\n"
                        f"امتیاز جدید: <b>{ch['new_pts']}</b> ({sign}{delta})")
            else:
                txt = ("🔧 <b>A match result was corrected</b>\n\n"
                       f"{f1} {t1}  <b>{r1}-{r2}</b>  {t2} {f2}\n")
                if p1 is not None:
                    txt += f"Penalties: {p1}-{p2}\n"
                txt += (f"\nYour pick: {ch['pred1']}-{ch['pred2']}\n"
                        f"Old points: {ch['old_pts'] or 0}\n"
                        f"New points: <b>{ch['new_pts']}</b> ({sign}{delta})")
            await bot.send_message(u["user_id"], txt, parse_mode="HTML")
            await asyncio.sleep(0.05)
        except Exception as e:
            log.warning(f"Correction notice to {ch['user_id']}: {e}")

# ── sync کردن api_id ها ─────────────────────

async def sync_api_ids():
    """هر بار اجرا میشه (دوره‌ای) تا api_id بازی‌ها (مخصوصاً حذفی که بعداً اضافه میشن) رو پر کنه"""
    from api_client import get_competition_matches
    log.info("Syncing API match IDs...")
    api_matches = await get_competition_matches()
    if not api_matches:
        log.warning("No matches from API")
        return

    pool = await get_pool()
    synced = 0
    async with pool.acquire() as conn:
        for am in api_matches:
            home = normalize_name(am.get("homeTeam",{}).get("name",""))
            away = normalize_name(am.get("awayTeam",{}).get("name",""))
            api_id = am.get("id")
            if not home or not away or not api_id:
                continue
            # FIX: پرانتزها — قبلاً api_id IS NULL فقط به شاخه دوم میچسبید و باعث بازنویسی میشد
            result = await conn.execute("""
                UPDATE matches SET api_id=$1
                WHERE ((team1=$2 AND team2=$3) OR (team1=$3 AND team2=$2))
                  AND api_id IS NULL
            """, api_id, home, away)
            if result != "UPDATE 0":
                synced += 1
    log.info(f"Synced {synced} match API IDs")

def normalize_name(name: str) -> str:
    from wc_data import API_NAME_MAP
    return API_NAME_MAP.get(name, name)
