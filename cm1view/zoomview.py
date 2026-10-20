"""Zoomable image (the sounding graphics): box-zoom, pan, pinch / Ctrl-wheel zoom.

Not interactive (narrow panel): a click increments `clicks`, which the app uses to
open the expanded view.  Interactive: drag a box to zoom into it, Shift- or
right-drag to pan, Ctrl/Cmd + wheel (or pinch) to zoom about the cursor,
double-click to reset.  The zoom is kept when a new image of the same shape
arrives, so stepping through time keeps the same close-up.
"""

import param
from panel.custom import JSComponent


class ZoomImage(JSComponent):
    src = param.String(default="", doc="image URL (usually a data: URI)")
    filename = param.String(default="sounding.svg", doc="name used by the save button")
    interactive = param.Boolean(default=False)
    clicks = param.Integer(default=0)

    _esm = r"""
export function render({ model, el }) {
  const box = document.createElement('div'); box.className = 'zv';
  const img = document.createElement('img'); img.draggable = false;
  const band = document.createElement('div'); band.className = 'band';
  const bar = document.createElement('div'); bar.className = 'bar';
  const hint = document.createElement('div'); hint.className = 'hint';
  hint.textContent = 'drag: zoom to box · shift-drag: pan · ctrl/⌘-scroll or pinch: zoom · double-click: reset';
  const btn = (txt, title, fn) => {
    const b = document.createElement('button'); b.textContent = txt; b.title = title;
    b.onpointerdown = (e) => e.stopPropagation();
    b.onclick = (e) => { e.stopPropagation(); fn(); }; bar.append(b); return b; };
  box.append(img, band, bar, hint); el.append(box);

  let s = 1, tx = 0, ty = 0, drag = null, aspect = null;
  const W = () => box.clientWidth, H = () => box.clientHeight;
  function clamp() {
    s = Math.min(Math.max(s, 1), 25);
    tx = Math.min(0, Math.max(W() - W() * s, tx));
    ty = Math.min(0, Math.max(H() - H() * s, ty));
  }
  function apply() {
    clamp();
    img.style.transform = `translate(${tx}px, ${ty}px) scale(${s})`;
    box.classList.toggle('zoomed', s > 1.001);
  }
  function zoomAt(cx, cy, ns) {
    ns = Math.min(Math.max(ns, 1), 25);
    tx = cx - (cx - tx) * ns / s; ty = cy - (cy - ty) * ns / s; s = ns; apply();
  }
  function reset() { s = 1; tx = 0; ty = 0; apply(); }
  btn('+', 'Zoom in', () => zoomAt(W() / 2, H() / 2, s * 1.5));
  btn('−', 'Zoom out', () => zoomAt(W() / 2, H() / 2, s / 1.5));
  btn('⟲', 'Reset (double-click)', reset);
  btn('⤓', 'Save image', () => {
    const a = document.createElement('a'); a.href = model.src; a.download = model.filename;
    document.body.append(a); a.click(); a.remove(); });

  function setMode() {
    box.classList.toggle('live', model.interactive);
    box.title = model.interactive ? '' : 'Click to expand';
    if (!model.interactive) reset();
  }
  function setSrc() {
    img.onload = () => {
      const a = img.naturalWidth / Math.max(img.naturalHeight, 1);
      box.style.aspectRatio = `${img.naturalWidth} / ${img.naturalHeight}`;
      if (aspect !== null && Math.abs(a - aspect) > 1e-3) reset();  // new layout
      aspect = a; apply();
    };
    img.src = model.src;
  }
  const pos = (e) => { const r = box.getBoundingClientRect();
                       return [e.clientX - r.left, e.clientY - r.top]; };

  box.addEventListener('click', () => {
    if (!model.interactive) model.clicks = model.clicks + 1; });
  box.addEventListener('pointerdown', (e) => {
    if (!model.interactive) return;
    const [x, y] = pos(e);
    const pan = e.shiftKey || e.button !== 0;
    drag = { pan, x, y, tx, ty };
    box.setPointerCapture(e.pointerId); e.preventDefault();
    if (pan) box.classList.add('panning');
  });
  box.addEventListener('pointermove', (e) => {
    if (!drag) return;
    const [x, y] = pos(e);
    if (drag.pan) { tx = drag.tx + x - drag.x; ty = drag.ty + y - drag.y; apply(); return; }
    Object.assign(band.style, { display: 'block', left: Math.min(x, drag.x) + 'px',
      top: Math.min(y, drag.y) + 'px', width: Math.abs(x - drag.x) + 'px',
      height: Math.abs(y - drag.y) + 'px' });
  });
  const end = (e) => {
    if (!drag) return;
    const d = drag; drag = null;
    band.style.display = 'none'; box.classList.remove('panning');
    if (d.pan) return;
    const [x, y] = pos(e);
    const rw = Math.abs(x - d.x), rh = Math.abs(y - d.y);
    if (rw < 8 || rh < 8) return;
    // box (screen) -> content coordinates, then fit it to the view
    const cu = (Math.min(x, d.x) - tx) / s, cv = (Math.min(y, d.y) - ty) / s;
    const cw = rw / s, ch = rh / s;
    s = Math.min(W() / cw, H() / ch);
    tx = (W() - cw * s) / 2 - cu * s; ty = (H() - ch * s) / 2 - cv * s; apply();
  };
  box.addEventListener('pointerup', end);
  box.addEventListener('pointercancel', end);
  box.addEventListener('dblclick', (e) => { if (model.interactive) reset(); });
  box.addEventListener('contextmenu', (e) => { if (model.interactive) e.preventDefault(); });
  box.addEventListener('wheel', (e) => {
    if (!model.interactive || !(e.ctrlKey || e.metaKey)) return;  // plain wheel scrolls
    e.preventDefault();
    const [x, y] = pos(e);
    zoomAt(x, y, s * Math.exp(-e.deltaY * (e.deltaMode ? 0.05 : 0.002)));
  }, { passive: false });
  new ResizeObserver(() => apply()).observe(box);

  model.on('src', setSrc);
  model.on('interactive', setMode);
  setSrc(); setMode();
}
"""

    _stylesheets = [r"""
.zv { position: relative; width: 100%; overflow: hidden; cursor: zoom-in;
      border-radius: 6px; touch-action: none; user-select: none; }
.zv img { position: absolute; left: 0; top: 0; width: 100%; height: 100%;
          transform-origin: 0 0; max-width: none; display: block; }
.zv.live { cursor: crosshair; outline: 1px solid #253045; }
.zv.live.panning { cursor: grabbing; }
.zv .band { position: absolute; display: none; border: 1px dashed #22d3ee;
            background: rgba(34, 211, 238, .12); pointer-events: none; }
.zv .bar { position: absolute; right: 8px; top: 8px; display: none; gap: 4px; }
.zv.live .bar { display: flex; }
.zv .bar button { width: 28px; height: 26px; border-radius: 6px; cursor: pointer;
                  background: rgba(17, 23, 35, .88); color: #d7dde8; font: 15px/1 system-ui;
                  border: 1px solid #253045; }
.zv .bar button:hover { background: rgba(34, 211, 238, .2); }
.zv .hint { position: absolute; left: 8px; bottom: 6px; display: none; padding: 2px 6px;
            font: 11px system-ui, sans-serif; color: #94a3b8; border-radius: 4px;
            background: rgba(11, 15, 23, .8); pointer-events: none; }
.zv.live:hover .hint { display: block; }
.zv.live.zoomed .hint { display: none; }
"""]
