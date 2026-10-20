"""Browser screenshots: Series tab (line + time-height), pan of a zoomed skew-T.
Usage: python tests/ui13.py URL OUTDIR PROFILE_DIR"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shot import FF, click, click_text  # noqa: E402
from ui6 import drag, rects  # noqa: E402
from ui9 import FIND_TEXT  # noqa: E402


def click_label(ff, txt):
    """Click any element showing `txt` (tab headers are not buttons)."""
    import json
    pos = json.loads(ff.js(FIND_TEXT + f"({json.dumps(txt)})"))
    click(ff, *pos)


SET_INPUT = r"""
((val) => { const walk = (root) => { root.querySelectorAll('*').forEach(el => {
    if (el.tagName === 'INPUT' && (el.value || '').endsWith('.nc')) {
      el.value = val; el.dispatchEvent(new Event('change', {bubbles: true})); }
    if (el.shadowRoot) walk(el.shadowRoot); }); }; walk(document); })
"""


def main():
    url, out, prof = sys.argv[1:4]
    os.makedirs(out, exist_ok=True)
    ff = FF(prof=prof)
    try:
        ff.go(url)
        time.sleep(10)
        # sounding, expand, box zoom, then pan
        click_text(ff, "Sounding")
        time.sleep(1)
        x, y, w, h = max(rects(ff, "canvas"), key=lambda r: r[2] * r[3])
        click(ff, x + w * 0.36, y + h * 0.56)
        time.sleep(35)
        z = rects(ff, ".zv")[0]
        click(ff, z[0] + z[2] / 2, z[1] + z[3] / 2)  # expand
        time.sleep(4)
        zx, zy, zw, zh = rects(ff, ".zv")[0]
        drag(ff, zx + zw * 0.08, zy + zh * 0.50, zx + zw * 0.36, zy + zh * 0.92)
        time.sleep(5)
        ff.shot(f"{out}/a_zoomed.png")
        drag(ff, zx + zw * 0.20, zy + zh * 0.70, zx + zw * 0.30, zy + zh * 0.60)
        time.sleep(5)
        ff.shot(f"{out}/b_panned.png")
        click_text(ff, "Map")  # back from the expanded view
        time.sleep(2)
        click_label(ff, "Series")
        time.sleep(2)
        click_text(ff, "Compute")
        time.sleep(25)
        ff.shot(f"{out}/c_series.png")
        if len(sys.argv) > 4:  # a saved layer series: load it, show time-height
            ff.js(SET_INPUT + f"({json.dumps(sys.argv[4])})")
            time.sleep(1)
            click_text(ff, "Load")
            time.sleep(3)
            click_label(ff, "Time–height")
            time.sleep(3)
            ff.shot(f"{out}/d_time_height.png")
    finally:
        ff.close()


if __name__ == "__main__":
    main()
