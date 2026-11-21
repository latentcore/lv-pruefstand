"""Find a Chromium browser for headless work: Google Chrome, Chromium or Microsoft Edge.

Used by the export (Risikobericht.pdf, web/export/files.py), the deck build and the
screenshots of pitch/ (pitch/chrome.py). A browser that is not on PATH is also looked
for where it installs itself on Windows and macOS (Edge comes with Windows; Chrome
often is not on PATH there). PITCH_CHROME names another browser file;
PITCH_CHROME=none makes this machine count as one without a browser.
"""
import os
import shutil

NAMES = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome",
         "microsoft-edge", "microsoft-edge-stable", "msedge")
# Install places, %VAR% for Windows. On other systems a %VAR% place is not expanded and is skipped.
PLACES = (
    r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
    r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
    r"%LocalAppData%\Google\Chrome\Application\chrome.exe",
    r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
    r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
)


def find(choice=None):
    """Path of the browser, or None.

    choice: a browser file or name, "none", or None for PITCH_CHROME, then PATH, then the
    install places.
    """
    choice = choice or os.environ.get("PITCH_CHROME")
    if choice:
        if choice.lower() == "none":
            return None
        return shutil.which(choice) or (choice if os.path.isfile(choice) else None)
    for name in NAMES:
        found = shutil.which(name)
        if found:
            return found
    for place in PLACES:
        path = os.path.expandvars(place)
        if "%" not in path and os.path.isfile(path):
            return path
    return None


def writes_dom(path):
    """True when the browser prints the page to its standard output with --dump-dom.

    The Windows launcher of Microsoft Edge (msedge.exe) hands the work to another process and
    prints nothing, so it serves for PDFs and screenshots but not for reading a page back.
    """
    return bool(path) and not (os.name == "nt" and os.path.basename(path).lower() == "msedge.exe")


def find_dom(choice=None):
    """Like find(), but only a browser that writes_dom(); None when there is none."""
    found = find(choice)
    if found and writes_dom(found):
        return found
    if choice or os.environ.get("PITCH_CHROME"):
        return None
    for name in NAMES:
        path = shutil.which(name)
        if path and writes_dom(path):
            return path
    for place in PLACES:
        path = os.path.expandvars(place)
        if "%" not in path and os.path.isfile(path) and writes_dom(path):
            return path
    return None
