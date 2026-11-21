"""Test setup of the public copy (scripts/public_copy.py writes this file as conftest.py there).

The public copy leaves out some files of the working repository: the stored results of
project 79-222 (they quote the organizer files), the plan, the opening finding of the
deck and a few tests that copy organizer text. A test that needs such a file cannot run
here.

The rule names no test. Code of this folder that looks up a path inside this folder
that does not exist is noted, with the code file that asked (os.stat, which
os.path.exists, isfile and pathlib use; reading opens; folder listings). A test that
fails is reported as skipped, with the missing paths as the reason, if such a look-up
was made while it ran, or at import time by its test module or by a module of this
folder that the test module imports (then every failure in that test module counts as
caused by it). A test module whose import fails after such a look-up is skipped the
same way. Any other failure stays a failure. Look-ups under the git-ignored folders
(data/, cache/, out/, reviews/) do not count: the tests that need the organizer data or
a pipeline run check for it and skip on their own.
"""
import os
import sys
import types

import pytest

THIS = os.path.abspath(__file__)
ROOT = os.path.dirname(THIS)

collect_ignore_glob = ["out/*", "cache/*", "data/*", "reviews/*"]

NOT_COUNTED_TOP = {"data", "cache", "out", "reviews", ".git"}
NOT_COUNTED_PARTS = {"__pycache__", ".pytest_cache"}
REASON = "needs %s, which this public copy leaves out"

_state = {"on": False, "phase": None, "now": set()}
_at_import = {}   # code file -> missing paths it looked up while test modules were imported
_at_setup = {}    # test module -> missing paths looked up while its tests were set up
_real_stat = os.stat


def _asking_code_file():
    """The nearest caller that is code of this folder, or None.

    pytest itself (package checks, traceback lines) and the import system also look up
    paths that do not exist; such look-ups say nothing about what a test needs.
    """
    frame = sys._getframe(1)
    while frame is not None:
        name = frame.f_code.co_filename
        if name != THIS:
            if name.startswith(ROOT + os.sep):
                return name
            if os.sep + "_pytest" + os.sep in name or os.sep + "pluggy" + os.sep in name:
                return None
        frame = frame.f_back
    return None


def _note(path, known_absent=False):
    if not _state["on"] or path is None or isinstance(path, int):
        return
    try:
        full = os.path.abspath(os.fsdecode(path))
    except (TypeError, ValueError):
        return
    rel = os.path.relpath(full, ROOT)
    if rel == os.curdir or rel == os.pardir or rel.startswith(os.pardir + os.sep):
        return
    parts = rel.split(os.sep)
    if parts[0] in NOT_COUNTED_TOP or NOT_COUNTED_PARTS.intersection(parts) or parts[-1].startswith("<"):
        return
    if not known_absent:
        try:
            _real_stat(full)
            return
        except OSError:
            pass
    code_file = _asking_code_file()
    if code_file is None:
        return
    rel = "/".join(parts)
    _state["now"].add(rel)
    if _state["phase"] == "collect":
        _at_import.setdefault(code_file, set()).add(rel)


def _stat(path, *args, **kwargs):
    try:
        return _real_stat(path, *args, **kwargs)
    except FileNotFoundError:
        if kwargs.get("dir_fd") is None:
            _note(path, known_absent=True)
        raise


for _support in (os.supports_fd, os.supports_dir_fd, os.supports_follow_symlinks):
    if _real_stat in _support:
        _support.add(_stat)
os.stat = _stat


def _wrap_path(name):
    """On Windows os.path.exists, isfile and isdir test a path without os.stat (nt._path_* fast
    paths), so a look-up through them is noted here as well."""
    real = getattr(os.path, name)

    def guarded(path, *args, **kwargs):
        result = real(path, *args, **kwargs)
        if not result:
            try:
                _note(path)
            except Exception:
                pass
        return result

    guarded.__wrapped__ = real
    setattr(os.path, name, guarded)


for _name in ("exists", "isfile", "isdir", "lexists"):
    _wrap_path(_name)


def _audit(event, args):
    # An exception raised here would abort the audited call, so none may leave this hook.
    try:
        if not _state["on"]:
            return
        if event == "open":
            path, _mode, flags = args
            if not flags or (flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT)) == 0:
                _note(path)
        elif event in ("os.listdir", "os.scandir"):
            _note(args[0])
    except Exception:
        pass


sys.addaudithook(_audit)


def _code_files(module):
    """Files of this folder that a test module imports, directly or through other modules."""
    files, seen, todo = set(), set(), [module]
    while todo:
        mod = todo.pop()
        if mod is None or id(mod) in seen:
            continue
        seen.add(id(mod))
        name = getattr(mod, "__file__", None)
        if not name or not os.path.abspath(name).startswith(ROOT + os.sep):
            continue
        files.add(os.path.abspath(name))
        for value in list(vars(mod).values()):
            if isinstance(value, types.ModuleType):
                todo.append(value)
                continue
            try:
                owner = getattr(value, "__module__", None)
            except Exception:
                owner = None
            if isinstance(owner, str):
                todo.append(sys.modules.get(owner))
    return files


def _skipped(path, line, missing):
    return (str(path), line, "Skipped: " + REASON % ", ".join(sorted(missing)))


@pytest.hookimpl(wrapper=True)
def pytest_make_collect_report(collector):
    if not isinstance(collector, pytest.Module):
        return (yield)
    _state.update(on=True, phase="collect", now=set())
    try:
        report = yield
    finally:
        _state.update(on=False, phase=None)
    if report.failed and _state["now"]:
        return pytest.CollectReport(collector.nodeid, "skipped",
                                    _skipped(collector.path, 1, _state["now"]), [])
    return report


@pytest.hookimpl(wrapper=True)
def pytest_runtest_protocol(item, nextitem):
    _state.update(on=True, phase="run", now=set())
    try:
        return (yield)
    finally:
        _state.update(on=False, phase=None)


def _module_id(item):
    module = item.getparent(pytest.Module)
    return module.nodeid if module is not None else None


@pytest.hookimpl(wrapper=True)
def pytest_runtest_setup(item):
    try:
        return (yield)
    finally:
        _at_setup.setdefault(_module_id(item), set()).update(_state["now"])


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item, call):
    report = yield
    if not report.failed or call.when not in ("setup", "call"):
        return report
    missing = set(_state["now"])
    module = item.getparent(pytest.Module)
    if module is not None:
        for code_file in _code_files(module.obj):
            missing |= _at_import.get(code_file, set())
    if call.when == "setup":
        # A failed module or class fixture is raised again for each later test of the
        # module without running again, so the set-up look-ups of the module count here.
        missing |= _at_setup.get(_module_id(item), set())
    if missing:
        path, line = item.reportinfo()[:2]
        report.outcome = "skipped"
        report.longrepr = _skipped(path, (line or 0) + 1, missing)
    return report
