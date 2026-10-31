"""Congress Scorecard: one picture post a day, 6:30 am Mountain, about the last market day.

    python3 scorecard.py                                   the look, 9 slides, SAMPLE numbers -> Morning/
    python3 scorecard.py --post data/close-<day>.json data/trades-<day>.json
                                                           the real post: every slide with real numbers,
                                                           numbered as posted -> Daily Posts/MM.DD Weekday/
    python3 scorecard.py --close ... --trades ...          the old proof (Real Proof MM.DD/Morning)

Every number in this file's own tables is SAMPLE data for the look only.

v3 (Andrew 10.29): every headshot cut out onto one backdrop with the same head size and eye line
(headshots.py), bars in tracks with a column head, one shared-scale intraday chart instead of sparklines.
"""
import datetime, html, json, math, os, random, re, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # our own code only; downloads live under data/
from headshots import shot  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
BONE = (255, 255, 255)                               # every logo, in white
MINUS = "−"
Q = "’"

# how each logo is cleaned for a dark ground: "recolour" turns its black and grey bone, "bone" turns all of it bone
LOGO_ALIAS = {"GOOG": "GOOGL"}               # share classes that wear the same logo
LOGO_CROP = {"CVX": (0, 0.24, 1, 1)}         # Chevron: the mark only, its dark blue wordmark is lost on the ground
ATLAS = os.environ.get("SCORECARD_ATLAS", os.path.join(HERE, "atlas"))   # portraits + logos (not in the repo: see README)
HANDLE = os.environ.get("SCORECARD_HANDLE", "")   # the account name at the foot of each slide
NAMES = {"NVDA": "Nvidia", "MSFT": "Microsoft", "AAPL": "Apple", "GOOGL": "Alphabet", "AMZN": "Amazon",
         "AVGO": "Broadcom", "META": "Meta", "TSLA": "Tesla", "JPM": "JPMorgan Chase", "XOM": "Exxon Mobil",
         "CVX": "Chevron", "DE": "John Deere", "PFE": "Pfizer", "DJT": "Trump Media"}

# portrait id: (name, chamber, party, state) or, for the cabinet, (name, "", "", role)
PEOPLE = {
    "m-p000197": ("Nancy Pelosi", "House", "Democrat", "California"),
    "m-k000389": ("Ro Khanna", "House", "Democrat", "California"),
    "m-m001157": ("Michael McCaul", "House", "Republican", "Texas"),
    "m-g000583": ("Josh Gottheimer", "House", "Democrat", "New Jersey"),
    "m-h001082": ("Kevin Hern", "House", "Republican", "Oklahoma"),
    "m-m001218": ("Rich McCormick", "House", "Republican", "Georgia"),
    "m-f000246": ("Pat Fallon", "House", "Republican", "Texas"),
    "m-m001217": ("Jared Moskowitz", "House", "Democrat", "Florida"),
    "m-j000310": ("Julie Johnson", "House", "Democrat", "Texas"),
    "m-d000626": ("Warren Davidson", "House", "Republican", "Ohio"),
    "m-c001129": ("Mike Collins", "House", "Republican", "Georgia"),
    "m-k000385": ("Robin Kelly", "House", "Democrat", "Illinois"),
    "m-k000388": ("Trent Kelly", "House", "Republican", "Mississippi"),
    "m-j000301": ("Dusty Johnson", "House", "Republican", "South Dakota"),
    "m-m001225": ("Kevin Mullin", "House", "Democrat", "California"),
    "m-m001243": ("David McCormick", "Senate", "Republican", "Pennsylvania"),
    "m-s001217": ("Rick Scott", "Senate", "Republican", "Florida"),
    "m-w000802": ("Sheldon Whitehouse", "Senate", "Democrat", "Rhode Island"),
    "m-h000601": ("Bill Hagerty", "Senate", "Republican", "Tennessee"),
    "m-m001242": ("Bernie Moreno", "Senate", "Republican", "Ohio"),
    "m-j000293": ("Ron Johnson", "Senate", "Republican", "Wisconsin"),
    "m-t000278": ("Tommy Tuberville", "Senate", "Republican", "Alabama"),
    "m-k000377": ("Mark Kelly", "Senate", "Democrat", "Arizona"),
    "m-j000312": ("Jim Justice", "Senate", "Republican", "West Virginia"),
    "m-o000174": ("Jon Ossoff", "Senate", "Democrat", "Georgia"),
    "p-q22686": ("Donald Trump", "", "", "President"),
    "m-v000137": ("JD Vance", "", "", "Vice President"),
    "p-q7435987": ("Scott Bessent", "", "", "Treasury Secretary"),
    "p-q16194176": ("Howard Lutnick", "", "", "Commerce Secretary"),
    "p-q22095395": ("Doug Burgum", "", "", "Interior Secretary"),
    "m-r000595": ("Marco Rubio", "", "", "Secretary of State"),
}

MAST = {"day": "THURSDAY", "date": "OCTOBER 29 2026"}

CLOSE = {
    "day": "Wednesday", "date": "October 28",          # yesterday: the post goes out the next morning
    # (index, change today in %, closing level); the first one gets the chart
    "market": [{"name": "S&P 500", "pct": 0.62, "level": 6912.45}, {"name": "Nasdaq", "pct": 1.10, "level": 23104.88},
               {"name": "Dow", "pct": 0.18, "level": 47512.30}],
    "movers": [("NVDA", 3.4, 61), ("MSFT", 1.2, 74), ("GOOGL", 0.9, 52), ("XOM", -2.1, 38)],
    # (person, estimated change in $K, the stocks that moved them most)
    "winners": [("m-p000197", 1840, ["NVDA", "AAPL", "GOOGL"]), ("m-k000389", 612, ["MSFT", "NVDA"]),
                ("m-m001243", 548, ["MSFT", "AMZN"]), ("m-s001217", 402, ["NVDA", "AVGO"]),
                ("m-m001157", 388, ["GOOGL"])],
    # (party, estimated change in $K, members who own stocks, how many rose, how many fell, its top three)
    "party": [("Democrats", 3120, 118, 84, 34, [("m-p000197", 1840), ("m-k000389", 612), ("m-w000802", 211)]),
              ("Republicans", 2410, 131, 92, 39, [("m-m001243", 548), ("m-s001217", 402), ("m-m001157", 388)])],
    "senate": [("m-m001243", 548, "MSFT"), ("m-s001217", 402, "NVDA"), ("m-w000802", 211, "GOOGL"),
               ("m-h000601", 188, "NVDA"), ("m-m001242", 154, "AMZN"), ("m-j000293", 121, "MSFT"),
               ("m-t000278", 97, "META"), ("m-k000377", 64, "AAPL"), ("m-j000312", 58, "JPM"),
               ("m-o000174", 31, "Index funds")],
    "house": [("m-p000197", 1840, "NVDA"), ("m-k000389", 612, "MSFT"), ("m-m001157", 388, "GOOGL"),
              ("m-g000583", 201, "MSFT"), ("m-h001082", 176, "NVDA"), ("m-m001218", 74, "AMZN"),
              ("m-f000246", 66, "TSLA"), ("m-m001217", 52, "AAPL"), ("m-j000310", 49, "NVDA"),
              ("m-d000626", 28, "MSFT")],
    "losers": [("m-c001129", -38, "XOM"), ("m-k000385", -24, "CVX"), ("m-k000388", -19, "XOM"),
               ("m-j000301", -12, "DE"), ("m-m001225", -9, "PFE")],
    "cabinet": [("p-q22686", 3200, "DJT"), ("m-v000137", 41, "Index funds"), ("p-q7435987", 12, "Treasury bills"),
                ("p-q16194176", 8, "Treasury bills"), ("p-q22095395", -22, "XOM"), ("m-r000595", 0, "No stocks")],
}

OPEN = {
    "yday": "Wednesday",
    # (ticker, when, members who own it, biggest holder, their range)
    "earnings": [("AAPL", "After the close", 41, "m-p000197", "$5M to $25M"),
                 ("XOM", "Before the open", 38, "m-c001129", "$250K to $500K"),
                 ("CVX", "Before the open", 29, "m-k000385", "$100K to $250K")],
    # (time, committee, subject, members on it who own the stock, ticker)
    "hearings": [("10 am", "Senate Banking", "Bank capital rules", ["m-h000601", "m-m001242", "m-m001243"], "JPM"),
                 ("2 pm", "House Energy and Commerce", "Drug prices", ["m-m001225", "m-j000310"], "PFE")],
    # (person, bought?, ticker, range, traded), all reported on the day in "filed"
    "filed": "2026-10-28",
    "trades": [("m-p000197", True, "NVDA", "$1M to $5M", "2026-10-09"),
               ("m-g000583", True, "MSFT", "$1K to $15K", "2026-10-02"),
               ("m-m001243", False, "XOM", "$50K to $100K", "2026-09-30"),
               ("m-f000246", True, "TSLA", "$15K to $50K", "2026-10-14"),
               ("m-h001082", False, "AAPL", "$100K to $250K", "2026-08-31")],
}
# the form a real pull takes (load_trades): whose account it was, the report's day, and its other stock trades
OPEN["trades"] = [{"pid": p, "owner": "self", "type": "P" if b else "S", "ticker": t, "range": r, "traded": td,
                   "filed": OPEN["filed"], "more": 0} for p, b, t, r, td in OPEN["trades"]]

SRC_STOCK = "Estimates from House and Senate stock disclosures, priced at the close."
e = html.escape


# ------------------------------------------------------------------ logos
def prep_logos():
    """Trim every logo to its ink and clean it for a dark ground, into logo_ready/. Returns {ticker: ratio}."""
    import numpy as np
    from PIL import Image
    src, dst = os.path.join(HERE, "logo"), os.path.join(HERE, "logo_ready")
    os.makedirs(dst, exist_ok=True)
    ratios = {}
    for f in sorted(os.listdir(src)):
        if not f.endswith(".png"):
            continue
        t = f[:-4]
        im = Image.open(os.path.join(src, f)).convert("RGBA")
        if t in LOGO_CROP:
            l, tp, r, b = LOGO_CROP[t]
            im = im.crop((int(l * im.width), int(tp * im.height), int(r * im.width), int(b * im.height)))
        box = im.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox()
        im = im.crop(box) if box else im
        a = np.asarray(im).astype(np.float32)         # every logo in one quiet colour: bone. White detail inside
        rgb, alpha = a[..., :3], a[..., 3]               # a logo (the N on a green square) is cut out, not lost
        lum = rgb @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
        chroma = rgb.max(axis=2) - rgb.min(axis=2)
        light = (lum > 225) & (chroma < 30) & (alpha > 0)
        if light.sum() < 0.5 * (alpha > 0).sum():      # light detail inside a dark or coloured logo; a logo
            alpha[light] = 0                           # that is light all over (Apple) keeps its shape
        rgb[alpha > 0] = np.array(BONE, dtype=np.float32)
        im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGBA")
        im.save(os.path.join(dst, f))
        ratios[t] = im.width / im.height
    return ratios


RATIO = {}


def logo(t, area, max_h, max_w=None):
    """One logo at the same ink area as its neighbours (never taller than max_h, never wider than max_w).
    A name with no logo is set as words."""
    if t not in RATIO:
        if t in NAMES:                                  # a company with no logo yet: its name, set like a wordmark
            return f'<span class="wordmark">{e(NAMES[t])}</span>'
        return f'<span class="words">{e(t)}</span>'
    r = RATIO[t]
    h = min(max_h, math.sqrt(area / r), (max_w / r) if max_w else max_h)
    return f'<img src="logo_ready/{t}.png" style="width:{h * r:.0f}px;height:{h:.0f}px" alt="{e(NAMES.get(t, t))}">'


# ------------------------------------------------------------------ words and numbers
def name(pid):
    return PEOPLE[pid][0]


def meta(pid, chamber=True):
    """'House Democrat, California' (or 'Democrat, California' on a one-chamber board); the cabinet gets its role."""
    _, ch, party, state = PEOPLE[pid]
    if not party:
        return state
    return f"{ch} {party}, {state}" if chamber else f"{party}, {state}"


def money(k):
    """1840 -> +$1.84M, 548 -> +$548K, -38 -> -$38K, 0 -> $0."""
    if k == 0:
        return "$0"
    s = "+" if k > 0 else MINUS
    k = abs(k)
    return f"{s}${k / 1000:.2f}M" if k >= 1000 else f"{s}${k}K"


def pct(v, places=2):
    return f"{'+' if v > 0 else MINUS if v < 0 else ''}{abs(v):.{places}f}%"


def tone(v):
    return "up" if v > 0 else "dn" if v < 0 else "flat"


# ------------------------------------------------------------------ shared pieces
STAMP = ["MOCKUP", "SAMPLE NUMBERS"]                  # the masthead's top right; a real pull says PROOF / REAL FILINGS


def masthead(stamp=None):
    stamp = stamp or STAMP
    return f"""<div class="mast"><div class="lock"><span>CONGRESS</span><span>SCORECARD</span></div>
<div class="when"><span>{MAST['day']}</span><span class="dim">{MAST['date']}</span></div>
<div class="mock"><span>§PAGE§</span><span class="dim">{stamp[1]}</span></div></div>"""


def head(word, dek, kick=None):
    """A slide's title: the day it is about on top (YESTERDAY / TODAY), the section word, one plain line."""
    top = f'<div class="kick2">{e(kick)}</div>' if kick else ""
    return f'{top}<div class="sec">{e(word)}</div><div class="dek">{e(dek)}</div>'


def yday(d):
    """The kicker on a slide about the last market day: 'Yesterday · Wednesday, October 28', or on a Monday
    (or after a holiday) 'Friday · October 30': never "yesterday" for a day that wasn't."""
    w = d.get("word", "Yesterday")
    return f"{w} \u00b7 {d['day']}, {d['date']}" if w == "Yesterday" else f"{d['day']} \u00b7 {d['date']}"


def word_for(day, post):
    """'Yesterday' when `day` is the day before the post, else the day's own name ('Friday')."""
    return "Yesterday" if (post - day).days == 1 else f"{day:%A}"


def today():
    return f"Today \u00b7 {MAST['day'].title()}, {MAST['date'].rsplit(' ', 1)[0].title()}"


def slide(body, src=None, cls="", stamp=None):
    src = SRC_STOCK if src is None else src
    foot = f'<div class="src">{e(src)}</div>' if src else ""
    return f'<section class="s {cls}">{masthead(stamp)}{body}{foot}<div class="handle">{HANDLE}</div></section>'


def board(rows, word, dek, metric="Estimated gain", chamber=False, size="board", kick=None):
    """A ranked table: rank, headshot, name, the figure, the stock that moved them most, and under the name
    a bar in a full-width track, so every row's bar starts in the same place and reads on the same scale."""
    top = max(abs(k) for _, k, _ in rows) or 1
    big = size == "big"
    trs = "".join(f"""<div class="tr"><span class="rk">{n + 1}</span><img class="hs" src="{shot(pid, size)}">
<div class="who"><div class="nm">{e(name(pid))}</div><div class="meta">{e(meta(pid, chamber))}</div></div>
<div class="val {tone(k)}">{money(k)}</div><div class="lg">{logo(t, 2600 if big else 1800, 50 if big else 40, 112)}</div>
<div class="trk {tone(k)}"><i style="width:{max(0.8, abs(k) / top * 100):.1f}%"></i></div></div>"""
                  for n, (pid, k, t) in enumerate(rows))
    th = f'<div class="th"><span class="c-g">{metric}</span><span class="c-l">Moved most</span></div>'
    return slide(head(word, dek, kick) + f'<div class="tbl {size}">{th}{trs}</div>')


def close_chart(index, w=936, h=300, seed=11):
    """One index through the day as its change from the prior close, drawn the way market sites draw it: one
    line, the area to the prior close shaded, the scale on the right. A real day passes `points` (minutes after
    9:30, price); the mockup draws a sample path."""
    chg = index["pct"]
    prior = index["level"] / (1 + chg / 100)
    if index.get("points"):
        path = [(m, (p / prior - 1) * 100) for m, p in index["points"]]
    else:
        random.seed(seed)
        walk = [0.0]
        for _ in range(78):
            walk.append(walk[-1] + random.gauss(0.004, 0.05))
        path = [(i * 5, v - (walk[-1] - chg) * i / 78) for i, v in enumerate(walk)]
    path[-1] = (390, chg)                               # end on the day's official close
    vals = [v for _, v in path] + [0.0]
    step = next(s for s in (0.05, 0.1, 0.2, 0.25, 0.5, 1.0, 2.0) if (max(vals) - min(vals)) / s <= 4)
    lo_t, hi_t = math.floor(min(vals) / step) * step, math.ceil(max(vals) / step) * step
    pw, top, bot = w - 92, 10, h - 40
    Y = lambda v: top + (hi_t - v) / (hi_t - lo_t) * (bot - top)
    X = lambda m: m / 390 * pw
    out = []
    t = lo_t
    while t <= hi_t + 1e-9:
        lab = "0%" if abs(t) < 1e-9 else pct(t, 2 if step < 0.1 else 1)
        out.append(f'<line x1="0" x2="{pw}" y1="{Y(t):.1f}" y2="{Y(t):.1f}" class="grid"/>')
        out.append(f'<text x="{w}" y="{Y(t) + 5:.1f}" class="tick" text-anchor="end">{lab}</text>')
        t += step
    for mins, lab in [(30, "10 am"), (150, "Noon"), (270, "2 pm"), (390, "4 pm")]:
        anchor = "end" if mins == 390 else "middle"
        out.append(f'<text x="{X(mins):.1f}" y="{h - 8}" class="tick" text-anchor="{anchor}">{lab}</text>')
    pts = " ".join(f"{X(m):.1f},{Y(v):.1f}" for m, v in path)
    base = Y(0)
    out.append(f'<polygon points="{X(path[0][0]):.1f},{base:.1f} {pts} {pw},{base:.1f}" class="area {tone(chg)}"/>')
    out.append(f'<line x1="0" x2="{pw}" y1="{base:.1f}" y2="{base:.1f}" class="zero"/>')
    out.append(f'<polyline points="{pts}" class="ln {tone(chg)}"/>')
    return f'<svg class="chart" width="{w}" height="{h}" viewBox="0 0 {w} {h}">{"".join(out)}</svg>'


def readouts(market):
    """Each index's move on the day, the charted one first and biggest; under it, its level, or the price of
    the fund that tracks it on a real day."""
    out = []
    for n, m in enumerate(market):
        under = f"{m['via']} {m['level']:,.2f}" if m.get("via") else f"{m['level']:,.2f}"
        out.append(f"""<div class="rd{' lead' if n == 0 else ''}"><div class="rn">{e(m['name'])}</div>
<div class="rl {tone(m['pct'])}">{pct(m['pct'])}</div><div class="rc">{e(under)}</div></div>""")
    return f'<div class="rds">{"".join(out)}</div>'


# ------------------------------------------------------------------ THE CLOSE
def close_cover(d):
    pid, k, drv = d["winners"][0]
    hero = f"""<div class="hero"><img class="hs" src="{shot(pid, 'hero')}"><div class="hc">
<div class="kick">No. 1</div><div class="nm">{e(name(pid))}</div><div class="meta">{e(meta(pid))}</div>
<div class="fig {tone(k)}">{money(k)}</div><div class="lab">Moved most</div>
<div class="logos">{''.join(logo(t, 3800, 46) for t in drv)}</div></div></div>"""
    runs = "".join(f"""<div class="ru"><span class="rk">{n + 2}</span><img class="hs" src="{shot(pid, 'roomy')}">
<div class="who"><div class="nm">{e(name(pid))}</div><div class="meta">{e(meta(pid))}</div></div>
<div class="logos">{''.join(logo(t, 1500, 28) for t in drv)}</div><div class="val {tone(k)}">{money(k)}</div></div>"""
                   for n, (pid, k, drv) in enumerate(d["winners"][1:]))
    body = f"""<h1>{d.get('word', 'Yesterday')}{Q}s biggest winners<br>{d.get('where', 'in Congress')}</h1>
<div class="dek">{d['day']}, {d['date']}. Estimated gains on the stocks they own.</div>{hero}<div class="runs">{runs}</div>"""
    return slide(body, SRC_STOCK, "cover")


def close_market(d):
    rows = "".join(f"""<div class="mo"><div class="lz">{logo(t, 5200, 54)}</div>
<div class="who"><div class="nm">Owned by {m} {d.get('owners', 'members')}</div><div class="meta">{e(FULL.get(t, NAMES[t]))}<span class="tkr">{t}</span></div></div>
<div class="val {tone(c)}">{pct(c, 1)}</div></div>""" for t, c, m in d["movers"])
    body = f"""{head(f"{d.get('word', 'Yesterday')}{Q}s close", f"How the S&P 500 moved through {d['day']}", yday(d))}{readouts(d['market'][:1])}{close_chart(d['market'][0])}
<div class="h2row"><span class="h2">The stocks Congress owns most</span><span class="colh">{d['day']}{Q}s move</span></div>{rows}"""
    return slide(body, d.get("market_src", "Prices at the 4 pm Eastern close."))


def close_cabinet(d):
    cards = "".join(f"""<div class="cab"><img class="hs" src="{shot(pid, 'cab')}"><div class="meta">{e(meta(pid))}</div>
<div class="nm">{e(name(pid))}</div><div class="cf"><div class="fig {tone(k)}">{money(k)}</div><div class="lg">{logo(t, 1900, 30)}</div></div></div>"""
                    for pid, k, t in d["cabinet"])
    body = head("White House", "The President and his cabinet, estimated gain on stocks", yday(d)) + f'<div class="cabs">{cards}</div>'
    return slide(body, "Estimates from yearly Office of Government Ethics filings, priced at the close.")


def close_party(d):
    """Democrats against Republicans: each party's total, one shared bar scale, and the three who led it."""
    top = max(abs(p[1]) for p in d["party"]) or 1
    blocks = "".join(f"""<div class="pt"><div class="pr"><span class="pn">{e(party)}</span><span class="fig {tone(k)}">{money(k)}</span></div>
<div class="trk {tone(k)}"><i style="width:{max(0.8, abs(k) / top * 100):.1f}%"></i></div>
<div class="ps">{owners} members own stocks. {up} rose, {down} fell.</div>
<div class="pl">{''.join(f'''<div class="pc"><img class="hs" src="{shot(pid, 'trade')}"><div><div class="nm2">{e(name(pid))}</div>
<div class="val {tone(v)}">{money(v)}</div></div></div>''' for pid, v in lead)}</div></div>"""
                     for party, k, owners, up, down, lead in d["party"])
    return slide(head("Party score", f"Estimated gain on stocks, {d.get('who', 'every member who owns them')}", yday(d))
                 + f'<div class="pts">{blocks}</div>')


# ------------------------------------------------------------------ THE TRADES AND TODAY
def face(pid, slot):
    """A headshot; an empty frame for someone the atlas has no clean portrait of yet (their name still shows)."""
    if os.path.exists(os.path.join(HERE, "cut", pid + ".png")):
        return f'<img class="hs" src="{shot(pid, slot)}">'
    import headshots
    w, h = headshots.SLOTS[slot][:2]
    return f'<div class="hs" style="width:{w}px;height:{h}px"></div>'


def open_calendar(d):
    """Before the bell: the companies members own that reported since the close (biggest holder beside each), and
    today's hearings. Either half alone fills the slide when the other has nothing."""
    earn = "".join(f"""<div class="er"><div class="lz">{logo(t, 6400, 66, 180)}</div>
<div class="who"><div class="meta">{e(when)}</div><div class="nm">Owned by {m} members</div></div>
<div class="hl">{face(pid, 'board')}<div><div class="nm2">{e(name(pid))}</div><div class="meta">{e(r)}</div></div></div></div>"""
                   for t, when, m, pid, r in d["earnings"])
    hear = "".join(f"""<div class="hr"><div class="tm">{e(tm)}</div><div class="who"><div class="nm">{e(com)}</div><div class="meta">{e(sub)}</div></div>
<div class="busts">{''.join(f'<div class="bust">{face(p, "board")}<span>{e(name(p).split()[-1])}</span></div>' for p in pids)}</div>
<div class="lg">{logo(t, 2800, 48, 130)}</div></div>""" for tm, com, sub, pids, t in d["hearings"])
    body = head('Before the bell', d.get("bell_dek") or 'Earnings and hearings that touch Congress' + Q + 's stocks', today())
    if earn:
        body += f'<div class="h2row"><span class="h2">Earnings</span><span class="colh">Biggest holder in Congress</span></div>{earn}'
    if hear:
        body += f'<div class="h2row"><span class="h2">Hearings</span><span class="colh">Members on the panel who own the stock</span></div>{hear}'
    return slide(body, d.get("bell_src") or
                 "Earnings times from company calendars. Hearings from committee schedules. Holdings from disclosures.",
                 "" if hear else "solo")


def day(iso):
    t = datetime.date.fromisoformat(iso)
    return f"{t:%B} {t.day}"


def traded(r, own_day):
    """'Traded October 9.' (with the report's day when the slide spans several), plus, past the law's
    45 days from the trade, how late the report came."""
    late = (datetime.date.fromisoformat(r["filed"]) - datetime.date.fromisoformat(r["traded"])).days - 45
    tag = f' <b class="late">Filed {late} day{"s" if late != 1 else ""} late.</b>' if late > 0 else ""
    return f"Traded {day(r['traded'])}{', reported ' + day(r['filed']) if own_day else ''}.{tag}"


def action(r):
    """'Bought Nvidia, $1M to $5M', or 'Spouse sold Apple, ...' when it was the spouse's or a child's account."""
    word = {"P": "Bought", "S": "Sold", "S (partial)": "Sold", "E": "Exchanged"}.get(r["type"], r["type"])
    whose = {"SP": "Spouse ", "DC": "Child "}.get(r["owner"], "")
    verb = f'<b class="{"up" if r["type"] == "P" else "dn"}">{word.lower() if whose else word}</b>'
    more = f' <span class="more">+{r["more"]} more trade{"s" if r["more"] != 1 else ""}</span>' if r["more"] else ""
    what = NAMES.get(r["ticker"], r["ticker"]) + (" options" if r.get("kind") == "OP" else "")
    return f"{whose}{verb} {e(what)}, {e(r['range'])}{more}"


def open_trades(d):
    days = sorted({r["filed"] for r in d["trades"]})
    rows = "".join(f"""<div class="td"><img class="hs" src="{shot(r['pid'], 'trade')}"><div class="who"><div class="nm">{e(name(r['pid']))}</div>
<div class="act">{action(r)}</div><div class="meta">{e(meta(r['pid']))}. {traded(r, len(days) > 1)}</div></div>
<div class="lg">{logo(r['ticker'], 5600, 64, 180)}</div></div>""" for r in d["trades"])
    first, last = datetime.date.fromisoformat(days[0]), datetime.date.fromisoformat(days[-1])
    if len(days) == 1:
        post = d.get("post")
        if not post or (post - first).days == 1:
            kick = "Filed yesterday"
        elif (post - first).days < 7:
            kick = f"Filed {first:%A}"                 # a Monday's post: "Filed Friday"
        else:
            kick = f"Filed {day(days[0])}"
        when = ""
    else:
        kick, when = "Latest filings", f"Reported {day(days[0])} to {last.day if last.month == first.month else day(days[-1])}. "
    body = head("New trades", when + "Members get up to 45 days to report a trade.", kick) + f'<div class="tds">{rows}</div>'
    if d.get("real"):
        return slide(body, d["src"], stamp=("PROOF", "REAL FILINGS"))
    return slide(body, "From House and Senate periodic transaction reports.")


# ------------------------------------------------------------------ a real pull (pull_trades.py)
def short_range(low, high):
    """15001, 50000 -> '$15K to $50K'; 50000001, None -> 'Over $50M'."""
    def m(n):
        n = n - 1 if n % 1000 == 1 else n
        return f"${n / 1e6:g}M" if n >= 1e6 else f"${n / 1e3:g}K" if n >= 1e3 else f"${n}"
    return f"Over {m(low)}" if high is None else m(low) if low == high else f"{m(low)} to {m(high)}"


def company(n):
    """'Datadog, Inc. - Class A Common Stock (DDOG) [ST]' -> 'Datadog'; an account path keeps its last step."""
    n = re.split(r"⇒|>", n)[-1].strip()
    n = re.split(r" - |\(|\[", n)[0]
    n = re.sub(r"\b(Inc|Incorporated|Corporation|Corp|Co|Company|Holdings?|N\.V|PLC|plc|Ltd|Limited|S\.A|AG|SE|"
               r"Class [A-C]|Common Stock|Common Shares|Capital Stock|Ordinary Shares|(?:American )?Depositary Shares)\b\.?", "", n)
    n = re.sub(r"\s+Com\w*$", "", n.strip())        # a name cut short on the report: 'Hyliion Commo'
    return re.sub(r"[\s,]+$", "", re.sub(r"\s{2,}", " ", n)).strip()


FULL = {}                                              # a fund's full name, for where its symbol isn't enough


def bring_logo(ticker, asset, atlas):
    """A logo for the ticker from the atlas, if it has one, and a short company name either way."""
    hit = next((v for v in atlas.values() if v.get("kind") == "company"
                and ticker in {x for _, x in v.get("tickers") or []}), None)
    fund = re.search(r"\b(ETF|Fund|Trust|Index|Portfolio|SPDR|iShares|Vanguard|Invesco|ProShares|Direxion|WisdomTree|"
                     r"MiniShares|Global X|Select Sector)\b", re.split(r"⇒|>", asset or "")[-1] + " " + (hit or {}).get("name", ""))
    fund = fund and not (hit and any(f.split(".")[0] == hit["id"] for f in os.listdir(os.path.join(ATLAS, "img"))))
    NAMES.setdefault(ticker, (ticker if fund else company(hit["name"]) if hit else company(asset or "")) or ticker)
    FULL.setdefault(ticker, company(asset) if fund else NAMES[ticker])                                # ...and their name
    path = os.path.join(HERE, "logo", f"{ticker}.png")
    src = hit and next((f for f in os.listdir(os.path.join(ATLAS, "img")) if f.split(".")[0] == hit["id"]), None)
    if src and not os.path.exists(path):
        from PIL import Image
        Image.open(os.path.join(ATLAS, "img", src)).convert("RGBA").save(path)


def bring_photos(pids):
    """Each person's portrait from the atlas, cut out (tools/cutout.swift) and added to cut/faces.json."""
    import shutil, tempfile
    import headshots
    known = os.path.join(HERE, "cut", "faces.json")
    faces = json.load(open(known)) if os.path.exists(known) else []     # a fresh copy has none yet
    have = {r["file"][:-4] for r in faces if r.get("cut") and r.get("face")}
    new = [p for p in pids if p not in have and os.path.exists(os.path.join(ATLAS, "img", p + ".jpg"))]
    if not new:
        return
    os.makedirs(os.path.join(HERE, "cut"), exist_ok=True)
    tin, tout = tempfile.mkdtemp(), tempfile.mkdtemp()
    for p in new:
        shutil.copy(os.path.join(ATLAS, "img", p + ".jpg"), os.path.join(HERE, "img", p + ".jpg"))
        shutil.copy(os.path.join(ATLAS, "img", p + ".jpg"), os.path.join(tin, p + ".jpg"))
    subprocess.run(["swift", os.path.join(HERE, "tools", "cutout.swift"), tin, tout], check=True)
    rows = json.load(open(os.path.join(tout, "faces.json")))
    for r in rows:
        if r.get("cut") and r.get("face"):
            shutil.move(os.path.join(tout, r["file"][:-4] + ".png"), os.path.join(HERE, "cut", r["file"][:-4] + ".png"))
        else:
            print("no clean cut-out for", r["file"])
    faces = [r for r in faces if r["file"][:-4] not in new] + rows
    json.dump(faces, open(os.path.join(HERE, "cut", "faces.json"), "w"), indent=1)
    headshots._faces = None


def real_market(day, before):
    """The S&P 500's move, tracked with the SPY fund (IEX has funds, not the index), and its five-minute path."""
    import prices
    out = []
    for nm_, t in (("S&P 500", "SPY"),):
        p0, p1 = prices.price(t, before), prices.price(t, day)
        out.append({"name": nm_, "pct": round((p1 / p0 - 1) * 100, 2), "level": p1, "via": t})
    out[0]["points"] = prices.intraday("SPY", day)
    return out


def load_close(path):
    """Put a real day on the results slides (estimate.py): the winners, the Senate and House boards, the biggest
    losses, the party score and the stocks members own most. Says 'House' wherever the Senate isn't read yet."""
    global SRC_STOCK
    res = json.load(open(path))
    atlas = json.load(open(os.path.join(ATLAS, "registry.json")))["entities"]
    shown = {v.get("bioguide"): v.get("name") for v in atlas.values() if v.get("kind") == "member"}
    rows = {r["bioguide"]: r for r in res["rows"]}
    words = {"D": "Democrat", "R": "Republican", "I": "Independent"}

    def who(bio):
        r, pid = rows[bio], "m-" + bio.lower()
        PEOPLE[pid] = (re.sub(r"\s[A-Z]\.(?=\s)", "", shown.get(bio) or r["name"]), r.get("chamber", "House"),
                       words.get(r["party"], r["party"]), r["state"])
        return pid

    def tk(t):
        t = LOGO_ALIAS.get(t, t)
        bring_logo(t, res["names"].get(t, t), atlas)
        return t
    k = lambda dollars: round(dollars / 1000)          # the slides count in thousands
    up = [r for r in res["rows"] if r["change"] > 0]
    down = sorted((r for r in res["rows"] if r["change"] < 0), key=lambda r: r["change"])
    d = datetime.date.fromisoformat(res["day"])
    import prices
    post = d + datetime.timedelta(days=1)              # the results go out the next morning the market opens
    while not prices.open_day(post):
        post += datetime.timedelta(days=1)
    both = "Senate" in res["chambers"]
    up_in = lambda ch: [r for r in up if r.get("chamber", "House") == ch][:10]
    CLOSE.update(winners=[(who(r["bioguide"]), k(r["change"]), [tk(t) for t in r["moved"][:3]]) for r in up[:5]],
                 house=[(who(r["bioguide"]), k(r["change"]), tk(r["moved"][0])) for r in up_in("House")],
                 senate=[(who(r["bioguide"]), k(r["change"]), tk(r["moved"][0])) for r in up_in("Senate")],
                 losers=[(who(r["bioguide"]), k(r["change"]), tk(r["moved"][0])) for r in down[:5]],
                 party=[(p["party"], k(p["change"]), p["owners"], p["rose"], p["fell"],
                         [(who(b), k(c)) for b, c in p["lead"]]) for p in res["party"]],
                 movers=[(tk(m["ticker"]), m["pct"], m["members"]) for m in res["movers"]],
                 market=real_market(res["day"], res["before"]), owners="members" if both else "House members",
                 market_src="Prices: IEX, the last trade before 4 pm Eastern. S&P 500 via the SPY fund.",
                 where="in Congress" if both else "in the House",
                 who="every member who owns them" if both else "every House member who owns them",
                 day=f"{d:%A}", date=f"{d:%B} {d.day}", word=word_for(d, post))
    MAST.update(day=f"{post:%A}".upper(), date=f"{post:%B} {post.day} {post.year}".upper())
    STAMP[:] = ["PROOF", "REAL FILINGS"]
    SRC_STOCK = (f"Estimates: {'House and Senate' if both else 'House'} disclosures, middle of each range, "
                 "no options. Prices: IEX.")
    bring_photos(sorted({x[0] for key in ("winners", "house", "senate", "losers") for x in CLOSE[key]}
                        | {pid for p in CLOSE["party"] for pid, _ in p[5]}))
    return post


def load_trades(path):
    """Put a real pull on the New trades slide: the people, their portraits and the companies' logos come along."""
    pull = json.load(open(path))
    atlas = json.load(open(os.path.join(ATLAS, "registry.json")))["entities"]
    rows = []
    for p in pull["rows"]:
        pid = "m-" + p["bioguide"].lower()
        PEOPLE[pid] = (re.sub(r"\s[A-Z]\.(?=\s)", "", p["name"]), p["chamber"], p["party"], p["state"])
        t = p["trade"]
        tk = LOGO_ALIAS.get(t["ticker"], t["ticker"])
        bring_logo(tk, t["asset"], atlas)
        rows.append({"pid": pid, "owner": t["owner"], "type": t["type"], "ticker": tk, "kind": t["kind"],
                     "range": short_range(t["low"], t["high"]), "traded": t["date"], "filed": p["filed"], "more": p["more"]})
    bring_photos([r["pid"] for r in rows])
    import prices
    post = datetime.date.fromisoformat(pull["day"]) + datetime.timedelta(days=1)   # the next morning the market opens
    while not prices.open_day(post):
        post += datetime.timedelta(days=1)
    OPEN.update(trades=rows, real=True, post=post,
                src=f"From {' and '.join(pull['sources'])} periodic transaction reports.")
    MAST.update(day=f"{post:%A}".upper(), date=f"{post:%B} {post.day} {post.year}".upper())
    return post


def span(low, high):
    """A holding's reported range, added up over its lines and rounded: 45004, 234999 -> '$45K to $235K';
    5500002, 26000000 -> '$5.5M to $26M'. A partial sale can leave the low end at nothing: 'Up to $1M'."""
    def m(n):
        return f"${round(n / 1e6, 2):g}M" if n >= 999500 else f"${max(1, round(n / 1e3))}K"
    if high is None:
        return f"Over {m(low)}"
    return f"Up to {m(high)}" if low <= 0 else f"{m(low)} to {m(high)}"


def load_bell(path):
    """Put the morning's Before the bell on its slide (bell.py): the companies members own that put out results
    since the last close, the biggest holder beside each. Nothing in it: no slide (real_post leaves it off)."""
    b = json.load(open(path))
    atlas = json.load(open(os.path.join(ATLAS, "registry.json")))["entities"]
    shown = {v.get("bioguide"): v.get("name") for v in atlas.values() if v.get("kind") == "member"}
    words = {"D": "Democrat", "R": "Republican", "I": "Independent"}
    rows = []
    for r in b["earnings"]:
        t, top = LOGO_ALIAS.get(r["ticker"], r["ticker"]), r["top"]
        pid = "m-" + top["bioguide"].lower()
        PEOPLE[pid] = (re.sub(r"\s[A-Z]\.(?=\s)", "", shown.get(top["bioguide"]) or top["name"]), top["chamber"],
                       words.get(top["party"], top["party"]), top["state"])
        bring_logo(t, r["company"], atlas)
        rows.append((t, r["when"], r["owners"], pid, span(top["low"], top["high"])))
    bring_photos(sorted(p for p in {x[3] for x in rows} if os.path.exists(os.path.join(ATLAS, "img", p + ".jpg"))))
    import prices
    post = datetime.date.fromisoformat(b["post_day"])
    last = datetime.date.fromisoformat(str(prices.previous_open(post)))
    since = "yesterday" if (post - last).days == 1 else f"{last:%A}"
    OPEN.update(earnings=rows, hearings=[], bell=bool(rows),
                bell_dek=f"Companies Congress owns that reported since {since}{Q}s close",
                bell_src=f"Earnings: the companies{Q} own SEC filings. Holdings: House and Senate disclosures, "
                         "the ranges members reported.")


def morning_post(c, o):
    """The one post a day, 6:30 am our time: yesterday's results first, then the trades filed yesterday,
    then the market's close handing over to what to watch today. Nine slides, under Instagram's ten."""
    return [close_cover(c), close_party(c),
            board(c["senate"], "Senate", "Top 10 by estimated gain on stocks", kick=yday(c)),
            board(c["house"], "House", "Top 10 by estimated gain on stocks", kick=yday(c)),
            close_cabinet(c),
            board(c["losers"], "Biggest losses", "The members whose stocks fell the most",
                  "Estimated loss", True, "big", kick=yday(c)),
            open_trades(o), close_market(c), open_calendar(o)]


def real_post(c, o):
    """The post that goes out: every slide with real numbers, in the same order. Before the bell comes last on a
    morning a company members own reported since the close (bell.py); the White House waits for OGE reports."""
    return [close_cover(c), close_party(c),
            board(c["senate"], "Senate", "Top 10 by estimated gain on stocks", kick=yday(c)),
            board(c["house"], "House", "Top 10 by estimated gain on stocks", kick=yday(c)),
            board(c["losers"], "Biggest losses", "The members whose stocks fell the most",
                  "Estimated loss", True, "big", kick=yday(c)),
            open_trades(o), close_market(c)] + ([open_calendar(o)] if o.get("bell") else [])


CSS = """
*{margin:0;padding:0;box-sizing:border-box}
:root{--ink:#0b0b0b;--bone:#FFFFFF;--soft:#D0D0D0;--grey:#9B9B9B;--dim:#868686;--gain:#3CC68A;--red:#EB6A5E;
 --track:rgba(255,255,255,.10);--rule:rgba(255,255,255,.22)}
@font-face{font-family:"Newsreader";src:url(fonts/Newsreader-latin.woff2) format("woff2");font-weight:400 800;font-display:block}
body{background:#000;font-family:"Helvetica Neue",Helvetica,Arial,sans-serif;color:var(--bone)}
.s{width:1080px;height:1350px;position:relative;overflow:hidden;padding:0 72px;display:none;
 background:#141517 url(img/grain.png)}                 /* black and white */
.s.on{display:block}
.mast{display:flex;align-items:center;gap:22px;padding-top:84px;height:160px}
.lock{display:flex;flex-direction:column;font-weight:700;font-size:23px;letter-spacing:.32em;line-height:1.5}
.lock span:first-child{border-bottom:2px solid var(--bone)}
.when,.mock{display:flex;flex-direction:column;font-size:22px;letter-spacing:.12em;line-height:1.5}
.when{border-left:2px solid #777;padding-left:20px}
.mock{margin-left:auto;text-align:right;font-size:17px;color:var(--soft)}
.handle{position:absolute;right:72px;bottom:52px;font-size:17px;color:var(--dim);letter-spacing:.02em}
.dim{color:#a8a59d} .mock .dim{color:var(--dim)}
.up{color:var(--gain)} .dn{color:var(--red)} .flat{color:var(--grey)}
.hs{display:block}
.nm{font-weight:700;letter-spacing:-.005em}
.meta{font-size:17px;color:var(--soft)}
@font-face{font-family:"Libre Franklin";src:url(fonts/LibreFranklin-latin.woff2) format("woff2");font-weight:400 800;font-display:block}
.sec,.cover h1,.pn{font-family:"Newsreader",Georgia,serif}
.fig,.val,.tm,.rk,.rl{font-family:"Libre Franklin","Helvetica Neue",sans-serif;font-weight:700;
 font-variant-numeric:lining-nums tabular-nums;line-height:.95;white-space:nowrap;letter-spacing:-.02em}
.kick2{font-size:19px;font-weight:700;letter-spacing:.16em;text-transform:uppercase;color:var(--soft);margin-top:40px}
.kick2 + .sec{margin-top:12px}
.val{text-align:right;font-size:32px}
.words{font-size:17px;color:var(--grey);font-weight:500;white-space:nowrap}
.wordmark{display:inline-block;max-width:100%;font-size:27px;font-weight:700;line-height:1.08;letter-spacing:-.01em;text-align:right}
.tr .wordmark{font-size:17px} .ru .wordmark{font-size:19px}
.logos{display:flex;align-items:center;gap:28px}
.lg{display:flex;justify-content:flex-end;align-items:center}
.lz{display:flex;align-items:center}
.src{position:absolute;left:72px;right:300px;bottom:52px;font-size:16px;line-height:1.35;color:var(--dim)}
.sec{font-size:72px;font-weight:600;letter-spacing:-.015em;line-height:1;margin-top:40px}
.dek{font-size:25px;color:var(--soft);margin-top:12px}
.rk{text-align:right;font-size:24px;color:var(--grey)}
.colh{font-size:15px;color:var(--grey);font-weight:500}
.h2row{display:flex;justify-content:space-between;align-items:baseline;margin-top:42px;padding-bottom:10px;border-bottom:1px solid var(--rule)}
.h2{font-size:30px;font-weight:700}
/* ranked tables */
.tbl{margin-top:30px}
.th,.tr{display:grid;grid-template-columns:34px 64px 1fr 150px 112px;column-gap:18px;align-items:center}
.th{height:34px;border-bottom:1px solid var(--rule);font-size:15px;color:var(--grey);font-weight:500;margin-bottom:4px}
.th .c-g{grid-column:4;text-align:right} .th .c-l{grid-column:5;text-align:right}
.tr{height:84px;grid-template-rows:auto auto;align-content:center}
.tr .rk,.tr .hs,.tr .lg{grid-row:1/3}
.tr .who{grid-column:3;grid-row:1} .tr .val{grid-column:4;grid-row:1} .tr .lg{grid-column:5}
.tr .nm{font-size:27px;line-height:1.1;white-space:nowrap}
.tr .meta{margin-top:4px;white-space:nowrap}
.trk{grid-column:3/5;grid-row:2;height:6px;margin-top:9px;background:var(--track)}
.trk i{display:block;height:100%}
.trk.up i,.trk.dn i{background:rgba(255,255,255,.4)}
.tbl.big .th,.tbl.big .tr{grid-template-columns:34px 104px 1fr 190px 112px}
.tbl.big .tr{height:138px}
.tbl.big .nm{font-size:31px} .tbl.big .meta{font-size:19px;margin-top:6px}
.tbl.big .val{font-size:40px} .tbl.big .trk{height:8px;margin-top:16px} .tbl.big .rk{font-size:28px}
/* covers */
.cover h1{font-size:56px;font-weight:600;line-height:1.06;letter-spacing:-.01em;margin-top:34px}
.cover > .dek{font-size:24px}
.hero{display:flex;gap:36px;margin-top:32px;height:420px}
.hc{display:flex;flex-direction:column;flex:1;min-width:0}
.kick{font-size:19px;font-weight:700;color:var(--grey)}
.hero .nm{font-size:54px;line-height:1.02;margin-top:10px}
.hero .meta{font-size:22px;margin-top:12px}
.hero .fig{font-size:100px;margin-top:auto}
.lab{font-size:16px;color:var(--grey);margin-top:22px}
.hero .logos{margin-top:12px;height:46px}
.runs{margin-top:22px;display:flex;flex-direction:column;gap:8px}
.ru{display:grid;grid-template-columns:30px 82px 1fr auto 150px;column-gap:22px;align-items:center;height:96px}
.ru .rk{font-size:28px}
.ru .nm{font-size:30px;white-space:nowrap}
.ru .meta{font-size:18px;margin-top:6px}
.ru .val{font-size:42px}
.ru .logos{gap:20px}
/* the close chart */
.rds{display:grid;grid-template-columns:1.6fr 1fr 1fr;column-gap:24px;align-items:end;margin-top:30px}
.rn{font-size:17px;font-weight:700;color:var(--soft)}
.rl{font-size:32px;line-height:1;margin-top:8px}
.rc{font-size:18px;font-weight:500;color:var(--grey);margin-top:8px}
.rd.lead .rl{font-size:46px} .rd.lead .rc{font-size:20px}
.chart{display:block;margin-top:26px;overflow:visible}
.chart .grid{stroke:rgba(255,255,255,.10);stroke-width:1}
.chart .zero{stroke:rgba(255,255,255,.4);stroke-width:1.5}
.chart .tick{fill:var(--dim);font-size:15px}
.chart .area{fill:none}
.chart .ln{fill:none;stroke:var(--bone);stroke-width:2.5;stroke-linejoin:round;stroke-linecap:round}
.mo{display:grid;grid-template-columns:200px 1fr 150px;column-gap:24px;align-items:center;height:84px}
.mo .nm{font-size:28px} .mo .meta{margin-top:5px}
.tkr{color:var(--grey);margin-left:12px;letter-spacing:.06em}
.mo .val{font-size:38px}
/* white house */
.cabs{display:grid;grid-template-columns:repeat(3,1fr);gap:26px 28px;margin-top:34px}
.cab .meta{margin-top:14px}
.cab .nm{font-size:27px;margin-top:4px}
.cf{display:flex;justify-content:space-between;align-items:flex-end;margin-top:12px}
.cab .fig{font-size:36px}
/* new trades */
.tds{margin-top:30px}
.td{display:grid;grid-template-columns:84px 1fr 180px;column-gap:26px;align-items:center;height:146px}
.td .nm{font-size:30px}
.act{font-size:22px;margin-top:8px}
.act b{font-weight:700}
.td .meta{margin-top:6px;font-size:18px;color:var(--grey)}
.late{color:var(--red);font-weight:700}
.more{color:var(--grey);font-size:19px;margin-left:6px}
.pts{margin-top:44px}
.pt{padding:44px 0 50px;border-top:1px solid var(--rule)}
.pr{display:flex;justify-content:space-between;align-items:baseline}
.pn{font-size:48px;font-weight:600;letter-spacing:-.01em}
.pr .fig{font-size:86px}
.pt .trk{height:12px;margin-top:18px}
.ps{font-size:22px;color:var(--soft);margin-top:22px}
.pl{display:grid;grid-template-columns:repeat(3,1fr);column-gap:24px;margin-top:30px}
.pc{display:flex;align-items:center;gap:16px}
.pc .nm2{font-size:21px;white-space:nowrap} .pc .val{font-size:30px;margin-top:8px;text-align:left}
/* before the bell */
.er{display:grid;grid-template-columns:200px 1fr 300px;column-gap:24px;align-items:center;height:136px}
.solo .er{height:150px}                    /* earnings alone: the rows fill the slide */
.er .meta{font-size:20px} .er .nm{font-size:33px;margin-top:8px}
.hl{display:flex;align-items:center;gap:16px}
.nm2{font-size:22px;font-weight:700} .hl .meta{font-size:18px;margin-top:5px}
.hr{display:grid;grid-template-columns:120px 1fr auto 130px;column-gap:24px;align-items:center;height:150px}
.tm{font-size:40px}
.hr .nm{font-size:30px;line-height:1.1} .hr .meta{font-size:20px;margin-top:8px}
.busts{display:flex;gap:8px}
.bust{width:78px;display:flex;flex-direction:column;align-items:center}
.bust span{font-size:14px;color:var(--soft);margin-top:7px;white-space:nowrap}
"""


def build(make=None, name="Morning"):
    global RATIO
    RATIO = prep_logos()
    posts = [(name, (make or morning_post)(CLOSE, OPEN))]
    posts = [(post, [x.replace("§PAGE§", f"{i} / {len(ss)}") for i, x in enumerate(ss, 1)]) for post, ss in posts]
    slides = [s for _, ss in posts for s in ss]
    js = "var n=+(location.hash.slice(1)||1);document.querySelectorAll('.s')[n-1].classList.add('on')"
    page = f"""<!doctype html><html><head><meta charset="utf-8"><title>Congress Scorecard</title>
<style>{CSS}</style></head><body>{''.join(slides)}<script>{js}</script></body></html>"""
    path = os.path.join(HERE, "cards.html")
    open(path, "w").write(page)
    names = [(post, i + 1) for post, ss in posts for i in range(len(ss))]
    return path, names


def render(path, names, only=None):
    for n, (post, i) in enumerate(names, 1):
        if only and f"{post}/{i}" not in only:
            continue
        png = os.path.join(HERE, f"slide{n}.png")
        for _ in range(3):                              # on a busy Mac Chrome can hang for good: kill it and go again
            if os.path.exists(png):
                os.remove(png)
            try:
                subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                                "--force-device-scale-factor=1", "--window-size=1080,1350",
                                "--virtual-time-budget=3000", f"--screenshot={png}",
                                f"file://{path}#{n}"], check=False, capture_output=True, timeout=60)
            except subprocess.TimeoutExpired:
                pass
            if os.path.exists(png) and os.path.getsize(png) > 0:
                break
        if not os.path.exists(png):
            sys.exit(f"Chrome made no picture for slide {n}")
        os.makedirs(os.path.join(OUT, post), exist_ok=True)
        jpg = os.path.join(OUT, post, f"Slide {i}.jpg")
        subprocess.run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", "92", png, "--out", jpg],
                       check=True, capture_output=True)


def caption(c, post):
    """The post's words (Instagram and Facebook alike): the top three, the party score, how it's worked out,
    and IEX's credit, which its terms ask for word for word."""
    import prices
    amount = lambda k: f"${abs(k) / 1000:.2f}M" if abs(k) >= 1000 else f"${abs(k)}K"     # no signs or dashes
    top = "\n".join(f"{i}. {PEOPLE[pid][0]}, up {amount(k)}" for i, (pid, k, _) in enumerate(c["winners"][:3], 1))
    party = ", ".join(f"{p[0]} {'made' if p[1] >= 0 else 'lost'} {amount(p[1])}"
                      for p in sorted(c["party"], key=lambda p: -p[1]))
    day_word = c.get("word", "Yesterday")
    when = "yesterday" if day_word == "Yesterday" else f"on {day_word}"
    swipe = ("the new trades they filed, the S&P 500 and the earnings out before the bell" if OPEN.get("bell")
             else "the new trades they filed and the S&P 500")
    return (f"Who in Congress made the most in the market {when}?\n\n{top}\n\nParty score: {party}.\n\n"
            f"Swipe for the Senate, the House, the biggest losses, {swipe}.\n\n"
            "All figures are estimates. Members report their stocks in value ranges, so each holding is taken at "
            "the middle of its range, plus the trades they reported this year, times the stock's move that day. "
            "Options are not counted.\n\n"
            f"Sources: House and Senate financial disclosures{', SEC filings' if OPEN.get('bell') else ''}. "
            f"{prices.CREDIT}\n\n"
            "#Congress #StockMarket")


if __name__ == "__main__":
    if "--post" in sys.argv:                           # the real post, as it goes out
        i = sys.argv.index("--post")
        post = load_close(sys.argv[i + 1])
        load_trades(sys.argv[i + 2])
        if "--bell" in sys.argv:                       # Before the bell (bell.py), when the SEC could be read
            load_bell(sys.argv[sys.argv.index("--bell") + 1])
        folder = f"{post:%m.%d %A}"
        OUT = os.path.abspath(sys.argv[sys.argv.index("--out") + 1]) if "--out" in sys.argv else \
            os.path.join(HERE, "out", "Daily Posts")         # --out: a proof, beside the real ones
        p, names = build(real_post, folder)
        if "--no-render" not in sys.argv:
            render(p, names)
        words = caption(CLOSE, post)
        with open(os.path.join(OUT, folder, "caption.txt"), "w") as f:
            f.write(words + "\n")
        top = CLOSE["winners"][0]
        with open(os.path.join(OUT, folder, "post.json"), "w") as f:
            json.dump({"post_day": post.isoformat(), "about": json.load(open(sys.argv[i + 1]))["day"],
                       "slides": [f"Slide {n}.jpg" for _, n in names], "caption": words,
                       "lead": f"{PEOPLE[top[0]][0]} +${top[1]}K" if top[1] < 1000 else
                               f"{PEOPLE[top[0]][0]} +${top[1] / 1000:.2f}M",
                       "built_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds")}, f, indent=1)
        print("built", len(names), "slides into", os.path.join(OUT, folder))
        sys.exit(0)
    only = []                                          # a real day renders only the slides it has real numbers for
    if "--close" in sys.argv:                          # winners, party score, Senate, House, losses, the close
        post = load_close(sys.argv[sys.argv.index("--close") + 1])
        OUT = os.path.join(OUT, f"Real Proof {post:%m.%d}")
        only += ["Morning/1", "Morning/2", "Morning/3", "Morning/4", "Morning/6", "Morning/8"]
    if "--trades" in sys.argv:                         # the new trades
        post = load_trades(sys.argv[sys.argv.index("--trades") + 1])
        OUT = os.path.join(HERE, "out", f"Real Proof {post:%m.%d}")
        only += ["Morning/7"]
    if "--out" in sys.argv:
        OUT = os.path.abspath(sys.argv[sys.argv.index("--out") + 1])
    if "--only" in sys.argv:
        only = sys.argv[sys.argv.index("--only") + 1].split(",")
    p, names = build()
    if "--no-render" not in sys.argv:
        render(p, names, only or None)
    print("built", len(names), "slides")
