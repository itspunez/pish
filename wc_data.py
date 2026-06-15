TEAM_FLAG = {
    "Mexico":"🇲🇽","South Africa":"🇿🇦","South Korea":"🇰🇷","Czechia":"🇨🇿",
    "Canada":"🇨🇦","Bosnia and Herzegovina":"🇧🇦","Qatar":"🇶🇦","Switzerland":"🇨🇭",
    "Brazil":"🇧🇷","Morocco":"🇲🇦","Haiti":"🇭🇹","Scotland":"🏴󠁧󠁢󠁳󠁣󠁴󠁿",
    "United States":"🇺🇸","Paraguay":"🇵🇾","Australia":"🇦🇺","Turkiye":"🇹🇷",
    "Germany":"🇩🇪","Curacao":"🇨🇼","Ivory Coast":"🇨🇮","Ecuador":"🇪🇨",
    "Netherlands":"🇳🇱","Japan":"🇯🇵","Sweden":"🇸🇪","Tunisia":"🇹🇳",
    "Belgium":"🇧🇪","Egypt":"🇪🇬","Iran":"🇮🇷","New Zealand":"🇳🇿",
    "Spain":"🇪🇸","Cape Verde":"🇨🇻","Saudi Arabia":"🇸🇦","Uruguay":"🇺🇾",
    "France":"🇫🇷","Senegal":"🇸🇳","Iraq":"🇮🇶","Norway":"🇳🇴",
    "Argentina":"🇦🇷","Algeria":"🇩🇿","Austria":"🇦🇹","Jordan":"🇯🇴",
    "Portugal":"🇵🇹","DR Congo":"🇨🇩","Uzbekistan":"🇺🇿","Colombia":"🇨🇴",
    "England":"🏴󠁧󠁢󠁥󠁮󠁧󠁿","Croatia":"🇭🇷","Ghana":"🇬🇭","Panama":"🇵🇦",
}

TEAM_FA = {
    "Mexico":"مکزیک","South Africa":"آفریقای جنوبی","South Korea":"کره جنوبی",
    "Czechia":"چک","Canada":"کانادا","Bosnia and Herzegovina":"بوسنی",
    "Qatar":"قطر","Switzerland":"سوئیس","Brazil":"برزیل","Morocco":"مراکش",
    "Haiti":"هائیتی","Scotland":"اسکاتلند","United States":"آمریکا",
    "Paraguay":"پاراگوئه","Australia":"استرالیا","Turkiye":"ترکیه",
    "Germany":"آلمان","Curacao":"کوراسائو","Ivory Coast":"ساحل عاج",
    "Ecuador":"اکوادور","Netherlands":"هلند","Japan":"ژاپن",
    "Sweden":"سوئد","Tunisia":"تونس","Belgium":"بلژیک","Egypt":"مصر",
    "Iran":"ایران","New Zealand":"نیوزیلند","Spain":"اسپانیا",
    "Cape Verde":"کیپ‌ورد","Saudi Arabia":"عربستان","Uruguay":"اروگوئه",
    "France":"فرانسه","Senegal":"سنگال","Iraq":"عراق","Norway":"نروژ",
    "Argentina":"آرژانتین","Algeria":"الجزایر","Austria":"اتریش",
    "Jordan":"اردن","Portugal":"پرتغال","DR Congo":"کنگو",
    "Uzbekistan":"ازبکستان","Colombia":"کلمبیا","England":"انگلیس",
    "Croatia":"کرواسی","Ghana":"غنا","Panama":"پاناما",
}

# نام‌های متفاوت که API ممکنه استفاده کنه
API_NAME_MAP = {
    "Korea Republic": "South Korea",
    "Czech Republic": "Czechia",
    "Bosnia Herzegovina": "Bosnia and Herzegovina",
    "Côte D'Ivoire": "Ivory Coast",
    "IR Iran": "Iran",
    "USA": "United States",
    "Türkiye": "Turkiye",
    "England": "England",
    "Congo DR": "DR Congo",
}

# (group, round, team1, team2, utc_time, city)
GROUP_MATCHES = [
    ("A",1,"Mexico","South Africa","2026-06-11 19:00","Mexico City"),
    ("A",1,"South Korea","Czechia","2026-06-12 02:00","Guadalajara"),
    ("A",2,"Czechia","South Africa","2026-06-18 16:00","Atlanta"),
    ("A",2,"Mexico","South Korea","2026-06-19 01:00","Guadalajara"),
    ("A",3,"Czechia","Mexico","2026-06-25 01:00","Mexico City"),
    ("A",3,"South Africa","South Korea","2026-06-25 01:00","Monterrey"),
    ("B",1,"Canada","Bosnia and Herzegovina","2026-06-12 19:00","Toronto"),
    ("B",1,"Qatar","Switzerland","2026-06-13 19:00","San Francisco"),
    ("B",2,"Switzerland","Bosnia and Herzegovina","2026-06-18 19:00","Los Angeles"),
    ("B",2,"Canada","Qatar","2026-06-18 22:00","Vancouver"),
    ("B",3,"Switzerland","Canada","2026-06-24 19:00","Vancouver"),
    ("B",3,"Bosnia and Herzegovina","Qatar","2026-06-24 19:00","Seattle"),
    ("C",1,"Brazil","Morocco","2026-06-13 22:00","New York"),
    ("C",1,"Haiti","Scotland","2026-06-14 01:00","Boston"),
    ("C",2,"Scotland","Morocco","2026-06-19 22:00","Boston"),
    ("C",2,"Brazil","Haiti","2026-06-20 00:30","Philadelphia"),
    ("C",3,"Scotland","Brazil","2026-06-24 22:00","Miami"),
    ("C",3,"Morocco","Haiti","2026-06-24 22:00","Atlanta"),
    ("D",1,"United States","Paraguay","2026-06-13 01:00","Los Angeles"),
    ("D",1,"Australia","Turkiye","2026-06-14 04:00","Vancouver"),
    ("D",2,"United States","Australia","2026-06-19 19:00","Seattle"),
    ("D",2,"Turkiye","Paraguay","2026-06-20 03:00","San Francisco"),
    ("D",3,"Turkiye","United States","2026-06-26 02:00","Los Angeles"),
    ("D",3,"Paraguay","Australia","2026-06-26 02:00","San Francisco"),
    ("E",1,"Germany","Curacao","2026-06-14 17:00","Houston"),
    ("E",1,"Ivory Coast","Ecuador","2026-06-14 23:00","Philadelphia"),
    ("E",2,"Germany","Ivory Coast","2026-06-20 20:00","Toronto"),
    ("E",2,"Ecuador","Curacao","2026-06-21 00:00","Kansas City"),
    ("E",3,"Curacao","Ivory Coast","2026-06-25 20:00","Philadelphia"),
    ("E",3,"Ecuador","Germany","2026-06-25 20:00","New York"),
    ("F",1,"Netherlands","Japan","2026-06-14 20:00","Dallas"),
    ("F",1,"Sweden","Tunisia","2026-06-15 02:00","Monterrey"),
    ("F",2,"Netherlands","Sweden","2026-06-20 17:00","Houston"),
    ("F",2,"Tunisia","Japan","2026-06-21 04:00","Monterrey"),
    ("F",3,"Japan","Sweden","2026-06-25 23:00","Dallas"),
    ("F",3,"Tunisia","Netherlands","2026-06-25 23:00","Kansas City"),
    ("G",1,"Belgium","Egypt","2026-06-15 19:00","Seattle"),
    ("G",1,"Iran","New Zealand","2026-06-16 01:00","Los Angeles"),
    ("G",2,"Belgium","Iran","2026-06-21 19:00","Los Angeles"),
    ("G",2,"New Zealand","Egypt","2026-06-22 01:00","Vancouver"),
    ("G",3,"Egypt","Iran","2026-06-27 03:00","Seattle"),
    ("G",3,"New Zealand","Belgium","2026-06-27 03:00","Vancouver"),
    ("H",1,"Spain","Cape Verde","2026-06-15 16:00","Atlanta"),
    ("H",1,"Saudi Arabia","Uruguay","2026-06-15 22:00","Miami"),
    ("H",2,"Spain","Saudi Arabia","2026-06-21 16:00","Atlanta"),
    ("H",2,"Uruguay","Cape Verde","2026-06-21 22:00","Miami"),
    ("H",3,"Cape Verde","Saudi Arabia","2026-06-27 00:00","Houston"),
    ("H",3,"Uruguay","Spain","2026-06-27 00:00","Guadalajara"),
    ("I",1,"France","Senegal","2026-06-16 19:00","New York"),
    ("I",1,"Iraq","Norway","2026-06-16 22:00","Boston"),
    ("I",2,"France","Iraq","2026-06-22 21:00","Philadelphia"),
    ("I",2,"Norway","Senegal","2026-06-23 00:00","New York"),
    ("I",3,"Norway","France","2026-06-26 19:00","Boston"),
    ("I",3,"Senegal","Iraq","2026-06-26 19:00","Toronto"),
    ("J",1,"Argentina","Algeria","2026-06-17 01:00","Kansas City"),
    ("J",1,"Austria","Jordan","2026-06-17 04:00","San Francisco"),
    ("J",2,"Argentina","Austria","2026-06-22 17:00","Dallas"),
    ("J",2,"Jordan","Algeria","2026-06-23 03:00","San Francisco"),
    ("J",3,"Algeria","Austria","2026-06-28 02:00","Kansas City"),
    ("J",3,"Jordan","Argentina","2026-06-28 02:00","Dallas"),
    ("K",1,"Portugal","DR Congo","2026-06-17 17:00","Houston"),
    ("K",1,"Uzbekistan","Colombia","2026-06-18 02:00","Mexico City"),
    ("K",2,"Portugal","Uzbekistan","2026-06-23 17:00","Houston"),
    ("K",2,"Colombia","DR Congo","2026-06-24 02:00","Guadalajara"),
    ("K",3,"Colombia","Portugal","2026-06-27 23:30","Miami"),
    ("K",3,"DR Congo","Uzbekistan","2026-06-27 23:30","Atlanta"),
    ("L",1,"England","Croatia","2026-06-17 20:00","Dallas"),
    ("L",1,"Ghana","Panama","2026-06-17 23:00","Toronto"),
    ("L",2,"England","Ghana","2026-06-23 20:00","Boston"),
    ("L",2,"Panama","Croatia","2026-06-23 23:00","Toronto"),
    ("L",3,"Panama","England","2026-06-27 21:00","New York"),
    ("L",3,"Croatia","Ghana","2026-06-27 21:00","Philadelphia"),
]

STAGE_LABEL = {
    "group": {"fa":"مرحله گروهی",     "en":"Group Stage"},
    "r32":   {"fa":"یک‌سی‌ودوم",      "en":"Round of 32"},
    "r16":   {"fa":"یک‌شانزدهم",      "en":"Round of 16"},
    "qf":    {"fa":"یک‌چهارم نهایی",  "en":"Quarter-finals"},
    "sf":    {"fa":"نیمه‌نهایی",      "en":"Semi-finals"},
    "third": {"fa":"رده‌بندی سوم",    "en":"Third Place"},
    "final": {"fa":"فینال",           "en":"Final"},
}

KNOCKOUT_ORDER = ["r32","r16","qf","sf","third","final"]
KNOCKOUT_STAGES = {"r32","r16","qf","sf","third","final"}

# ─── KNOCKOUT MATCHES (FIFA WC 2026 — schedule v17, 10 April 2026) ──────────
# ساعت‌ها UTC هستن (ET + 4 ساعت — EDT)
# نام تیم‌ها به‌صورت placeholder طبق براکت رسمی FIFA:
#   "1A"  = صدرنشین گروه A
#   "2B"  = تیم دوم گروه B
#   "3CDEF" = تیم سوم از یکی از گروه‌های C/D/E/F (طبق ترتیب براکت)
#   "W74" = برنده‌ی بازی شماره ۷۴
# بعد از مشخص شدن تیم‌ها، ادمین با /editmatch به‌روزرسانی می‌کنه.
# (stage, match_no, team1, team2, utc_time, city)
KNOCKOUT_MATCHES = [
    ("r32",73,"2A","2B","2026-06-28 19:00","Los Angeles"),
    ("r32",74,"1E","3ABCDF","2026-06-29 17:00","Houston"),
    ("r32",75,"1F","2C","2026-06-29 20:30","Boston"),
    ("r32",76,"1C","2F","2026-06-30 01:00","Monterrey"),
    ("r32",77,"1I","3CDFGH","2026-06-30 17:00","Dallas"),
    ("r32",78,"2E","2I","2026-06-30 21:00","New York"),
    ("r32",79,"1A","3CEFHI","2026-07-01 01:00","Mexico City"),
    ("r32",80,"1L","3EHIJK","2026-07-01 16:00","Atlanta"),
    ("r32",81,"1D","3BEFIJ","2026-07-01 20:00","Seattle"),
    ("r32",82,"1G","3AEHIJ","2026-07-02 00:00","San Francisco"),
    ("r32",83,"2K","2L","2026-07-02 19:00","Los Angeles"),
    ("r32",84,"1H","2J","2026-07-02 23:00","Toronto"),
    ("r32",85,"1B","3EFGIJ","2026-07-03 03:00","Vancouver"),
    ("r32",86,"1J","2H","2026-07-03 18:00","Dallas"),
    ("r32",87,"1K","3DEIJL","2026-07-03 22:00","Miami"),
    ("r32",88,"2D","2G","2026-07-04 01:30","Kansas City"),
    ("r16",89,"W74","W77","2026-07-04 17:00","Houston"),
    ("r16",90,"W73","W75","2026-07-04 21:00","Philadelphia"),
    ("r16",91,"W76","W78","2026-07-05 20:00","New York"),
    ("r16",92,"W79","W80","2026-07-06 00:00","Mexico City"),
    ("r16",93,"W83","W84","2026-07-06 19:00","Dallas"),
    ("r16",94,"W81","W82","2026-07-07 00:00","Seattle"),
    ("r16",95,"W86","W88","2026-07-07 16:00","Atlanta"),
    ("r16",96,"W85","W87","2026-07-07 20:00","Vancouver"),
    ("qf",97,"W89","W90","2026-07-09 20:00","Boston"),
    ("qf",98,"W93","W94","2026-07-10 19:00","Los Angeles"),
    ("qf",99,"W91","W92","2026-07-11 21:00","Miami"),
    ("qf",100,"W95","W96","2026-07-12 01:00","Kansas City"),
    ("sf",101,"W97","W98","2026-07-14 19:00","Dallas"),
    ("sf",102,"W99","W100","2026-07-15 19:00","Atlanta"),
    ("third",103,"L101","L102","2026-07-18 21:00","Miami"),
    ("final",104,"W101","W102","2026-07-19 19:00","New York"),
]

def is_placeholder_team(name: str) -> bool:
    """True اگر نام تیم هنوز placeholder باشه (1A, 2B, 3CDEF, W77, L101 ...)
    و هنوز تیم واقعی جایگزین نشده باشه."""
    if not name:
        return True
    import re
    return bool(re.fullmatch(r"[1-3][A-L]+|W\d{1,3}|L\d{1,3}", name.strip()))
