"""F4: video export beside the GIF.  No real encoder is needed: a stand-in script reads the raw
frames the way ffmpeg is driven and records what it was given."""
import os
import stat
import sys

import pytest
from PIL import Image

from cm1view.figures import spec as fg

FAKE = """#!{py}
import sys
args = sys.argv[1:]
data = sys.stdin.buffer.read()
size = args[args.index("-s") + 1]
open(args[-1], "wb").write((size + " " + str(len(data))).encode())
"""


def fake_encoder(tmp_path, body=None):
    exe = tmp_path / "fakeffmpeg"
    exe.write_text((body or FAKE).format(py=sys.executable))
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
    return str(exe)


def test_frames_are_padded_to_one_even_size(tmp_path):
    imgs = [Image.new("RGB", (11, 7), "red"), Image.new("RGB", (9, 8), "blue")]
    out = fg.write_video(imgs, str(tmp_path / "sub" / "a.mp4"), 4.0, encoder=fake_encoder(tmp_path))
    size, n = open(out).read().split()
    assert size == "12x8" and int(n) == 2 * 12 * 8 * 3


def test_a_failing_encoder_says_why(tmp_path):
    bad = fake_encoder(tmp_path, "#!{py}\nimport sys\nsys.stderr.write('no such codec')\nsys.exit(1)\n")
    with pytest.raises(RuntimeError, match="no such codec"):
        fg.write_video([Image.new("RGB", (4, 4))], str(tmp_path / "a.mp4"), encoder=bad)


def test_no_encoder_is_a_clear_error(tmp_path, monkeypatch):
    monkeypatch.setattr(fg.base, "video_encoder", lambda: None)
    with pytest.raises(RuntimeError, match="No video encoder"):
        fg.write_video([Image.new("RGB", (4, 4))], str(tmp_path / "a.mp4"))


def test_encoder_is_found_on_path(tmp_path, monkeypatch):
    exe = fake_encoder(tmp_path)
    monkeypatch.setenv("PATH", os.path.dirname(exe))
    os.rename(exe, str(tmp_path / "ffmpeg"))
    assert fg.video_encoder() == str(tmp_path / "ffmpeg")
