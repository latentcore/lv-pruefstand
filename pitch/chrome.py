"""Headless Chrome, Chromium or Microsoft Edge for the deck PDF and the screenshots (W10).

No browser on the machine is not an error: browser() gives None and the caller
writes what it can without it. PITCH_CHROME names another browser file;
PITCH_CHROME=none makes this machine count as one without a browser. The search
itself is web/browser.py (PATH, then the install places of Windows and macOS).
"""
import os
import subprocess
import tempfile
from pathlib import Path

from web import browser as _browser

BROWSERS = _browser.NAMES
TIMEOUT = 120


def browser(choice=None):
    """Path of the browser, or None. choice: a path, "none", or None for the search of web/browser.py."""
    return _browser.find(choice)


def _run(chrome, arguments, target=None, timeout=TIMEOUT):
    """Run the browser once with a profile of its own. Returns (stdout bytes, None) or (None, why not)."""
    with tempfile.TemporaryDirectory(prefix="pitch-chrome-") as profile:
        command = [chrome, "--headless=new", "--no-sandbox", "--disable-gpu", "--disable-extensions", "--no-first-run",
                   "--hide-scrollbars", "--user-data-dir=%s" % profile] + arguments
        try:
            done = subprocess.run(command, capture_output=True, timeout=timeout)
        except (OSError, subprocess.TimeoutExpired) as error:
            return None, "the browser did not run: %s" % error
    if target and (not os.path.isfile(target) or os.path.getsize(target) == 0):
        return None, "the browser wrote no file (exit code %s)" % done.returncode
    return done.stdout, None


def as_url(place):
    return place if "://" in place else Path(os.path.abspath(place)).as_uri()


def print_pdf(chrome, page, target):
    """Print a page to PDF; the page size comes from its style sheet (@page)."""
    _, why = _run(chrome, ["--no-pdf-header-footer", "--print-to-pdf=%s" % target, as_url(page)], target)
    return why


def screenshot(chrome, page, target, width, height, wait_ms=4000):
    _, why = _run(chrome, ["--window-size=%d,%d" % (width, height), "--force-device-scale-factor=1",
                           "--virtual-time-budget=%d" % wait_ms, "--screenshot=%s" % target, as_url(page)], target)
    return why


def dump_dom(chrome, page, width=1920, height=1200, wait_ms=4000):
    """The page's HTML after its scripts ran. Returns (text, None) or (None, why not)."""
    if not _browser.writes_dom(chrome):
        return None, "this browser prints no page on its standard output (Microsoft Edge on Windows); use Chrome or Chromium"
    out, why = _run(chrome, ["--window-size=%d,%d" % (width, height), "--virtual-time-budget=%d" % wait_ms,
                             "--dump-dom", as_url(page)])
    if why:
        return None, why
    return out.decode("utf-8", "replace"), None
