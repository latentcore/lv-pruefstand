"""Independent refute pass that fills the skeptic field of each finding (W5b, MASTER_PLAN §8 and K3).

evidence.py  gathers, for one finding, every item and preliminary note of all lists that matches its terms
rules.py     rule checks by code; they can lower a verdict, never raise it
merge.py     writes the findings with the skeptic field replaced by the verdict
"""

STATUSES = ("survived", "weakened", "refuted")
AGENT_ORIGIN = "agent session, independent context"
