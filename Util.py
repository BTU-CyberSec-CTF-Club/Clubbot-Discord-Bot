import builtins
import io
import sys
import datetime
import traceback
import requests
import random
from PIL import Image


def pretty_print_feeditem(entry):
    """
    This is used purely for debugging

    Works both on feeditems (SimpleNamespace) and rss entries dicts
    """
    try:
        entry = entry.entry_obj
    except (KeyError, ValueError):
        pass

    for i, v in entry.items():
        print(i, "---", v)
    print(80 * "=")
    print()


def bannerize_logo(logo_link):
    """
    Load the image at the given URL and turn it into a 5:2 banner (if the image isn't
    already wider than this, in which case it is returned taken as is)

    Returns:
        Byte-Array of the resulting image
    """
    _, ending = logo_link.rsplit(".", maxsplit=1)

    distinguisher = random.randint(0, 2**16)

    r = requests.get(logo_link)
    logo_img = Image.open(io.BytesIO(r.content))

    img_width, img_height = logo_img.size
    banner_width = int(img_height / 2 * 5)  # Discord recommends a banner in 5:2 format

    if banner_width > img_width:
        logo_img.convert("RGBA")
        banner_img = Image.new(
            mode="RGBA", size=(banner_width, img_height), color="#ffffff00"
        )

        paste_x = int(banner_width / 2 - img_width / 2)
        banner_img.paste(logo_img, (paste_x, 0), logo_img)
    else:
        banner_img = logo_img

    banner_byte_arr = io.BytesIO()
    banner_img.save(banner_byte_arr, format="PNG")
    banner_byte_arr = banner_byte_arr.getvalue()

    return banner_byte_arr


def as_kebab_case(string):
    return string.lower().replace(" ", "-")


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
