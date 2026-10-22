"""The viewer in a real browser (headless Firefox): the server starts on the demo run,
the page draws, a click on the map gives a sounding, and the Figure workspace, the
settings window and the page without a run open.  Screenshots of each step go to
$CM1VIEW_SHOTS (default: a temporary folder) for a look by eye.

  pytest -m browser            (needs Firefox on PATH, or $FIREFOX)
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

import pytest

from shot import _WALK, FF, click, click_text, find, firefox, rects, until

pytestmark = [pytest.mark.browser,
              pytest.mark.skipif(not firefox(), reason="Firefox not found ($FIREFOX)")]


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def shots():
    d = os.environ.get("CM1VIEW_SHOTS") or tempfile.mkdtemp(prefix="cm1view-shots-")
    os.makedirs(d, exist_ok=True)
    print(f"\nscreenshots: {d}")
    return d


def serve(args, cfg_dir, extra_env=None):
    """Start `cm1view args` on a free port with its own settings file; its base URL."""
    port = free_port()
    env = dict(os.environ, CM1VIEW_CONFIG=os.path.join(cfg_dir, "config.toml"),
               **(extra_env or {}))
    p = subprocess.Popen([sys.executable, "-m", "cm1view", *args, "--port", str(port)],
                         env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    url = f"http://127.0.0.1:{port}/cm1view"

    def up():
        try:
            return urllib.request.urlopen(url, timeout=5).status == 200
        except OSError:
            return False
    if not until(up, 120, 1.0):
        p.terminate()
        raise RuntimeError("the server did not start")
    return p, url


@pytest.fixture(scope="module")
def scanned_run(demo_run, tmp_path_factory):
    """A run only the runs_root scan finds (not next to the demo run, not recent)."""
    d = tmp_path_factory.mktemp("scan-root") / "supercell_scanned"
    d.mkdir()
    for f in os.listdir(demo_run):
        if f == "namelist.input" or f.endswith(".nc"):
            os.symlink(os.path.join(demo_run, f), d / f)
    return str(d)


@pytest.fixture(scope="module")
def server(demo_run, demo_root, scanned_run, tmp_path_factory):
    cfg = tmp_path_factory.mktemp("browser-cfg")
    with open(cfg / "config.toml", "w") as f:
        f.write(f'[paths]\nruns_root = ["{demo_root}", "{os.path.dirname(scanned_run)}"]\n')
    p, url = serve([demo_run], str(cfg))
    yield url
    p.terminate()
    p.wait(30)


@pytest.fixture
def ff(tmp_path):
    prof, dl = tmp_path / "profile", tmp_path / "downloads"
    prof.mkdir()
    dl.mkdir()
    with open(prof / "user.js", "w") as f:  # downloads land in tmp_path/downloads, unasked
        f.write(f'user_pref("browser.download.dir", "{dl}");\n'
                'user_pref("browser.download.folderList", 2);\n'
                'user_pref("browser.download.useDownloadDir", true);\n'
                'user_pref("browser.download.always_ask_before_handling_new_types", false);\n')
    b = FF(w=1280, h=850, port=free_port(), prof=str(prof))
    b.downloads = str(dl)
    yield b
    b.close()


def map_canvas(ff):
    """The largest canvas (the map) once the page has drawn it: [x, y, w, h]."""
    return until(lambda: max(rects(ff, "canvas"), key=lambda r: r[2] * r[3], default=None),
                 60)


def test_map_and_a_sounding(ff, server, shots):
    ff.go(server)
    x, y, w, h = map_canvas(ff)
    assert w > 300 and h > 300
    time.sleep(3)
    ff.shot(f"{shots}/a_map.png")
    click_text(ff, "Sounding")
    time.sleep(1)
    click(ff, x + w * 0.70, y + h * 0.25)  # the environment, ahead of the storm
    assert until(lambda: rects(ff, ".zv"), 120), "no sounding graphics"
    time.sleep(2)
    ff.shot(f"{shots}/b_sounding.png")
    z = rects(ff, ".zv")[0]
    click(ff, z[0] + z[2] / 2, z[1] + z[3] / 2)  # expanded view
    time.sleep(3)
    ff.shot(f"{shots}/c_expanded.png")


def test_figure_workspace(ff, server, shots):
    ff.go(server)
    map_canvas(ff)
    click_text(ff, "Figure")
    assert until(lambda: find(ff, "Panels"), 60), "no Figure editor"
    time.sleep(8)
    ff.shot(f"{shots}/d_figure.png")


def status_has(ff, text):
    """Whether a status line of the page (.cv-status) shows `text`."""
    return ff.js("(() => {" + _WALK + "let hit = false; walk(document, el => { if (el.classList "
                 "&& el.classList.contains('cv-status') && el.textContent.includes("
                 + json.dumps(text) + ")) hit = true; }); return hit; })()")


def pick(ff, label):
    """Choose the option showing `label` in whichever select offers it."""
    return ff.js("(() => {" + _WALK + "let ok = false; walk(document, el => { if (ok || "
                 "el.tagName !== 'SELECT') return; for (const o of el.options) if "
                 "(o.textContent.trim() === " + json.dumps(label) + ") { el.value = o.value; "
                 "el.dispatchEvent(new Event('change')); ok = true; } }); return ok; })()")


def test_figure_clicks_download_and_scanned_runs(ff, server, shots, scanned_run):
    ff.go(server)
    map_canvas(ff)
    click_text(ff, "Figure")
    assert until(lambda: find(ff, "Panels"), 60), "no Figure editor"
    # the runs_root scan (in the background) feeds the Run lists
    name = os.path.basename(scanned_run)
    offered = ("(() => {" + _WALK + "let n = 0; walk(document, el => { if (el.tagName === "
               "'OPTGROUP' && el.label.startsWith('Other runs')) for (const o of el.children) "
               "if (o.textContent.includes(" + json.dumps(name) + ")) n++; }); return n; })()")
    assert until(lambda: ff.js(offered), 90), "the scanned run is not offered"
    # a click on the preview places a marker where it lands in a panel
    assert until(lambda: rects(ff, "img"), 60), "no preview"
    time.sleep(5)  # (the first preview)
    assert pick(ff, "Click to add a marker")
    x, y, w, h = max(rects(ff, "img"), key=lambda r: r[2] * r[3])
    for fx, fy in ((0.25, 0.3), (0.5, 0.3), (0.25, 0.7), (0.5, 0.6)):
        click(ff, x + fx * w, y + fy * h)
        if until(lambda: status_has(ff, "Added marker"), 10):
            break
    else:
        raise AssertionError("no click landed in a panel")
    ff.shot(f"{shots}/h_figure_click.png")
    # the download is drawn in the background, then saved by the browser
    click_text(ff, "Download")
    png = until(lambda: [f for f in os.listdir(ff.downloads) if f.endswith(".png")], 120)
    assert png, "no download"
    time.sleep(1)
    with open(os.path.join(ff.downloads, png[0]), "rb") as f:
        assert f.read(8) == b"\x89PNG\r\n\x1a\n"
    assert not status_has(ff, "Could not draw the download")


def test_settings_window(ff, server, shots):
    ff.go(server)
    map_canvas(ff)
    click_text(ff, "ti-settings", how="class")
    assert until(lambda: find(ff, "Config file"), 30), "no settings window"
    ff.shot(f"{shots}/e_settings.png")
    click_text(ff, "Config file")
    time.sleep(1)
    ff.shot(f"{shots}/f_config_file.png")


def test_first_run_page(ff, tmp_path, shots):
    p, url = serve([], str(tmp_path / "cfg"))
    try:
        ff.go(url)
        assert until(lambda: find(ff, "Save and continue"), 60), "no first-run window"
        ff.shot(f"{shots}/g_first_run.png")
    finally:
        p.terminate()
        p.wait(30)
