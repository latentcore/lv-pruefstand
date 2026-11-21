"""The browser search of web/browser.py: PITCH_CHROME, PATH, then the install places."""
import os
import sys

from web import browser


def test_none_means_no_browser():
    assert browser.find("none") is None
    assert browser.find("NONE") is None


def test_a_named_file_is_taken_as_it_is():
    assert browser.find(sys.executable) == sys.executable
    assert browser.find("no-such-browser-file") is None


def test_the_environment_names_the_browser(monkeypatch):
    monkeypatch.setenv("PITCH_CHROME", "none")
    assert browser.find() is None
    monkeypatch.setenv("PITCH_CHROME", sys.executable)
    assert browser.find() == sys.executable


def test_path_comes_before_the_install_places(monkeypatch):
    monkeypatch.delenv("PITCH_CHROME", raising=False)
    monkeypatch.setattr(browser.shutil, "which", lambda name: "/bin/" + name if name == "msedge" else None)
    assert browser.find() == "/bin/msedge"


def test_an_install_place_is_found_when_nothing_is_on_path(monkeypatch, tmp_path):
    monkeypatch.delenv("PITCH_CHROME", raising=False)
    monkeypatch.setattr(browser.shutil, "which", lambda name: None)
    edge = tmp_path / "msedge.exe"
    edge.write_bytes(b"")
    monkeypatch.setattr(browser, "PLACES", (r"%NO_SUCH_VARIABLE_X9%\chrome.exe", str(edge)))
    assert browser.find() == str(edge)


def test_nothing_found(monkeypatch):
    monkeypatch.delenv("PITCH_CHROME", raising=False)
    monkeypatch.setattr(browser.shutil, "which", lambda name: None)
    monkeypatch.setattr(browser, "PLACES", (os.path.join("no", "such", "browser"),))
    assert browser.find() is None


def test_edge_on_windows_prints_no_page_back(monkeypatch):
    monkeypatch.setattr(browser.os, "name", "nt")
    assert browser.writes_dom("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe") is False
    assert browser.writes_dom("C:/Program Files/Google/Chrome/Application/chrome.exe") is True
    assert browser.writes_dom(None) is False


def test_the_page_reader_skips_edge_on_windows(monkeypatch):
    monkeypatch.delenv("PITCH_CHROME", raising=False)
    monkeypatch.setattr(browser.os, "name", "nt")
    monkeypatch.setattr(browser.shutil, "which", lambda name: "C:/x/msedge.exe" if name == "msedge" else None)
    monkeypatch.setattr(browser, "PLACES", ())
    assert browser.find() == "C:/x/msedge.exe"
    assert browser.find_dom() is None
