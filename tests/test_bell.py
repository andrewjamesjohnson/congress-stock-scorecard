"""Before the bell (bell.py) with the SEC faked: which filings count, the words over each row, who owns what.

    cd _build && /usr/bin/python3 -m unittest discover -s tests
"""
import datetime, os, sys, unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import bell  # noqa: E402

FRI, MON = datetime.date(2026, 10, 30), datetime.date(2026, 11, 2)


def held(ticker, low, high, owner="self"):
    return {"ticker": ticker, "owner": owner, "low": low, "high": high, "kind": "ST"}


def person(name, *lines, trades=(), chamber="House"):
    return {"name": name, "party": "R", "state": "Texas", "chamber": chamber, "held": list(lines), "trades": list(trades)}


class FakeSEC:
    """filings: [(cik, "TICK, TICK2", items, utc time)]; the full-text search pages them 2 at a time."""
    def __init__(self, filings, slow_after=None):
        self.filings, self.calls, self.slow_after = filings, [], slow_after

    def get(self, url):
        self.calls.append(url)
        if self.slow_after is not None and len(self.calls) > self.slow_after:
            raise TimeoutError("slow")
        if "efts.sec.gov" in url:
            at = int(url.rsplit("from=", 1)[1])
            hits = [{"_source": {"adsh": f"000{c}-26-1", "items": items,
                                 "display_names": [f"Company {c}  ({tks})  (CIK {c:010d})"]}}
                    for c, tks, items, _ in self.filings]
            return {"hits": {"total": {"value": len(hits)}, "hits": hits[at:at + 2]}}
        cik = int(url.split("CIK")[1][:10])
        mine = [f for f in self.filings if f[0] == cik]
        return {"filings": {"recent": {"accessionNumber": [f"000{c}-26-1" for c, *_ in mine],
                                       "acceptanceDateTime": [t for *_, t in mine]}}}


class BellTest(unittest.TestCase):
    def setUp(self):
        self.saved = bell.get, bell.members
        bell._until[0] = None

    def tearDown(self):
        bell.get, bell.members = self.saved

    def run_bell(self, filings, people, post_day=FRI, now=None, slow_after=None):
        sec = FakeSEC(filings, slow_after)
        bell.get = sec.get
        bell.members = lambda: people
        now = now or datetime.datetime.combine(post_day, datetime.time(9, 0), bell.ET)
        rows, info = bell.earnings(post_day, now)
        return rows, info, sec

    def test_only_results_from_the_close_to_now_count(self):
        people = {f"A{i}": person(f"Member {i}", held("AAA", 1001, 15000), held("BBB", 1001, 15000),
                                  held("CCC", 1001, 15000), held("DDD", 1001, 15000)) for i in range(3)}
        rows, info, _ = self.run_bell([
            (1, "AAA", ["2.02", "9.01"], "2026-10-29T19:59:00.000Z"),      # 3:59 pm Thursday: before the close
            (2, "BBB", ["2.02", "9.01"], "2026-10-29T20:05:00.000Z"),      # 4:05 pm Thursday
            (3, "CCC", ["2.02"], "2026-10-30T10:30:00.000Z"),              # 6:30 am Friday
            (4, "DDD", ["2.02"], "2026-10-30T13:45:00.000Z"),              # 9:45 am: after this run (9:00)
            (5, "AAA", ["7.01"], "2026-10-29T21:00:00.000Z"),              # not results
        ], people)
        self.assertEqual([(r["ticker"], r["when"]) for r in rows],
                         [("BBB", "Last night, after the close"), ("CCC", "This morning, before the open")])
        self.assertEqual(info["filings"], 4)
        self.assertEqual(rows[0]["owners"], 3)

    def test_a_monday_says_friday_and_the_weekend(self):
        people = {f"A{i}": person(f"Member {i}", held("AAA", 1001, 15000), held("BBB", 1001, 15000),
                                  held("CCC", 1001, 15000)) for i in range(2)}
        rows, *_ = self.run_bell([
            (1, "AAA", ["2.02"], "2026-10-30T20:10:00.000Z"),             # Friday 4:10 pm
            (2, "BBB", ["2.02"], "2026-10-31T14:00:00.000Z"),             # Saturday
            (3, "CCC", ["2.02"], "2026-11-02T12:00:00.000Z"),             # Monday 7 am (EST from Nov 1)
        ], people, post_day=MON)
        self.assertEqual([r["when"] for r in rows],
                         ["Friday, after the close", "Over the weekend", "This morning, before the open"])

    def test_two_share_classes_are_one_holder(self):
        people = {"A1": person("Both", held("GOOGL", 1001, 15000), held("GOOG", 15001, 50000)),
                  "A2": person("One", held("GOOG", 1001, 15000)),
                  "A3": person("Other", held("ZZZ", 1001, 15000)),
                  "A4": person("Other 2", held("ZZZ", 1001, 15000))}
        rows, *_ = self.run_bell([(7, "GOOGL, GOOG", ["2.02"], "2026-10-29T20:01:00.000Z"),
                                  (8, "ZZZ", ["2.02"], "2026-10-29T20:02:00.000Z"),
                                  (9, "YYY", ["2.02"], "2026-10-29T20:03:00.000Z")], people)
        goog = rows[0]
        self.assertEqual(goog["owners"], 2)
        self.assertEqual(goog["top"]["name"], "Both")
        self.assertEqual((goog["top"]["low"], goog["top"]["high"]), (16002, 65000))
        self.assertEqual(len(rows), 2)                                   # YYY: nobody owns it

    def test_one_owner_is_not_enough(self):
        people = {"A1": person("Solo", held("AAA", 1001, 15000))}
        rows, info, sec = self.run_bell([(1, "AAA", ["2.02"], "2026-10-29T20:05:00.000Z")], people)
        self.assertEqual(rows, [])
        self.assertFalse([u for u in sec.calls if "submissions" in u])    # no company list read for it

    def test_biggest_following_first_five_at_most(self):
        people = {f"A{i}": person(f"Member {i}", *[held(f"T{k}", 1001, 15000) for k in range(8) if k <= i])
                  for i in range(8)}
        rows, *_ = self.run_bell([(10 + k, f"T{k}", ["2.02"], "2026-10-29T20:05:00.000Z") for k in range(8)],
                                 people)
        self.assertEqual([r["ticker"] for r in rows], ["T0", "T1", "T2", "T3", "T4"])
        self.assertEqual([r["owners"] for r in rows], [8, 7, 6, 5, 4])

    def test_a_partial_sale_widens_the_range(self):
        m = person("Seller", held("AAA", 50001, 100000, "JT"), held("AAA", 15001, 50000),
                   trades=[{"ticker": "AAA", "owner": "JT", "type": "S (partial)", "date": "2026-09-23",
                            "low": 15001, "high": 50000}])
        mid, low, high = bell.holdings(m, "2026-10-29")["AAA"]
        self.assertEqual((low, high), (15002, 134999))
        self.assertAlmostEqual(mid, 75000.5 - 32500.5 + 32500.5)
        sold = person("Gone", held("AAA", 1001, 15000), trades=[{"ticker": "AAA", "owner": "self", "type": "S",
                                                                  "date": "2026-02-01", "low": 1001, "high": 15000}])
        self.assertEqual(bell.holdings(sold, "2026-10-29"), {})
        self.assertIn("AAA", bell.holdings(sold, "2026-01-31"))         # before the sale it was still held

    def test_a_slow_sec_keeps_what_it_found(self):
        people = {f"A{i}": person(f"Member {i}", held("AAA", 1001, 15000), held("BBB", 1001, 15000))
                  for i in range(3)}
        rows, *_ = self.run_bell([(1, "AAA", ["2.02"], "2026-10-29T20:05:00.000Z"),
                                  (2, "BBB", ["2.02"], "2026-10-29T20:06:00.000Z")], people, slow_after=2)
        self.assertEqual([r["ticker"] for r in rows], ["AAA"])

    def test_the_sec_contact_line(self):
        import json, tempfile
        saved = bell.CONTACT
        try:
            with tempfile.TemporaryDirectory() as d:
                bell.CONTACT = os.path.join(d, "sec.json")
                self.assertEqual(bell.agent(), "Congress Scorecard (github.com/andrewjamesjohnson/congress-stock-scorecard)")   # no file
                json.dump({"contact": "someone@example.com"}, open(bell.CONTACT, "w"))
                self.assertEqual(bell.agent(), "Congress Scorecard someone@example.com")
        finally:
            bell.CONTACT = saved

    def test_brk_spellings_match(self):
        self.assertEqual({bell.norm(t) for t in ("BRK-B", "BRK/B", "brk.b")}, {"BRK.B"})


class SpanTest(unittest.TestCase):
    def test_ranges_read_cleanly(self):
        import scorecard
        self.assertEqual(scorecard.span(45004, 234999), "$45K to $235K")
        self.assertEqual(scorecard.span(5500002, 26000000), "$5.5M to $26M")
        self.assertEqual(scorecard.span(1250002, 5500000), "$1.25M to $5.5M")
        self.assertEqual(scorecard.span(500001, 1000000), "$500K to $1M")
        self.assertEqual(scorecard.span(0, 34999), "Up to $35K")
        self.assertEqual(scorecard.span(50000001, None), "Over $50M")


if __name__ == "__main__":
    unittest.main()
