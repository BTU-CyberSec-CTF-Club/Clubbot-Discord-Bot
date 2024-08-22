import builtins
import sys
import datetime
import traceback


def print(*args, **kwargs):
    """
    Overloading the print function for convenience. This print function will by default
    also print a timestamp to the line

    Args:
        Same args as print. With some additional kwargs:
            mode: [normal, exception] - What mode to print in
            ts: [true, false] - Whether to prefix a timestamp
    """
    mode = kwargs.get("mode")
    if mode is not None:
        del kwargs["mode"]
    else:
        mode = "normal"

    ts = kwargs.get("ts")
    if ts is not None:
        del kwargs["ts"]
    else:
        ts = True

    if not kwargs.get("file"):
        if mode == "normal":
            kwargs["file"] = sys.stdout
        else:
            kwargs["file"] = sys.stderr

    if ts:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        builtins.print(timestamp, end=" ", file=kwargs["file"])

    builtins.print(*args, **kwargs)


def print_exception(custom_message, e):
    print("## ", custom_message.upper(), " ##", mode="exception")

    print("MESSAGE:", e, mode="exception")
    print(
        2 * "-",
        " TRACEBACK ",
        (40 - 2 - len(" TRACEBACK ")) * "-",
        sep="",
        mode="exception",
    )
    traceback.print_exc()
    print(40 * "-", mode="exception")


def fancy_format_datetime(datetime_obj):
    # Based on https://stackoverflow.com/a/16671271
    # TODO: Need to check timezone info
    ordinal = lambda n: str(n) + (
        "th" if 4 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    )
    f = "%a, {th} %B %Y %H:%M"
    return datetime_obj.strftime(f).replace("{th}", ordinal(datetime_obj.day))


def fancy_format_duration(days, hours):
    days = int(days)
    hours = int(hours)
    plural_h = hours > 1
    plural_d = days > 1

    if days:
        if hours:
            return f"{days} day{'s' if plural_d else ''}, {hours} hour{'s' if plural_h else ''}"
        else:
            return f"{days} day{'s' if plural_d else ''}"
    else:
        return f"{hours} hour{'s' if plural_h else ''}"
