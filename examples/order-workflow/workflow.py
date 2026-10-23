"""Order transitions are an explicit finite model."""

TRANSITIONS = {
    ("pending", "pay"): "paid",
    ("pending", "cancel"): "cancelled",
    ("paid", "ship"): "shipped",
    ("paid", "cancel"): "cancelled",
    ("cancelled", "reopen"): "pending",
}
TERMINAL_STATES = {"shipped", "cancelled"}


def transition(state, event):
    """Apply a known transition; reject unsupported events."""
    if (state, event) not in TRANSITIONS:
        raise ValueError(f"Unsupported transition: {state}, {event}")
    return TRANSITIONS[(state, event)]


def is_terminal(state):
    return state in TERMINAL_STATES
