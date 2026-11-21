"""W10: screenshots of the real review screen, 1920 x 1080 px, into out/pitch/shots/."""
import json
import os
import shutil
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from pitch import chrome, numbers, shots  # noqa: E402

BROWSER = chrome.browser()
try:
    PROJECT = numbers.load()["project"]
except OSError:  # the public copy leaves pitch/numbers.json out; its tests that need no data still run
    PROJECT = "79-222"
SAMPLES = os.path.join(ROOT, "contract", "samples")
OUT_FINDINGS = numbers.path(numbers.files(PROJECT)["out_findings"])
needs_chrome = pytest.mark.skipif(not BROWSER, reason="no Chrome or Chromium on this machine")
needs_dom = pytest.mark.skipif(not chrome._browser.writes_dom(BROWSER),
                               reason="no browser here prints a page back (Microsoft Edge on Windows does not)")


@pytest.fixture()
def sample_out(tmp_path):
    """A pipeline output folder with the synthetic contract samples as project P1."""
    folder = tmp_path / "out" / "P1"
    folder.mkdir(parents=True)
    for name in ("findings.json", "items.json"):
        shutil.copy(os.path.join(SAMPLES, name), str(folder / name))
    with open(os.path.join(SAMPLES, "findings.json"), encoding="utf-8") as handle:
        finding_id = json.load(handle)[0]["id"]
    return str(tmp_path / "out"), str(tmp_path / "reviews"), finding_id


def test_driven_page_is_the_apps_page_plus_one_script():
    page = "<html><body><main></main><script src=\"/static/app.js\"></script>\n</body>\n</html>"
    driven = shots.driven_page(page, 'X2-"a')
    assert driven.count("<script>") == 1 and driven.index("<script>") > driven.index("app.js")
    assert 'var id = "X2-\\"a"' in driven
    assert driven.replace(shots.DRIVER % json.dumps('X2-"a'), "") == page
    with pytest.raises(ValueError):
        shots.driven_page("<html></html>", "X2-a")


def test_shot_page_is_served_by_the_real_app(sample_out):
    out_dir, reviews_dir, finding_id = sample_out
    client = TestClient(shots.make_app(out_dir, reviews_dir, "P1", finding_id))
    page = client.get("/shot")
    assert page.status_code == 200
    with open(os.path.join(ROOT, "web", "static", "index.html"), encoding="utf-8") as handle:
        assert page.text == shots.driven_page(handle.read(), finding_id)
    answer = client.get("/api/findings").json()
    assert answer["project"] == "P1" and finding_id in [finding["id"] for finding in answer["findings"]]
    assert client.get("/static/app.js").status_code == 200
    assert not os.path.exists(reviews_dir), "taking a picture writes no review"


def test_no_picture_of_the_synthetic_samples(tmp_path):
    code, lines = shots.take("79-222", str(tmp_path / "shots"), data_dir=str(tmp_path / "out"), browser="/bin/true")
    assert code == 2 and "No picture of the synthetic samples is taken" in lines[0]
    assert not os.path.exists(str(tmp_path / "shots"))


def test_without_chrome_nothing_is_written_and_the_exit_code_is_0(sample_out, tmp_path):
    out_dir, reviews_dir, finding_id = sample_out
    code, lines = shots.take("P1", str(tmp_path / "shots"), out_dir, reviews_dir, browser=None, finding_id=finding_id)
    assert code == 0 and lines == ["no Chrome or Chromium on this machine: no screenshots. The deck shows grey boxes."]
    assert not os.path.exists(str(tmp_path / "shots"))
    assert shots.main(["--project", "P1", "--data", out_dir, "--reviews", reviews_dir, "--out", str(tmp_path / "shots"),
                       "--chrome", "none"]) == 0


def test_command_exits_2_without_the_findings_file(tmp_path, capsys):
    assert shots.main(["--project", "79-222", "--data", str(tmp_path), "--out", str(tmp_path / "shots"), "--chrome", "none"]) == 2
    assert "is missing" in capsys.readouterr().err


def test_png_size(tmp_path):
    (tmp_path / "a.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x07\x80\x00\x00\x048")
    assert shots.png_size(str(tmp_path / "a.png")) == (1920, 1080)
    (tmp_path / "b.png").write_bytes(b"not a picture")
    with pytest.raises(ValueError):
        shots.png_size(str(tmp_path / "b.png"))


@needs_chrome
def test_pictures_of_both_views_are_1920_by_1080(sample_out, tmp_path):
    out_dir, reviews_dir, finding_id = sample_out
    target = tmp_path / "shots"
    code, lines = shots.take("P1", str(target), out_dir, reviews_dir, BROWSER, finding_id)
    assert code == 0, lines
    assert sorted(os.listdir(str(target))) == ["bauwerk.png", "fund.png"]
    for name in ("bauwerk.png", "fund.png"):
        assert shots.png_size(str(target / name)) == (shots.WIDTH, shots.HEIGHT) == (1920, 1080)
        assert os.path.getsize(str(target / name)) > 20000, "%s looks like an empty page" % name
    assert (target / "fund.png").read_bytes() != (target / "bauwerk.png").read_bytes()
    assert not os.path.exists(reviews_dir)


@needs_chrome
@needs_dom
def test_the_script_picks_the_named_finding_in_both_views(sample_out):
    out_dir, reviews_dir, _ = sample_out
    with open(os.path.join(SAMPLES, "findings.json"), encoding="utf-8") as handle:
        survived = [finding["id"] for finding in json.load(handle) if finding["skeptic"]["status"] == "survived"]
    wanted = survived[-1]
    assert wanted != survived[0]
    with shots.Server(shots.make_app(out_dir, reviews_dir, "P1", wanted)) as base:
        for anchor, box in (("", "fund-detail"), ("#pruefen", "pruefen-detail")):
            dom, why = chrome.dump_dom(BROWSER, base + "/shot" + anchor)
            assert why is None, why
            assert 'data-shot-ready="%s"' % wanted in dom
            detail = dom.split('id="%s"' % box, 1)[1].split("</h2>", 1)[0]
            assert wanted in detail, "the view %s does not show %s" % (box, wanted)


@needs_chrome
@pytest.mark.skipif(not os.path.isfile(OUT_FINDINGS), reason="out/%s/findings.json is not built" % PROJECT)
def test_realdata_command_takes_both_pictures(tmp_path):
    assert shots.main(["--project", PROJECT, "--out", str(tmp_path)]) == 0
    for name in ("bauwerk.png", "fund.png"):
        assert shots.png_size(str(tmp_path / name)) == (1920, 1080)
