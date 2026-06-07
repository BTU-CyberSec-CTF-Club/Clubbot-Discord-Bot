"""
General utility functions
"""

import datetime
import io
import logging
import re
import time

import pytz
import requests
from PIL import Image, UnidentifiedImageError

from Common import REQUESTS_HEADERS

log = logging.getLogger(__name__)

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


def pretty_fmt_feeditem(entry):
    """
    This is used purely for debugging

    Works both on feeditems (SimpleNamespace) and rss entries dicts

    Returns: A string pretty formatting the item
    """
    out = ""

    try:
        entry = entry.entry_obj
    except (KeyError, ValueError):
        pass

    for i, v in entry.items():
        out += f"{i} --- {v}"

    out += 80 * "="
    out += "\n"

    return out


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
        log.exception(f"Failed to load logo image from {logo_link}")
        raise

    img_width, img_height = logo_img.size
    banner_width = int(img_height / 2 * 5)  # Discord recommends a banner in 5:2 format

    if banner_width > img_width:
        logo_img.convert("RGBA")
        banner_img = Image.new(mode="RGBA", size=(banner_width, img_height), color="#ffffff00")

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


def fancy_format_datetime(datetime_obj):
    """
    Format a datetime with ordinal day numbers (e.g., 'Tue, 7th June 2023 14:30').

    Important: The function does **not** perform any timezone conversion. The input
    `datetime_obj` must already be in the timezone you intend to display (e.g., after
    calling `.astimezone(your_local_tz)`). Passing a naive datetime or a UTC datetime
    will produce a wall-clock output in that timezone, which may be incorrect for your
    audience.

    The format uses `%a` (abbreviated weekday) and `%B` (full month name), which are
    locale‑sensitive. On non‑English systems, weekday/month names will appear in the
    system's language.

    Based on https://stackoverflow.com/a/16671271

    Args:
        datetime_obj (datetime.datetime): An aware or naive datetime in the desired
            display timezone.

    Returns:
        str: Formatted date string like 'Sun, 1st January 2023 09:05'.

    Example:
        >>> import pytz
        >>> from datetime import datetime
        >>> utc = pytz.UTC
        >>> berlin = pytz.timezone('Europe/Berlin')
        >>> dt = datetime(2023, 6, 7, 10, 30).replace(tzinfo=utc).astimezone(berlin)
        >>> fancy_format_datetime(dt)
        'Wed, 7th June 2023 12:30'
    """
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
