"""Browser screenshots: toolbars in the page flow at a narrow window (map with the
analysis panel open, expanded sounding view), the hover readout of the sounding
graphics, the Series tab's plot settings.
Usage: python tests/ui18.py URL OUTDIR PROFILE_DIR"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shot import FF, click, click_text  # noqa: E402
from ui13 import click_label  # noqa: E402

# bounding boxes of elements matching a selector, also inside shadow roots
RECTS = r"""
((sel) => { const out = []; const walk = (root) => { root.querySelectorAll('*').forEach(el => {
    if (el.matches(sel)) { const r = el.getBoundingClientRect();
      if (r.width) out.push([r.x, r.y, r.width, r.height]); }
    if (el.shadowRoot) walk(el.shadowRoot); }); }; walk(document); return JSON.stringify(out); })
"""


SCROLL_TO = r"""
((sel, n) => { const hits = []; const walk = (root) => { root.querySelectorAll('*').forEach(el => {
    if (el.matches(sel)) hits.push(el); if (el.shadowRoot) walk(el.shadowRoot); }); };
  walk(document); if (hits[n]) hits[n].scrollIntoView({block: 'center'}); return hits.length; })
"""


def rects(ff, sel):
    return json.loads(ff.js(RECTS + f"({json.dumps(sel)})"))


def move(ff, x, y):
    ff.cmd("input.performActions", {"context": ff.ctx, "actions": [{
        "type": "pointer", "id": "mouse", "parameters": {"pointerType": "mouse"},
        "actions": [{"type": "pointerMove", "x": int(x), "y": int(y)}]}]})


def main():
    url, out, prof = sys.argv[1:4]
    os.makedirs(out, exist_ok=True)
    ff = FF(w=1280, h=800, prof=prof)
    try:
        ff.go(url)
        time.sleep(12)
        click_text(ff, "Sounding")
        time.sleep(1)
        canvas = max(rects(ff, "canvas"), key=lambda r: r[2] * r[3])
        click(ff, canvas[0] + canvas[2] * 0.45, canvas[1] + canvas[3] * 0.55)
        time.sleep(45)
        ff.shot(f"{out}/a_panel_open.png")
        # expand: a click on the skew-T image opens the expanded view
        z = rects(ff, ".zv")
        click(ff, z[0][0] + z[0][2] / 2, z[0][1] + z[0][3] / 2)
        time.sleep(8)
        ff.shot(f"{out}/b_expanded.png")
        z = rects(ff, ".zv")
        x, y, w, h = z[0]
        move(ff, x + w * 0.30, y + h * 0.45)   # skew-T
        time.sleep(1)
        ff.shot(f"{out}/c_hover_skew.png")
        move(ff, x + w * 0.78, y + h * 0.50)   # hodograph
        time.sleep(1)
        ff.shot(f"{out}/d_hover_hodo.png")
        if len(z) > 1:
            ff.js(SCROLL_TO + "('.zv', 1)")
            time.sleep(1)
            x, y, w, h = rects(ff, ".zv")[1]
            move(ff, x + w * 0.5, y + h * 0.5)  # profiles
            time.sleep(1)
            ff.shot(f"{out}/e_hover_prof.png")
        click_text(ff, "Map")
        time.sleep(3)
        click_label(ff, "Series")
        time.sleep(2)
        click_text(ff, "⚙ Plot")
        time.sleep(2)
        ff.shot(f"{out}/f_series_plot.png")
        click_text(ff, "3D")
        time.sleep(4)
        ff.shot(f"{out}/g_3d.png")
        click_text(ff, "Figure")
        time.sleep(15)
        ff.shot(f"{out}/h_figure.png")
    finally:
        ff.close()


if __name__ == "__main__":
    main()
