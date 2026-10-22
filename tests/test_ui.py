"""Layout logic: the tool rail and its panels, the Storm chip, the items tray, and the
always-offered 3D workspace."""
import os

from conftest import tap, wait


def test_tool_opens_its_panel_and_reclick_closes(viewer):
    v = viewer
    assert v.mode.value is None and not v.panel_col.visible
    v.mode._on("Cross-section", None)
    assert v.mode.value == "Cross-section" and v.panel_col.visible and v.tabs.active == 1
    assert v.mode.btns["Cross-section"].css_classes == ["cv-on"]
    v.mode._on("Series", None)  # another tool: its panel, no click mode on the map
    assert v.mode.value == "Series" and v.tabs.active == 3
    assert v.mode.btns["Cross-section"].css_classes == []
    v.mode._on("Series", None)  # the lit tool again: off, panel closed
    assert v.mode.value is None and not v.panel_col.visible


def test_closed_panel_reopens_from_its_tool(viewer):
    v = viewer
    v.mode.set("Sounding")
    v._show_panel(False)  # the panel's close button: the tool stays on
    assert v.mode.value == "Sounding" and not v.panel_col.visible
    v.mode._on("Sounding", None)
    assert v.mode.value == "Sounding" and v.panel_col.visible and v.tabs.active == 0


def test_panel_opened_elsewhere_moves_the_tool(viewer):
    v = viewer
    v.mode.set("3D region")
    v._show_panel(True, 2)  # e.g. the Storm chip
    assert v.mode.value == "Track"


def test_area_sounding_is_the_sounding_tool(viewer):
    v = viewer
    v.mode.set("Sounding")
    v.snd_pick.value = "Area sounding"
    assert v.mode.value == "Area sounding"
    assert v.mode.btns["Sounding"].css_classes == ["cv-on"]
    v.mode._on("Sounding", None)  # off, and back on as the same kind
    v.mode._on("Sounding", None)
    assert v.mode.value == "Area sounding"


def test_3d_is_always_offered(viewer):
    assert viewer.workspace.options == ["Map", "3D", "Figure"]


def test_storm_chip_loads_the_runs_track(viewer):
    v = viewer
    assert v.storm_btn.name.startswith("Load storm track (demo_supercell")
    v._on_storm_btn(None)
    assert v.fixes and v.mode.value == "Track" and v.tabs.active == 2
    assert v.storm_btn.name.startswith(f"Storm track · {len(v.fixes)} fixes")
    v.tslider.value = max(v.fixes) + 1 if max(v.fixes) + 1 <= v.tslider.end else 0
    if v.t not in v.fixes:
        assert "no fix at this time" in v.storm_btn.name
    v._on_clear_track(None)
    assert v.storm_btn.name.startswith("Load storm track")


def labels(v):
    return [(k, lab) for k, _, lab, _ in v._item_entries()]


def test_items_tray_lists_and_removes(viewer):
    v = viewer
    v.mode.set("Sounding")
    tap(v, 5.0, -5.0)
    tap(v, 10.0, 0.0, shift=True)
    v.mode.set("Cross-section")
    tap(v, -10.0, 0.0)
    tap(v, 10.0, 0.0)
    v._set_box((-10.0, 10.0, -10.0, 10.0))
    kinds = [k for k, _ in labels(v)]
    assert kinds == ["snd", "snd", "xs", "box"]
    assert "Section A–B · 20.0 km" in dict(labels(v)).values()
    assert len(v.items_bar.objects) == 4  # map view, soundings, section, box
    v._remove_point(0)
    assert [p[1][:2] for p in v.points] == [(10.0, 0.0)]
    v._remove_xs()
    v._remove_box()
    assert [k for k, _ in labels(v)] == ["snd"] and v.box is None


def test_tray_figure_buttons_switch_to_figure(viewer):
    v = viewer
    v._add_mean()
    snd = v.items_bar.objects[1]
    fig_btn = [w for w in snd.objects if getattr(w, "icon", "") == "photo"][0]
    fig_btn.clicks += 1
    assert v.workspace.value == "Figure"
    assert v.figed.spec["kind"] == "sounding"
