"""Custom components for the sounding panel.

ParamTable: the parameter table.  Clicking the units cell of a level row (LCL, LFC,
...) switches that row between metres and hPa; the choice (`alt_rows`) survives
updates of the table.
"""

import param
from panel.custom import JSComponent


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
