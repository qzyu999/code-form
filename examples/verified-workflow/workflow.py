TRANSITIONS = {
    ("pending", "pay"): "paid",
    ("pending", "cancel"): "cancelled",
    ("paid", "ship"): "shipped",
    ("paid", "cancel"): "cancelled",
}
TERMINAL_STATES = {"shipped", "cancelled"}


def transition(state, event):
    if (state, event) not in TRANSITIONS:
        raise ValueError("Unsupported transition")
    return TRANSITIONS[(state, event)]
