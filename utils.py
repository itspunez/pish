import re
from datetime import datetime, timedelta
from wc_data import TEAM_FLAG, TEAM_FA
from config import POINTS

MONTHS_FA = ["","ژانویه","فوریه","مارس","آوریل","مه","ژوئن",
             "ژوئیه","اوت","سپتامبر","اکتبر","نوامبر","دسامبر"]
IRAN_OFFSET = timedelta(hours=3, minutes=30)

def flag(team: str) -> str:
    return TEAM_FLAG.get(team, "🏳️")

def tname(team: str, lang: str) -> str:
    return TEAM_FA.get(team, team) if lang == "fa" else team

def fmt_time(dt_str: str, lang: str) -> str:
    try:
        dt = datetime.strptime(str(dt_str)[:16], "%Y-%m-%d %H:%M")
    except Exception:
        return str(dt_str)
    if lang == "fa":
        dt_ir = dt + IRAN_OFFSET
        return f"{dt_ir.day} {MONTHS_FA[dt_ir.month]}، ساعت {dt_ir.strftime('%H:%M')} (ایران)"
    return dt.strftime("%b %d, %H:%M UTC")

def fmt_pred_result(t1, t2, p1, p2, lang):
    """نمایش پیش‌بینی در دو خط"""
    return f"{flag(t1)} {tname(t1,lang)}: {p1}\n{flag(t2)} {tname(t2,lang)}: {p2}"

def make_display_name(user) -> str:
    return (user.full_name or user.first_name or "User").strip()

def parse_score(text: str):
    text = text.strip().replace("–","-").replace(" ","-")
    m = re.match(r"^(\d{1,2})-(\d{1,2})$", text)
    if not m: return None
    a, b = int(m.group(1)), int(m.group(2))
    if a > 20 or b > 20: return None
    return (a, b)

def calc_points(pred1, pred2, result1, result2) -> int:
    if pred1 == result1 and pred2 == result2:
        return POINTS["exact"]
    if (pred1 - pred2) == (result1 - result2):
        return POINTS["diff"]
    def winner(a,b): return 1 if a>b else (2 if a<b else 0)
    if winner(pred1,pred2) == winner(result1,result2):
        return POINTS["winner"]
    return POINTS["wrong"]
