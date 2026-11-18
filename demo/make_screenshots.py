"""Screenshot the dashboard for the README and portfolio (needs Microsoft Edge or Chrome).

    python demo/make_screenshots.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import build  # noqa: E402

OUT = ROOT / "docs" / "screenshots"
WIDTH = 1600


def find_browser():
    candidates = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        shutil.which("google-chrome"), shutil.which("chromium"), shutil.which("msedge"),
    ]
    return next((c for c in candidates if c and Path(c).exists()), None)


def main() -> None:
    build.main()
    browser = find_browser()
    if not browser:
        raise SystemExit("Edge or Chrome is needed for screenshots.")
    OUT.mkdir(parents=True, exist_ok=True)
    full = OUT / "full_page.png"
    with tempfile.TemporaryDirectory() as profile:
        subprocess.run(
            [browser, "--headless=new", "--disable-gpu", "--hide-scrollbars",
             f"--user-data-dir={profile}", f"--window-size={WIDTH},3000",
             "--virtual-time-budget=15000", f"--screenshot={full}",
             (ROOT / "docs" / "index.html").as_uri()],
            check=True, timeout=120, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    page = Image.open(full)
    # Crop the empty background below the footer.
    gray = page.convert("L")
    bottom = page.height
    while bottom > 1000 and min(gray.crop((0, bottom - 20, WIDTH, bottom)).getdata()) > 240:
        bottom -= 20
    page = page.crop((0, 0, WIDTH, bottom + 20))
    page.save(full)
    page.crop((0, 0, WIDTH, 1000)).save(OUT / "overview.png")
    print(f"Saved {OUT / 'overview.png'} and {full}")


if __name__ == "__main__":
    main()
