"""Browser screenshots: Figure workspace (layout tab, layers tab, export tab).
Usage: python tests/ui14.py URL OUTDIR PROFILE_DIR"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shot import FF, click_text  # noqa: E402
from ui13 import click_label  # noqa: E402


def main():
    url, out, prof = sys.argv[1:4]
    os.makedirs(out, exist_ok=True)
    ff = FF(prof=prof)
    try:
        ff.go(url)
        time.sleep(10)
        click_text(ff, "Figure")
        time.sleep(12)
        ff.shot(f"{out}/f_layout.png")
        click_label(ff, "Layers")
        time.sleep(2)
        ff.shot(f"{out}/g_layers.png")
        click_label(ff, "Text & axes")
        time.sleep(2)
        ff.shot(f"{out}/h_text.png")
        click_label(ff, "Export")
        time.sleep(2)
        ff.shot(f"{out}/i_export.png")
    finally:
        ff.close()


if __name__ == "__main__":
    main()
