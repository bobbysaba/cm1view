"""F6: table panels as CSV and LaTeX (figures/tablefile.py).  The text is made from the same
arrays and table settings the figure draws (draw.tbl_grid), so these use arrays of the shape
spec.tbl_panel makes and need no run."""

from cm1view.figures import batch, draw as figdraw, tablefile
from cm1view.figures.spec import tables as st


def arrays():
    """Arrays of a table panel of field statistics for two runs (as spec.tbl_panel makes them)."""
    ent = dict(st.tbl_defaults(dict(field="w"), 0, 600.0), what="field", runs=[0, 1],
               times_s=[600.0], stats=["mean", "max", "n"])
    spec = dict(runs=[dict(label="Control"), dict(label="Warm")], tables=[ent])
    d = st.tbl_panel(spec, 0, lambda e, k, ts: dict(mean=-0.04 - k, hi=12.3456 + 100 * k, n=5000))
    return spec, d


def doc_with(d=None):
    return dict(version=3, size=[6.0, 4.0], grid=dict(rows=1, cols=1), style={}, kinds={},
                layers={}, sections={}, annotations=[], runs=[], export=dict(format="png"),
                panels=[dict(id=0, kind="table", cell=[0, 0, 1, 1], run=None, time_s=None,
                             title="", layers=[], opts=dict(table=dict(layout="rows", decimals=-1)))])


def test_csv_is_what_the_figure_shows():
    _, d = arrays()
    doc = doc_with()
    (pid, letter, heads, rows, spans, why), = tablefile.tables_of(doc, {0: d})
    assert (pid, letter) == (0, "a")
    assert (heads, rows, spans) == figdraw.tbl_grid(d, {"layout": "rows", "decimals": -1})
    text = tablefile.to_csv(heads, rows, spans)
    lines = text.strip().split("\n")
    assert len(lines) == 1 + len(rows)
    assert "\u2212" not in text and "Control,-0.04," in text and "Warm,-1.04," in text


def test_latex_has_rules_and_escapes():
    t = tablefile.to_latex(["a_b (m s^-1)", "x"], [("Run 1", ["1", "−" + "2.5"]),
                                                  ("Run 2", ["–", "3"])], [("src", 0, 2)],
                           why="no sounding")
    assert "\\toprule" in t and "\\midrule" in t and "\\bottomrule" in t
    assert "a\\_b" in t and "\\^{}" in t and "$-$2.5" in t and "--" in t
    assert "\\multicolumn{2}{c}{src}" in t and "\\cmidrule(lr){2-3}" in t
    assert t.count("\\\\") == 4 and "% no value: no sounding" in t


def test_units_in_mathtext_stay_math_in_latex_and_read_plainly_in_csv():
    heads = ["CAPE (J kg$^{-1}$)"]
    assert "CAPE (J kg$^{-1}$)" in tablefile.to_latex(heads, [("a", ["1"])])
    assert tablefile.to_csv(heads, [("a", ["1"])]).split("\n")[0] == ',CAPE (J kg^-1)'
    assert "\\$" in tablefile.to_latex(["cost $5"], [])


def test_files_named_by_count(tmp_path):
    _, d = arrays()
    doc = doc_with()
    one = tablefile.table_paths(doc, {0: d}, str(tmp_path / "fig.png"))
    assert sorted(one) == [str(tmp_path / "fig_table.csv"), str(tmp_path / "fig_table.tex")]
    doc["panels"].append(dict(doc["panels"][0], id=1, cell=[0, 1, 1, 1]))
    doc["grid"]["cols"] = 2
    two = tablefile.save_tables(doc, {0: d, 1: d}, str(tmp_path / "fig"), tex=False)
    assert [p.split("/")[-1] for p in two] == ["fig_table_a.csv", "fig_table_b.csv"]
    assert (tmp_path / "fig_table_b.csv").read_text().startswith(",")


def test_a_panel_without_values_is_left_out():
    assert tablefile.tables_of(doc_with(), {0: dict(missing="no values picked")}) == []


def test_render_offers_tables():
    assert batch.parser().parse_args(["x", "--tables"]).tables is True
