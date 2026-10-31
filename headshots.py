"""Headshots for the scorecard: every person cut out of their portrait (tools/cutout.swift), set on one
backdrop, with the same head size and eye line in every slot of a kind.

shot(pid, "board") -> "shots/<pid>-board.png" (relative to the build folder)
"""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
PLATE = (40, 42, 46)          # the one backdrop every headshot sits on

# slot: (width, height, face height as a share of the slot height, headroom above the hair as a share of the height)
# The small slots crop tight on purpose: a Congress directory photo can have a face 64% as tall as the photo is
# wide, and a looser crop runs out of photo at the sides, so that one head comes out bigger than the rest.
# Here the face is 65% of the slot's width, so every head in a table is the same size.
SLOTS = {
    "hero": (340, 420, 0.40, 0.08),
    "roomy": (82, 96, 0.55, 0.07),
    "big": (104, 122, 0.55, 0.07),
    "board": (64, 76, 0.55, 0.07),
    "cab": (293, 298, 0.50, 0.08),
    "hold": (116, 150, 0.50, 0.07),
    "trade": (84, 100, 0.55, 0.07),
    "mini": (56, 66, 0.55, 0.07),
}
_faces = None


def _face(pid):
    global _faces
    if _faces is None:
        known = os.path.join(HERE, "cut", "faces.json")
        rows = json.load(open(known)) if os.path.exists(known) else []     # a fresh copy has none yet
        _faces = {r["file"][:-4]: r for r in rows}
    return _faces[pid]["face"]


def shot(pid, slot):
    from PIL import Image, ImageFilter
    sw, sh, frac, room = SLOTS[slot]
    rel = f"shots/{pid}-{slot}.png"
    out = os.path.join(HERE, rel)
    src = os.path.join(HERE, "cut", pid + ".png")
    if os.path.exists(out) and os.path.getmtime(out) > max(os.path.getmtime(src), os.path.getmtime(__file__)):
        return rel
    os.makedirs(os.path.dirname(out), exist_ok=True)
    cut = Image.open(src).convert("RGBA")
    edge = cut.getchannel("A").filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.7))
    cut.putalpha(edge)                                  # pull the edge in a pixel so no old background shows
    W, H = cut.size
    fx, fy, fw, fh = _face(pid)
    fx, fy, fw, fh = fx * W, fy * H, fw * W, fh * H
    fcx, fcy = fx + fw / 2, fy + fh / 2

    alpha = cut.getchannel("A")
    above = alpha.crop((int(fx), 0, int(fx + fw), int(fcy))).point(lambda v: 255 if v > 128 else 0).getbbox()
    crown = above[1] if above else max(0, fy - 0.6 * fh)   # the top of the hair, straight above the face
    hair_at_top = crown <= 2                            # the photo itself cuts the hair: no headroom above it
    room = 0 if hair_at_top else room

    s = frac * sh / fh                                  # the scale that gives the standard head size
    s = max(s, sw / W)                                  # never wider than the photo (no cut shoulders)
    s = max(s, sh * (1 - room) / (H - crown))           # never past the photo's bottom (no gap under the chest)
    cw, ch = sw / s, sh / s
    x0 = min(max(fcx - cw / 2, 0), W - cw)
    y0 = min(crown - room * sh / s, H - ch)             # the same headroom above every head

    face = cut.crop((round(x0), round(y0), round(x0 + cw), round(y0 + ch))).resize((sw, sh), Image.LANCZOS)
    plate = Image.new("RGBA", (sw, sh), PLATE + (255,))
    plate.alpha_composite(face)
    plate.convert("RGB").save(out)
    return rel


if __name__ == "__main__":                              # a check sheet of every face in the hero and cabinet slots
    from PIL import Image
    pids = sorted(f[:-4] for f in os.listdir(os.path.join(HERE, "cut")) if f.endswith(".png"))
    sheet = Image.new("RGB", (8 * 180, ((len(pids) + 7) // 8) * 360), (12, 12, 12))
    for i, p in enumerate(pids):
        a = Image.open(os.path.join(HERE, shot(p, "hero"))).resize((170, 210))
        b = Image.open(os.path.join(HERE, shot(p, "board"))).resize((128, 152))
        x, y = (i % 8) * 180, (i // 8) * 360
        sheet.paste(a, (x + 5, y + 5))
        sheet.paste(b, (x + 5, y + 210))
    sheet.save("/private/tmp/claude-501/shots.jpg", quality=88)
    print(len(pids), "people")
