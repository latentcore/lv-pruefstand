"""Check data against the contract v1 schemas in contract/ (MASTER_PLAN §8).

The schema files are plain JSON Schema. This module checks the keywords those
files use, with the standard library only, so the check also runs offline on a
machine without the jsonschema package. A schema keyword it does not know is an
error, never silently skipped.
"""
import json
import os
import re

CONTRACT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "contract",
)
NAMES = ("items", "findings", "reviews", "manifest")

_ANNOTATIONS = frozenset(["$schema", "$id", "$comment", "title", "description"])
_CHECKED = frozenset([
    "type", "enum", "pattern", "minLength", "minimum", "items", "minItems",
    "properties", "required", "additionalProperties",
])


class ContractError(ValueError):
    """Data does not follow its contract schema."""


def schema_path(name):
    if name not in NAMES:
        raise KeyError("unknown contract name %r; known: %s" % (name, ", ".join(NAMES)))
    return os.path.join(CONTRACT_DIR, "%s.schema.json" % name)


def sample_path(name):
    if name not in NAMES:
        raise KeyError("unknown contract name %r; known: %s" % (name, ", ".join(NAMES)))
    return os.path.join(CONTRACT_DIR, "samples", "%s.json" % name)


def _load(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def load_schema(name):
    return _load(schema_path(name))


def load_sample(name):
    return _load(sample_path(name))


def _is_type(value, name):
    if name == "null":
        return value is None
    if name == "boolean":
        return isinstance(value, bool)
    if name == "string":
        return isinstance(value, str)
    if name == "array":
        return isinstance(value, list)
    if name == "object":
        return isinstance(value, dict)
    if isinstance(value, bool):
        return False
    if name == "number":
        return isinstance(value, (int, float))
    if name == "integer":
        return isinstance(value, int) or (isinstance(value, float) and value.is_integer())
    raise ValueError("schema uses unknown type %r" % name)


def schema_errors(data, schema, path="$"):
    """Return a list of messages, one per place where data breaks the schema."""
    unknown = set(schema) - _ANNOTATIONS - _CHECKED
    if unknown:
        raise ValueError("schema keyword not supported at %s: %s" % (path, ", ".join(sorted(unknown))))
    errors = []
    if "type" in schema:
        types = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_is_type(data, t) for t in types):
            return ["%s: expected %s, got %s" % (path, " or ".join(types), type(data).__name__)]
    if "enum" in schema and data not in schema["enum"]:
        errors.append("%s: %r is not one of %s" % (path, data, ", ".join(map(repr, schema["enum"]))))
    if isinstance(data, str):
        if "pattern" in schema and not re.search(schema["pattern"], data):
            errors.append("%s: %r does not match %s" % (path, data, schema["pattern"]))
        if "minLength" in schema and len(data) < schema["minLength"]:
            errors.append("%s: shorter than %d characters" % (path, schema["minLength"]))
    if isinstance(data, (int, float)) and not isinstance(data, bool):
        if "minimum" in schema and data < schema["minimum"]:
            errors.append("%s: %r is below %r" % (path, data, schema["minimum"]))
    if isinstance(data, list):
        if "minItems" in schema and len(data) < schema["minItems"]:
            errors.append("%s: fewer than %d entries" % (path, schema["minItems"]))
        if "items" in schema:
            for index, entry in enumerate(data):
                errors.extend(schema_errors(entry, schema["items"], "%s[%d]" % (path, index)))
    if isinstance(data, dict):
        for key in schema.get("required", []):
            if key not in data:
                errors.append("%s: key %r is missing" % (path, key))
        properties = schema.get("properties", {})
        extra = schema.get("additionalProperties", True)
        for key, value in data.items():
            child = "%s.%s" % (path, key)
            if key in properties:
                errors.extend(schema_errors(value, properties[key], child))
            elif extra is False:
                errors.append("%s: key not allowed" % child)
            elif isinstance(extra, dict):
                errors.extend(schema_errors(value, extra, child))
    return errors


def errors(name, data):
    """Messages for every place where data breaks the contract file `name`."""
    return schema_errors(data, load_schema(name))


def check(name, data):
    """Raise ContractError when data breaks the contract file `name`."""
    found = errors(name, data)
    if found:
        shown = "; ".join(found[:5])
        more = "" if len(found) <= 5 else " (and %d more)" % (len(found) - 5)
        raise ContractError("%s.json breaks contract v1: %s%s" % (name, shown, more))
    return data
