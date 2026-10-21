"""Minimal WebDriver BiDi client for headless Firefox: open URL, run JS, screenshot."""
import base64, json, subprocess, sys, time, os
import websocket  # websocket-client, in environment.yml

class FF:
    def __init__(self, w=1600, h=950, port=9333, prof=None):
        self.p = subprocess.Popen(["firefox", "--headless", "--no-remote", "--profile", prof,
                                   f"--remote-debugging-port={port}",
                                   f"--width={w}", f"--height={h}"],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.ws = None
        for _ in range(60):
            try:
                self.ws = websocket.create_connection(f"ws://127.0.0.1:{port}/session", timeout=120, suppress_origin=True)
                break
            except Exception:
                time.sleep(0.5)
        self.n = 0
        self.cmd("session.new", {"capabilities": {}})
        self.ctx = self.cmd("browsingContext.getTree", {})["contexts"][0]["context"]
        self.cmd("browsingContext.setViewport", {"context": self.ctx, "viewport": {"width": w, "height": h}})

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
        self.cmd("browsingContext.navigate", {"context": self.ctx, "url": url, "wait": "complete"})

    def js(self, expr):
        r = self.cmd("script.evaluate", {"expression": expr, "target": {"context": self.ctx},
                                         "awaitPromise": True})
        return r.get("result", {}).get("value")

    def shot(self, path):
        r = self.cmd("browsingContext.captureScreenshot", {"context": self.ctx})
        open(path, "wb").write(base64.b64decode(r["data"]))

    def close(self):
        if self.ws is None:
            self.p.terminate()
            return
        try: self.cmd("session.end", {})
        except Exception: pass
        self.p.terminate()


def click(ff, x, y):
    """Real mouse click at viewport coordinates (WebDriver BiDi input actions)."""
    ff.cmd("input.performActions", {"context": ff.ctx, "actions": [{
        "type": "pointer", "id": "mouse", "parameters": {"pointerType": "mouse"},
        "actions": [{"type": "pointerMove", "x": int(x), "y": int(y)},
                    {"type": "pointerDown", "button": 0}, {"type": "pause", "duration": 60},
                    {"type": "pointerUp", "button": 0}]}]})


FIND = r"""
((txt) => { let hit = null; const walk = (root) => {
  root.querySelectorAll('*').forEach(el => {
    if (!hit && (el.tagName === 'BUTTON') && (el.textContent || '').trim() === txt) {
      const r = el.getBoundingClientRect(); if (r.width) hit = [r.x + r.width / 2, r.y + r.height / 2]; }
    if (el.shadowRoot) walk(el.shadowRoot); }); };
  walk(document); return JSON.stringify(hit); })
"""


def click_text(ff, txt):
    import json
    pos = json.loads(ff.js(FIND + f"({json.dumps(txt)})"))
    if pos is None:
        raise RuntimeError(f"no button {txt!r}")
    click(ff, *pos)
