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
