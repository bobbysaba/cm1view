"""The viewer in a real browser (headless Firefox): the server starts on the demo run,
the page draws, a click on the map gives a sounding, and the Figure workspace, the
settings window and the page without a run open.  Screenshots of each step go to
$CM1VIEW_SHOTS (default: a temporary folder) for a look by eye.

  pytest -m browser            (needs Firefox on PATH, or $FIREFOX)
"""
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

import pytest

from shot import FF, click, click_text, find, firefox, rects, until

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
def server(demo_run, demo_root, tmp_path_factory):
    cfg = tmp_path_factory.mktemp("browser-cfg")
    with open(cfg / "config.toml", "w") as f:
        f.write(f'[paths]\nruns_root = ["{demo_root}"]\n')
    p, url = serve([demo_run], str(cfg))
    yield url
    p.terminate()
    p.wait(30)


@pytest.fixture
def ff(tmp_path):
    b = FF(w=1280, h=850, port=free_port(), prof=str(tmp_path / "profile"))
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
