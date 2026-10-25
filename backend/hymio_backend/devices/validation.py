FIELDS = {
    "bash": {"command", "cwd"},
    "browser": {"action", "url", "selector", "text", "key", "page_id"},
    "computer": {"action", "x", "y", "x2", "y2", "duration_ms", "text", "key", "amount"},
}
REQUIRED = {
    "browser": {
        "snapshot": (),
        "screenshot": ("page_id",),
        "navigate": ("url",),
        "click": ("selector",),
        "fill": ("selector", "text"),
        "key": ("key",),
        "tabs": (),
        "new_tab": (),
        "switch_tab": ("page_id",),
        "close_tab": ("page_id",),
        "back": (),
        "forward": (),
        "reload": (),
    },
    "computer": {
        "screenshot": (),
        "click": ("x", "y"),
        "type": ("text",),
        "key": ("key",),
        "scroll": (),
        "swipe": ("x", "y", "x2", "y2"),
    },
}


def validate(capability, args):
    if capability not in FIELDS or not isinstance(args, dict) or set(args) - FIELDS[capability]:
        raise ValueError("invalid_operation")
    if capability == "bash":
        required = ("command",)
    else:
        action = args.get("action")
        if action not in REQUIRED[capability]:
            raise ValueError("invalid_action")
        required = REQUIRED[capability][action]
    if any(field not in args for field in required):
        raise ValueError("missing_argument")
    for field, value in args.items():
        if field in ("x", "y", "x2", "y2", "duration_ms", "amount"):
            upper = {"x": 1279, "y": 799, "x2": 1279, "y2": 799, "duration_ms": 2000, "amount": 20}[
                field
            ]
            lower = -20 if field == "amount" else 100 if field == "duration_ms" else 0
            if (
                type(value) is not int
                or not lower <= value <= upper
                or field == "amount"
                and value == 0
            ):
                raise ValueError("invalid_coordinate")
        elif not isinstance(value, str) or len(value) > 8192:
            raise ValueError("invalid_text")
    if capability == "bash" and not args["command"].strip():
        raise ValueError("empty_command")
    if (
        capability == "browser"
        and "url" in args
        and not args["url"].startswith(("http://", "https://"))
    ):
        raise ValueError("invalid_url")
