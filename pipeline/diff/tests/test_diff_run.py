import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from diff_items import item, order, tender  # noqa: E402
from pipeline.common import contract  # noqa: E402
from pipeline.diff import run  # noqa: E402


def write(path, items):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(items, handle)
    return str(path)


def read(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def test_synthetic_items_follow_the_contract():
    assert contract.errors("items", tender() + order()) == []


def test_twin_is_the_default_mode(tmp_path, capsys):
    a, b, out = write(tmp_path / "a.json", tender()), write(tmp_path / "b.json", order()), tmp_path / "o" / "d.json"
    assert run.main([a, b, str(out)]) == 0
    result = read(out)
    assert result["mode"] == "twin" and result["matching"]["both"] == 3 and "stage" not in result
    printed = capsys.readouterr().out
    assert printed.startswith("twin: A 3 items, B 3 items; in both 3, only A 0, only B 0")


def test_stage_mode_lists_added_and_changed(tmp_path, capsys):
    new = item("1.40", "Hydrant DN 80", "Hydrant setzen.", 0.0, None, doc="B.D86",
               unit_price=4321.99, total=0.0)
    a = write(tmp_path / "a.json", tender())
    b = write(tmp_path / "b.json", order({"01.0010": {"quantity": 11.0}}, extra=[new]))
    out = tmp_path / "d.json"
    assert run.main([a, b, str(out), "--mode", "stage"]) == 0
    result = read(out)
    assert result["stage"]["added"] == ["1.40"]
    assert [entry["item_no"] for entry in result["stage"]["changed"]["quantity"]] == ["01.0010"]
    with open(out, encoding="utf-8") as handle:
        assert "4321.99" not in handle.read()
    assert "4321.99" not in capsys.readouterr().out


def test_one_file_with_two_documents(tmp_path, capsys):
    both = write(tmp_path / "items.json", tender() + order())
    out = tmp_path / "d.json"
    assert run.main([both, both, str(out), "--doc-a", "A.X83", "--doc-b", "B.D86"]) == 0
    assert read(out)["matching"]["both"] == 3
    assert run.main([both, both, str(out)]) == 2
    assert "--doc-a" in capsys.readouterr().err
    assert run.main([both, both, str(out), "--doc-a", "A.X83", "--doc-b", "none"]) == 2


def test_text_map_option(tmp_path):
    a = write(tmp_path / "a.json", [item("1.1", "Rohr DN 100", "liefern.")])
    b = write(tmp_path / "b.json", [item("1.1", "Rohr", "Rohr DN 100\nliefern.", doc="B")])
    out = tmp_path / "d.json"
    assert run.main([a, b, str(out), "--text-map", "a_all_to_b_long"]) == 0
    assert read(out)["fields"]["text"]["equal"] == 1


def test_unreadable_input_is_an_error_not_a_trace(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")
    good = write(tmp_path / "a.json", tender())
    assert run.main([str(bad), good, str(tmp_path / "d.json")]) == 2
    assert run.main([str(tmp_path / "missing.json"), good, str(tmp_path / "d.json")]) == 2
    assert run.main([write(tmp_path / "c.json", {"a": 1}), good, str(tmp_path / "d.json")]) == 2
    assert capsys.readouterr().err.count("error:") == 3
    assert not (tmp_path / "d.json").exists()
