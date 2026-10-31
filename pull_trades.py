"""Pull the stock trade reports members of Congress filed on one day (House Clerk + Senate eFD) and write
data/trades-<day>.json for the New trades slide. It reads downloaded files, so run it isolated:

    python3 -I pull_trades.py [--day 2026-10-28]

Everything downloaded lands under data/ (one folder per source); nothing here runs what it downloads.
"""
import datetime, http.cookiejar, json, os, re, subprocess, sys, time, urllib.parse, urllib.request, zipfile
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
HOUSE = "https://disclosures-clerk.house.gov/public_disc"
JAR = http.cookiejar.CookieJar()
WEB = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(JAR))


def get(url, data=None, headers=None, tries=3):
    for n in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, **(headers or {})})
            with WEB.open(req, timeout=60) as r:
                return r.read()
        except Exception as ex:                         # the House and Senate sites drop the odd request
            if n == tries - 1:
                raise
            print("  retry", url, ex)
            time.sleep(3 * (n + 1))


def save(url, path, fresh=False):
    """Download once; fresh=True fetches again (the House index changes every morning)."""
    if fresh or not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        body = get(url)
        with open(path + ".part", "wb") as f:
            f.write(body)
        os.replace(path + ".part", path)
        time.sleep(0.3)                                 # polite to the House and Senate sites: only after a real download
    return path


# ------------------------------------------------------------------ HOUSE
def house_index(year):
    """Every House filing this year: name, state and district, type (P = trade report), date, document id."""
    z = save(f"{HOUSE}/financial-pdfs/{year}FD.zip", os.path.join(DATA, "house", f"{year}FD.zip"), fresh=True)
    with zipfile.ZipFile(z) as zf:
        name = f"{year}FD.xml"
        if name not in zf.namelist():
            sys.exit(f"{name} missing from the House index zip: {zf.namelist()}")
        root = ET.fromstring(zf.read(name))
    rows = []
    for m in root.iter("Member"):
        r = {c.tag: (c.text or "").strip() for c in m}
        rows.append(r)
    return rows


TX = re.compile(r"\s(P|S \(partial\)|S|E)\s+(\d\d/\d\d/\d{4})\s+(\d\d/\d\d/\d{4})\s+"
                r"(\$[\d,]+\s*-\s*\$[\d,]+|\$[\d,]+\s*-|Over \$[\d,]+|Spouse/DC Over \$[\d,]+|\$[\d,]+(?:\.\d\d)?)\s*$")
META = re.compile(r"^\s*[A-Z](?:\s+[A-Z])*\s*:\s")       # 'F  S : New' (filing status), 'S  O : ...' (subholding of)
MORE = re.compile(r"^(.*?)\s{2,}(\$[\d,]+)\s*$")         # an asset line that also carries the amount's second half


def money_range(text):
    """'$15,001 - $50,000' -> (15001, 50000); 'Over $50,000,000' -> (50000001, None); '$344.99' -> (344, 344)."""
    nums = [int(float(n.replace(",", ""))) for n in re.findall(r"\$([\d,]+(?:\.\d+)?)", text)]
    if "Over" in text:
        return nums[0] + 1, None
    return (nums[0], nums[1]) if len(nums) > 1 else (nums[0], nums[0])


READER = 2                                              # bump when a reader changes, so remembered reads are redone


def cached(name, read):
    """A report read once and remembered (data/parsed/<name>-r<READER>.json), so the morning run reads only new ones."""
    path = os.path.join(DATA, "parsed", f"{name}-r{READER}.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    out = read()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(out, f)
    return out


def house_ptr(doc, year):
    """The trades in one House report. Scanned paper reports have no text: they come back empty."""
    return cached(f"ptr-{doc}", lambda: read_ptr(doc, year))


def read_ptr(doc, year):
    pdf = save(f"{HOUSE}/ptr-pdfs/{year}/{doc}.pdf", os.path.join(DATA, "house", "ptr", f"{doc}.pdf"))
    text = subprocess.run(["pdftotext", "-layout", pdf, "-"], capture_output=True, text=True).stdout
    trades, cur = [], None
    for line in text.splitlines():
        m = TX.search(line)
        if m:
            left = line[:m.start()].strip()
            owner = left.split()[0] if left.split() and left.split()[0] in ("SP", "JT", "DC") else "self"
            cur = {"owner": owner, "asset": left[len(owner):].strip() if owner != "self" else left,
                   "type": m.group(1), "date": m.group(2), "notified": m.group(3), "amount": m.group(4), "account": ""}
            trades.append(cur)
            continue
        if cur is None or not line.strip():
            if not line.strip() and cur is not None and cur["amount"].endswith("-"):
                continue
            cur = None if not line.strip() and cur is not None and "]" in cur["asset"] else cur
            continue
        if META.match(line):
            k, _, v = line.partition(":")
            if k.split() == ["S", "O"]:
                cur["account"] = v.strip()
            continue
        m = MORE.match(line)
        if m and cur["amount"].endswith("-"):
            cur["amount"] += " " + m.group(2)
            line = m.group(1)
        if "]" not in cur["asset"] and not line.lstrip().startswith("*"):
            cur["asset"] += " " + line.strip()
    for t in trades:
        t["asset"] = re.sub(r"\s+", " ", t["asset"]).strip()
        tk = re.search(r"\(([A-Z][A-Z.\-]{0,6})\)", t["asset"])
        kind = re.search(r"\[([A-Z]{2})\]", t["asset"])
        t["ticker"] = tk.group(1) if tk else ""
        t["kind"] = kind.group(1) if kind else ""
        t["low"], t["high"] = money_range(t["amount"])
        for f in ("date", "notified"):
            t[f] = datetime.datetime.strptime(t[f], "%m/%d/%Y").date().isoformat()
    return trades


def house_members():
    """The House's own member list, by seat ('OK01'): bioguide id, last name, party, state."""
    x = save("https://clerk.house.gov/xml/lists/MemberData.xml", os.path.join(DATA, "house", "MemberData.xml"), fresh=True)
    out = {}
    for m in ET.parse(x).getroot().iter("member"):
        info = m.find("member-info")
        if info is None:
            continue
        st = info.find("state")
        out[(m.findtext("statedistrict") or "").strip()] = {
            "bioguide": (info.findtext("bioguideID") or "").strip(), "last": (info.findtext("lastname") or "").strip(),
            "party": (info.findtext("party") or "").strip(),
            "state": (st.findtext("state-fullname") or "").strip() if st is not None else ""}
    return out


ATLAS = os.environ.get("SCORECARD_ATLAS", os.path.join(HERE, "atlas"))   # portraits + logos (not in the repo: see README)
PARTY = {"D": "Democrat", "R": "Republican", "I": "Independent"}


def us_date(s):
    return datetime.datetime.strptime(s, "%m/%d/%Y").date()


def senators():
    """(who, party): who('James Conley', 'Justice, II') finds Jim Justice among the sitting senators in the atlas
    ('Moran, ' and 'Lujan' match too); party is the Senate's own list, by bioguide id."""
    import unicodedata
    x = save("https://www.senate.gov/general/contact_information/senators_cfm.xml",
             os.path.join(DATA, "senate", "senators.xml"), fresh=True)
    party = {(m.findtext("bioguide_id") or "").strip(): (m.findtext("party") or "").strip() for m in ET.parse(x).getroot().iter("member")}
    sens = [v for v in json.load(open(os.path.join(ATLAS, "registry.json")))["entities"].values()
            if v.get("kind") == "member" and v.get("current") and v.get("chamber") == "senate"]
    plain = lambda t: unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()

    def who(first, last):
        last = re.sub(r",?\s+(Jr\.?|Sr\.?|II|III|IV)\s*$", "", last.strip(), flags=re.I)
        last = plain(re.sub(r"[,\s]+$", "", last))
        hits = [v for v in sens if plain(v.get("last", "")) == last]
        if len(hits) > 1:                               # two Scotts: Tim and Rick (Richard)
            hits = [v for v in hits if v["name"][0].lower() == first.strip()[0].lower()] or hits
        return hits[0] if len(hits) == 1 else None
    return who, party


def senate_rows(day):
    """The Senate's trade reports from the last browser-panel read (data/senate/ptr-2026.json; reading the Senate
    needs its box ticked by Andrew): one entry per senator per filing day, with their biggest stock or option
    trade, how many more stock trades the report holds, and how late it came."""
    path = os.path.join(DATA, "senate", "ptr-2026.json")
    if not os.path.exists(path):
        return []
    who, party = senators()
    named = os.path.join(DATA, "senate", "annual-2025.json")   # company names, from what senators hold
    names = {h["ticker"]: h["name"] for s in (json.load(open(named)) if os.path.exists(named) else []) for h in s["held"]}
    by = {}
    for rep in json.load(open(path)):
        v, filed = who(rep["first"], rep["last"]), us_date(rep["filed"])
        stocks = [t for t in rep["trades"] if t[3] in ("ST", "OP")]
        if v and stocks and filed <= day:
            by.setdefault((v["bioguide"], filed), (v, []))[1].extend(stocks)
    out = []
    for (bio, filed), (v, ts) in by.items():
        ts.sort(key=lambda t: t[6] or t[5], reverse=True)
        date, owner, ticker, kind, typ, low, high = ts[0][:7]
        asset = ts[0][7] if len(ts[0]) > 7 else names.get(ticker, "")
        trade = {"owner": owner, "asset": asset, "ticker": ticker, "kind": kind, "type": typ, "date": date,
                 "notified": "", "amount": "", "low": low, "high": high, "account": ""}
        out.append({"bioguide": bio, "name": v["name"], "chamber": "Senate", "party": PARTY.get(party.get(bio, ""), ""),
                    "state": v["title"].split(",")[-1].strip().title(), "filed": filed.isoformat(), "doc": "",
                    "trade": trade, "more": len(ts) - 1, "trades": [],
                    "late": max(0, (filed - datetime.date.fromisoformat(date)).days - 45)})
    return out


def pick(day, back=5, want=4, most=5):
    """The newest stock trades for the New trades slide: reports filed on `day`, reaching back over earlier
    filing days (at most `back`) until `want` members are on the list. One row per member: their biggest
    stock trade in their newest report, how many more stock trades that report holds, and how late it came."""
    rows = [r for r in house_index(day.year) if r.get("FilingType") == "P" and us_date(r["FilingDate"]) <= day]
    seats = house_members()
    names = {v.get("bioguide"): v.get("name") for v in json.load(open(os.path.join(ATLAS, "registry.json")))["entities"].values()
             if v.get("kind") == "member"}
    senate = [s for s in senate_rows(day) if s["filed"] <= day.isoformat()]
    out, paper, seen = [], [], set()
    days = {us_date(r["FilingDate"]) for r in rows} | {datetime.date.fromisoformat(s["filed"]) for s in senate}
    for d in sorted(days, reverse=True)[:back]:
        for r in sorted((r for r in rows if us_date(r["FilingDate"]) == d), key=lambda r: r["Last"]):
            who = f"{r['First']} {r['Last']}"
            m = seats.get(r["StateDst"])
            if not m or m["last"].lower() != r["Last"].lower():
                print("  not in the seat list (left the House?):", who, r["StateDst"], r["DocID"])
                continue
            ts = house_ptr(r["DocID"], d.year)
            if not ts:
                paper.append({"name": who, "doc": r["DocID"], "filed": d.isoformat()})
                continue
            stocks = sorted((t for t in ts if t["ticker"] and t["kind"] == "ST"),
                            key=lambda t: t["high"] or t["low"], reverse=True)
            if not stocks or m["bioguide"] in seen:
                continue
            seen.add(m["bioguide"])
            top = stocks[0]
            late = (d - datetime.date.fromisoformat(top["date"])).days - 45
            out.append({"bioguide": m["bioguide"], "name": names.get(m["bioguide"]) or who, "chamber": "House",
                        "party": PARTY.get(m["party"], m["party"]), "state": m["state"], "filed": d.isoformat(),
                        "doc": r["DocID"], "trade": top, "more": len(stocks) - 1, "late": max(0, late),
                        "trades": ts})
        for s in senate:
            if s["filed"] == d.isoformat() and s["bioguide"] not in seen:
                seen.add(s["bioguide"])
                out.append(s)
        if len(out) >= want:
            break
    out.sort(key=lambda p: (p["filed"], p["trade"]["high"] or p["trade"]["low"]), reverse=True)
    return {"day": day.isoformat(), "rows": out[:most], "others": out[most:], "paper": paper,
            "sources": ["House"] + (["Senate"] if senate else [])}


if __name__ == "__main__":
    if "--day" in sys.argv:
        day = datetime.date.fromisoformat(sys.argv[sys.argv.index("--day") + 1])
    else:                                               # the last weekday before today
        day = datetime.date.today() - datetime.timedelta(days=1)
        while day.weekday() > 4:
            day -= datetime.timedelta(days=1)
    res = pick(day)
    path = os.path.join(DATA, f"trades-{day}.json")
    with open(path, "w") as f:
        json.dump(res, f, indent=1)
    for p in res["rows"] + res["others"]:
        t = p["trade"]
        print(f"{p['filed']} {p['name']} ({p['party']}, {p['state']}) {t['owner']} {t['type']} {t['ticker']} "
              f"{t['low']}-{t['high']} traded {t['date']} +{p['more']} more, late {p['late']}")
    print("paper:", ", ".join(f"{q['name']} {q['doc']}" for q in res["paper"]) or "none")
    print("wrote", path)
