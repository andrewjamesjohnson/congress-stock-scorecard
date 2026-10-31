"""The morning runner's steps (daily.py) with every outside call faked: no network, no Meta, no phone.

    cd _build && /usr/bin/python3 -m unittest discover -s tests
"""
import datetime, os, shutil, sys, tempfile, types, unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
os.environ["CLIP_FACTORY_OFFLINE"] = "1"
os.environ["HTTPS_PROXY"] = "http://127.0.0.1:9"
import daily  # noqa: E402

FRI = datetime.date(2026, 10, 30)                     # the post day: about Thursday 10-29
# The steps are tested on this fixed morning (the first one, 10-30), so the live times in daily.CONFIG can move
# without these moving; test_the_six_thirty_morning runs the live times themselves.
TIMES = {"prices_from": "03:30", "build_from": "07:00", "build_wait": 20, "build_by": "08:45", "ask_from": "07:00",
         "post_at": "07:30", "answer_until": "09:30"}


def conf(**kw):
    return lambda: dict(daily.CONFIG, **{**TIMES, **kw})


def clock(hhmm, day=FRI):
    h, m = map(int, hhmm.split(":"))
    return datetime.datetime.combine(day, datetime.time(h, m)).astimezone()


class Fakes:
    def __init__(self, tmp):
        self.tmp, self.pushes, self.presses, self.calls = tmp, [], [], []
        self.fresh, self.fetch_ok, self.blocked, self.fail = True, True, "", None
        self.published, self.found = [], None

    def fetch(self, d):
        self.calls.append(("fetch", d))
        if self.fetch_ok:
            open(os.path.join(daily.prices.CACHE, f"{d}.json"), "w").write("{}")
        return self.fetch_ok

    def build(self, st, about, cfg_):
        self.calls.append(("build", about))
        folder = os.path.join(self.tmp, "Daily Posts", f"{FRI:%m.%d %A}")
        os.makedirs(folder, exist_ok=True)
        slides = []
        for i in range(1, 8):
            open(os.path.join(folder, f"Slide {i}.jpg"), "wb").write(b"jpg%d" % i)
            slides.append(f"Slide {i}.jpg")
        st["built"] = {"at": "x", "folder": folder, "about": about, "slides": slides,
                       "shas": [daily.sha(os.path.join(folder, s)) for s in slides], "caption": "words",
                       "lead": "Darrell Issa +$818K", "targets": list(cfg_["targets"]),
                       "hash": daily.post_hash(folder, slides, "words", cfg_["targets"])}

    def push(self, title, message, image=None, buttons=None, priority="high"):
        self.pushes.append((title, message, buttons))
        return True, "id1"

    def stage(self, st, folder):
        self.calls.append(("stage",))
        if self.fail:
            raise SystemExit(self.fail)
        st.setdefault("outlets", {})["facebook_feed"] = {"photo_ids": ["p1"]}
        st["outlets"]["instagram_carousel"] = {"container": "c1"}

    def publish(self, st):
        self.calls.append(("publish",))
        for k in st["outlets"]:
            st["outlets"][k].update(id="x", url=f"https://{k}")
        self.published.append(1)


class DailyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.f = Fakes(self.tmp)
        self.saved = {k: getattr(daily, k) for k in ("STATE", "PROJECT", "now", "push", "build", "stage", "publish",
                                                       "house_fresh", "replies", "read_up_to", "factory", "blocked",
                                                       "config", "sheet")}
        self.cache = daily.prices.CACHE
        daily.prices.CACHE = os.path.join(self.tmp, "iex")
        os.makedirs(daily.prices.CACHE)
        daily.STATE = os.path.join(self.tmp, "state")
        daily.PROJECT = self.tmp
        daily.push, daily.build, daily.stage, daily.publish = self.f.push, self.f.build, self.f.stage, self.f.publish
        daily.house_fresh = lambda today: self.f.fresh
        daily.replies = lambda: list(self.f.presses)
        daily.read_up_to = lambda mid: self.f.presses.clear()
        daily.factory = lambda: (None, None, None, None, None, None, None)
        daily.blocked = lambda *a: self.f.blocked
        daily.config = conf()
        daily.sheet = lambda folder, slides: None
        self.fetch = daily.prices.fetch
        daily.prices.fetch = self.f.fetch

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(daily, k, v)
        daily.prices.CACHE = self.cache
        daily.prices.fetch = self.fetch
        shutil.rmtree(self.tmp)

    def at(self, hhmm, day=FRI):
        daily.now = lambda: clock(hhmm, day)
        daily.tick()
        return daily.read(day)

    def press(self, verb, st=None, day=FRI):
        h = (st or daily.read(day))["built"]["hash"]
        self.f.presses.append(("m1", ["score", verb, str(day), h]))

    def test_nothing_on_a_shut_day(self):
        sat = datetime.date(2026, 10, 31)
        st = self.at("08:00", sat)
        self.assertEqual(self.f.calls, [])
        self.assertNotIn("built", st)
        self.at("08:00", datetime.date(2026, 11, 26))      # Thanksgiving
        self.assertEqual(self.f.calls, [])

    def test_the_whole_morning(self):
        self.at("03:00")
        self.assertEqual(self.f.calls, [])
        self.at("03:30")
        self.assertEqual(self.f.calls, [("fetch", "2026-10-28"), ("fetch", "2026-10-29")])
        st = self.at("07:00")
        self.assertIn("built", st)
        self.assertNotIn("asked", st)                      # one heavy step per run
        st = self.at("07:02")
        self.assertTrue(st["asked"]["ok"])
        title, message, buttons = self.f.pushes[-1]
        self.assertIn("Darrell Issa", message)
        self.assertEqual(buttons[0], ("Post it", f"score post 2026-10-30 {st['built']['hash']}"))
        self.press("post", st)
        st = self.at("07:10")
        self.assertEqual(st["answer"]["verb"], "post")
        self.assertIn(("stage",), self.f.calls)
        self.assertNotIn(("publish",), self.f.calls)       # staged: it goes public at 07:30
        st = self.at("07:30")
        self.assertEqual(st["done"], "posted")
        self.assertEqual(len(self.f.published), 1)
        self.assertTrue(self.f.pushes[-1][0].startswith("✅"))
        self.at("07:32")
        self.assertEqual(len(self.f.published), 1)         # never twice

    def test_a_late_yes_posts_at_once(self):
        self.at("07:00")
        self.at("07:02")
        self.press("post")
        st = self.at("08:15")
        self.assertEqual(st["done"], "posted")

    def test_no_means_nothing(self):
        self.at("07:00")
        self.at("07:02")
        self.press("skip")
        st = self.at("07:10")
        self.assertEqual(st["answer"]["verb"], "skip")
        self.at("07:40")
        self.assertNotIn(("stage",), self.f.calls)

    def test_a_button_for_old_slides_is_refused(self):
        self.at("07:00")
        st = self.at("07:02")
        self.f.presses.append(("m1", ["score", "post", "2026-10-30", "0" * 20]))
        st = self.at("07:10")
        self.assertNotIn("answer", st)
        self.assertEqual(st["stale"], ["score post 2026-10-30 " + "0" * 20])
        self.assertNotIn(("stage",), self.f.calls)

    def test_no_answer_by_0930(self):
        self.at("07:00")
        self.at("07:02")
        st = self.at("09:31")
        self.assertIn("no answer", st["gave_up"])
        self.press("post", st)
        st = self.at("09:33")
        self.assertNotIn(("stage",), self.f.calls)

    def test_waits_for_the_house_index_then_builds_anyway(self):
        self.f.fresh = False
        st = self.at("07:00")
        self.assertNotIn("built", st)
        st = self.at("07:20")
        self.assertIn("built", st)

    def test_no_prices_no_post(self):
        self.f.fetch_ok = False
        st = self.at("07:00")
        self.assertNotIn("built", st)
        self.assertNotIn(("build", "2026-10-29"), self.f.calls)
        st = self.at("08:50")
        self.assertIn("no slides by", st["gave_up"])
        self.assertEqual(self.f.pushes[-1][0], "Scorecard: none today")

    def test_blocked_waits_and_says_so_once(self):
        self.at("07:00")
        self.at("07:02")
        self.press("post")
        self.f.blocked = "Stop everything is on"
        self.at("07:30")
        self.at("07:32")
        self.assertEqual(sum(1 for t, *_ in self.f.pushes if t == "Scorecard waits"), 1)
        self.assertNotIn(("stage",), self.f.calls)
        self.f.blocked = ""
        st = self.at("07:34")
        self.assertEqual(st["done"], "posted")

    def test_failures_retry_then_stop(self):
        self.at("07:00")
        self.at("07:02")
        self.press("post")
        self.f.fail = "Meta said no"
        for i in range(8):
            st = self.at(f"07:{30 + 2 * i}")
        self.assertEqual(len(st["post_errors"]), 6)
        self.assertEqual(st["gave_up"], "six tries failed")
        self.assertEqual(sum(1 for t, *_ in self.f.pushes if t.startswith("⚠️")), 1)

    def test_meta_too_many_calls_waits_and_is_not_counted(self):
        self.at("07:00")
        self.at("07:02")
        self.press("post")
        self.f.fail = "HTTP 403 from graph.facebook.com: Application request limit reached"
        st = self.at("07:30")
        self.assertNotIn("post_errors", st)
        self.assertEqual(st["post_retry"][11:16], "07:50")
        self.at("07:32")                                   # resting: not tried again yet
        self.assertEqual(self.f.calls.count(("stage",)), 1)
        self.f.fail = None
        st = self.at("07:52")
        self.assertEqual(st["done"], "posted")
        self.assertFalse([t for t, *_ in self.f.pushes if t.startswith("⚠️")])

    def test_meta_too_many_calls_all_morning_gives_up_once(self):
        self.at("07:00")
        self.at("07:02")
        self.press("post")
        self.f.fail = "Application request limit reached"
        self.at("07:30")
        st = self.at("14:02")
        self.assertIn("had not cleared", st["gave_up"])
        self.assertEqual(sum(1 for t, *_ in self.f.pushes if t.startswith("⚠️")), 1)

    def test_the_six_thirty_morning(self):
        daily.config = lambda: dict(daily.CONFIG)          # the live times (Andrew's pick 10-30: posts at 6:30)
        self.f.fresh = False                               # the House's index comes out about 7: not waited for
        self.at("02:00")
        self.assertEqual(self.f.calls, [])
        self.at("02:30")
        self.assertEqual(self.f.calls, [("fetch", "2026-10-28"), ("fetch", "2026-10-29")])
        st = self.at("05:58")
        self.assertNotIn("built", st)
        st = self.at("06:00")
        self.assertIn("built", st)
        self.assertTrue(any("not new yet" in n for n in st["notes"]))
        st = self.at("06:02")
        self.assertTrue(st["asked"]["ok"])
        self.assertIn("at 6:30", self.f.pushes[-1][1])
        self.press("post")
        st = self.at("06:04")
        self.assertIn(("stage",), self.f.calls)
        self.assertNotIn("done", st)                       # staged, not public before 6:30
        st = self.at("06:30")
        self.assertEqual(st["done"], "posted")

    def test_started_late_in_the_day_asks_nothing(self):
        st = self.at("22:45")                              # the timer installed in the evening
        self.assertIn("no slides by", st["gave_up"])
        self.assertEqual(self.f.pushes, [])
        self.assertNotIn(("build", "2026-10-29"), self.f.calls)

    def test_built_late_is_not_asked(self):
        self.f.fresh = False
        self.at("07:00")
        daily.config = conf(build_by="23:00")
        st = self.at("09:40")
        self.assertIn("built", st)
        st = self.at("09:42")
        self.assertNotIn("asked", st)
        self.assertEqual(self.f.pushes, [])

    def test_practice_posts_nothing(self):
        daily.config = conf(post="practice")
        self.at("07:00")
        self.at("07:02")
        self.press("post")
        st = self.at("07:40")
        self.assertEqual(st["done"], "practice")
        self.assertNotIn(("stage",), self.f.calls)


class PublishTest(unittest.TestCase):
    """publish() itself, with a fake clip factory: a try that may have gone is looked up, never sent again."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.saved = (daily.STATE, daily.factory, daily.find_ours)
        daily.STATE = self.tmp
        self.sent = []
        test = self

        class G:
            @staticmethod
            def meta_keys(acct):
                return type("K", (), {"page_id": "page"})

            @staticmethod
            def gpost(acct, path, form=None, **kw):
                test.sent.append(path)
                return {"id": "fbpost"}

        class API:
            found = None

            @staticmethod
            def find(acct, outlet, since):
                return API.found

            @staticmethod
            def room_words(limit, due):
                return ""

            @staticmethod
            def publish_limit(acct):
                return {}

            @staticmethod
            def _ig(acct):
                return "ig"

            @staticmethod
            def _publish(acct, ig, cid, mark, what):
                test.sent.append(f"publish {cid}")
                return {"id": "igpost", "url": "https://instagram/p/1"}

        class Cards:
            @staticmethod
            def _reels_due(cfg, acct, now):
                return 0

            @staticmethod
            def _now(cfg):
                return None

        self.API = API
        daily.find_ours = lambda acct, API_, G_, target, since, caption: API.found
        self.had = sys.modules.get("clipfactory")
        sys.modules["clipfactory"] = types.ModuleType("clipfactory")
        sys.modules["clipfactory"].graph = G
        daily.factory = lambda: (None, None, Cards, API, None, None, None)

    def tearDown(self):
        daily.STATE, daily.factory, daily.find_ours = self.saved
        if self.had is None:
            sys.modules.pop("clipfactory", None)
        else:
            sys.modules["clipfactory"] = self.had
        shutil.rmtree(self.tmp)

    def st(self):
        return {"post_day": "2026-10-30", "notes": [],
                "built": {"targets": ["facebook_feed", "instagram_carousel"], "caption": "words"},
                "outlets": {"facebook_feed": {"photo_ids": ["a", "b"]}, "instagram_carousel": {"container": "c1"}}}

    def test_posts_both(self):
        st = self.st()
        daily.publish(st)
        self.assertEqual(self.sent, ["page/feed", "publish c1"])
        self.assertEqual(st["outlets"]["instagram_carousel"]["id"], "igpost")

    def test_a_lost_answer_is_looked_up_not_sent_again(self):
        st = self.st()
        st["outlets"]["facebook_feed"]["attempt"] = "2026-10-30T13:30:00+00:00"
        self.API.found = {"id": "fbpost", "url": "https://facebook/1"}
        daily.publish(st)
        self.assertEqual(self.sent, ["publish c1"])        # Facebook was found, only Instagram went
        self.assertEqual(st["outlets"]["facebook_feed"]["how"], "looked up after an earlier try")


if __name__ == "__main__":
    unittest.main()


class FindTest(unittest.TestCase):
    """find_ours matches the post's own words, never another carousel posted in the same minutes."""

    def test_only_our_words_count(self):
        class G:
            @staticmethod
            def meta_keys(acct):
                return type("K", (), {"page_id": "page"})

            @staticmethod
            def gget(acct, path, params):
                return {"data": [
                    {"id": "news", "caption": "Alphabet misses", "media_type": "CAROUSEL_ALBUM",
                     "timestamp": "2026-10-30T13:31:00+0000", "permalink": "https://ig/news"},
                    {"id": "ours", "caption": "Who in Congress made the most in the market yesterday?\n\n1.",
                     "media_type": "CAROUSEL_ALBUM", "timestamp": "2026-10-30T13:30:20+0000",
                     "permalink": "https://ig/ours"}]}

        class API:
            @staticmethod
            def _ig(acct):
                return "ig"
        since = datetime.datetime(2026, 10, 30, 13, 30, tzinfo=datetime.timezone.utc)
        got = daily.find_ours(None, API, G, "instagram_carousel", since,
                              "Who in Congress made the most in the market yesterday?\n\n1. Issa")
        self.assertEqual(got["id"], "ours")
        self.assertIsNone(daily.find_ours(None, API, G, "instagram_carousel", since, "Something else"))
