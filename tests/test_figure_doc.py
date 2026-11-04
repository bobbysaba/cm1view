"""The figure document (version 3): conversion from older figures, what is drawn from it,
and panels read one at a time."""
import copy
import json

import numpy as np
import pytest


@pytest.fixture
def tools(ed):
    """(a synchronous FigureData, the plain spec of a new figure of a kind)."""
    from cm1view.figures.render import FigureData
    fd = FigureData(ed.data.run, ed.data.F, reg=ed.data.reg, viewer_fixes=ed.data.viewer_fixes)
    ed.auto.value = False

    def quick(kind, rows=1, cols=2):
        ed.open_quick()
        ed.qs_kind.value = kind
        ed.qs_rows.value, ed.qs_cols.value = rows, cols
        ed._quick_make()
        if kind in ("th", "line"):
            ed._add_series()
            ed._add_series()
        return json.loads(json.dumps(ed.collect_all(), default=float))

    return fd, quick


def _pixels(spec, data):
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from cm1view.figures import draw as figdraw
    fig = figdraw.draw(spec, data)
    fig.set_dpi(60)
    canvas = FigureCanvasAgg(fig)
    canvas.draw()
    return np.asarray(canvas.buffer_rgba()).copy()


def _same_figure(fd, form):
    from cm1view.figures import spec as fg
    doc = json.loads(json.dumps(fg.to_doc(form)))  # (it has to survive a file)
    a, b = _pixels(form, fd.panel_data(form)), _pixels(doc, fd.panel_data(doc))
    # (2 levels: identical draws of a sounding can differ by 1 in a few pixels)
    assert a.shape == b.shape and np.abs(a.astype(int) - b.astype(int)).max() <= 2
    return doc


@pytest.mark.parametrize("kind", ["plan", "xsec", "th", "line", "sounding", "dist", "profile",
                                  "joint", "azim", "table"])
def test_every_kind_draws_the_same_from_its_document(tools, kind):
    fd, quick = tools
    doc = _same_figure(fd, quick(kind))
    ids = [p["id"] for p in doc["panels"]]
    assert doc["version"] == 3 and ids and ids == sorted(ids) and ids[0] == 0
    assert set(doc["kinds"]) == {kind}


def test_panel_settings_draw_the_same_from_the_document(tools, ed):
    """Panel edits, an empty cell, a layer in some panels, ids for places and layers."""
    from cm1view.figures import spec as fg
    fd, quick = tools
    s = quick("plan", 2, 3)
    s["times_s"][1] = None
    s["titles"], s["row_titles"] = ["A", "", "C"], ["one", "two"]
    s["layers"][0]["panels"] = [0, 2, 3, 4, 5]
    s["layers"][1]["legend"] = "w"
    s["legend"] = dict(s["legend"], panel=2, panels=[0, 2])
    s["extremes"] = dict(s["extremes"], on=True, layer=0)
    s["contour_key"] = dict(s["contour_key"], on=True, layer=1)
    s["annotations"] = [dict(kind="text", panel=2, x=0.5, y=0.5, coords="axes", text="hi")]
    s["edits"] = {"2": dict(title="own", time_s=s["times_s"][3], z=3.0,
                            layers={"0": dict(cmap="viridis")},
                            extra=[dict(fg.layer_defaults("contour", ed.data.F, "winterp", 3.0))]),
                  "4": dict(xlabel="my x", layers={"1": dict(on=False)})}
    doc = _same_figure(fd, s)
    by = {p["id"]: p for p in doc["panels"]}
    assert 1 not in by and by[2]["letter"] == 2  # (the empty cell keeps its letter)
    assert "letter" not in by[0]
    ids = list(doc["layers"])
    assert [i["ref"] for i in by[0]["layers"]] == ids and not by[0]["layers"][0]["over"]
    assert by[2]["layers"][0]["over"]["cmap"] == "viridis" and by[2]["title"] == "own"
    assert by[2]["layers"][-1]["type"] == "contour"  # (its own layer)
    assert by[4]["layers"][1]["over"] == dict(on=False)
    assert all("panels" not in lay for lay in doc["layers"].values())
    assert doc["style"]["extremes"]["layer"] == ids[0]
    assert doc["style"]["contour_key"]["layer"] == ids[1]
    assert doc["style"]["legend"]["panel"] == 3  # (third of those drawn: panel id 3)
    assert doc["style"]["legend"]["panels"] == [0, 3]


def test_runs_have_ids_and_several_runs_draw_the_same(tools, demo_root):
    import os
    fd, quick = tools
    s = quick("plan", 2, 3)
    s["runs"].append(dict(path=os.path.join(demo_root, "demo", "supercell_weak"), label="weak",
                          track=""))
    s.update(grid=dict(rows="runs", cols="times", runs=[]), times_s=s["times_s"][:3])
    doc = _same_figure(fd, s)
    assert [r["id"] for r in doc["runs"]] == ["r0", "r1"]
    assert {p["run"] for p in doc["panels"]} == {"r0", "r1"}


def test_a_layers_run_is_an_id_and_a_removed_run_is_said_so(tools, demo_root):
    import os
    from cm1view.figures import draw as figdraw, spec as fg
    fd, quick = tools
    s = quick("plan")
    s["runs"].append(dict(path=os.path.join(demo_root, "demo", "supercell_weak"), label="weak",
                          track=""))
    s["layers"][0] = dict(s["layers"][0], minus=dict(run=1))
    doc = _same_figure(fd, s)
    lid = doc["panels"][0]["layers"][0]["ref"]
    assert doc["layers"][lid]["minus"]["run"] == "r1"
    assert figdraw.resolve(doc)["panels"][0]["layers"][0]["minus"]["run"] == 1
    gone = copy.deepcopy(doc)
    gone["runs"] = gone["runs"][:1]  # (nothing else needs to change)
    assert "no longer" in fd.panel_data(gone)[0]["missing"]
    assert fg.is_doc(gone)


def test_one_panel_is_a_figure_of_one_panel(tools):
    from cm1view.figures import spec as fg
    _, quick = tools
    doc = fg.to_doc(quick("sounding"))
    one = fg.one_panel(doc, doc["panels"][1]["id"])
    assert one["version"] == 1 and (one["rows"], one["cols"]) == (1, 1) and fg.npanels(one) == 1
    assert [int(e["panel"]) for e in one["soundings"]] == [0] * len(one["soundings"])
    assert len(one["runs"]) == len(doc["runs"])


def test_a_panels_own_area_comes_from_its_opts(tools):
    from cm1view.figures import spec as fg
    fd, quick = tools
    doc = fg.to_doc(quick("plan"))
    doc["panels"][1]["opts"] = dict(domain=dict(mode="box", box=[-12.0, 4.0, -14.0, 2.0]))
    data = fd.panel_data(doc)
    assert tuple(data[1]["xlim"]) != tuple(data[0]["xlim"])
    assert np.ptp(data[1]["xlim"]) == pytest.approx(16.0)


def test_mixed_kinds_on_one_grid_with_a_spanning_panel(tools):
    """Each kind keeps its axes; ids key the data; a panel spans two rows."""
    from cm1view.figures import draw as figdraw, spec as fg
    fd, quick = tools
    doc = fg.to_doc(quick("plan"))
    snd = fg.to_doc(quick("sounding", 1, 1))
    doc["kinds"].update(snd["kinds"])
    q = snd["panels"][0]
    doc["panels"][0]["cell"] = [0, 0, 2, 1]
    doc["panels"][1]["cell"] = [0, 1, 1, 1]
    doc["panels"].append(dict(q, id=7, cell=[1, 1, 1, 1]))
    doc["grid"] = dict(rows=2, cols=2)
    data = fd.panel_data(doc)
    assert set(data) == {0, 1, 7}
    fig = figdraw.draw(doc, data)
    assert set(fig._cv_axes) == {0, 1, 7}
    res = figdraw.resolve(doc)
    v = figdraw.panel_view(res, next(p for p in res["panels"] if p["id"] == 7))
    assert all(v["axes"][k] == val for k, val in snd["kinds"]["sounding"]["axes"].items())
    assert fig._cv_axes[0].get_xlabel() == doc["kinds"]["plan"]["axes"]["xlabel"]


def _parts(quick, arrange, one=False):
    from cm1view.figures.combo import combine
    return json.loads(json.dumps(combine([quick("plan"), quick("sounding", 1, 1)],
                                         arrange=arrange, one_colorbar=one), default=float))


@pytest.mark.parametrize("arrange", ["row", "col"])
def test_parts_go_onto_one_grid(tools, arrange):
    from cm1view.figures import draw as figdraw, spec as fg
    fd, quick = tools
    doc = fg.to_doc(_parts(quick, arrange))
    assert sorted(p["id"] for p in doc["panels"]) == [0, 1, 1000]
    assert (doc["grid"]["cols"] if arrange == "row" else doc["grid"]["rows"]) >= 2
    assert doc["style"]["colorbar"]["mode"] == "groups" and set(doc["groups"]) == {"part0", "part1"}
    assert {p["group"] for p in doc["panels"]} == {"part0", "part1"}
    assert sum(doc["grid"]["widths"]) == pytest.approx(1.0, abs=1e-4)
    data = fd.panel_data(doc)
    fig = figdraw.draw(doc, data)
    assert set(fig._cv_axes) == set(data) == {0, 1, 1000}
    ylabels = {i: ax.get_ylabel() for i, ax in fig._cv_axes.items()}
    assert ylabels[0] and ylabels[1000]  # (each part's own first column keeps its label)


def test_parts_keep_their_letters_panel_settings_and_say_what_is_left_out(tools):
    from cm1view.figures import spec as fg
    _, quick = tools
    s = _parts(quick, "row")
    s["parts"][1]["suptitle"] = "only here"
    s["parts"][1]["letters"] = dict(s["parts"][1]["letters"], fmt="({a})")
    s["parts"][1]["annotations"] = [dict(kind="text", panel=-1, x=0.5, y=0.5, text="t")]
    doc = fg.to_doc(s)
    p = next(q for q in doc["panels"] if q["id"] == 1000)
    assert p["opts"]["letters"]["fmt"] == "({a})" and "(" not in doc["style"]["letters"]["fmt"]
    assert doc["annotations"][-1]["panel"] == [1000]  # (every panel of that part)
    assert any("only here" in n for n in doc["notes"])


def test_one_colorbar_of_parts_stays_one(tools):
    from cm1view.figures import spec as fg
    _, quick = tools
    doc = fg.to_doc(_parts(quick, "row", one=True))
    assert doc["style"]["colorbar"]["mode"] == "shared"
    assert all("colorbar" not in g for g in doc["groups"].values())


def test_to_doc_takes_version_1_only_and_leaves_its_input_alone(tools):
    from cm1view.figures import spec as fg
    _, quick = tools
    s = quick("plan")
    was = copy.deepcopy(s)
    doc = fg.to_doc(s)
    assert s == was
    with pytest.raises(ValueError):
        fg.to_doc(doc)


def test_upgrade_and_exported_code_know_documents(tools):
    from cm1view.figures import draw as figdraw, spec as fg
    _, quick = tools
    doc = fg.to_doc(quick("plan"))
    v2, _ = figdraw.upgrade(doc)
    assert v2["version"] == 2 and len(v2["blocks"]) == 1
    assert "def resolve(" in figdraw.source()
