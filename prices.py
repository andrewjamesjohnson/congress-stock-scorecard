"""Prices for the scorecard, from IEX's free historical data (HIST): each trading day's TOPS file, read once with
tools/iextops (every symbol's last regular-session trade, and SPY's five-minute marks), cached in data/iex/<day>.json.

Why IEX: its terms let us post what we make from it, with this credit (CREDIT below, in every caption):
"Data provided for free by IEX. By accessing or using IEX Historical Data, you agree to the IEX Historical Data
Terms of Use." (https://www.iex.io/legal/hist-data-terms). Massive's free plan forbids any public post made from its
data (its Market Data Terms, 5(c): "Derived Works" may not go to any third party), so it is not used any more
(the old reader is in _old/prices_massive.py; Andrew's key is left where it was).

IEX's prices are the trades on IEX itself. The last one before 4 pm sits within cents of the official close for the
big stocks members own; a symbol with no IEX trade that day has no price (left out, as before). A day's file is
out by about 6 am Eastern the next morning, 10 to 15 GB compressed: the reader streams it (nothing is kept on
disk) and stops at 4 pm Eastern, a few minutes on this Mac.

    python3 -I prices.py 2026-10-27 2026-10-28      fetch and cache those days
"""
import datetime, fcntl, json, os, subprocess, sys, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "data", "iex")
TOOL = os.path.join(HERE, "tools", "iextops")
HIST = "https://iextrading.com/api/1.0/hist?date={}"
RATE = os.environ.get("SCORECARD_IEX_RATE", "30M")     # curl's --limit-rate: leaves room for the clip factory
WATCH = ("SPY",)
CREDIT = ("Data provided for free by IEX. By accessing or using IEX Historical Data, you agree to the IEX "
          "Historical Data Terms of Use. https://www.iex.io/legal/hist-data-terms")
SOURCE = "Prices: IEX"

# NYSE full-day holidays (the market's own calendar; check it each December)
HOLIDAYS = {"2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25", "2026-06-19", "2026-07-03",
            "2026-09-07", "2026-11-26", "2026-12-25",
            "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31", "2027-06-18", "2027-07-05",
            "2027-09-06", "2027-11-25", "2027-12-24"}
_mem = {}


def open_day(date):
    """True when the US stock market is open that day (a weekday that is not a holiday)."""
    d = datetime.date.fromisoformat(str(date)[:10])
    return d.weekday() < 5 and d.isoformat() not in HOLIDAYS


def previous_open(date):
    """The last open day before `date`."""
    d = datetime.date.fromisoformat(str(date)[:10]) - datetime.timedelta(days=1)
    while not open_day(d):
        d -= datetime.timedelta(days=1)
    return d.isoformat()


def link(date):
    """The day's TOPS file on IEX's storage, or None when IEX has none (market shut, or not out yet)."""
    url = HIST.format(date.replace("-", ""))
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=60) as r:
            rows = json.load(r)
    except urllib.error.HTTPError as ex:
        if ex.code == 404:
            return None
        raise
    tops = [x for x in rows or [] if x.get("feed") == "TOPS"]
    return max(tops, key=lambda x: x.get("version", ""))["link"] if tops else None


def fetch(date, quiet=False):
    """Read the day's TOPS file once (curl | gzip | iextops) into data/iex/<date>.json. False when it is not out."""
    path = os.path.join(CACHE, f"{date}.json")
    if os.path.exists(path):
        return True
    os.makedirs(CACHE, exist_ok=True)
    lock = open(path + ".lock", "w")
    try:                                         # one reader per day: a second one (the timer, a hand run) waits out
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        lock.close()
        return False
    try:
        return _fetch(date, path, quiet)
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()


def _fetch(date, path, quiet):
    if os.path.exists(path):
        return True
    url = link(date)
    if not url:
        return False
    part = path + ".part"
    t0 = datetime.datetime.now()
    os.makedirs(os.path.join(HERE, "logs"), exist_ok=True)
    # A stall ends the try (10-30: the 04:30 download crawled for 3 h 44 min, then broke): under 300 KB/s for
    # 4 minutes, or 50 minutes in all. A good day takes about 7 to 15 minutes.
    with open(part, "w") as out, open(os.path.join(HERE, "logs", f"iex-{date}.log"), "a") as err:
        err.write(f"{t0:%Y-%m-%d %H:%M:%S} start\n")
        err.flush()
        curl = subprocess.Popen(["curl", "-sS", "--fail", "-L", "--limit-rate", RATE, "--retry", "2",
                                 "--connect-timeout", "30", "--speed-limit", "300000", "--speed-time", "240",
                                 "--max-time", "3000", url], stdout=subprocess.PIPE, stderr=err)
        gz = subprocess.Popen(["/usr/bin/gzip", "-dc"], stdin=curl.stdout, stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL)
        curl.stdout.close()
        tops = subprocess.Popen([TOOL, *WATCH], stdin=gz.stdout, stdout=out)
        gz.stdout.close()
        tops.wait()
        for p in (gz, curl):                     # the reader stops at 4 pm: the download stops with it
            if p.poll() is None:
                p.terminate()
            p.wait()
        err.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} end: curl {curl.returncode}, reader {tops.returncode}\n")
    with open(part) as f:
        got = json.load(f)
    if not got.get("complete"):
        os.remove(part)
        raise RuntimeError(f"IEX {date}: the file ended before 4 pm (a broken download); nothing kept")
    os.replace(part, path)
    if not quiet:
        secs = (datetime.datetime.now() - t0).seconds
        print(f"IEX {date}: {len(got['symbols'])} symbols in {secs // 60} min {secs % 60} s", flush=True)
    return True


def _load(date):
    if date not in _mem:
        path = os.path.join(CACHE, f"{date}.json")
        if not os.path.exists(path) and not fetch(date):
            return None
        with open(path) as f:
            _mem[date] = json.load(f)
    return _mem[date]


THIN_VOLUME = 500                  # fewer IEX shares than this in the day = no price (a thin print, checked 10-28)
STALE_MIN = 30                     # its last IEX trade more than this long before 4 pm = no price (a stale one)


def day(date):
    """{symbol: last regular-session price} for one day; {} when the market was shut or the file isn't out yet.
    A symbol IEX barely traded, or not in the last half hour, gets none: on 10-28 such prints were up to 5.7 points
    off the official move, the rest 0.04 points (value-weighted) and 1.4 at the most."""
    got = _load(date) if open_day(date) else None
    if not got:
        return {}
    cut = got["close_ns"] - STALE_MIN * 60e9
    return {s: v[0] for s, v in got["symbols"].items() if v[0] and v[6] >= THIN_VOLUME and v[1] >= cut}


def trading(date, back=True):
    """The day itself if the market was open (and IEX's file is out), else the nearest such day before it."""
    d = datetime.date.fromisoformat(str(date)[:10])
    for _ in range(10):
        if open_day(d) and day(d.isoformat()):
            return d.isoformat()
        d -= datetime.timedelta(days=1)
    return None


RENAMED = {"SQ": "XYZ", "FB": "META", "ANTM": "ELV", "RTN": "RTX", "PEAK": "DOC"}   # old symbols still on reports
MOVES_WITH = {"BRK.A": "BRK.B", "BRK/A": "BRK.B", "BRK-A": "BRK.B"}   # barely trades on IEX; the B shares move with it


def price(ticker, date):
    """The last regular-session IEX price for a ticker that day; None if it did not trade on IEX."""
    closes = day(date)
    ticker = MOVES_WITH.get(ticker, RENAMED.get(ticker, ticker))   # only the day's move is used, never the level
    for t in (ticker, ticker.replace("-", "."), ticker.replace("/", "."), ticker.replace(".", "")):
        if t in closes:
            return closes[t]
    return None


def intraday(ticker, date):
    """[(minutes after 9:30 Eastern, price)] in five-minute steps through the regular session (SPY only)."""
    got = _load(date)
    return [(int(m), p) for m, p in (got or {}).get("marks", {}).get(ticker, [])]


if __name__ == "__main__":
    for d in sys.argv[1:]:
        if not fetch(d):
            print(f"IEX {d}: no file (market shut, or not out yet)")
