"""Browser screenshots: dark run picker with folders, zoomed skew-T with axes, m/hPa
toggle.  Usage: python tests/ui9.py URL OUTDIR PROFILE_DIR"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shot import FF, click, click_text  # noqa: E402
from ui6 import drag, rects  # noqa: E402

FIND_TEXT = r"""
((txt) => { let hit = null; const walk = (root) => {
  root.querySelectorAll('*').forEach(el => {
    if (!hit && (el.tagName === "BUTTON" || el.children.length === 0) && (el.textContent || '').includes(txt)) {
      const r = el.getBoundingClientRect(); if (r.width) hit = [r.x + r.width / 2, r.y + r.height / 2]; }
    if (el.shadowRoot) walk(el.shadowRoot); }); };
  walk(document); return JSON.stringify(hit); })
"""


def main():
    url, out, prof = sys.argv[1:4]
    os.makedirs(out, exist_ok=True)
    ff = FF(prof=prof)
    try:
        ff.go(url)
        time.sleep(8)
        pos = json.loads(ff.js(FIND_TEXT + '("test/initiation/c")'))
        click(ff, *pos)
        time.sleep(3)
        ff.shot(f"{out}/a_picker.png")
        ff.go(url)
        time.sleep(8)
        click_text(ff, "Sounding")
        time.sleep(1)
        x, y, w, h = max(rects(ff, "canvas"), key=lambda r: r[2] * r[3])
        click(ff, x + w * 0.36, y + h * 0.56)
        time.sleep(35)
        z = rects(ff, ".zv")[0]
        click(ff, z[0] + z[2] / 2, z[1] + z[3] / 2)  # expand
        time.sleep(4)
        ff.shot(f"{out}/b_expanded.png")
        zx, zy, zw, zh = rects(ff, ".zv")[0]
        drag(ff, zx + zw * 0.08, zy + zh * 0.50, zx + zw * 0.36, zy + zh * 0.92)
        time.sleep(5)
        ff.shot(f"{out}/c_zoomed.png")
        tog = rects(ff, "td.tog")
        print("toggles:", len(tog))
        click(ff, tog[0][0] + tog[0][2] / 2, tog[0][1] + tog[0][3] / 2)
        click(ff, tog[3][0] + tog[3][2] / 2, tog[3][1] + tog[3][3] / 2)
        time.sleep(1.5)
        ff.shot(f"{out}/d_hpa.png")
    finally:
        ff.close()


if __name__ == "__main__":
    main()
