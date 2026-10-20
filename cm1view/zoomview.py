"""Custom components for the sounding panel.

ZoomImage: a sounding graphic.  Not interactive (narrow panel): a click increments
`clicks`, which the app uses to open the expanded view.  Interactive: dragging a box
sets `box` (image fractions, y down) and the app redraws the figure with the axes
limits of that box, so axes, labels and line widths stay intact; the − button
(`zoom_out`) widens the view, double-click or ⟲ (`resets`) goes back to the full view.

ParamTable: the parameter table.  Clicking the units cell of a level row (LCL, LFC,
...) switches that row between metres and hPa; the choice (`alt_rows`) survives
updates of the table.
"""

import param
from panel.custom import JSComponent


class ZoomImage(JSComponent):
    src = param.String(default="", doc="image URL (usually a data: URI)")
    filename = param.String(default="sounding.svg", doc="name used by the save button")
    interactive = param.Boolean(default=False)
    clicks = param.Integer(default=0)
    box = param.List(default=[], doc="[x0, y0, x1, y1, nonce]: dragged box, image fractions")
    zoom_out = param.Integer(default=0)
    resets = param.Integer(default=0)
    done = param.Integer(default=0, doc="bumped by the app when it has answered a zoom")

    _esm = r"""
export function render({ model, el }) {
  const box = document.createElement('div'); box.className = 'zv';
  const img = document.createElement('img'); img.draggable = false;
  const band = document.createElement('div'); band.className = 'band';
  const bar = document.createElement('div'); bar.className = 'bar';
  const hint = document.createElement('div'); hint.className = 'hint';
  hint.textContent = 'drag a box to zoom (axes redraw) · − zoom out · double-click: full view';
  const btn = (txt, title, fn) => {
    const b = document.createElement('button'); b.textContent = txt; b.title = title;
    b.onpointerdown = (e) => e.stopPropagation();
    b.onclick = (e) => { e.stopPropagation(); fn(); }; bar.append(b); return b; };
  box.append(img, band, bar, hint); el.append(box);

  const busy = () => box.classList.add('busy');
  btn('−', 'Zoom out', () => { busy(); model.zoom_out = model.zoom_out + 1; });
  btn('⟲', 'Full view (double-click)', () => { busy(); model.resets = model.resets + 1; });
  btn('⤓', 'Save image', () => {
    const a = document.createElement('a'); a.href = model.src; a.download = model.filename;
    document.body.append(a); a.click(); a.remove(); });

  let drag = null;
  const pos = (e) => { const r = box.getBoundingClientRect();
                       return [e.clientX - r.left, e.clientY - r.top]; };
  function setMode() {
    box.classList.toggle('live', model.interactive);
    box.title = model.interactive ? '' : 'Click to expand';
  }
  function setSrc() {
    img.onload = () => {
      box.style.aspectRatio = `${img.naturalWidth} / ${img.naturalHeight}`;
      box.classList.remove('busy');
    };
    img.src = model.src;
  }
  box.addEventListener('click', () => {
    if (!model.interactive) model.clicks = model.clicks + 1; });
  box.addEventListener('pointerdown', (e) => {
    if (!model.interactive || e.button !== 0) return;
    const [x, y] = pos(e); drag = { x, y };
    box.setPointerCapture(e.pointerId); e.preventDefault();
  });
  box.addEventListener('pointermove', (e) => {
    if (!drag) return;
    const [x, y] = pos(e);
    Object.assign(band.style, { display: 'block', left: Math.min(x, drag.x) + 'px',
      top: Math.min(y, drag.y) + 'px', width: Math.abs(x - drag.x) + 'px',
      height: Math.abs(y - drag.y) + 'px' });
  });
  const end = (e) => {
    if (!drag) return;
    const d = drag; drag = null; band.style.display = 'none';
    const [x, y] = pos(e);
    if (Math.abs(x - d.x) < 8 || Math.abs(y - d.y) < 8) return;
    const W = box.clientWidth, H = box.clientHeight;
    busy();
    model.box = [Math.min(x, d.x) / W, Math.min(y, d.y) / H,
                 Math.max(x, d.x) / W, Math.max(y, d.y) / H, Date.now()];
  };
  box.addEventListener('pointerup', end);
  box.addEventListener('pointercancel', end);
  box.addEventListener('dblclick', () => {
    if (model.interactive) { busy(); model.resets = model.resets + 1; } });
  // nothing to redraw: the app answers with the same image, so drop the busy look
  model.on("done", () => box.classList.remove("busy"));

  model.on('src', setSrc);
  model.on('interactive', setMode);
  setSrc(); setMode();
}
"""

    _stylesheets = [r"""
.zv { position: relative; width: 100%; overflow: hidden; cursor: zoom-in;
      border-radius: 6px; touch-action: none; user-select: none; }
.zv img { position: absolute; left: 0; top: 0; width: 100%; height: 100%;
          max-width: none; display: block; transition: opacity .15s; }
.zv.live { cursor: crosshair; outline: 1px solid #253045; }
.zv.busy img { opacity: .55; }
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
"""]


class ParamTable(JSComponent):
    html = param.String(default="")
    alt_rows = param.List(default=[], doc="names of rows shown in their alternate units")

    _esm = r"""
export function render({ model, el }) {
  const root = document.createElement('div'); el.append(root);
  function apply() {
    const on = new Set(model.alt_rows);
    root.querySelectorAll('tr.alt').forEach(tr =>
      tr.classList.toggle('show-b', on.has(tr.dataset.row)));
  }
  function draw() { root.innerHTML = model.html; apply(); }
  root.addEventListener('click', (e) => {
    const td = e.target.closest('td.tog'); if (!td) return;
    const row = td.parentElement.dataset.row;
    const on = new Set(model.alt_rows);
    on.has(row) ? on.delete(row) : on.add(row);
    model.alt_rows = [...on];
  });
  model.on('html', draw);
  model.on('alt_rows', apply);
  draw();
}
"""

    _stylesheets = [r"""
tr.alt .ub { display: none; }
tr.alt.show-b .ua { display: none; }
tr.alt.show-b .ub { display: inline; }
td.tog { cursor: pointer; text-decoration: underline dotted; text-underline-offset: 3px; }
td.tog:hover { color: #a5f3fc !important; }
"""]
