import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

import pytest  # noqa: E402

from pipeline.common import contract  # noqa: E402

SCHEMA = {
    "type": "array",
    "minItems": 1,
    "items": {
        "type": "object",
        "required": ["name", "count"],
        "properties": {
            "name": {"type": "string", "minLength": 1, "pattern": "^[a-z]+$"},
            "count": {"type": ["integer", "null"], "minimum": 0},
            "kind": {"type": "string", "enum": ["a", "b"]},
            "flag": {"type": "boolean"},
            "size": {"type": "number"},
        },
        "additionalProperties": True,
    },
}


def errs(data, schema=SCHEMA):
    return contract.schema_errors(data, schema)


def test_valid_data_gives_no_errors():
    assert errs([{"name": "abc", "count": 3, "kind": "a", "flag": True, "size": 1.5, "unknown": [1]}]) == []
    assert errs([{"name": "abc", "count": None}]) == []


def test_missing_key_is_reported_with_its_path():
    assert errs([{"name": "abc"}]) == ["$[0]: key 'count' is missing"]


def test_wrong_types_are_reported():
    assert len(errs({"name": "abc"})) == 1
    assert len(errs([{"name": 5, "count": 1}])) == 1
    assert len(errs([{"name": "abc", "count": "1"}])) == 1
    assert len(errs([{"name": "abc", "count": 1.5}])) == 1
    assert len(errs([{"name": "abc", "count": 1, "size": "big"}])) == 1


def test_bool_is_not_a_number_and_a_number_is_not_a_bool():
    assert len(errs([{"name": "abc", "count": True}])) == 1
    assert len(errs([{"name": "abc", "count": 1, "size": False}])) == 1
    assert len(errs([{"name": "abc", "count": 1, "flag": 1}])) == 1


def test_whole_float_counts_as_integer():
    assert errs([{"name": "abc", "count": 2.0}]) == []


def test_enum_pattern_length_minimum_and_min_items():
    assert len(errs([{"name": "abc", "count": 1, "kind": "c"}])) == 1
    assert len(errs([{"name": "ABC", "count": 1}])) == 1
    assert len(errs([{"name": "", "count": 1}])) == 2
    assert len(errs([{"name": "abc", "count": -1}])) == 1
    assert len(errs([])) == 1


def test_every_error_is_collected():
    assert len(errs([{"name": "abc"}, {"count": 1}, {"name": 1, "count": "x"}])) == 4


def test_additional_properties_false_and_schema():
    closed = {"type": "object", "properties": {"a": {"type": "string"}}, "additionalProperties": False}
    assert errs({"a": "x"}, closed) == []
    assert errs({"a": "x", "b": 1}, closed) == ["$.b: key not allowed"]
    mapped = {"type": "object", "additionalProperties": {"type": "integer"}}
    assert errs({"x": 1, "y": 2}, mapped) == []
    assert len(errs({"x": 1, "y": "2"}, mapped)) == 1


def test_unknown_schema_keyword_is_an_error_not_skipped():
    with pytest.raises(ValueError):
        errs("x", {"type": "string", "maxLength": 3})


def test_contract_files_use_only_supported_keywords():
    for name in contract.NAMES:
        contract.schema_errors(contract.load_sample(name), contract.load_schema(name))


def test_check_raises_with_the_file_name_and_returns_good_data():
    with pytest.raises(contract.ContractError) as info:
        contract.check("items", [{"doc": "LV_91"}])
    assert "items.json" in str(info.value)
    good = contract.load_sample("items")
    assert contract.check("items", good) is good


def test_unknown_contract_name_is_an_error():
    with pytest.raises(KeyError):
        contract.load_schema("offers")
