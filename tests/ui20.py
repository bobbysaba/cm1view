"""Browser screenshots of the settings: the first-run window on the page without a run,
the runs found after saving, then the ⚙ window in the viewer (with its config-file tab).
Start the server with a fresh CM1VIEW_CONFIG and no run argument.
Usage: python tests/ui20.py URL RUN OUTDIR PROFILE_DIR"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shot import FF, click, click_text  # noqa: E402

ICON = r"""
((cls) => { let hit = null; const walk = (root) => {
  root.querySelectorAll('*').forEach(el => {
    if (!hit && el.classList && el.classList.contains(cls)) {
      const b = el.closest('button') || el; b.scrollIntoView({block: 'center'});
      const r = b.getBoundingClientRect();
      if (r.width) hit = [r.x + r.width / 2, r.y + r.height / 2]; }
    if (el.shadowRoot) walk(el.shadowRoot); }); };
  walk(document); return JSON.stringify(hit); })
"""

TEXT = r"""
((txt) => { let hit = null; const walk = (root) => {
  root.querySelectorAll('*').forEach(el => {
    if (!hit && el.children.length === 0 && (el.textContent || '').trim() === txt) {
      el.scrollIntoView({block: 'center'}); const r = el.getBoundingClientRect(); if (r.width) hit = [r.x + r.width / 2, r.y + r.height / 2]; }
    if (el.shadowRoot) walk(el.shadowRoot); }); };
  walk(document); return JSON.stringify(hit); })
"""


def click_any(ff, js, arg):
    pos = json.loads(ff.js(js + f"({json.dumps(arg)})"))
    if pos is None:
        raise RuntimeError(f"not found: {arg!r}")
    click(ff, *pos)


def main():
    url, run, out, prof = sys.argv[1:5]
    os.makedirs(out, exist_ok=True)
    ff = FF(w=1280, h=900, prof=prof)
    try:
        ff.go(url)
        time.sleep(8)
        ff.shot(f"{out}/a_first_run.png")
        click_any(ff, TEXT, "More settings")
        time.sleep(1.5)
        ff.shot(f"{out}/b_more.png")
        click_text(ff, "Save and continue")
        time.sleep(6)
        ff.shot(f"{out}/c_landing.png")
        ff.go(url + "?run=" + run)
        time.sleep(14)
        click_any(ff, ICON, "ti-settings")
        time.sleep(3)
        ff.shot(f"{out}/d_settings.png")
        click_any(ff, TEXT, "Advanced (server and performance)")
        time.sleep(1.5)
        ff.shot(f"{out}/e_advanced.png")
        click_any(ff, TEXT, "Config file")
        time.sleep(1.5)
        ff.shot(f"{out}/f_file.png")
    finally:
        ff.close()


if __name__ == "__main__":
    main()
