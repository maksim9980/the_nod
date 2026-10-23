"""Canonical vocabulary of the state files.

The values the core and the pane compare or store are English identifiers under any
interface language. The pane and the texts show them by a caption of the chosen language.
Commit subjects (`state: ...`) and JSON keys are English as well.
"""

# Answers to `owner-action` decisions.
DONE = "done"
POSTPONE = "postpone"

# Answers to `next-batch` decisions and the proposed answer to `pain`.
YES = "yes"
NO = "no"
WAIT = "wait"

# Answers to `verdict` decisions.
ACCEPT = "accept"
RETURN = "return"

# Answers to `return` and `run-stuck` decisions.
RERUN = "rerun"
BACKLOG = "backlog"
RESTART = "restart"

# Result of an acceptance.
SOLVED = "solved"
UNSOLVED = "unsolved"
UNVERIFIED = "unverified"

# Status of a review suggestion.
PROPOSED = "proposed"
APPLIED = "applied"

# Marker lines in the body of a decision: the driver applied the answer / made the card of a `pain`.
CONSUMED_MARK = "Consumed:"
CARD_MARK = "Card:"
