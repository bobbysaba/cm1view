"""Custom components for the sounding panel.

ZoomImage: a sounding graphic.  Not interactive (narrow panel): a click increments
`clicks`, which the app uses to open the expanded view.  Interactive: dragging a box
sets `box` (image fractions, y down) and the app redraws the figure with the axes
limits of that box, so axes, labels and line widths stay intact.  After a zoom, dragging
pans instead (`pan`: start point and offset, image fractions; the image follows the
pointer until the redraw arrives); Shift-drag does the other mode, the ✥/⬚ button
switches.  The − button (`zoom_out`) widens the view, double-click or ⟲ (`resets`) goes
back to the full view (and to box mode).  Hovering the expanded view reads the
profiles off the figure (`probe`, from sounding_plot.probe_*): the values of every
sounding at the pointer's height in a strip below the image, the nearest level on the
hodograph.

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
    pan = param.List(default=[], doc="[x, y, dx, dy, nonce]: pan drag start and offset, "
                                     "image fractions")
    zoom_out = param.Integer(default=0)
    resets = param.Integer(default=0)
    done = param.Integer(default=0, doc="bumped by the app when it has answered a zoom")
    probe = param.Dict(default={}, doc="hover data of the figure (sounding_plot.probe_*)")

    _esm = r"""
export function render({ model, el }) {
  const box = document.createElement('div'); box.className = 'zv';
  const img = document.createElement('img'); img.draggable = false;
  const band = document.createElement('div'); band.className = 'band';
  const bar = document.createElement('div'); bar.className = 'bar';
  const hint = document.createElement('div'); hint.className = 'hint';
  let panMode = false;
  const setHint = () => { hint.textContent = panMode
    ? 'drag to pan · Shift-drag: zoom box · − zoom out · double-click: full view'
    : 'drag a box to zoom · Shift-drag: pan · − zoom out · double-click: full view'; };
  const btn = (txt, title, fn) => {
    const b = document.createElement('button'); b.textContent = txt; b.title = title;
    b.onpointerdown = (e) => e.stopPropagation();
    b.onclick = (e) => { e.stopPropagation(); fn(); }; bar.append(b); return b; };
  const guide = document.createElement('div'); guide.className = 'guide';
  const dot = document.createElement('div'); dot.className = 'dot';
  const ro = document.createElement('div'); ro.className = 'readout';
  box.append(img, band, guide, dot, bar, hint); el.append(box, ro);

  const busy = () => box.classList.add('busy');
  const modeBtn = btn('', '', () => setPan(!panMode));
  function setPan(on) {
    panMode = on; box.classList.toggle('panning', on);
    modeBtn.textContent = on ? '⬚' : '✥';
    modeBtn.title = on ? 'Switch to box zoom' : 'Switch to pan';
    setHint();
  }
  btn('−', 'Zoom out', () => { busy(); model.zoom_out = model.zoom_out + 1; });
  btn('⟲', 'Full view (double-click)', () => {
    busy(); setPan(false); model.resets = model.resets + 1; });
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
  const unshift = () => { img.style.transform = ''; };
  function setSrc() {
    img.onload = () => {
      box.style.aspectRatio = `${img.naturalWidth} / ${img.naturalHeight}`;
      box.classList.remove('busy'); unshift();
    };
    img.src = model.src;
  }
  box.addEventListener('click', () => {
    if (!model.interactive) model.clicks = model.clicks + 1; });
  box.addEventListener('pointerdown', (e) => {
    if (!model.interactive || e.button !== 0) return;
    const [x, y] = pos(e); drag = { x, y, pan: panMode !== e.shiftKey };
    guide.style.display = dot.style.display = 'none';
    box.setPointerCapture(e.pointerId); e.preventDefault();
  });
  box.addEventListener('pointermove', (e) => {
    if (!drag) return;
    const [x, y] = pos(e);
    if (drag.pan) {
      img.style.transform = `translate(${x - drag.x}px, ${y - drag.y}px)`; return; }
    Object.assign(band.style, { display: 'block', left: Math.min(x, drag.x) + 'px',
      top: Math.min(y, drag.y) + 'px', width: Math.abs(x - drag.x) + 'px',
      height: Math.abs(y - drag.y) + 'px' });
  });
  const end = (e) => {
    if (!drag) return;
    const d = drag; drag = null; band.style.display = 'none';
    const [x, y] = pos(e);
    const W = box.clientWidth, H = box.clientHeight;
    if (d.pan) {
      if (Math.hypot(x - d.x, y - d.y) < 4) { unshift(); return; }
      busy();
      model.pan = [d.x / W, d.y / H, (x - d.x) / W, (y - d.y) / H, Date.now()];
      return;
    }
    if (Math.abs(x - d.x) < 8 || Math.abs(y - d.y) < 8) return;
    busy(); setPan(true);
    model.box = [Math.min(x, d.x) / W, Math.min(y, d.y) / H,
                 Math.max(x, d.x) / W, Math.max(y, d.y) / H, Date.now()];
  };
  box.addEventListener('pointerup', end);
  box.addEventListener('pointercancel', end);
  box.addEventListener('dblclick', () => {
    if (model.interactive) { busy(); setPan(false); model.resets = model.resets + 1; } });
  // nothing to redraw: the app answers with the same image, so drop the busy look
  model.on("done", () => { box.classList.remove("busy"); unshift(); });


  // ---- hover readout
  const esc = (t) => String(t).replace(/[&<>]/g, (c) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;'})[c]);
  function interp(xs, ys, x) {
    for (let i = 0; i + 1 < xs.length; i++) {
      const a = xs[i], b = xs[i + 1];
      if (a === null || b === null || ys[i] === null || ys[i + 1] === null) continue;
      if ((x - a) * (x - b) <= 0) {
        const f = b === a ? 0 : (x - a) / (b - a);
        return ys[i] + f * (ys[i + 1] - ys[i]);
      }
    }
    return null;
  }
  const fmt = (v, d) => v === null || !isFinite(v) ? '–' : v.toFixed(d);
  const aff = (m, fx, fy) => m[0] * fx + m[1] * fy + m[2];
  const wind = (u, v, units) => {
    if (u === null || v === null) return '–';
    const d = ((270 - Math.atan2(v, u) * 180 / Math.PI) % 360 + 360) % 360;
    return `${d.toFixed(0).padStart(3, '0')}°/${Math.hypot(u, v).toFixed(0)} ${units}`;
  };
  const kv = (k, v, u) => `<span class="k">${esc(k)}</span> ${v}${u ? ' ' + esc(u) : ''}`;
  const name = (s) => `<span class="nm" style="color:${s.color}">${esc(s.label)}</span>`;
  function idle() {
    const pr = model.probe;
    ro.innerHTML = pr && pr.panels && pr.panels.length
      ? '<span class="k">Hover over the profiles to read their values</span>' : '';
    guide.style.display = dot.style.display = 'none';
  }
  function hline(fr, fy) {
    const W = box.clientWidth, H = box.clientHeight;
    Object.assign(guide.style, { display: 'block', left: fr[0] * W + 'px', width: (fr[2] - fr[0]) * W + 'px',
                                 top: fy * H + 'px' });
  }
  function readout(e) {
    const pr = model.probe;
    if (!model.interactive || drag || !pr || !pr.panels) return;
    const [x, y] = pos(e), W = box.clientWidth, H = box.clientHeight;
    const fx = x / W, fy = y / H;
    const P = pr.panels.find((p) => fx >= p.frame[0] && fx <= p.frame[2] &&
                                    fy >= p.frame[1] && fy <= p.frame[3]);
    if (!P) { idle(); return; }
    const U = pr.units, lines = [];
    dot.style.display = 'none'; guide.style.display = 'none';
    if (P.kind === 'y') {          // skew-T: everything at the pointer's pressure
      const lp = aff(P.aff[1], fx, fy), T = aff(P.aff[0], fx, fy);
      lines.push(kv('p', fmt(Math.pow(10, lp), 0), 'hPa') + ' · ' + kv('pointer T', fmt(T, 1), '°C'));
      for (const s of P.snd) {
        const parts = s.cols.map(([k, u, d, a]) => kv(k, fmt(interp(s.y, a, lp), d), u));
        parts.push(kv('wind', wind(interp(s.y, s.wind[0], lp), interp(s.y, s.wind[1], lp), U)));
        lines.push(name(s) + ' ' + parts.join(' · '));
      }
      hline(P.frame, fy);
    } else if (P.kind === 'z') {   // profiles: every panel at the pointer's height
      const z = aff(P.aff[1], fx, fy);
      lines.push(kv('z', fmt(z, 2), 'km AGL'));
      for (const s of P.snd)
        lines.push(name(s) + ' ' + s.cols.map(([k, u, d, yk, a]) =>
          kv(k, fmt(interp(s.ys[yk], a, z), d), u)).join(' · '));
      const g = P.frames.map((f) => `<div style="left:${f[0] * W}px;width:${(f[2] - f[0]) * W}px"></div>`);
      Object.assign(guide.style, { display: 'block', left: '0px', width: W + 'px', top: fy * H + 'px' });
      guide.innerHTML = g.join(''); guide.classList.add('multi');
    } else {                       // hodograph: the level nearest the pointer
      const u = aff(P.aff[0], fx, fy), v = aff(P.aff[1], fx, fy);
      lines.push(kv('pointer', wind(u, v, U)) + ' · ' + kv('u', fmt(u, 1)) + ' ' + kv('v', fmt(v, 1), U));
      let best = null;
      for (const s of P.snd)
        for (let i = 0; i < s.fx.length; i++) {
          if (s.fx[i] === null) continue;
          const d = Math.hypot((s.fx[i] - fx) * W, (s.fy[i] - fy) * H);
          if (!best || d < best.d) best = { d, s, i };
        }
      if (best && best.d < 40) {
        const { s, i } = best;
        lines.push(name(s) + ' ' + [kv('z', fmt(s.z[i], 2), 'km AGL'),
          kv('wind', wind(s.wind[0][i], s.wind[1][i], U)), kv('u', fmt(s.wind[0][i], 1)),
          kv('v', fmt(s.wind[1][i], 1), U)].join(' · '));
        Object.assign(dot.style, { display: 'block', left: s.fx[i] * W + 'px', top: s.fy[i] * H + 'px',
                                   borderColor: s.color });
      }
    }
    if (P.kind !== 'z') { guide.innerHTML = ''; guide.classList.remove('multi'); }
    ro.innerHTML = lines.map((l) => `<div>${l}</div>`).join('');
  }
  box.addEventListener('pointermove', readout);
  box.addEventListener('pointerleave', idle);
  model.on('probe', idle);
  model.on('interactive', () => { ro.classList.toggle('live', model.interactive); idle(); });
  ro.classList.toggle('live', model.interactive); idle();

  model.on('src', setSrc);
  model.on('interactive', setMode);
  setSrc(); setMode(); setPan(false);
}
"""

    _stylesheets = [r"""
.zv { position: relative; width: 100%; overflow: hidden; cursor: zoom-in;
      border-radius: 6px; touch-action: none; user-select: none; }
.zv img { position: absolute; left: 0; top: 0; width: 100%; height: 100%;
          max-width: none; display: block; transition: opacity .15s; }
.zv.live { cursor: crosshair; outline: 1px solid #253045; }
.zv.live.panning { cursor: grab; }
.zv.live.panning:active { cursor: grabbing; }
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
.zv .guide { position: absolute; display: none; height: 0; pointer-events: none;
             border-top: 1px dashed rgba(165, 243, 252, .8); }
.zv .guide.multi { border-top: none; }
.zv .guide.multi div { position: absolute; top: 0; height: 0;
                       border-top: 1px dashed rgba(165, 243, 252, .8); }
.zv .dot { position: absolute; display: none; width: 10px; height: 10px; margin: -6px 0 0 -6px;
           border: 2px solid #a5f3fc; border-radius: 50%; pointer-events: none; }
.readout { display: none; padding: 4px 8px; margin-top: 2px; min-height: 36px;
           font: 12px/1.55 ui-monospace, SFMono-Regular, Menlo, monospace; color: #d7dde8;
           background: rgba(17, 23, 35, .9); border: 1px solid #253045; border-radius: 6px; }
.readout.live { display: block; }
.readout .k { color: #94a3b8; }
.readout .nm { font-weight: 600; margin-right: 4px; }
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
