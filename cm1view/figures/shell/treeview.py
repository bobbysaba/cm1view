"""The tree of a figure: one widget, its rows drawn in the browser, so a figure of many panels
costs nothing to show and folding asks nothing of the server."""

import param
from panel.reactive import ReactiveHTML

from ...theme import ACCENT, GRID, MUTED, TEXT

CSS = f"""
.row {{ display: flex; align-items: center; gap: 2px; padding: 3px 6px 3px 0; cursor: pointer;
  color: {TEXT}; font-size: 13px; line-height: 18px; border-radius: 4px; white-space: nowrap; }}
.row:hover {{ background: {GRID}; }}
.row.top {{ font-weight: 600; }}
.row.sel {{ background: rgba(34,211,238,.18); color: {ACCENT}; }}
.fold {{ flex: 0 0 16px; text-align: center; color: {MUTED}; }}
.name {{ overflow: hidden; text-overflow: ellipsis; }}
"""


class TreeView(ReactiveHTML):
    """Rows items = [{id, label, depth}], the row sel marked.  Clicking a row sets pick =
    [id, n] (n: a count, so the same row twice is a new event); its arrow folds it instead.
    Top rows start open, the others folded; showing a row opens what holds it."""

    items = param.List(default=[])
    sel = param.String(default="")
    pick = param.List(default=[])

    _template = '<div id="rows" onclick="${script(\'hit\')}"></div>'
    _scripts = {
        "render": "state.fold = new Set(); state.known = new Set(); self.draw();",
        "items": "self.draw();",
        "sel": "self.draw();",
        "hit": """
            const row = state.event.target.closest('[data-id]');
            if (!row) return;
            const id = row.dataset.id;
            if (state.event.target.classList.contains('fold')) {
                if (row.dataset.parent !== '1') return;
                state.fold.has(id) ? state.fold.delete(id) : state.fold.add(id);
                self.draw();
                return;
            }
            state.n = (state.n || 0) + 1;
            data.pick = [id, state.n];
        """,
        "draw": """
            const items = data.items;
            items.forEach((it, i) => {
                const parent = i + 1 < items.length && items[i + 1].depth > it.depth;
                if (parent && !state.known.has(it.id)) {
                    state.known.add(it.id);
                    if (it.depth > 0) state.fold.add(it.id);
                }
            });
            const at = items.findIndex(it => it.id === data.sel);
            let need = at >= 0 ? items[at].depth : 0;  // (what holds the row marked: open)
            for (let i = at - 1; i >= 0 && need > 0; i--) {
                if (items[i].depth < need) {
                    state.fold.delete(items[i].id);
                    need = items[i].depth;
                }
            }
            const out = [];
            let skip = null;
            items.forEach((it, i) => {
                if (skip !== null && it.depth > skip) return;
                skip = null;
                const parent = i + 1 < items.length && items[i + 1].depth > it.depth;
                const shut = parent && state.fold.has(it.id);
                if (shut) skip = it.depth;
                const row = document.createElement('div');
                row.className = 'row' + (it.depth === 0 ? ' top' : '')
                    + (it.id === data.sel ? ' sel' : '');
                row.dataset.id = it.id;
                row.dataset.parent = parent ? '1' : '0';
                row.style.paddingLeft = (it.depth * 12) + 'px';
                row.title = it.label;
                const fold = document.createElement('span');
                fold.className = 'fold';
                fold.textContent = parent ? (shut ? '▸' : '▾') : '';
                const name = document.createElement('span');
                name.className = 'name';
                name.textContent = it.label;
                row.append(fold, name);
                out.push(row);
            });
            rows.replaceChildren(...out);
        """}

    def __init__(self, **kw):
        super().__init__(stylesheets=[CSS], **kw)
