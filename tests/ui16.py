"""Browser screenshots: Figure workspace phase 3 -- soundings (Layers tab), time-height
(Layers + Region tabs), Annotate tab, map with streamlines.
Usage: python tests/ui16.py URL OUTDIR PROFILE_DIR"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shot import FF, click_text  # noqa: E402
from ui13 import click_label  # noqa: E402

SET_SELECT = r"""
((opt) => { let done = false; const walk = (root) => { root.querySelectorAll('*').forEach(el => {
    if (!done && el.tagName === 'SELECT' && [...el.options].some(o => o.text === opt)) {
      const o = [...el.options].find(o => o.text === opt);
      el.value = o.value; el.dispatchEvent(new Event('change', {bubbles: true})); done = true; }
    if (el.shadowRoot) walk(el.shadowRoot); }); }; walk(document); return done; })
"""


def select(ff, opt):
    print("select", opt, ff.js(SET_SELECT + f"({json.dumps(opt)})"))


def main():
    url, out, prof = sys.argv[1:4]
    os.makedirs(out, exist_ok=True)
    ff = FF(prof=prof)
    try:
        ff.go(url)
        time.sleep(10)
        click_text(ff, "Winds ▾")
        time.sleep(1)
        select(ff, "Streamlines")
        ff.js(r"""(() => { const walk = (root) => { root.querySelectorAll('*').forEach(el => {
            if (el.tagName === 'INPUT' && el.type === 'checkbox' && !el.checked
                && el.closest && el.parentElement) {}
            if (el.shadowRoot) walk(el.shadowRoot); }); }; walk(document); })()""")
        time.sleep(1)
        ff.shot(f"{out}/a_winds_drawer.png")
        click_text(ff, "Figure")
        time.sleep(10)
        click_text(ff, "Soundings")
        time.sleep(40)
        click_label(ff, "Layers")
        time.sleep(2)
        ff.shot(f"{out}/b_soundings.png")
        select(ff, "Time–height (series)")
        time.sleep(90)
        ff.shot(f"{out}/c_th_layers.png")
        click_label(ff, "Region")
        time.sleep(2)
        ff.shot(f"{out}/d_th_region.png")
        click_label(ff, "Annotate")
        time.sleep(2)
        ff.shot(f"{out}/e_annotate.png")
    finally:
        ff.close()


if __name__ == "__main__":
    main()
