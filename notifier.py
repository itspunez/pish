"""notifier.py — یادآوری، اعلام نتایج، اعلام اصلاح نتیجه"""
import asyncio
import logging

from telegram import Bot, InlineKeyboardButton as Btn, InlineKeyboardMarkup as Markup

from database import (
    get_matches_to_notify, get_matches_to_check_result,
    get_match, get_prediction, get_all_users, get_user,
    set_result, mark_notif_sent, mark_result_sent,
    count_exact_predictions, get_pool,
    score_advancements, apply_boosts_to_predictions,
    get_advancement,
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
    if not result or result["status"] not in ("FINISHED", "FT", "AET", "PEN"):
        return
    r1 = result["home_score"]
    r2 = result["away_score"]
    if r1 is None:
        return
    p1 = result.get("penalty_home")
    p2 = result.get("penalty_away")
    count, winner, changed_preds = await set_result(
        m["id"], r1, r2, p1, p2,
        et1=result.get("et_home"), et2=result.get("et_away"))

    boost_changes = await apply_boosts_to_predictions(m["id"])
    boost_map = {b["user_id"]: b for b in boost_changes}

    adv_changes = []
    if winner:
        adv_changes = await score_advancements(m["id"], winner)
    adv_map = {a["user_id"]: a for a in adv_changes}

    await mark_result_sent(m["id"])
    await _announce_result(bot, m, r1, r2, p1, p2, count, winner, boost_map, adv_map)

async def _announce_result(bot: Bot, m, r1, r2, p1, p2, pred_count, winner=None,
                           boost_map=None, adv_map=None):
    users = await get_all_users()
    f1, f2 = flag(m["team1"]), flag(m["team2"])
    exact_count = await count_exact_predictions(m["id"])
    is_knockout = m["stage"] in KNOCKOUT_STAGES
    boost_map = boost_map or {}
    adv_map = adv_map or {}

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

            uid = u["user_id"]
            pred = await get_prediction(uid, m["id"])
            txt += "\n"
            if pred and pred["points"] is not None:
                pts = pred["points"]
                is_boosted = uid in boost_map
                boost_note = ""
                if is_boosted:
                    old = boost_map[uid]["old_pts"]
                    boost_note = f" 🚀×۲ ({old}→{pts})" if lang=="fa" else f" 🚀×2 ({old}→{pts})"
                if lang == "fa":
                    txt += (f"پیش‌بینی تو: {pred['pred1']}-{pred['pred2']}\n"
                            f"امتیاز این بازی: <b>+{pts}</b>{boost_note} "
                            f"{'🎯' if pts>=20 else '🎯' if pts==10 else '✅' if pts>=5 else '❌'}\n")
                else:
                    txt += (f"Your pick: {pred['pred1']}-{pred['pred2']}\n"
                            f"Points: <b>+{pts}</b>{boost_note} "
                            f"{'🎯' if pts>=20 else '🎯' if pts==10 else '✅' if pts>=5 else '❌'}\n")
            elif lang == "fa":
                txt += "پیش‌بینی نکرده بودی — ۰ امتیاز\n"
            else:
                txt += "No prediction — 0 points\n"

            # امتیاز صعود
            if is_knockout and winner and uid in adv_map:
                adv = adv_map[uid]
                adv_pts = adv["points"]
                adv_team = tname(adv["team"], lang)
                if lang == "fa":
                    txt += (f"🏆 پیش‌بینی صعود: {adv_team} → "
                            f"<b>+{adv_pts}</b> {'✅' if adv_pts==5 else '❌'}\n")
                else:
                    txt += (f"🏆 Advancement pick: {adv_team} → "
                            f"<b>+{adv_pts}</b> {'✅' if adv_pts==5 else '❌'}\n")

            if lang == "fa":
                txt += f"\n🎯 <b>{exact_count}</b> نفر نتیجه رو دقیق زدن"
            else:
                txt += f"\n🎯 <b>{exact_count}</b> players got it exactly right"

            await bot.send_message(u["user_id"], txt, parse_mode="HTML")
            await asyncio.sleep(0.05)
        except Exception as e:
            log.warning(f"Result announce to {u['user_id']}: {e}")

# ── اعلام اصلاح نتیجه ─────────────────────────

async def announce_result_correction(bot: Bot, m, r1, r2, p1, p2, changed: list,
                                     boost_map: dict = None, adv_map: dict = None):
    """بعد از اصلاح نتیجه توسط ادمین، به همه کاربرها پیام بفرست.
    - کسایی که امتیازشون عوض شد: تغییر امتیاز رو میبینن
    - کسایی که بوست داشتن: بوست اعمال‌شده رو میبینن
    - کسایی که صعود پیش‌بینی کرده بودن: امتیاز صعود رو میبینن
    """
    boost_map = boost_map or {}
    adv_map = adv_map or {}
    f1, f2 = flag(m["team1"]), flag(m["team2"])
    is_knockout = m["stage"] in KNOCKOUT_STAGES

    # ساخت set از user_idهایی که باید پیام بگیرن
    changed_map = {ch["user_id"]: ch for ch in changed}
    notif_users = set(changed_map.keys()) | set(boost_map.keys()) | set(adv_map.keys())

    for uid in notif_users:
        try:
            u = await get_user(uid)
            if not u:
                continue
            lang = u["lang"]
            t1 = tname(m["team1"], lang); t2 = tname(m["team2"], lang)

            if lang == "fa":
                txt = ("🔧 <b>نتیجه یک بازی اصلاح شد</b>\n\n"
                       f"{f1} {t1}  <b>{r1}-{r2}</b>  {t2} {f2}\n")
                if p1 is not None:
                    txt += f"پنالتی: {p1}-{p2}\n"
            else:
                txt = ("🔧 <b>A match result was corrected</b>\n\n"
                       f"{f1} {t1}  <b>{r1}-{r2}</b>  {t2} {f2}\n")
                if p1 is not None:
                    txt += f"Penalties: {p1}-{p2}\n"

            txt += "\n"

            # تغییر امتیاز پیش‌بینی
            if uid in changed_map:
                ch = changed_map[uid]
                delta = ch["new_pts"] - (ch["old_pts"] or 0)
                sign = "+" if delta >= 0 else ""
                boost_note = ""
                if uid in boost_map:
                    boost_note = " 🚀×۲" if lang == "fa" else " 🚀×2"
                if lang == "fa":
                    txt += (f"پیش‌بینی تو: {ch['pred1']}-{ch['pred2']}\n"
                            f"امتیاز قبلی: {ch['old_pts'] or 0}\n"
                            f"امتیاز جدید: <b>{ch['new_pts']}</b>{boost_note} ({sign}{delta})\n")
                else:
                    txt += (f"Your pick: {ch['pred1']}-{ch['pred2']}\n"
                            f"Old points: {ch['old_pts'] or 0}\n"
                            f"New points: <b>{ch['new_pts']}</b>{boost_note} ({sign}{delta})\n")
            elif uid in boost_map:
                # بوست داشت ولی امتیاز پیش‌بینی تغییر نکرد
                b = boost_map[uid]
                if lang == "fa":
                    txt += f"🚀 بوست ×۲ اعمال شد: {b['old_pts']}→{b['new_pts']}\n"
                else:
                    txt += f"🚀 Boost ×2 applied: {b['old_pts']}→{b['new_pts']}\n"

            # امتیاز صعود
            if is_knockout and uid in adv_map:
                adv = adv_map[uid]
                adv_pts = adv["points"]
                adv_team = tname(adv["team"], lang)
                if lang == "fa":
                    txt += (f"🏆 پیش‌بینی صعود: {adv_team} → "
                            f"<b>+{adv_pts}</b> {'✅' if adv_pts > 0 else '❌'}\n")
                else:
                    txt += (f"🏆 Advancement pick: {adv_team} → "
                            f"<b>+{adv_pts}</b> {'✅' if adv_pts > 0 else '❌'}\n")

            await bot.send_message(uid, txt, parse_mode="HTML")
            await asyncio.sleep(0.05)
        except Exception as e:
            log.warning(f"Correction notice to {uid}: {e}")

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
