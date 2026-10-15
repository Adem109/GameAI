"""Update check: compares our VERSION with the one on GitHub.

It only reads a version number. Installing is left to the player: the
"Download" button opens the zip in their browser.
"""
import re
import threading
import urllib.request
import webbrowser

from .ai import SSL_CONTEXT
from .version import VERSION

REPO = "Adem109/GameAI"
VERSION_URL = f"https://raw.githubusercontent.com/{REPO}/HEAD/cozyroads/version.py"
DOWNLOAD_URL = f"https://github.com/{REPO}/archive/HEAD.zip"


def parse_version(text):
    m = re.search(r"^VERSION\s*=\s*(\d+)", text, re.M)
    return int(m.group(1)) if m else None


class UpdateChecker:
    def __init__(self):
        self.state = "idle"  # idle | checking | current | available | error
        self.message = f"Version {VERSION}"
        self.remote_version = None

    def check(self):
        if self.state != "checking":
            self.state, self.message = "checking", "Checking for updates..."
            threading.Thread(target=self._check, daemon=True).start()

    def _check(self):
        try:
            req = urllib.request.Request(VERSION_URL, headers={"User-Agent": "CozyRoads", "Cache-Control": "no-cache"})
            with urllib.request.urlopen(req, timeout=15, context=SSL_CONTEXT) as resp:
                remote = parse_version(resp.read().decode())
        except Exception as exc:
            self.state, self.message = "error", f"Couldn't check for updates: {exc}"
            return
        self.remote_version = remote
        if remote and remote > VERSION:
            self.state = "available"
            self.message = f"Version {remote} is out (you have {VERSION}). Press Enter to download."
        else:
            self.state, self.message = "current", f"You're up to date (version {VERSION})."

    def open_download(self):
        webbrowser.open(DOWNLOAD_URL)
        self.message = "Download started in your browser. Unzip it and copy the files over your CozyRoads folder."
