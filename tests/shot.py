"""Minimal WebDriver BiDi client for headless Firefox: open a URL, run JS, click, drag,
take screenshots.  Used by test_browser.py (pytest -m browser).  Firefox is found on
PATH, or set $FIREFOX to its executable."""
import base64
import json
import os
import shutil
import subprocess
import time

import websocket  # websocket-client, in environment.yml


def firefox():
    """The Firefox executable, or None."""
    return os.environ.get("FIREFOX") or shutil.which("firefox")


class FF:
    def __init__(self, w=1600, h=950, port=9333, prof=None):
        self.p = subprocess.Popen([firefox(), "--headless", "--no-remote", "--profile", prof,
                                   f"--remote-debugging-port={port}",
                                   f"--width={w}", f"--height={h}"],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.ws = None
        for _ in range(60):
            try:
                self.ws = websocket.create_connection(f"ws://127.0.0.1:{port}/session",
                                                      timeout=120, suppress_origin=True)
                break
            except Exception:  # noqa: BLE001
                time.sleep(0.5)
        if self.ws is None:
            self.p.terminate()
            raise RuntimeError("headless Firefox did not start")
        self.n = 0
        self.cmd("session.new", {"capabilities": {}})
        self.ctx = self.cmd("browsingContext.getTree", {})["contexts"][0]["context"]
        self.cmd("browsingContext.setViewport", {"context": self.ctx,
                                                 "viewport": {"width": w, "height": h}})

    def cmd(self, method, params):
        self.n += 1
        self.ws.send(json.dumps({"id": self.n, "method": method, "params": params}))
        while True:
            m = json.loads(self.ws.recv())
            if m.get("id") == self.n:
                if m.get("type") == "error":
                    raise RuntimeError(m)
                return m["result"]

    def go(self, url):
        self.cmd("browsingContext.navigate", {"context": self.ctx, "url": url,
                                              "wait": "complete"})

    def js(self, expr):
        r = self.cmd("script.evaluate", {"expression": expr, "target": {"context": self.ctx},
                                         "awaitPromise": True})
        return r.get("result", {}).get("value")

    def shot(self, path):
        r = self.cmd("browsingContext.captureScreenshot", {"context": self.ctx})
        with open(path, "wb") as f:
            f.write(base64.b64decode(r["data"]))

    def close(self):
        if self.ws is not None:
            try:
                self.cmd("session.end", {})
            except Exception:  # noqa: BLE001
                pass
        self.p.terminate()


def _pointer(ff, acts):
    ff.cmd("input.performActions", {"context": ff.ctx, "actions": [{
        "type": "pointer", "id": "mouse", "parameters": {"pointerType": "mouse"},
        "actions": acts}]})


def click(ff, x, y):
    """Real mouse click at viewport coordinates."""
    _pointer(ff, [{"type": "pointerMove", "x": int(x), "y": int(y)},
                  {"type": "pointerDown", "button": 0}, {"type": "pause", "duration": 60},
                  {"type": "pointerUp", "button": 0}])


def move(ff, x, y):
    _pointer(ff, [{"type": "pointerMove", "x": int(x), "y": int(y)}])


def drag(ff, x0, y0, x1, y1):
    acts = [{"type": "pointerMove", "x": int(x0), "y": int(y0)},
            {"type": "pointerDown", "button": 0}]
    acts += [{"type": "pointerMove", "x": int(x0 + (x1 - x0) * f),
              "y": int(y0 + (y1 - y0) * f), "duration": 40} for f in (0.25, 0.5, 0.75, 1.0)]
    _pointer(ff, acts + [{"type": "pointerUp", "button": 0}])


# elements are searched inside shadow roots too (Panel / Bokeh widgets use them)
_WALK = r"""
const walk = (root, fn) => { root.querySelectorAll('*').forEach(el => {
  fn(el); if (el.shadowRoot) walk(el.shadowRoot, fn); }); };
"""

RECTS = "(() => {" + _WALK + r"""
return (sel) => { const out = []; walk(document, el => { if (el.matches(sel)) {
  const r = el.getBoundingClientRect(); if (r.width) out.push([r.x, r.y, r.width, r.height]); }});
  return JSON.stringify(out); }; })()
"""

# the centre of the first visible element whose own text is `txt` (a button, a tab
# header, a label), or of the first element with that title / class
FIND = "(() => {" + _WALK + r"""
return (how, txt) => { let hit = null; walk(document, el => { if (hit) return;
  const ok = how === 'text' ? (el.children.length === 0 || el.tagName === 'BUTTON')
             && (el.textContent || '').trim() === txt
           : how === 'title' ? el.getAttribute('title') === txt
           : el.classList && el.classList.contains(txt);
  if (!ok) return;
  const b = el.closest('button') || el; b.scrollIntoView({block: 'center'});
  const r = b.getBoundingClientRect(); if (r.width) hit = [r.x + r.width / 2, r.y + r.height / 2];
  }); return JSON.stringify(hit); }; })()
"""


def rects(ff, sel):
    return json.loads(ff.js(f"{RECTS}({json.dumps(sel)})"))


def find(ff, txt, how="text"):
    return json.loads(ff.js(f"{FIND}({json.dumps(how)}, {json.dumps(txt)})"))


def click_text(ff, txt, how="text"):
    """Click the element showing `txt` (how='title': with that tooltip; 'class': with
    that CSS class, e.g. an icon)."""
    pos = find(ff, txt, how)
    if pos is None:
        raise RuntimeError(f"not found: {txt!r}")
    click(ff, *pos)


def until(pred, tmax=60, step=0.5):
    """Poll pred() until true (returns its value); None after tmax seconds."""
    t0 = time.time()
    while time.time() - t0 < tmax:
        v = pred()
        if v:
            return v
        time.sleep(step)
    return None
