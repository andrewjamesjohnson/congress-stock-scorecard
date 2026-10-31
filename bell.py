"""Before the bell: the companies Congress owns that put out their results since the last close, for the morning
post's last slide. (Hearings join once there is a congress.gov key: see REAL NUMBERS PLAN.txt.)

Where it comes from, all of it public and free to post:
  the SEC (its records are the public's)   every 8-K with Item 2.02, "Results of Operations and Financial
                                           Condition" (the filing that goes with an earnings release), taken by the
                                           SEC from 4 pm Eastern on the last market day to 9:30 am Eastern today.
                                           EDGAR's full-text search finds those days' 8-Ks with their items and
                                           tickers; each company's own filing list (data.sec.gov) gives the minute
                                           the SEC took it (in UTC: Apple's 4:30 pm releases read 20:30Z).
  House and Senate disclosures             who owns each one the evening of the last market day (the estimate's own
                                           positions), and the biggest holder with the range they reported.

    python3 -I bell.py --day 2026-10-30      writes data/bell-2026-10-30.json (the post day)
"""
import datetime, json, os, re, sys, time, urllib.error, urllib.request
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import estimate, prices  # noqa: E402

DATA = os.path.join(HERE, "data")
ET = ZoneInfo("America/New_York")
FTS = "https://efts.sec.gov/LATEST/search-index?forms=8-K&dateRange=custom&startdt={}&enddt={}&from={}"
SUBS = "https://data.sec.gov/submissions/CIK{:010d}.json"
CONTACT = os.path.expanduser("~/.config/congress-scorecard/sec.json")    # {"contact": "<email>"}: the SEC asks for one
GAP = 0.25                     # seconds between SEC calls (its limit is 10 a second)
SHOW = 5                       # rows on the slide
MIN_OWNERS = 2                 # a company fewer members own than this is left off
CHECK = 60                     # at most this many companies' filing lists read in a morning
BUDGET = 240                   # seconds for the whole read: a slow SEC leaves the slide off, never holds the post
_until = [None]
NAMES = re.compile(r"\(([A-Z0-9][A-Z0-9.\-/]*(?:,\s*[A-Z0-9][A-Z0-9.\-/]*)*)\)\s*\(CIK (\d{10})\)")


def agent():
    """Who runs this, as the SEC's fair access rules ask every program to say."""
    try:
        c = json.load(open(CONTACT)).get("contact", "")
    except (OSError, ValueError):
        c = ""
    return f"Congress Scorecard {c}" if c else "Congress Scorecard (github.com/andrewjamesjohnson/congress-stock-scorecard)"


def get(url):
    if _until[0] is None:
        _until[0] = time.monotonic() + BUDGET
    req = urllib.request.Request(url, headers={"User-Agent": agent()})
    for i in range(3):
        if time.monotonic() > _until[0]:
            raise TimeoutError(f"the SEC took more than {BUDGET} s")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as ex:
            if ex.code not in (429, 500, 502, 503, 504) or i == 2:
                raise
            time.sleep(10 * (i + 1))
        finally:
            time.sleep(GAP)


def norm(t):
    """'BRK-B', 'BRK/B' and 'BRK.B' are one ticker."""
    return t.strip().upper().replace("-", ".").replace("/", ".")


def window(post_day):
    """(the last market day, 4 pm Eastern on it, 9:30 am Eastern on the post day)."""
    last = datetime.date.fromisoformat(str(prices.previous_open(post_day)))
    return (last, datetime.datetime.combine(last, datetime.time(16, 0), ET),
            datetime.datetime.combine(post_day, datetime.time(9, 30), ET))


def results_filed(first, last_day):
    """Every 8-K with Item 2.02 EDGAR dates from `first` to `last_day` (one per filing, the first filer with a
    ticker): [{"cik", "tickers", "name", "adsh"}]."""
    out, seen, at = [], set(), 0
    while True:
        d = get(FTS.format(first, last_day, at))
        hits = d["hits"]["hits"]
        for h in hits:
            s = h["_source"]
            if "2.02" not in (s.get("items") or []) or s.get("adsh") in seen:
                continue
            seen.add(s["adsh"])
            for dn in s.get("display_names") or []:
                m = NAMES.search(dn)
                if m:
                    out.append({"cik": int(m.group(2)), "tickers": [norm(x) for x in m.group(1).split(",")],
                                "name": dn[:m.start()].strip(), "adsh": s["adsh"]})
                    break
        at += len(hits)
        if not hits or at >= d["hits"]["total"]["value"]:
            return out


def accepted(cik, adsh):
    """The moment the SEC took that filing, in Eastern time (None when its list doesn't have it)."""
    r = get(SUBS.format(cik))["filings"]["recent"]
    for a, t in zip(r["accessionNumber"], r["acceptanceDateTime"]):
        if a == adsh:
            return datetime.datetime.fromisoformat(t.replace("Z", "+00:00")).astimezone(ET)
    return None


def when(at, last, post_day):
    """The words over a row: when the results came out, against the post day."""
    if at.date() == post_day:
        return "This morning, before the open"
    if at.date() == last:
        return "Last night, after the close" if (post_day - last).days == 1 else f"{last:%A}, after the close"
    return "Over the weekend" if at.weekday() >= 5 else f"On {at:%A}"


def holdings(member, upto):
    """{ticker: (dollars, low, high)} the evening of `upto`: the estimate's middle of each range (estimate.positions,
    the same rules), with the reported range carried beside it (a partial sale widens it: it could have been any
    part). high None = 'Over $50M'."""
    pos = {}
    for a in member["held"]:
        k = (norm(a["ticker"]), a["owner"])
        mid, lo, hi = pos.get(k, (0.0, 0, 0))
        pos[k] = (mid + estimate.mid(a["low"], a["high"]), lo + a["low"],
                  None if hi is None or a["high"] is None else hi + a["high"])
    for t in sorted(member["trades"], key=lambda t: t["date"]):
        if t["date"] > upto:
            break
        k = (norm(t["ticker"]), t["owner"])
        mid, lo, hi = pos.get(k, (0.0, 0, 0))
        if t["type"] == "P":
            pos[k] = (mid + estimate.mid(t["low"], t["high"]), lo + t["low"],
                      None if hi is None or t["high"] is None else hi + t["high"])
        elif t["type"] == "S":
            pos[k] = (0.0, 0, 0)
        elif t["type"] == "S (partial)":
            pos[k] = (max(0.0, mid - estimate.mid(t["low"], t["high"])), max(0, lo - (t["high"] or lo)),
                      None if hi is None else max(0, hi - t["low"]))
    out = {}
    for (tk, _), (mid, lo, hi) in pos.items():
        if mid > 0:
            m0, l0, h0 = out.get(tk, (0.0, 0, 0))
            out[tk] = (m0 + mid, l0 + lo, None if h0 is None or hi is None else h0 + hi)
    return out


def members():
    got = dict(json.load(open(os.path.join(DATA, "house-holdings.json")))["members"])
    sen = os.path.join(DATA, "senate-holdings.json")
    if os.path.exists(sen):
        got.update(json.load(open(sen)))
    return got


def owners_of(everyone, upto):
    """{ticker: [(dollars, low, high, bioguide)]}, biggest first."""
    by = {}
    for bio, m in everyone.items():
        for tk, (mid, lo, hi) in holdings(m, upto).items():
            by.setdefault(tk, []).append((mid, lo, hi, bio))
    for rows in by.values():
        rows.sort(key=lambda r: -r[0])
    return by


def earnings(post_day, now=None):
    """The companies members own that put out results between the last close and the bell: biggest following
    first. Also returns how many filings were looked at, for the log."""
    last, start, end = window(post_day)
    end = min(end, (now or datetime.datetime.now(ET)).astimezone(ET))
    everyone = members()
    own = owners_of(everyone, str(last))
    seen, cands = set(), []
    for f in results_filed(last, post_day):
        if f["cik"] in seen:
            continue
        seen.add(f["cik"])
        mine = {}                                    # one member who owns two share classes counts once
        for tk in f["tickers"]:
            for mid, lo, hi, bio in own.get(tk, []):
                m0, l0, h0 = mine.get(bio, (0.0, 0, 0))
                mine[bio] = (m0 + mid, l0 + lo, None if h0 is None or hi is None else h0 + hi)
        if len(mine) >= MIN_OWNERS:
            cands.append((f, mine))
    cands.sort(key=lambda c: (-len(c[1]), -sum(v[0] for v in c[1].values())))
    rows = []
    for f, mine in cands[:CHECK]:
        try:
            at = accepted(f["cik"], f["adsh"])
        except TimeoutError:
            break                                    # out of time: the rows found so far
        if at is None:
            continue
        if not start <= at <= end:
            continue
        bio, (mid, lo, hi) = max(mine.items(), key=lambda kv: kv[1][0])
        m = everyone[bio]
        held = [t for t in f["tickers"] if t in own]
        rows.append({"ticker": max(held, key=lambda t: len(own[t])), "tickers": f["tickers"], "company": f["name"],
                     "cik": f["cik"], "adsh": f["adsh"], "accepted": at.isoformat(timespec="seconds"),
                     "when": when(at, last, post_day), "owners": len(mine), "value": round(sum(v[0] for v in mine.values())),
                     "top": {"bioguide": bio, "name": m["name"], "chamber": m.get("chamber", "House"),
                             "party": m["party"], "state": m["state"], "low": lo, "high": hi, "value": round(mid)}})
        if len(rows) == SHOW:
            break
    return rows, {"window": [start.isoformat(), end.isoformat()], "filings": len(seen), "owned": len(cands)}


if __name__ == "__main__":
    post_day = datetime.date.fromisoformat(sys.argv[sys.argv.index("--day") + 1]) if "--day" in sys.argv \
        else datetime.date.today()
    rows, info = earnings(post_day)
    res = {"post_day": str(post_day), "made": datetime.datetime.now(ET).isoformat(timespec="seconds"),
           "earnings": rows, "hearings": [], "hearings_note": "hearings wait for a congress.gov key",
           "sources": "SEC EDGAR (8-K Item 2.02); House and Senate financial disclosures", **info}
    path = os.path.join(DATA, f"bell-{post_day}.json")
    with open(path + ".part", "w") as f:
        json.dump(res, f, indent=1)
    os.replace(path + ".part", path)
    print(f"{post_day}: {info['filings']} companies filed results dated {info['window'][0][:10]} to {post_day}, "
          f"{info['owned']} owned by {MIN_OWNERS}+ members, {len(rows)} on the slide (since the close, by the minute)")
    for r in rows:
        t = r["top"]
        print(f"  {r['ticker']:<6} {r['when']:<32} owned by {r['owners']:>3}  top: {t['name']} "
              f"(${t['low']:,} to {'over' if t['high'] is None else '$' + format(t['high'], ',')})  {r['accepted'][11:16]} ET")
