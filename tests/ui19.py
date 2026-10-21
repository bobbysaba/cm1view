"""Browser screenshots: the workspace switch shows Map | Figure until a 3D region is
drawn, then Map | 3D | Figure.
Usage: python tests/ui19.py URL OUTDIR PROFILE_DIR"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shot import FF, click_text  # noqa: E402
from ui6 import drag  # noqa: E402
from ui18 import rects  # noqa: E402


def main():
    url, out, prof = sys.argv[1:4]
    os.makedirs(out, exist_ok=True)
    ff = FF(w=1280, h=800, prof=prof)
    try:
        ff.go(url)
        time.sleep(12)
        ff.shot(f"{out}/a_start.png")
        click_text(ff, "3D region")
        time.sleep(1)
        x, y, w, h = max(rects(ff, "canvas"), key=lambda r: r[2] * r[3])
        drag(ff, x + w * 0.40, y + h * 0.40, x + w * 0.55, y + h * 0.55)
        time.sleep(8)
        ff.shot(f"{out}/b_region.png")
        click_text(ff, "Map")
        time.sleep(3)
        ff.shot(f"{out}/c_back_to_map.png")
    finally:
        ff.close()


if __name__ == "__main__":
    main()
