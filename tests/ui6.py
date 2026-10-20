"""Browser screenshots of the new UI (headless Firefox via tests/shot.py).
Usage: python tests/ui6.py URL OUTDIR PROFILE_DIR"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shot import FF, click, click_text  # noqa: E402

FIND_SEL = r"""
((sel) => { const out = []; const walk = (root) => {
  root.querySelectorAll(sel).forEach(el => { const r = el.getBoundingClientRect();
    if (r.width > 20 && r.height > 20) out.push([r.x, r.y, r.width, r.height]); });
  root.querySelectorAll('*').forEach(el => { if (el.shadowRoot) walk(el.shadowRoot); }); };
  walk(document); return JSON.stringify(out); })
"""


def rects(ff, sel):
    return json.loads(ff.js(FIND_SEL + f"({json.dumps(sel)})"))


def drag(ff, x0, y0, x1, y1, shift=False):
    acts = [{"type": "pointerMove", "x": int(x0), "y": int(y0)},
            {"type": "pointerDown", "button": 0}]
    acts += [{"type": "pointerMove", "x": int(x0 + (x1 - x0) * f), "y": int(y0 + (y1 - y0) * f),
              "duration": 40} for f in (0.25, 0.5, 0.75, 1.0)]
    acts += [{"type": "pointerUp", "button": 0}]
    actions = [{"type": "pointer", "id": "mouse", "parameters": {"pointerType": "mouse"},
                "actions": acts}]
    if shift:
        keys = [{"type": "keyDown", "value": ""}] + [{"type": "pause"}] * (len(acts) - 1)
        keys += [{"type": "keyUp", "value": ""}]
        actions.insert(0, {"type": "key", "id": "kbd", "actions": keys[:len(acts) + 1]})
    ff.cmd("input.performActions", {"context": ff.ctx, "actions": actions})


def main():
    url, out, prof = sys.argv[1:4]
    os.makedirs(out, exist_ok=True)
    ff = FF(prof=prof)
    try:
        ff.go(url)
        time.sleep(8)
        ff.shot(f"{out}/a_start.png")
        cv = max(rects(ff, "canvas"), key=lambda r: r[2] * r[3])
        print("map canvas", cv)
        click_text(ff, "Area sounding")
        time.sleep(1)
        x, y, w, h = cv
        drag(ff, x + w * 0.36, y + h * 0.45, x + w * 0.46, y + h * 0.58)
        time.sleep(40)
        ff.shot(f"{out}/b_area.png")
        imgs = rects(ff, ".zv")
        print("zoom images", imgs)
        click(ff, imgs[0][0] + imgs[0][2] / 2, imgs[0][1] + imgs[0][3] / 2)
        time.sleep(4)
        ff.shot(f"{out}/c_expanded.png")
        imgs = rects(ff, ".zv")
        print("zoom images (expanded)", imgs)
        zx, zy, zw, zh = imgs[0]
        drag(ff, zx + zw * 0.08, zy + zh * 0.55, zx + zw * 0.35, zy + zh * 0.92)
        time.sleep(1.5)
        ff.shot(f"{out}/d_boxzoom.png")
        click_text(ff, "Map")
        time.sleep(3)
        click_text(ff, "Cross-section")
        time.sleep(1)
        cv = max(rects(ff, "canvas"), key=lambda r: r[2] * r[3])
        x, y, w, h = cv
        click(ff, x + w * 0.25, y + h * 0.5)
        time.sleep(1)
        click(ff, x + w * 0.45, y + h * 0.55)
        time.sleep(45)
        ff.shot(f"{out}/e_xsec.png")
    finally:
        ff.close()


if __name__ == "__main__":
    main()
