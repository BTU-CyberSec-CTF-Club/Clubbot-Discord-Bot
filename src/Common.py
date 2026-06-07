"""
Common variables and utility functions used across the software
"""

import logging

import requests

log = logging.getLogger(__name__)

CTF_FLAG_EMOJI = "🚩"
NEWSPAPER_EMOJI = "📰"
REQUESTS_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

ctftime_api_urlformat = "https://ctftime.org/api/v1/events/{event_id}/"


def fetch_ctftime_api_info(ctftime_event_url):
    """
    Gets a JSON object with the CTFTime API info for this event.

    Args:
        The url to the ctftime event, e.g. https://ctftime.org/event/2404

    Returns:
        The JSON Object. Example contents:
            organizers
                0
                id	182074
                name	"CISA ICSJWG"
            ctftime_url	"https://ctftime.org/event/2404/"
            ctf_id	784
            weight	0
            duration
                hours	23
                days	3
            live_feed	""
            logo	""
            id	2404
            title	"CISA ICS CTF 2024"
            start	"2024-08-31T17:00:00+00:00"
            participants	3
            location	""
            finish	"2024-09-04T16:00:00+00:00"
            description	"DHS CISA's annual ICS (industrial control systems) CTF is oriented around an incident response scenario involving attacks on critical infrastructure. This year, the featured critical infrastructure sectors are city infrastructure, water purification, medical facilities, and railway."
            format	"Jeopardy"
            is_votable_now	false
            prizes	""
            format_id	1
            onsite	false
            restrictions	"Open"
            url	"https://ctf.cisaicsctf.com/"
            public_votable	true
    """
    event_id = ctftime_event_url.rsplit("/", 1)[-1]
    api_info_url = ctftime_api_urlformat.format(event_id=event_id)
    ctftime_api_info = requests.get(api_info_url, headers=REQUESTS_HEADERS).json()

    return ctftime_api_info
