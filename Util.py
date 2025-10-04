import re
import builtins
import io
import sys
import datetime
import traceback
import requests
import time
import pytz
from PIL import Image, UnidentifiedImageError
from Common import REQUESTS_HEADERS

UTC_TZ = pytz.timezone("Etc/UTC")
BERLIN_TZ = pytz.timezone("Europe/Berlin")

HTML_TAG_REGEX = re.compile("<.*?>")


def strip_html_tags(string):
    """
    Removes all html tags from the given string.
    """
    return HTML_TAG_REGEX.sub("", string)


def published_or_updated_datetime(entry):
    """
    Most RSS feed entries have a "published" keyword, showing what date they were
    published at. But sometimes, they do not have it, and instead have an "updated"
    keyword. This function chooses updated as a fallback.

    Raises: RuntimeError if neither keyword is available
    """
    for key in ["published_parsed", "updated_parsed"]:
        val = entry.get(key, None)
        if val is not None:
            return datetime.datetime.fromtimestamp(time.mktime(val), tz=UTC_TZ)

    raise RuntimeError(
        f"Could neither find a 'published' nor an 'updated' keyword in the feedentry: {entry}"
    )


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
    MAX_BANNER_IMG_WIDTH = 1500

    r = requests.get(logo_link, headers=REQUESTS_HEADERS)
    r.raise_for_status()
    try:
        logo_img = Image.open(io.BytesIO(r.content))
    except UnidentifiedImageError:
        print(f"Failed to load logo image from {logo_link}", mode="exception")
        raise

    img_width, img_height = logo_img.size
    banner_width = int(img_height / 2 * 5)  # Discord recommends a banner in 5:2 format

    if banner_width > img_width:
        logo_img.convert("RGBA")
        banner_img = Image.new(
            mode="RGBA", size=(banner_width, img_height), color="#ffffff00"
        )

        paste_x = int(banner_width / 2 - img_width / 2)
        banner_img.paste(logo_img, (paste_x, 0))
    else:
        banner_img = logo_img

    if banner_img.width > MAX_BANNER_IMG_WIDTH:
        new_width = MAX_BANNER_IMG_WIDTH
        new_height = int(banner_img.height * new_width / banner_img.width)
        banner_img = banner_img.resize((new_width, new_height))

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
