#!/usr/bin/env python3
"""Clean-clone check (W9): does the demo open from an empty folder, with the network off?

    python scripts/clean_clone_check.py [branch] [--data DIR] [--python EXE] [--keep] [--copy-data]

Run it from a checkout of this repository, with Python 3.12 (macOS, Linux).
branch: a branch (or any commit name) of this checkout; default: the commit
that is checked out. Only committed files are tested.

What it does, and prints as a table "step / ok or failed" at the end:

  with the network (the only part that needs it)
    clone the branch from this checkout into an empty temporary folder,
    make a virtual environment there, pip install -r requirements.txt
  without the network (see below)
    without data/:  python -m pipeline.run says what is missing (exit 3),
                    the screen opens on its sample data, python -m pytest -q
    with data/ (a link to the data folder of this checkout, or a copy):
                    python -m pipeline.run (exit 0), a second run leaves every
                    file byte-equal, python -m pytest -q, the screen on a free
                    port: page, its static files, /api/findings, one page
                    image; python -m web.export
    no outside address in web/static and in the exported HTML
    no Python process of this part tried to reach an outside address

"Without the network" is proven in two ways. (1) On Linux the whole second
part runs inside `unshare -n` (a network namespace that has only its own
loopback); the script checks there that an outside connection fails. Where
`unshare -n` is not allowed, and on macOS and Windows, the script says so and
relies on (2); the proof with the switch is then the hand test of docs/DEMO.md
("What the humans do themselves"), Wi-Fi off. (2) Everywhere: every Python process of the second part loads a
small guard (a sitecustomize.py on PYTHONPATH) that refuses and writes down
each connection or name lookup that is not this machine. The table shows how
many were written down (0 is the proof; a self-test shows the guard works).
The guard does not see programs that are not Python (pdftotext, Chrome).

Windows: `py -3.12 scripts\\clean_clone_check.py` runs the same steps (data is
copied, there is no unshare, proof (2) only). We did not try it on Windows;
if it stops there, do the steps of docs/DEMO.md ("What the humans do
themselves") by hand.

Exit code 0: every step ok. 1: a step failed. 2: the check could not start.
No line printed here holds a price or an amount.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE = os.path.dirname(HERE)
PROJECT = "79-222"
OK, FAILED, NOT_HERE = "ok", "failed", "n/a"
OUTSIDE = re.compile(r"(?:https?:)?//[A-Za-z0-9][^\s\"'<>)]*", re.IGNORECASE)
OUTSIDE_TEST_ADDRESS = ("192.0.2.1", 9)      # TEST-NET-1 (RFC 5737): never a real host

GUARD = r'''"""Loaded by every Python process of the offline part (clean_clone_check.py)."""
import os, socket
_LOG = os.environ.get("W9_NET_LOG")
_LOCAL_NAMES = ("localhost", "ip6-localhost", "")
def _local(host):
    if host is None: return True
    if isinstance(host, bytes): host = host.decode("ascii", "replace")
    host = str(host)
    return host in _LOCAL_NAMES or host.startswith("127.") or host in ("::1", "0.0.0.0", "::") \
        or host == socket.gethostname()
def _note(what, target):
    if _LOG:
        with open(_LOG, "a", encoding="utf-8") as handle:
            handle.write("%s %s pid=%d\n" % (what, target, os.getpid()))
    raise OSError("clean-clone check: outside address refused: %s %s" % (what, target))
def _wrap_connect(name):
    real = getattr(socket.socket, name)
    def guarded(self, address, *rest):
        if self.family in (socket.AF_INET, socket.AF_INET6) and isinstance(address, tuple) and not _local(address[0]):
            _note(name, "%s:%s" % (address[0], address[1]))
        return real(self, address, *rest)
    setattr(socket.socket, name, guarded)
def _wrap_lookup(name):
    real = getattr(socket, name)
    def guarded(host, *rest, **more):
        if not _local(host):
            try:
                import ipaddress; ipaddress.ip_address(host.decode() if isinstance(host, bytes) else host)
            except ValueError:
                _note(name, host)
        return real(host, *rest, **more)
    setattr(socket, name, guarded)
if _LOG:
    for _name in ("connect", "connect_ex"): _wrap_connect(_name)
    for _name in ("getaddrinfo", "gethostbyname", "gethostbyname_ex"): _wrap_lookup(_name)
'''


class Table:
    def __init__(self):
        self.rows = []

    def add(self, step, status, note=""):
        self.rows.append([step, status, note])
        print("  [%s] %s%s" % (status, step, ("  (" + note + ")") if note else ""), flush=True)
        return status == OK

    def show(self, stream=sys.stdout):
        width = max(len(row[0]) for row in self.rows)
        print("\n%-*s  %-6s  %s" % (width, "step", "result", "note"), file=stream)
        print("%s  %s  %s" % ("-" * width, "-" * 6, "-" * 20), file=stream)
        for step, status, note in self.rows:
            print("%-*s  %-6s  %s" % (width, step, status, note), file=stream)


def run(arguments, cwd=None, env=None, log=None, timeout=1800):
    """Run a command; returns (exit code, output). The output also goes to the log file."""
    try:
        done = subprocess.run(arguments, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              timeout=timeout)
        code, text = done.returncode, done.stdout.decode("utf-8", "replace")
    except (OSError, subprocess.TimeoutExpired) as error:
        code, text = -1, "%s: %s" % (type(error).__name__, error)
    if log:
        with open(log, "w", encoding="utf-8") as handle:
            handle.write("$ %s\n(exit code %d)\n%s" % (" ".join(arguments), code, text))
    return code, text


def last_line(text):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[-1][:160] if lines else ""


def venv_python(venv):
    return os.path.join(venv, "Scripts", "python.exe") if os.name == "nt" else os.path.join(venv, "bin", "python")


def hashes(*folders):
    found = {}
    for folder in folders:
        for base, _dirs, files in os.walk(folder):
            for name in files:
                path = os.path.join(base, name)
                with open(path, "rb") as handle:
                    found[os.path.relpath(path, os.path.dirname(folder))] = hashlib.sha256(handle.read()).hexdigest()
    return found


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def fetch(url, timeout=20):
    """(status, content type, body bytes) of a GET on this machine; proxies are not used."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url, timeout=timeout) as answer:
            return answer.status, answer.headers.get("Content-Type", ""), answer.read()
    except urllib.error.HTTPError as error:
        return error.code, error.headers.get("Content-Type", ""), error.read()
    except (OSError, ValueError) as error:
        return 0, "", str(error).encode("utf-8")


def outside_reachable():
    """True when a connection to an outside address can be opened now."""
    for target in (("1.1.1.1", 443), ("8.8.8.8", 53)):
        try:
            socket.create_connection(target, timeout=3).close()
            return True
        except OSError:
            pass
    return False


def test_counts(text):
    line = last_line(text)
    found = {word: int(number) for number, word in re.findall(r"(\d+) (passed|failed|skipped|errors?)", line)}
    return found, line


# ---- the part with the network: clone, virtual environment, install ----------

def git(arguments, cwd):
    done = subprocess.run(["git"] + arguments, cwd=cwd, capture_output=True, text=True)
    return done.returncode, (done.stdout + done.stderr).strip()


def outer(args):
    table = Table()
    code, commit = git(["rev-parse", "--verify", "--quiet", (args.branch or "HEAD") + "^{commit}"], SOURCE)
    if code != 0 and args.branch:
        code, commit = git(["rev-parse", "--verify", "--quiet", "origin/%s^{commit}" % args.branch], SOURCE)
    if code != 0:
        print("No branch or commit \"%s\" in %s." % (args.branch, SOURCE), file=sys.stderr)
        return 2
    _code, dirty = git(["status", "--porcelain", "--untracked-files=no"], SOURCE)
    work = tempfile.mkdtemp(prefix="lv-pruefstand-clean-clone-")
    clone, venv, logs = os.path.join(work, "clone"), os.path.join(work, "venv"), os.path.join(work, "logs")
    os.mkdir(logs)
    print("Clean-clone check of %s (commit %s) in %s" % (args.branch or "the checked-out commit", commit[:7], work))
    if dirty:
        print("Note: this checkout has changes that are not committed; they are not part of the check.")
    if sys.version_info[:2] != (3, 12):
        print("Note: this is Python %d.%d; the project is built and tested with 3.12." % sys.version_info[:2])

    code, text = run(["git", "clone", "--quiet", "--no-checkout", "--no-hardlinks", SOURCE, clone],
                     log=os.path.join(logs, "01_clone.log"))
    if code == 0:
        code, text = run(["git", "-c", "advice.detachedHead=false", "checkout", "--quiet", "--detach", commit],
                         cwd=clone, log=os.path.join(logs, "01_checkout.log"))
    left = [name for name in ("data", "cache", "out", "reviews") if os.path.exists(os.path.join(clone, name))]
    fresh = code == 0 and not left
    table.add("clone into an empty folder", OK if fresh else FAILED,
              "commit %s, no data/ cache/ out/ reviews/" % commit[:7] if fresh else (last_line(text) or "has " + ", ".join(left)))
    ready = fresh
    if ready:
        code, text = run([args.python, "-m", "venv", venv], log=os.path.join(logs, "02_venv.log"))
        ready = table.add("virtual environment", OK if code == 0 else FAILED, "" if code == 0 else last_line(text))
    if ready:
        start = time.time()
        code, text = run([venv_python(venv), "-m", "pip", "install", "--quiet", "--disable-pip-version-check",
                          "-r", os.path.join(clone, "requirements.txt")], log=os.path.join(logs, "03_install.log"))
        ready = table.add("pip install -r requirements.txt", OK if code == 0 else FAILED,
                          "%.0f s" % (time.time() - start) if code == 0 else last_line(text))
    if not ready:
        table.show()
        print("\nFAILED before the offline part. Folder kept: %s" % work)
        return 1

    data = os.path.abspath(args.data) if args.data else os.path.join(SOURCE, "data")
    state = {"work": work, "clone": clone, "venv": venv, "logs": logs, "data": data, "copy_data": args.copy_data,
             "rows": table.rows, "mode": "guard", "uid_note": ""}
    state_file = os.path.join(work, "state.json")
    prefix = offline_prefix(state)
    with open(state_file, "w", encoding="utf-8") as handle:
        json.dump(state, handle)
    print("Offline part: %s" % {
        "netns": "inside `unshare -n` (network namespace with its own loopback only)",
        "guard": "`unshare -n` is not available here; outside connections of Python processes are refused "
                 "and counted by the guard"}[state["mode"]] + state["uid_note"], flush=True)
    done = subprocess.run(prefix + [venv_python(venv), os.path.abspath(__file__), "--inner", state_file])
    with open(state_file, encoding="utf-8") as handle:
        state = json.load(handle)
    table.rows = state["rows"]
    if not state.get("finished"):
        table.add("offline part ran to its end", FAILED, "exit code %d" % done.returncode)
    table.show()
    failed = [row[0] for row in table.rows if row[1] == FAILED]
    if failed or args.keep:
        print("\n%s Folder kept: %s (logs in logs/)" % ("FAILED: %s." % "; ".join(failed) if failed else "All ok.", work))
    else:
        shutil.rmtree(work, ignore_errors=True)
        print("\nAll ok. The temporary folder was removed (--keep keeps it).")
    return 1 if failed else 0


def offline_prefix(state):
    """The command prefix that switches the network off, or [] when that is not possible here."""
    unshare = shutil.which("unshare") if sys.platform.startswith("linux") else None
    if not unshare:
        return []
    probe = [unshare, "-r", "-n"]
    if subprocess.run(probe + ["true"], capture_output=True).returncode != 0:
        return []
    state["mode"] = "netns"
    lo_up = "ip link set lo up 2>/dev/null; "
    ids = ["--map-user=%d" % os.getuid(), "--map-group=%d" % os.getgid()]
    nested = probe + ["sh", "-c", lo_up + 'exec "$@"', "sh", unshare, "-U"] + ids
    if subprocess.run(nested + ["true"], capture_output=True).returncode == 0:
        return nested                      # network off, and the user id stays the real one
    state["uid_note"] = "; the commands run as root of that namespace"
    return probe + ["sh", "-c", lo_up + 'exec "$@"', "sh"]


# ---- the part without the network ------------------------------------------------

class Screen:
    """python -m web on a free port, in the clone."""

    def __init__(self, python, clone, env, log, extra=()):
        self.port = free_port()
        self.base = "http://127.0.0.1:%d" % self.port
        self.log = open(log, "w", encoding="utf-8")
        self.process = subprocess.Popen([python, "-m", "web", "--port", str(self.port)] + list(extra), cwd=clone,
                                        env=env, stdout=self.log, stderr=subprocess.STDOUT)

    def wait(self, seconds=30):
        end = time.time() + seconds
        while time.time() < end and self.process.poll() is None:
            if fetch(self.base + "/", timeout=2)[0] == 200:
                return True
            time.sleep(0.3)
        return False

    def stop(self):
        self.process.terminate()
        try:
            self.process.wait(10)
        except subprocess.TimeoutExpired:
            self.process.kill()
        self.log.close()


def inner(state_file):
    with open(state_file, encoding="utf-8") as handle:
        state = json.load(handle)
    table = Table()
    table.rows = state["rows"]

    def save(finished=False):
        state["rows"], state["finished"] = table.rows, finished
        with open(state_file, "w", encoding="utf-8") as handle:
            json.dump(state, handle)

    clone, logs, python = state["clone"], state["logs"], venv_python(state["venv"])
    log = lambda name: os.path.join(logs, name)  # noqa: E731
    guard_dir, net_log = os.path.join(state["work"], "guard"), os.path.join(state["work"], "outside_attempts.log")
    os.makedirs(guard_dir, exist_ok=True)
    with open(os.path.join(guard_dir, "sitecustomize.py"), "w", encoding="utf-8") as handle:
        handle.write(GUARD)
    env = dict(os.environ, PYTHONPATH=guard_dir, W9_NET_LOG=net_log, PYTHONDONTWRITEBYTECODE="1",
               PYTHONIOENCODING="utf-8")
    for name in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "all_proxy"):
        env.pop(name, None)

    # the network
    reachable = outside_reachable()
    if state["mode"] == "netns":
        table.add("network off (unshare -n)", FAILED if reachable else OK,
                  "an outside address answers" if reachable else "an outside connection fails, loopback works")
    else:
        table.add("network off", OK if not reachable else NOT_HERE,
                  "no outside address answers (Wi-Fi off)" if not reachable else
                  "no unshare -n here and the network is on: the guard rows below are the proof")
    probe = "import socket; socket.socket().connect(%r)" % (OUTSIDE_TEST_ADDRESS,)
    run([python, "-c", probe], env=env, log=log("04_guard_selftest.log"), timeout=30)
    caught = os.path.isfile(net_log) and "connect 192.0.2.1:9" in open(net_log, encoding="utf-8").read()
    table.add("guard self-test: an outside connect is refused and written down", OK if caught else FAILED)
    if os.path.isfile(net_log):
        os.remove(net_log)
    save()

    # without data
    code, text = run([python, "-m", "pipeline.run"], cwd=clone, env=env, log=log("05_run_no_data.log"))
    plain = code == 3 and "no folder" in text and not os.path.exists(os.path.join(clone, "out"))
    table.add("without data: python -m pipeline.run says what is missing", OK if plain else FAILED,
              "exit code %d%s" % (code, ", names the missing data folder, writes nothing" if plain else ""))
    screen = Screen(python, clone, env, log("06_screen_no_data.log"))
    try:
        up = screen.wait()
        status, _kind, body = fetch(screen.base + "/api/findings") if up else (0, "", b"")
        try:
            answer = json.loads(body.decode("utf-8")) if status == 200 else {}
        except ValueError:
            answer = {}
        sample = up and answer.get("mode") == "sample" and bool(answer.get("findings"))
        table.add("without data: the screen opens on its sample data", OK if sample else FAILED,
                  "page 200, mode sample (yellow line \"Beispieldaten\")" if sample else "page or /api/findings not as expected")
    finally:
        screen.stop()
    start = time.time()
    code, text = run([python, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=clone, env=env,
                     log=log("07_tests_no_data.log"))
    counts, line = test_counts(text)
    green = code == 0 and counts.get("passed", 0) > 0 and not counts.get("failed") and not counts.get("error")
    table.add("without data: python -m pytest -q", OK if green else FAILED,
              "%d passed, %d skipped, 0 failed, %.0f s" % (counts.get("passed", 0), counts.get("skipped", 0),
                                                         time.time() - start) if green else line)
    save()

    # with data
    data, target = state["data"], os.path.join(clone, "data")
    have_data = os.path.isdir(data) and bool(os.listdir(data))
    if have_data:
        linked = False
        if not state["copy_data"] and os.name != "nt":
            try:
                os.symlink(data, target, target_is_directory=True)
                linked = True
            except OSError:
                pass
        if not linked:
            shutil.copytree(data, target)
        table.add("data/ %s" % ("linked" if linked else "copied"), OK, "%d files" % len(os.listdir(target)))
    else:
        table.add("data/ linked", FAILED, "no organizer data in %s (name it with --data)" % data)
    if have_data:
        with_data(state, table, python, clone, env, log)
    save()

    # outside addresses in the files of the screen and in the exported HTML
    found, searched = [], 0
    places = [os.path.join(clone, "web", "static")]
    export = os.path.join(clone, "out", PROJECT, "export")
    places += [os.path.join(export, name) for name in (sorted(os.listdir(export)) if os.path.isdir(export) else [])
               if name.lower().endswith((".html", ".htm"))]
    served = os.path.join(state["work"], "Risikobericht_from_the_screen.html")
    places += [served] if os.path.isfile(served) else []
    for place in places:
        files = [os.path.join(place, name) for name in sorted(os.listdir(place))] if os.path.isdir(place) else [place]
        for path in files:
            searched += 1
            with open(path, encoding="utf-8", errors="replace") as handle:
                for number, text_line in enumerate(handle, 1):
                    for match in OUTSIDE.findall(text_line):
                        found.append("%s:%d %s" % (os.path.basename(path), number, match[:60]))
    html_count = searched - len(os.listdir(places[0]))
    table.add("no outside address (http://, https://, //host) in web/static and the exported HTML",
              OK if not found and (html_count or not have_data) else FAILED,
              "%d files searched (%d exported HTML), 0 found" % (searched, html_count) if not found
              else "; ".join(found[:5]))
    attempts = open(net_log, encoding="utf-8").read().splitlines() if os.path.isfile(net_log) else []
    table.add("no Python process of the offline part tried an outside address (guard)", OK if not attempts else FAILED,
              "0 attempts written down" if not attempts else "%d attempts, first: %s" % (len(attempts), attempts[0]))
    save(finished=True)
    return 0


def with_data(state, table, python, clone, env, log):
    start = time.time()
    code, text = run([python, "-m", "pipeline.run"], cwd=clone, env=env, log=log("08_run.log"))
    step_lines = [line for line in text.splitlines() if re.match(r"^ *\d+/\d+  ", line)]
    for line in step_lines:
        print("        " + line)
    all_ok = code == 0 and step_lines and all(re.search(r"  ok +\d", line) for line in step_lines)
    ran = table.add("python -m pipeline.run", OK if all_ok else FAILED,
                    "exit code %d, %d steps ok, %.0f s" % (code, len(step_lines), time.time() - start) if all_ok
                    else "exit code %d: %s" % (code, last_line("\n".join(l for l in text.splitlines() if "FAILED" in l or "skipped:" in l) or text)))
    folders = [os.path.join(clone, "out"), os.path.join(clone, "cache")]
    first = hashes(*folders)
    code, text = run([python, "-m", "pipeline.run"], cwd=clone, env=env, log=log("09_run_again.log"))
    second = hashes(*folders)
    same = ran and code == 0 and first == second and bool(first)
    table.add("second run: every output file byte-equal", OK if same else FAILED,
              "%d files in out/ and cache/" % len(first) if same else
              "%d files differ or are new" % len([n for n in set(first) | set(second) if first.get(n) != second.get(n)]))

    start = time.time()
    code, text = run([python, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=clone, env=env, log=log("10_tests.log"))
    counts, line = test_counts(text)
    green = code == 0 and counts.get("passed", 0) > 0 and not counts.get("failed") and not counts.get("error")
    table.add("with data: python -m pytest -q", OK if green else FAILED,
              "%d passed, %d skipped, 0 failed, %.0f s" % (counts.get("passed", 0), counts.get("skipped", 0),
                                                         time.time() - start) if green else line)

    screen = Screen(python, clone, env, log("11_screen.log"), ["--project", PROJECT])
    try:
        up = screen.wait()
        status, _kind, page = fetch(screen.base + "/") if up else (0, "", b"")
        page_text = page.decode("utf-8", "replace")
        linked = sorted(set(re.findall(r"(?:src|href)=\"(/[^\"#?]+)", page_text)))
        broken = [path for path in linked if fetch(screen.base + path)[0] != 200]
        fine = up and status == 200 and linked and not broken
        table.add("the screen on a free port: page and its static files", OK if fine else FAILED,
                  "port %d, page 200, %s 200" % (screen.port, ", ".join(linked)) if fine
                  else "page %d, not served: %s" % (status, ", ".join(broken) or "-"))
        status, _kind, body = fetch(screen.base + "/api/findings") if up else (0, "", b"")
        try:
            answer = json.loads(body.decode("utf-8")) if status == 200 else {}
        except ValueError:
            answer = {}
        findings = answer.get("findings") or []
        real = answer.get("mode") == "real" and answer.get("project") == PROJECT and bool(findings) \
            and answer.get("contract_errors") == 0
        standing = len([f for f in findings if (f.get("skeptic") or {}).get("status") == "survived"])
        table.add("/api/findings", OK if real else FAILED,
                  "project %s, %d findings, %d left standing by the counter-check" % (PROJECT, len(findings), standing)
                  if real else "status %d, mode %s" % (status, answer.get("mode")))
        image_note, image_ok = "no finding to ask for", False
        if findings:
            status, kind, body = fetch(screen.base + "/api/page-image/%s/0" % findings[0]["id"])
            image_ok = status == 200 and kind.startswith("image/png") and body[:8] == b"\x89PNG\r\n\x1a\n"
            image_note = "finding %s, source 1: PNG, %d kB" % (findings[0]["id"], len(body) // 1024) if image_ok else \
                "status %d: %s" % (status, last_line(body.decode("utf-8", "replace")))
        table.add("one page image (\"Quelle zeigen\")", OK if image_ok else FAILED, image_note)
        status, _kind, body = fetch(screen.base + "/api/export/risikobericht?format=html&project=%s" % PROJECT)
        if status == 200:
            with open(os.path.join(state["work"], "Risikobericht_from_the_screen.html"), "wb") as handle:
                handle.write(body)
    finally:
        screen.stop()

    code, text = run([python, "-m", "web.export", "--project", PROJECT], cwd=clone, env=env, log=log("12_export.log"))
    export = os.path.join(clone, "out", PROJECT, "export")
    written = sorted(os.listdir(export)) if os.path.isdir(export) else []
    table.add("python -m web.export --project %s" % PROJECT, OK if code == 0 and written else FAILED,
              "%d files: %s" % (len(written), ", ".join(written)) if code == 0 and written
              else "exit code %d: %s" % (code, last_line(text)))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("branch", nargs="?", default=None, help="branch or commit of this checkout (default: HEAD)")
    parser.add_argument("--data", default=None, help="folder with the organizer files (default: data/ of this checkout)")
    parser.add_argument("--python", default=sys.executable, help="the Python that makes the virtual environment")
    parser.add_argument("--copy-data", action="store_true", help="copy data/ into the clone instead of linking it")
    parser.add_argument("--keep", action="store_true", help="keep the temporary folder")
    parser.add_argument("--inner", default=None, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.inner:
        return inner(args.inner)
    if not shutil.which("git"):
        print("git is not on PATH.", file=sys.stderr)
        return 2
    return outer(args)


if __name__ == "__main__":
    sys.exit(main())
