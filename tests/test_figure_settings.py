"""The table of figure-level settings (figures/settings.py) behind set_spec and collect."""
import copy
import json

import pytest


def _plain(ed):
    return json.loads(json.dumps(ed.collect(), default=float))


def _shown(obj, into):
    """The ids of what is shown under obj (sections opened: they fill when first opened)."""
    if not getattr(obj, "visible", True):
        return
    into.add(id(obj))
    if getattr(obj, "collapsed", False):
        obj.collapsed = False
    for o in list(getattr(obj, "objects", None) or []):
        _shown(o, into)


def test_each_row_has_its_own_widget_and_key(ed):
    from cm1view.figures import settings
    rows = settings.SETTINGS
    assert len({r.key for r in rows}) == len(rows)
    assert len({r.widget for r in rows}) == len(rows)
    for r in rows:
        assert settings.widget_of(ed, r) is not None
        assert r.section and r.kinds


@pytest.mark.parametrize("attr", ["sk", "ds", "po", "jo", "ao", "to"])
def test_every_widget_of_a_kinds_block_is_in_the_table(ed, attr):
    from cm1view.figures import settings
    listed = {r.widget.split(".")[1] for r in settings.SETTINGS
              if r.widget.startswith(attr + ".")}
    assert listed == set(getattr(ed, attr))


def test_number_boxes_are_read_as_numbers(ed):
    """A number box left RAW would put a blank in the spec; a blank-able list would fail."""
    from cm1view.figures import settings
    from cm1view.viewer.numinput import FloatInput
    for r in settings.SETTINGS:
        boxed = isinstance(settings.widget_of(ed, r), FloatInput)
        assert not (boxed and r.as_ is settings.RAW), r.key
        assert boxed or r.as_ not in (settings.BLANKABLE, settings.SIZE), r.key


def test_every_number_and_switch_goes_through_the_widgets_and_back(ed):
    from cm1view.figures import settings
    s = _plain(ed)
    s["letters"]["auto"] = False  # (else the panels decide)
    want = {}
    for r in settings.SETTINGS:
        block, _, key = r.key.rpartition(".")
        held = s[block] if block else s
        v = held.get(key)
        if isinstance(v, bool):
            held[key] = want[r.key] = not v
        elif isinstance(v, float):
            held[key] = want[r.key] = round(v * 0.5 + 0.1, 3)
    assert len(want) > 60
    ed.set_spec(copy.deepcopy(s))
    out = _plain(ed)
    for key, v in want.items():
        block, _, name = key.rpartition(".")
        assert (out[block] if block else out)[name] == v, key


def test_older_figures_values(ed):
    s = _plain(ed)
    s["axes"].update(tickdir="sideways", frame_lw=None)
    s["font"]["family"] = "No Such Font"
    s["letters"]["fmt"] = "{i}"
    s["colorbar"].update(mode="each")
    s["colorbar"].pop("location"), s["colorbar"].pop("orientation")
    s["legend"].update(title=None, ncol=None)
    s["mplstyle"] = None
    s["code"] = dict(on=1, text=None)
    ed.set_spec(s)
    out = _plain(ed)
    assert out["axes"]["tickdir"] == "out" and out["axes"]["frame_lw"] == 0.8
    assert out["font"]["family"] == "sans-serif" and out["letters"]["fmt"] == "{a}"
    assert (out["colorbar"]["location"], out["colorbar"]["orientation"]) == ("right", "vertical")
    assert out["legend"]["title"] == "" and out["legend"]["ncol"] == 1
    assert out["mplstyle"] == "" and out["code"] == dict(on=True, text="")


@pytest.mark.parametrize("tight, exact, fit", [(True, False, "trim"), (True, True, "width"),
                                               (False, False, "full")])
def test_one_widget_of_two_keys(ed, tight, exact, fit):
    s = _plain(ed)
    s["export"].update(tight=tight, exact_width=exact)
    ed.set_spec(s)
    assert ed.fit.value == fit
    out = _plain(ed)["export"]
    assert (out["tight"], out["exact_width"]) == (tight, exact)
    ed.cb_loc.value = "left"
    assert _plain(ed)["colorbar"]["orientation"] == "vertical"
    ed.cb_loc.value = "top"
    assert _plain(ed)["colorbar"]["orientation"] == "horizontal"


def test_emptied_boxes(ed):
    """What a number box left blank is in the spec."""
    ed.fsize.value = ed.dpi.value = ed.half.value = ed.ts_zmax.value = None
    ed.sp_w.value = ed.ds["alpha"].value = ed.jo["ms"].value = ed.sk["pmax"].value = None
    ed.fs_tick.value = ed.po["xmin"].value = None
    ed.ts_tmin.value = "soon"
    s = _plain(ed)
    assert s["font"]["size"] == 10.0 and s["export"]["dpi"] == 250
    assert s["domain"]["half"] == 12.5 and s["ts"]["zmax"] == 10.0
    assert s["spacing"]["wspace"] == 0.0 and s["skewt"]["pmax"] == 0.0
    assert s["dist"]["alpha"] == 0.35 and s["joint"]["ms"] == 2.0
    assert s["font"]["tick"] is None and s["prof"]["xmin"] is None and s["ts"]["tmin"] is None


def test_keys_without_a_widget(ed):
    """Most blocks keep them; those written whole don't."""
    s = _plain(ed)
    s["contour_key"]["r0"] = 0.5
    s["colorbar"]["mine"] = 1
    s["font"]["mine"] = 1
    ed.set_spec(s)
    out = _plain(ed)
    assert out["contour_key"]["r0"] == 0.5 and out["colorbar"]["mine"] == 1
    assert "mine" not in out["font"]


def test_letters_follow_the_panels_until_set_by_hand(ed):
    s = _plain(ed)
    assert s["letters"]["auto"] is True
    ed.let_on.value = not ed.let_on.value
    assert _plain(ed)["letters"]["auto"] is False


@pytest.mark.parametrize("kind", ["plan", "xsec", "th", "line", "sounding", "dist", "profile",
                                  "joint", "azim", "table", "scene"])
def test_no_kind_shows_a_setting_not_listed_for_it(ed, kind):
    from cm1view.figures import settings
    ed.open_quick()
    ed.qs_kind.value = kind
    ed.qs_rows.value, ed.qs_cols.value = 1, 2
    ed._quick_make()
    shown = set()
    for _, tab in ed.tab_list:
        _shown(tab, shown)
    _shown(ed.exp_dlg, shown)
    leaks = [r.key for r in settings.SETTINGS
             if kind not in r.kinds and id(settings.widget_of(ed, r)) in shown]
    assert not leaks
    assert id(ed.fsize) in shown  # (the walk does reach the widgets)
