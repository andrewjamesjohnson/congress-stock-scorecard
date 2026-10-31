"""Each member's estimated gain or loss on one trading day, from what they hold (pull_holdings.py) and IEX's
prices (prices.py). Every number here is an ESTIMATE: holdings are reported as ranges, so each is taken at
the middle of its range (the low end when the range is open, like 'Over $1,000,000').

The method, for one member:
  1. Year-end positions: each stock or ETF on the yearly report, by owner (self, spouse, joint, child),
     at the middle of its range on December 31.
  2. The trades they reported this year, in date order: a buy adds the middle of its range, a partial
     sale takes it off (never below zero), a full sale ends that owner's position.
  3. The day's gain: every position, times its stock's move that day (the last IEX trade before 4 pm
     against the day before's).
Positions are NOT grown with prices since December 31. IEX's prices are not adjusted for splits, and many
funds members hold split in 2026 (VO, VUG, VGT, IWF, VOOG, BKNG, KLAC...: checked 10-29 against IEX's Dec 31
file), so a Dec 31 ratio is off by 2 to 30 times for them, and splits within 1/4 to 4 can't be told from real
moves. The old method grew everything with Massive's split-adjusted prices, which we may not post from
(_old/estimate_rolled.py). So the estimate is "the middle of each range", exactly as the slides say.

A move that looks like a split (exactly 1/2, 1/3, 2x, 10x...) or over 60 % is left out that day: it is
listed under "skipped" in the output, never put on a named person.
"""
import collections, datetime, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # our own code only; downloads live under data/

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")


def mid(low, high):
    return low if high is None else (low + high) / 2


SPLITS = (1 / 2, 1 / 3, 2 / 3, 1 / 4, 1 / 5, 1 / 8, 1 / 10, 1 / 15, 1 / 20, 1 / 25, 1 / 50, 3 / 2, 2, 3, 4, 5,
          8, 10, 15, 20, 25, 50)
skipped = {}


def suspect(p0, p1):
    """True when a day's move looks like a split or a bad print rather than a real move."""
    r = p1 / p0
    return abs(r - 1) > 0.6 or any(abs(r / s - 1) < 0.015 for s in SPLITS)


def positions(member, upto):
    """{(ticker, owner): dollars} the evening of `upto`: the middle of each reported range, no price growth."""
    pos = collections.defaultdict(float)
    for a in member["held"]:
        pos[(a["ticker"], a["owner"])] += mid(a["low"], a["high"])
    for t in sorted(member["trades"], key=lambda t: t["date"]):
        if t["date"] > upto:
            break
        key = (t["ticker"], t["owner"])
        amount = mid(t["low"], t["high"])
        if t["type"] == "P":
            pos[key] += amount
        elif t["type"] == "S":
            pos[key] = 0.0
        elif t["type"] == "S (partial)":
            pos[key] = max(0.0, pos[key] - amount)
    return {k: v for k, v in pos.items() if v > 0}


def day_change(member, day, before, price):
    """(estimated $ change on `day`, {ticker: $ change}) from the positions held the evening `before`."""
    by = collections.defaultdict(float)
    for (tk, _), v in positions(member, before).items():
        p0, p1 = price(tk, before), price(tk, day)
        if p0 and p1 and suspect(p0, p1):
            skipped[tk] = round((p1 / p0 - 1) * 100, 1)
        elif p0 and p1:
            by[tk] += v * (p1 / p0 - 1)
    return sum(by.values()), dict(by)


def board(members, day, before, price):
    """Every member who holds priced stocks: their change, what moved them most, chamber, party."""
    rows = []
    for bio, m in members.items():
        total, by = day_change(m, day, before, price)
        if not by:
            continue
        moved = sorted(by, key=lambda t: abs(by[t]), reverse=True)
        rows.append({"bioguide": bio, "name": m["name"], "chamber": m.get("chamber", "House"), "party": m["party"],
                     "state": m["state"], "change": round(total), "moved": moved[:3], "stocks": len(by)})
    return sorted(rows, key=lambda r: r["change"], reverse=True)


def party_score(rows):
    """Each party's total, how many of its members own stocks, how many rose and fell, its top three."""
    out = []
    for code, word in (("D", "Democrats"), ("R", "Republicans")):
        rs = sorted((r for r in rows if r["party"] == code), key=lambda r: r["change"], reverse=True)
        out.append({"party": word, "change": sum(r["change"] for r in rs), "owners": len(rs),
                    "rose": sum(r["change"] > 0 for r in rs), "fell": sum(r["change"] < 0 for r in rs),
                    "lead": [(r["bioguide"], r["change"]) for r in rs[:3]]})
    return out


def most_owned(members, day, before, price, n=4):
    """The stocks the most members held the evening before, with the day's move."""
    count = collections.Counter(t for m in members.values() for t in {tk for tk, _ in positions(m, before)})
    out = []
    for tk, k in count.most_common():
        p0, p1 = price(tk, before), price(tk, day)
        if p0 and p1 and not suspect(p0, p1):
            out.append({"ticker": tk, "members": k, "pct": round((p1 / p0 - 1) * 100, 1)})
        if len(out) == n:
            break
    return out


if __name__ == "__main__":
    import prices
    day = prices.trading(sys.argv[sys.argv.index("--day") + 1])
    if not day:
        sys.exit("no IEX prices for that day yet (the file is out about 6 am Eastern the next morning)")
    before = prices.trading(prices.previous_open(day))
    members = json.load(open(os.path.join(DATA, "house-holdings.json")))["members"]
    chambers = ["House"]
    if os.path.exists(os.path.join(DATA, "senate-holdings.json")):  # the Senate, once its reports are read
        members.update(json.load(open(os.path.join(DATA, "senate-holdings.json"))))
        chambers.append("Senate")
    rows = board(members, day, before, prices.price)
    names = {a["ticker"]: a.get("asset") or a.get("name") or a["ticker"] for m in members.values() for a in m["held"] + m["trades"]}
    res = {"day": day, "before": before, "chambers": chambers, "rows": rows, "party": party_score(rows),
           "movers": most_owned(members, day, before, prices.price), "prices": prices.SOURCE,
           "skipped": dict(sorted(skipped.items())),
           "names": {t: names.get(t, t) for r in rows for t in r["moved"]}}
    with open(os.path.join(DATA, f"close-{day}.json"), "w") as f:
        json.dump(res, f, indent=1)
    print(f"{day} vs {before}: {len(rows)} members with priced stocks")
    for r in rows[:10] + rows[-5:]:
        print(f"  {r['change']:>+12,} {r['name']} ({r['party']}-{r['state']}) moved most: {', '.join(r['moved'])}")
    for p in res["party"]:
        print(f"  {p['party']}: {p['change']:+,} | {p['owners']} own stocks, {p['rose']} rose, {p['fell']} fell")
    print("  most owned:", res["movers"])
    if skipped:
        print("  left out (split or bad print?):", res["skipped"])

