"""The Congress Scorecard's morning, by itself (launchd every 2 minutes: com.andrewjamesjohnson.scorecard).

On a day the market opens (Mountain time), about the last market day:
  02:30  IEX's prices for that day, as soon as IEX has the file out (prices.py: about 10 minutes; a stalled
         download stops and tries again 15 minutes later)
  06:00  new trades, holdings, every member's estimate, Before the bell (the SEC's earnings filings since the
         close), the slides into "Daily Posts/MM.DD Weekday/" (morning.sh --day <day> --post). It does not wait
         for the House's index (it updates about 07:00): that morning's House filings show the next day.
  then   ONE push to Andrew's phone (ntfy, the clip factory's ask topic): every slide on one sheet, the top line,
         and two buttons, "Post it" / "No"
  06:30  on his Post it (8:30 Eastern; his pick 10-30, it was 07:30, the opening bell): Facebook (one post with
         every slide) and Instagram (one carousel), through the clip factory's own Graph calls
         (clipfactory/cards_api.py), every slide checked against the bytes he was shown.
         A Post it after 06:30 goes at once; none is taken after 09:30 (the morning has moved on).

Nothing posts without his Post it for that day's exact slides: the button carries their hash, and a slide that
changed afterwards is refused. Nothing on a day the market is shut. It stands still for the clip factory's Stop
everything, its Meta hold, the account switched off, or cards.post off; config.json "post": "off" stops it here,
"practice" does everything but the Graph calls.

    /usr/bin/python3 -E daily.py tick              the timer's step (what launchd runs; -E, not -I: the phone
                                                   sheet needs Pillow from the user's site-packages)
    /usr/bin/python3 daily.py status [--day D]     a day, in words
    /usr/bin/python3 daily.py tick --dry-run       what the step would do now: no network, nothing written
    /usr/bin/python3 daily.py install | remove     the launchd job

State: state/<post day>.json (what happened, step by step), state/phone.json (this job's own reply topic),
logs/daily.log. Every Graph step is marked on the state BEFORE the call that cannot be undone, and a step that may
have gone is looked up (cards_api.find) before anything is sent again: never posted twice.
"""
import base64, datetime, hashlib, json, os, secrets, subprocess, sys, urllib.parse, urllib.request
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.join(HERE, "out")
STATE = os.path.join(HERE, "state")
FACTORY = os.path.expanduser("~/clip-factory")
LABEL = "com.andrewjamesjohnson.scorecard"
PLIST = os.path.expanduser(f"~/Library/LaunchAgents/{LABEL}.plist")
# the Python the clip factory's timers run: the one this Mac lets reach the Desktop from launchd (the /usr/bin/python3
# shim runs a different binary, and launchd refuses it the Desktop: "Operation not permitted", 10-29)
PY = ("/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/Resources/Python.app/"
      "Contents/MacOS/Python")
CONFIG = {"post": "live", "account": "politics", "targets": ["facebook_feed", "instagram_carousel"],
          "prices_from": "02:30", "build_from": "06:00", "build_wait": 0, "build_by": "08:30",
          "ask_from": "06:00", "post_at": "06:30", "answer_until": "09:30", "busy_wait": 20, "busy_until": "14:00"}
# build_wait: minutes past build_from to wait for the House's index to be new (0: build at build_from with what it has)
WHERE = {"facebook_feed": "Facebook", "instagram_carousel": "Instagram"}
sys.path.insert(0, HERE)
import prices  # noqa: E402

DRY = "--dry-run" in sys.argv


# ------------------------------------------------------------------ small pieces
def config():
    path = os.path.join(HERE, "config.json")
    got = dict(CONFIG)
    if os.path.exists(path):
        got.update(json.load(open(path)))
    return got


def now():
    return datetime.datetime.now().astimezone()


def at(day, hhmm):
    h, m = map(int, hhmm.split(":"))
    return datetime.datetime.combine(day, datetime.time(h, m)).astimezone()


def log(*words):
    line = f"{now():%Y-%m-%d %H:%M:%S} " + " ".join(str(w) for w in words)
    print(line, flush=True)


def read(day):
    path = os.path.join(STATE, f"{day}.json")
    return json.load(open(path)) if os.path.exists(path) else {"post_day": str(day), "notes": []}


def write(st):
    if DRY:
        return
    os.makedirs(STATE, exist_ok=True)
    path = os.path.join(STATE, f"{st['post_day']}.json")
    with open(path + ".part", "w") as f:
        json.dump(st, f, indent=1)
    os.replace(path + ".part", path)


def note(st, words):
    st.setdefault("notes", []).append(f"{now():%H:%M} {words}")
    log(words)
    write(st)


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def post_hash(folder, slides, caption, targets):
    """What a Post it signs: every slide's bytes, the words and where it goes."""
    blob = json.dumps({"slides": [sha(os.path.join(folder, s)) for s in slides], "caption": caption,
                       "targets": list(targets)}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:20]


# ------------------------------------------------------------------ the phone (ntfy)
def _h(v):
    """A header value: plain one-line ASCII as it is, anything else RFC 2047 (as clipfactory/phone.py does)."""
    try:
        v.encode("ascii")
        if "\r" not in v and "\n" not in v:
            return v
    except UnicodeEncodeError:
        pass
    return "=?UTF-8?B?" + base64.b64encode(v.encode()).decode() + "?="


def phone():
    """The clip factory's ask topic (his ntfy app is subscribed to it) and this job's own reply topic."""
    fac = json.load(open(os.path.join(FACTORY, "state", "phone.json")))
    path = os.path.join(STATE, "phone.json")
    if os.path.exists(path):
        mine = json.load(open(path))
    else:
        mine = {"reply": "score-reply-" + secrets.token_hex(10), "since": ""}
        if not DRY:
            os.makedirs(STATE, exist_ok=True)
            json.dump(mine, open(path, "w"), indent=1)
    return {"on": bool(fac.get("on")), "server": fac.get("server") or "https://ntfy.sh", "topic": fac["topic"],
            "reply": mine["reply"], "since": mine.get("since", "")}


def push(title, message, image=None, buttons=None, priority="high"):
    """One push to Andrew's phone. Never raises: (False, why) when it did not go."""
    if DRY:
        log(f"(dry run) push: {title} | {message[:120]}")
        return True, "dry run"
    try:
        s = phone()
        if not s["on"]:
            return False, "phone pushes are off (clip factory state/phone.json)"
        headers = {"Title": _h(title), "Priority": priority, "Tags": "bar_chart"}
        if buttons:
            url = f"{s['server']}/{s['reply']}"
            headers["Actions"] = _h("; ".join(f"http, {label}, {url}, method=POST, body={body}, clear=true"
                                              for label, body in buttons))
        url = f"{s['server']}/{s['topic']}"
        if image:
            headers.update(Message=_h(message), Filename=os.path.basename(image))
            req = urllib.request.Request(url, data=open(image, "rb").read(), headers=headers, method="PUT")
        else:
            req = urllib.request.Request(url, data=message.encode(), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=30) as r:
            return True, json.loads(r.read() or b"{}").get("id", "sent")
    except Exception as ex:  # noqa: BLE001  (a push that fails must never stop the morning)
        return False, f"{type(ex).__name__}: {ex}"


def replies():
    """The button presses on this job's reply topic since the last read: [(id, words)]."""
    s = phone()
    since = s["since"] or "12h"
    url = f"{s['server']}/{s['reply']}/json?poll=1&since={urllib.parse.quote(since)}"
    with urllib.request.urlopen(url, timeout=30) as r:
        rows = [json.loads(ln) for ln in r.read().decode().splitlines() if ln.strip()]
    return [(m["id"], (m.get("message") or "").split()) for m in rows if m.get("event") == "message"]


def read_up_to(mid):
    path = os.path.join(STATE, "phone.json")
    mine = json.load(open(path))
    mine["since"] = mid
    json.dump(mine, open(path, "w"), indent=1)


def sheet(folder, slides):
    """Every slide on one picture for the phone: two across, half size."""
    from PIL import Image
    w, h = 540, 675
    rows = (len(slides) + 1) // 2
    out = Image.new("RGB", (w * 2 + 12, rows * h + (rows - 1) * 12), (0, 0, 0))
    for i, s in enumerate(slides):
        im = Image.open(os.path.join(folder, s)).convert("RGB").resize((w, h), Image.LANCZOS)
        out.paste(im, ((i % 2) * (w + 12), (i // 2) * (h + 12)))
    path = os.path.join(folder, "phone sheet.jpg")
    out.save(path, quality=86)
    return path


# ------------------------------------------------------------------ the clip factory (posting)
def factory():
    """The clip factory's own modules, its config and the account (read only; its Graph calls do the posting)."""
    if FACTORY not in sys.path:
        sys.path.insert(0, FACTORY)
    from clipfactory import cards, cards_api, config as C, outlets, outward, switches  # noqa: F401
    cfg = C.load()
    acct = cfg.account(config()["account"])
    return cfg, acct, cards, cards_api, outlets, outward, switches


def blocked(cfg, acct, outlets, outward, switches):
    """'' when posting may go now; else the plain reason it waits."""
    return (cfg.why_off(acct) or outward.stopped(cfg) or outlets.meta_hold(acct)
            or ("" if switches.mode(acct, "cards.post") == "on" else
                f"cards.post is {switches.mode(acct, 'cards.post')} for {acct.name} in the clip factory"))


def stage(st, folder):
    """Upload everything ahead of the post (nothing goes public): each slide as an unpublished Facebook photo, and
    the Instagram carousel's container (each slide as a 6 second MP4 child, then the parent with the caption).
    Each id is saved as soon as Meta gives it."""
    cfg, acct, cards, API, *_ = factory()
    from clipfactory import graph as G
    b = st["built"]
    slides = [os.path.join(folder, s) for s in b["slides"]]
    shas = [sha(p) for p in slides]
    if shas != b["shas"]:
        raise SystemExit("a slide changed after Andrew was shown it: not sent")
    out = st.setdefault("outlets", {})
    if "facebook_feed" in b["targets"]:
        fb = out.setdefault("facebook_feed", {})
        if not fb.get("photo_ids") and not fb.get("id"):
            page = G.meta_keys(acct).page_id
            fb["photo_ids"] = [API._fb_photo(acct, page, p, x) for p, x in zip(slides, shas)]
            note(st, f"Facebook: {len(slides)} photos uploaded (unpublished)")
    if "instagram_carousel" in b["targets"]:
        ig = out.setdefault("instagram_carousel", {})
        if not ig.get("container") and not ig.get("id"):
            mp4s = []
            for p in slides:
                mp4 = p[:-4] + ".mp4"
                if not os.path.exists(mp4):
                    cards._to_mp4(Path(p), Path(mp4))
                mp4s.append(mp4)
            user = API._ig(acct)
            kids = [API._ig_video(acct, user, Path(m), {"media_type": "VIDEO", "is_carousel_item": "true"}, sha(m))
                    for m in mp4s]
            parent = G.gpost(acct, f"{user}/media", form={"media_type": "CAROUSEL", "children": ",".join(kids),
                                                          "caption": b["caption"]})
            pid = str(parent.get("id") or "")
            if not pid:
                raise SystemExit("Instagram made no carousel container")
            API._wait_ready(acct, pid)
            ig.update(children=kids, container=pid, staged_at=now().isoformat(timespec="seconds"))
            note(st, f"Instagram: carousel of {len(kids)} ready (not published)")
    write(st)


def find_ours(acct, API, G, target, since, caption):
    """What went up on that outlet since the try began AND carries this post's words (a news post is a carousel
    too, so the time alone is not enough): {"id", "url"} or None."""
    head = caption.split("\n", 1)[0][:60]
    since = since - datetime.timedelta(minutes=3)
    if target == "facebook_feed":
        rows = G.gget(acct, f"{G.meta_keys(acct).page_id}/feed",
                      {"fields": "id,message,created_time,permalink_url", "limit": 25}).get("data") or []
        for r in rows:
            t = datetime.datetime.strptime(r["created_time"], "%Y-%m-%dT%H:%M:%S%z")
            if t >= since and (r.get("message") or "").startswith(head):
                return {"id": r["id"], "url": r.get("permalink_url") or f"https://www.facebook.com/{r['id']}"}
        return None
    rows = G.gget(acct, f"{API._ig(acct)}/media", {"fields": "id,caption,media_type,timestamp,permalink",
                                                   "limit": 25}).get("data") or []
    for r in rows:
        t = datetime.datetime.strptime(r["timestamp"], "%Y-%m-%dT%H:%M:%S%z")
        if t >= since and r.get("media_type") == "CAROUSEL_ALBUM" and (r.get("caption") or "").startswith(head):
            return {"id": r["id"], "url": r.get("permalink") or ""}
    return None


def publish(st):
    """Make it public: the Facebook post, then the Instagram carousel. A step that may have gone already is looked
    up first; each step is marked before the call that cannot be undone."""
    cfg, acct, cards, API, *_ = factory()
    from clipfactory import graph as G
    b = st["built"]
    out = st["outlets"]
    for target in b["targets"]:
        rec = out.get(target) or {}
        if rec.get("id"):
            continue
        if rec.get("attempt"):                                   # it may have gone: look before anything else
            got = find_ours(acct, API, G, target, datetime.datetime.fromisoformat(rec["attempt"]), b["caption"])
            if got:
                rec.update(got, posted_at=rec["attempt"], how="looked up after an earlier try")
                note(st, f"{WHERE[target]}: it had gone ({got.get('url')})")
                continue
        if target == "instagram_carousel":
            words = API.room_words(API.publish_limit(acct), cards._reels_due(cfg, acct, cards._now(cfg)))
            if words:
                raise SystemExit(words)
        rec["attempt"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
        out[target] = rec
        write(st)
        if target == "facebook_feed":
            page = G.meta_keys(acct).page_id
            form = {f"attached_media[{i}]": json.dumps({"media_fbid": p}) for i, p in enumerate(rec["photo_ids"])}
            form["message"] = b["caption"]
            got = G.gpost(acct, f"{page}/feed", form=form)
            post = str(got.get("id") or "")
            if not post:
                raise SystemExit("Facebook took the post but gave no id back")
            rec.update(id=post, url=f"https://www.facebook.com/{post}")
        else:
            got = API._publish(acct, API._ig(acct), rec["container"], lambda f: None, "carousel")
            rec.update(id=got["id"], url=got.get("url") or "")
        rec["posted_at"] = now().isoformat(timespec="seconds")
        note(st, f"{WHERE[target]}: posted {rec.get('url')}")


# ------------------------------------------------------------------ the steps
def build(st, about, cfg_):
    """morning.sh for the day: trades, holdings, estimate, slides. Fills st["built"] or notes why not."""
    if DRY:
        log(f"(dry run) build: morning.sh --day {about} --post")
        return
    run = subprocess.run(["/bin/bash", os.path.join(HERE, "morning.sh"), "--day", about, "--post"], cwd=HERE,
                         capture_output=True, text=True, timeout=3600)
    tail = (run.stdout + run.stderr).strip().splitlines()[-6:]
    if run.returncode:
        st.setdefault("build_errors", []).append(f"{now():%H:%M} " + " | ".join(tail)[-400:])
        note(st, "build failed: " + (tail[-1] if tail else f"exit {run.returncode}"))
        return
    folder = next((os.path.join(PROJECT, "Daily Posts", f) for f in os.listdir(os.path.join(PROJECT, "Daily Posts"))
                   if f.startswith(datetime.date.fromisoformat(st["post_day"]).strftime("%m.%d "))), None)
    man = json.load(open(os.path.join(folder, "post.json")))
    if man["about"] != about:
        note(st, f"build made {man['about']}, not {about}: not asked")
        return
    targets = [t for t in cfg_["targets"] if t in WHERE]
    st["built"] = {"at": now().isoformat(timespec="seconds"), "folder": folder, "about": about,
                   "slides": man["slides"], "shas": [sha(os.path.join(folder, s)) for s in man["slides"]],
                   "caption": man["caption"], "lead": man["lead"], "targets": targets,
                   "hash": post_hash(folder, man["slides"], man["caption"], targets)}
    note(st, f"built {len(man['slides'])} slides: {folder}")


def ask(st):
    b = st["built"]
    folder = b["folder"]
    where = " and ".join(WHERE[t] for t in b["targets"])
    word = "Yesterday" if (datetime.date.fromisoformat(st["post_day"]) - datetime.date.fromisoformat(b["about"])).days == 1 \
        else datetime.date.fromisoformat(b["about"]).strftime("%A")
    when = config()["post_at"]
    lines = [f"{word}'s biggest winner: {b['lead']}.",
             f"{len(b['slides'])} slides. Goes to {where} at {int(when[:2])}:{when[3:]} (at once if later). Post it?"]
    img = sheet(folder, b["slides"]) if not DRY else None
    ref = f"{st['post_day']} {b['hash']}"
    ok, why = push(f"SCORECARD · {datetime.date.fromisoformat(st['post_day']):%A}", "\n".join(lines), image=img,
                   buttons=[("Post it", f"score post {ref}"), ("No", f"score skip {ref}")])
    st["asked"] = {"at": now().isoformat(timespec="seconds"), "push": why, "ok": ok}
    note(st, f"asked on the phone: {'sent' if ok else 'NOT sent, ' + why}")


def hear(st, today):
    """Read the button presses: the ones for today's slides, as they are now, count."""
    if DRY:
        return
    try:
        got = replies()
    except Exception as ex:  # noqa: BLE001
        log(f"replies not read: {type(ex).__name__}: {ex}")
        return
    for mid, w in got:
        if len(w) == 4 and w[0] == "score" and w[1] in ("post", "skip") and w[2] == str(today):
            b = st.get("built") or {}
            if st.get("answer"):
                log(f"another press ({' '.join(w)}): already answered {st['answer']['verb']}")
            elif w[3] != b.get("hash"):
                st.setdefault("stale", []).append(" ".join(w))
                note(st, "a button for slides that changed since: not counted")
                push("Scorecard: old button", "Those slides changed after they were sent. Not posted.",
                     priority="default")
            elif now() > at(today, config()["answer_until"]):
                st["answer"] = {"verb": "late", "at": now().isoformat(timespec="seconds")}
                note(st, f"Andrew pressed {w[1]} after {config()['answer_until']}: too late, not posted")
                push("Scorecard: too late", f"That came after {config()['answer_until']}. Not posted today.",
                     priority="default")
            else:
                st["answer"] = {"verb": w[1], "at": now().isoformat(timespec="seconds"), "by": "Andrew (phone)"}
                note(st, f"Andrew said {'POST IT' if w[1] == 'post' else 'no'} on his phone")
                if w[1] == "skip":
                    push("Scorecard: not posted", "OK, nothing goes today.", priority="default")
        elif w and w[0] == "score":
            log(f"a press for another day: {' '.join(w)}")
        read_up_to(mid)
    write(st)


def too_busy(ex):
    """Meta's limits on calls (the app's, the Page's, Instagram's): they clear by themselves within the hour."""
    s = str(ex).lower()
    return any(w in s for w in ("request limit reached", "too many calls", "rate limit", "limit has been reached"))


def resting(st, key):
    """True while a failed step waits before its next try (st[key] = the time it may go again)."""
    return bool(st.get(key)) and now() < datetime.datetime.fromisoformat(st[key])


def rest(st, key, minutes):
    st[key] = (now() + datetime.timedelta(minutes=minutes)).isoformat(timespec="seconds")
    write(st)


def tick():
    cfg_ = config()
    t = now()
    today = t.date()
    if cfg_["post"] == "off" or not prices.open_day(today):
        return
    about = prices.previous_open(today)
    st = read(today)
    if st.get("done") or st.get("gave_up"):
        return

    # 0. too late for slides this morning
    if not st.get("built") and t > at(today, cfg_["build_by"]):
        st["gave_up"] = f"no slides by {cfg_['build_by']}"
        note(st, st["gave_up"])
        if st.get("build_errors") or st.get("prices_waiting") or st.get("prices_retry"):   # it tried and failed
            push("Scorecard: none today", "The slides could not be made this morning. " +
                 ((st.get("build_errors") or ["IEX's prices were not out"])[-1])[-180:], priority="default")
        return

    # 1. the prices (the day before too, the first time)
    if t >= at(today, cfg_["prices_from"]) and not resting(st, "prices_retry"):
        for d in (prices.previous_open(about), about):
            if not os.path.exists(os.path.join(prices.CACHE, f"{d}.json")):
                if DRY:
                    log(f"(dry run) would read IEX for {d}")
                    return
                try:
                    if not prices.fetch(d):
                        log(f"IEX {d}: not out yet")
                        if st.get("prices_waiting") != d:
                            st["prices_waiting"] = d
                            write(st)
                        return
                    st.pop("prices_waiting", None)
                    note(st, f"IEX prices for {d} read")
                except Exception as ex:  # noqa: BLE001
                    note(st, f"IEX {d}: {ex}")
                    rest(st, "prices_retry", 15)
                    return

    # 2. the slides, once the House's index is new (or after a wait)
    if not st.get("built") and t >= at(today, cfg_["build_from"]):
        if resting(st, "build_retry"):
            return
        fresh = house_fresh(today)
        if fresh or t >= at(today, cfg_["build_from"]) + datetime.timedelta(minutes=cfg_["build_wait"]):
            if not fresh:
                note(st, "the House's index is not new yet: built with what it has")
            build(st, about, cfg_)
            write(st)
            if not st.get("built"):
                rest(st, "build_retry", 10)
        else:
            log("waiting for the House's index (it updates about 07:00)")
        return                                      # one heavy step per run

    # 3. the ask
    if st.get("built") and not st.get("asked") and t >= at(today, cfg_["ask_from"]):
        if t > at(today, cfg_["answer_until"]):
            st["gave_up"] = f"built after {cfg_['answer_until']}: not asked"
            note(st, st["gave_up"])
            return
        ask(st)

    # 4. the answer
    if st.get("asked") and not st.get("answer"):
        hear(st, today)
        if not st.get("answer") and t > at(today, cfg_["answer_until"]):
            st["gave_up"] = f"no answer by {cfg_['answer_until']}"
            note(st, st["gave_up"] + ": not posted")
            return

    # 5. the post
    if (st.get("answer") or {}).get("verb") == "post" and not st.get("done"):
        if cfg_["post"] == "practice":
            st["done"] = "practice"
            note(st, "practice: everything but the Graph calls; nothing posted")
            push("Scorecard (practice)", "Practice mode: nothing was posted.", priority="default")
            return
        if DRY:
            log("(dry run) would stage and post")
            return
        if resting(st, "post_retry"):
            return
        try:
            cfg, acct, cards, API, outlets, outward, switches = factory()
            why = blocked(cfg, acct, outlets, outward, switches)
            if why:
                if st.get("waiting") != why:
                    st["waiting"] = why
                    note(st, f"waits: {why}")
                    push("Scorecard waits", why[:300], priority="default")
                return
            stage(st, st["built"]["folder"])
            if now() < at(today, cfg_["post_at"]):
                return                              # staged: it goes public at post_at
            publish(st)
            st["done"] = "posted"
            links = "\n".join(f"{WHERE[k]}: {v.get('url')}" for k, v in st["outlets"].items())
            note(st, "posted")
            push("✅ Scorecard posted", links or "Posted.", priority="default")
        except (Exception, SystemExit) as ex:  # noqa: BLE001
            if too_busy(ex):                        # Meta's limit on calls: it clears by itself, so wait, don't count
                gone = [WHERE[k] for k, v in (st.get("outlets") or {}).items() if v.get("id")]
                if now() > at(today, cfg_["busy_until"]):
                    st["gave_up"] = f"Meta's limit on calls had not cleared by {cfg_['busy_until']}"
                    note(st, st["gave_up"])
                    push("⚠️ Scorecard not posted", (f"{' and '.join(gone)} went up. " if gone else "") +
                         f"Meta said too many calls all morning, so the rest did not go.", priority="default")
                    return
                rest(st, "post_retry", cfg_["busy_wait"])
                note(st, f"Meta says too many calls ({str(ex)[-60:]}): next try {st['post_retry'][11:16]}")
                return
            st.setdefault("post_errors", []).append(f"{now():%H:%M} {type(ex).__name__}: {ex}"[:400])
            note(st, f"post try failed: {type(ex).__name__}: {ex}")
            if len(st["post_errors"]) == 3:
                push("⚠️ Scorecard not posted", f"{type(ex).__name__}: {ex}"[:300], priority="default")
            if len(st["post_errors"]) >= 6:
                st["gave_up"] = "six tries failed"
                write(st)


def house_fresh(today):
    """True when the House's yearly index was updated this morning (its Last-Modified)."""
    if DRY:
        return True
    try:
        req = urllib.request.Request(f"https://disclosures-clerk.house.gov/public_disc/financial-pdfs/{today.year}FD.zip",
                                     method="HEAD", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            mod = r.headers.get("Last-Modified")
        when = datetime.datetime.strptime(mod, "%a, %d %b %Y %H:%M:%S GMT").replace(tzinfo=datetime.timezone.utc)
        return when.astimezone().date() == today
    except Exception:  # noqa: BLE001
        return False


def status(day):
    st = read(day)
    print(f"Scorecard {day} ({'market open' if prices.open_day(day) else 'market shut'}), config {config()['post']}")
    for k in ("built", "asked", "answer", "outlets", "done", "gave_up", "waiting"):
        if st.get(k):
            print(f"  {k}: {json.dumps(st[k])[:300]}")
    for n in st.get("notes", [])[-12:]:
        print("  .", n)


def install():
    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
 <key>Label</key><string>{LABEL}</string>
 <key>ProgramArguments</key><array><string>{PY}</string><string>-E</string><string>{os.path.join(HERE, 'daily.py')}</string><string>tick</string></array>
 <key>WorkingDirectory</key><string>{HERE}</string>
 <key>StartInterval</key><integer>120</integer>
 <key>RunAtLoad</key><false/>
 <key>EnvironmentVariables</key><dict><key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string></dict>
 <key>StandardOutPath</key><string>{os.path.join(HERE, 'logs', 'daily.log')}</string>
 <key>StandardErrorPath</key><string>{os.path.join(HERE, 'logs', 'daily.log')}</string>
</dict></plist>
"""
    os.makedirs(os.path.join(HERE, "logs"), exist_ok=True)
    open(PLIST, "w").write(plist)
    subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}/{LABEL}"], capture_output=True)
    r = subprocess.run(["launchctl", "bootstrap", f"gui/{os.getuid()}", PLIST], capture_output=True, text=True)
    print(f"{LABEL}: {'loaded' if r.returncode == 0 else 'NOT loaded: ' + r.stderr.strip()} ({PLIST})")


def remove():
    subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}/{LABEL}"], capture_output=True)
    if os.path.exists(PLIST):
        os.remove(PLIST)
    print(f"{LABEL}: removed")


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "status"
    if what == "tick":
        tick()
    elif what == "status":
        d = sys.argv[sys.argv.index("--day") + 1] if "--day" in sys.argv else now().date().isoformat()
        status(datetime.date.fromisoformat(d))
    elif what == "install":
        install()
    elif what == "remove":
        remove()
    else:
        sys.exit(__doc__)
