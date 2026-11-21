"""Stable finding ids (MASTER_PLAN §8).

id = check + "-" + first 6 hex digits of
     sha1(check | sorted "doc:item_no" pairs | normalized first quote)

The three parts are joined with "|", the sorted pairs with ",", and the text is
hashed as UTF-8. "First quote" is the quote of sources[0] as the finding lists
them. The same finding gets the same id in every run.
"""
import hashlib

from pipeline.common.quotes import normalize

ID_HEX_DIGITS = 6


def finding_id(check, sources):
    """Return the stable id for a finding of the given check and sources."""
    if not check:
        raise ValueError("check is empty")
    if not sources:
        raise ValueError("a finding needs at least one source for its id")
    pairs = sorted("%s:%s" % (s["doc"], s["item_no"]) for s in sources)
    raw = "|".join([check, ",".join(pairs), normalize(sources[0]["quote"])])
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()
    return "%s-%s" % (check, digest[:ID_HEX_DIGITS])


def has_stable_id(finding):
    """True when the finding's id equals the id computed from its content."""
    return finding.get("id") == finding_id(finding["check"], finding["sources"])
