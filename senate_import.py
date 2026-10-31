"""Bring a Senate read from the browser panel (tools/senate_read.js) onto disk. The panel's result is too big
to come back inline, so the tool saves it to a file; this turns that file into our data files:

    python3 -I senate_import.py <saved result file> annual     -> data/senate/annual-2025.json
    python3 -I senate_import.py <saved result file> ptr        -> data/senate/ptr-2026.json

then   python3 -I pull_holdings.py --senate
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
src, what = sys.argv[1], sys.argv[2]
text = json.load(open(src))[0]["text"].split("\n\n(captured at origin")[0].strip()
data = json.loads(text)
if isinstance(data, str):                               # the page handed back a JSON string
    data = json.loads(data)
os.makedirs(os.path.join(HERE, "data", "senate"), exist_ok=True)
if what == "annual":
    out = [{"first": f, "last": l, "filed": fd, "title": t,
            "held": [{"ticker": r[0], "owner": r[1], "low": r[2], "high": r[3], "kind": r[4], "name": r[5]} for r in rows]}
           for f, l, fd, t, rows in data]
    dst = os.path.join(HERE, "data", "senate", "annual-2025.json")
    print(len(out), "senators,", sum(len(x["held"]) for x in out), "holdings")
else:
    out = data
    dst = os.path.join(HERE, "data", "senate", "ptr-2026.json")
    print(len(out), "reports,", sum(len(x["trades"]) for x in out), "trades")
with open(dst, "w") as f:
    json.dump(out, f, indent=1)
print("wrote", dst)
