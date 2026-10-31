"""What every sitting House member owns: the stocks on their yearly report (what they held on December 31),
plus the stock trades they reported since. Writes data/house-holdings.json. It reads downloaded files,
so run it isolated:

    python3 -I pull_holdings.py

Prices come later (a data source is still Andrew's to pick); this file only records what they hold.
"""
import collections, datetime, json, os, re, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)                                # our own code only; downloads live under data/
from pull_trades import DATA, HOUSE, cached, house_index, house_members, house_ptr, money_range, save, senators, us_date

SCHED = re.compile(r"^\s*S\s+([A-J]):")                # 'S   A: A ...' starts Schedule A (the PDF's font spaces it out)
META = re.compile(r"^\s*[A-Z](?:\s+[A-Z])*\s*:\s")      # 'L  : place', 'D  : description', 'C  : comment'
VALUE = re.compile(r"(\$[\d,]+\s*-\s*\$[\d,]+|\$[\d,]+\s*-|Spouse/DC Over \$[\d,]+|Over \$[\d,]+|None|Undetermined)")
TICKER = re.compile(r"\(([A-Z][A-Z0-9.\-]{0,6})\)")
KIND = re.compile(r"\[([A-Z0-9]{2})\]")
START = re.compile(r"^\s*(?:(?:JT|SP|DC)\s+)?(\$[\d,]+\s*-|Spouse/DC Over|Over \$|None\b|Undetermined)")   # an asset's first line
KEEP = {"ST", "EF"}                                    # stocks and exchange-traded funds; options, funds without
                                                       # a ticker, bonds and property stay out of the estimate


def annual_assets(doc, year):
    """Schedule A of one yearly report (remembered after the first read): (assets, how many type codes it shows)."""
    assets, codes = cached(f"annual-{doc}", lambda: list(read_annual(doc, year)))
    return assets, codes


def read_annual(doc, year):
    """Schedule A of one yearly report: each asset with its owner and value range. Blocks are separated by
    blank lines; the owner column moves from page to page, so each page's header sets it."""
    pdf = save(f"{HOUSE}/financial-pdfs/{year}/{doc}.pdf", os.path.join(DATA, "house", "annual", f"{doc}.pdf"))
    text = subprocess.run(["pdftotext", "-layout", pdf, "-"], capture_output=True, text=True).stdout
    in_a, col, blocks, cur, codes = False, None, [], [], 0
    for line in text.splitlines():
        m = SCHED.match(line)
        if m:
            in_a = m.group(1) == "A"
            if cur:
                blocks.append(cur)
                cur = []
            continue
        if not in_a:
            continue
        if "Owner" in line and "Value of Asset" in line:
            col = line.index("Owner")
            continue
        if col is None or META.match(line) or "Filing ID #" in line or line.strip() in ("$1,000?", "Tx. >") \
                or line.lstrip().startswith("* For the complete list"):
            continue
        if not line.strip():
            if cur:
                blocks.append(cur)
                cur = []
            continue
        cut = max(0, col - 1)                           # a long name can run past the owner column: keep its word whole
        while cut < len(line) and line[cut] != " " and not line[cut:].startswith(("JT ", "SP ", "DC ", "$")):
            cut += 1
        left, right = line[:cut].strip(), line[cut:]
        codes += bool(KIND.search(left))
        if cur and START.match(right) and any(KIND.search(l) for l, _ in cur):
            blocks.append(cur)                          # two assets with no blank line between them
            cur = []
        cur.append((left, right))
    if cur:
        blocks.append(cur)
    assets = []
    for b in blocks:
        rights = [r for _, r in b]
        anchor = next((i for i, r in enumerate(rights) if VALUE.search(r)), None)
        if anchor is None:
            if assets:                                  # a page break split the asset's name: join it back
                assets[-1]["asset"] += " " + " ".join(l for l, _ in b if l)
            continue
        r = rights[anchor].split()
        owner = r[0] if r and r[0] in ("JT", "SP", "DC") else "self"
        value = VALUE.search(rights[anchor][rights[anchor].find(r[0]) + len(r[0]) if owner != "self" else 0:]).group(1)
        if value.endswith("-"):
            more = next((re.search(r"\$[\d,]+", x).group(0) for x in rights[anchor + 1:] if re.search(r"\$[\d,]+", x)), "")
            value += " " + more
        assets.append({"asset": " ".join(l for l, _ in b if l), "owner": owner, "value": value})
    for a in assets:
        a["asset"] = re.sub(r"\s+", " ", a["asset"]).strip()
        tk, kind = TICKER.findall(a["asset"]), KIND.findall(a["asset"])
        a["ticker"], a["kind"] = (tk[-1] if tk else ""), (kind[-1] if kind else "")
        a["low"], a["high"] = money_range(a["value"]) if "$" in a["value"] else (0, 0)
    return assets, codes


def senate_members(annual_path, ptr_path):
    """Each senator's holdings (their 2025 yearly report) and this year's trades, keyed by bioguide id like the
    House. Both files are read in the browser panel after Andrew ticks the Senate's box himself (Claude may not
    tick it for him): data/senate/annual-2025.json and data/senate/ptr-2026.json."""
    who, party = senators()
    out = {}
    for s in json.load(open(annual_path)):
        v = who(s["first"], s["last"])
        if not v:
            print("  senator not matched:", s["first"], s["last"])
            continue
        out[v["bioguide"]] = {"name": v["name"], "chamber": "Senate", "party": party.get(v["bioguide"], ""),
                              "state": v["title"].split(",")[-1].strip().title(), "report": s["title"],
                              "filed": s["filed"], "held": [h for h in s["held"] if h["low"]], "trades": []}
    for p in json.load(open(ptr_path)):
        v = who(p["first"], p["last"])
        if not v or v["bioguide"] not in out:
            continue
        for date, owner, ticker, kind, typ, low, high in (t[:7] for t in p["trades"]):
            if date >= "2026-01-01" and kind != "OP":    # options stay out, as on the House side
                out[v["bioguide"]]["trades"].append({"ticker": ticker, "owner": owner, "type": typ, "date": date,
                                                      "low": low, "high": high, "filed": p["filed"]})
    return out


def main():
    seats = house_members()
    ann = [r for r in house_index(2025) if r.get("FilingType") == "O"]
    ptr = [r for r in house_index(2026) if r.get("FilingType") == "P"]
    sitting = lambda r: (m := seats.get(r["StateDst"])) and m["last"].lower() == r["Last"].lower() and m
    out, paper, odd = {}, [], []
    for r in sorted(ann, key=lambda r: r["Last"]):
        m = sitting(r)
        if not m:
            continue
        if not r["DocID"].startswith("1"):
            paper.append(f"{r['First']} {r['Last']} ({r['StateDst']}) {r['DocID']}")
            continue
        assets, codes = annual_assets(r["DocID"], 2025)
        if codes != len([a for a in assets if a["kind"]]):
            odd.append(f"{r['Last']} {r['DocID']}: {codes} type codes, {len([a for a in assets if a['kind']])} parsed")
        held = [a for a in assets if a["ticker"] and a["kind"] in KEEP and a["low"]]
        out[m["bioguide"]] = {"name": f"{r['First']} {r['Last']}", "seat": r["StateDst"], "party": m["party"],
                              "state": m["state"], "report": r["DocID"], "filed": us_date(r["FilingDate"]).isoformat(),
                              "assets": len(assets), "held": held, "trades": []}
    for r in ptr:
        m = sitting(r)
        if not m or m["bioguide"] not in out:
            continue
        for t in house_ptr(r["DocID"], 2026):
            if t["date"] >= "2026-01-01" and t["ticker"] and t["kind"] in KEEP:
                out[m["bioguide"]]["trades"].append({**t, "doc": r["DocID"], "filed": us_date(r["FilingDate"]).isoformat()})
    with open(os.path.join(DATA, "house-holdings.json"), "w") as f:
        json.dump({"members": out, "paper": paper, "unread": odd}, f, indent=1)
    holders = collections.Counter(t for v in out.values() for t in {a["ticker"] for a in v["held"]})
    print(len(out), "members read,", sum(1 for v in out.values() if v["held"]), "hold stocks;", len(paper), "paper reports")
    print(len(holders), "different stocks; most held:", ", ".join(f"{t} {n}" for t, n in holders.most_common(12)))
    print(sum(len(v["trades"]) for v in out.values()), "stock trades in 2026 reports")
    print("blocks that didn't add up:", len(odd), *odd[:8], sep="\n  ")


if __name__ == "__main__":
    if "--senate" in sys.argv:                          # after the browser-panel read has written both files
        sen = senate_members(os.path.join(DATA, "senate", "annual-2025.json"), os.path.join(DATA, "senate", "ptr-2026.json"))
        with open(os.path.join(DATA, "senate-holdings.json"), "w") as f:
            json.dump(sen, f, indent=1)
        print(len(sen), "senators,", sum(1 for v in sen.values() if v["held"]), "hold stocks,",
              sum(len(v["trades"]) for v in sen.values()), "trades in 2026")
    else:
        main()
