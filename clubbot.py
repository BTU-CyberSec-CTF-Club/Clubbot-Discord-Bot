#!/bin/python3
import os
import random
import datetime
import requests
import json
from types import SimpleNamespace
from abc import ABC, abstractmethod

import discord
from dotenv import load_dotenv

import feedparser

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents(messages=True, message_content=True, guilds=True)
client = discord.Client(intents=intents)

CMD_PREFIX = "!"

REQUESTS_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


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


class RSSFeed(ABC):
    last_feedupdate_etag = None
    last_feedupdate_modified = None
    last_seen_item_id = None
    feed_url = None
    new_feed_items = []  # New feed items, in order from oldest to newest
    associated_channel = None
    reversed_recency = False

    def _iter_feedentries(self, f):
        return iter(f.entries) if not self.reversed_recency else reversed(f.entries)

    def __init__(self, feed_url, associated_channel, reversed_recency=False):
        """
        Args:
            feed_url: The URL of the RSS feed
            associated_channel: ID of the discord channel to post feed updates into
            reversed_recency: If True, the newest RSS feed items will be taken from the bottom of the feed list, rather than the top.
        """
        self.feed_url = feed_url
        self.associated_channel = associated_channel
        self.reversed_recency = reversed_recency

    async def update(self):
        """
        Checks for updates in the feed and if so, adds new feed items to the list.

        If no feed update has been done within the lifetime of the script execution, the RSS feed is guaranteed to be pulled and evaluated.
        To ensure only actually new items are taken, on the first execution the associated discord channel's last message is checked and the last seen ID determined based on the message title. From then on, the remembered last seen ID is used.
        """
        f = feedparser.parse(
            self.feed_url,
            etag=self.last_feedupdate_etag,
            modified=self.last_feedupdate_modified,
        )

        # Determine last seen ID in case of initial execution
        if self.last_seen_item_id is None:
            try:
                last_msg = [
                    m
                    async for m in client.get_channel(self.associated_channel).history(
                        limit=1
                    )
                ][0]

                last_embed_title = last_msg.embeds[0].title
            except IndexError:
                # There was no valid last message in the channel, i.e. the bot never posted there.
                # Keep last_seen None and post everything!
                pass

            if last_embed_title:
                # Assumption: Title is unique within the window of the recent RSS feed contents
                for entry in self._iter_feedentries(f):
                    if entry.title == last_embed_title:
                        self.last_seen_item_id = entry.id
                        break

        for entry in self._iter_feedentries(f):
            if entry.id != self.last_seen_item_id:
                feed_item = self.make_feeditem(entry)
                self.new_feed_items.insert(0, feed_item)
            else:
                if self.new_feed_items:
                    self.last_seen_item_id = self.new_feed_items[-1].id
                break

    @abstractmethod
    def make_feeditem(entry):
        return None

    @abstractmethod
    def iterate_field_item_embeds(self):
        while False:
            yield None

    async def post_new_feed_items(self):
        """
        Posts new feeditems as embeds into the associated channel
        """
        for feeditem_embed in self.iterate_field_item_embeds():
            await client.get_channel(self.associated_channel).send(embed=feeditem_embed)

        self.clear_new_feed_items()

    def clear_new_feed_items(self):
        self.new_feed_items = []


class CTFTimeFeed(RSSFeed):
    ctftime_api_urlformat = "https://ctftime.org/api/v1/events/{event_id}/"
    MAX_DESCRIPTION_LENGTH = 1000

    def make_feeditem(self, entry):
        event_id = entry.id.rsplit("/", 1)[-1]
        api_info_url = self.ctftime_api_urlformat.format(event_id=event_id)
        ctftime_api_info = requests.get(api_info_url, headers=REQUESTS_HEADERS).json()

        feeditem = {
            "id": entry.id,
            "title": entry.title,
            "url": entry.href,
            "ctftime_url": entry.link,
            "start_date": entry.start_date,
            "end_date": entry.finish_date,
            "logo_url": "https://ctftime.org" + entry.logo_url,
            "ctf_format": entry.format_text,
            "restrictions": entry.restrictions,
            "location": entry.location,
            "onsite": entry.onsite,
            "organizers": [o["name"] for o in json.loads(entry.organizers)],
            "description": ctftime_api_info["description"],
            "expected_participants": ctftime_api_info["participants"],
            "prizes": ctftime_api_info["prizes"],
            "duration": ctftime_api_info["duration"],
        }

        return SimpleNamespace(**feeditem)

    def iterate_field_item_embeds(self):
        """
        Iterator through the new field items, already formatted as a Discord embed.

        Yields: Discord embeds representing the new field items.
        """
        for feeditem in self.new_feed_items:
            # Determine color
            UNINTERESTING_COLOR = discord.Color.light_grey()
            if feeditem.onsite == "True" or feeditem.restrictions != "Open":
                color = UNINTERESTING_COLOR
            else:
                format_to_color = {
                    "Jeopardy": discord.Color.blue(),
                    "Attack-Defense": discord.Color.red(),
                }
                color = format_to_color.get(feeditem.ctf_format, discord.Color.purple())

            # Embed with baseinfo
            embed = discord.Embed(
                title=feeditem.title,
                description=(
                    feeditem.description
                    if len(feeditem.description) <= self.MAX_DESCRIPTION_LENGTH
                    else feeditem.description[0 : self.MAX_DESCRIPTION_LENGTH]
                    + " [...]"
                ),
                url=feeditem.url,
                color=color,
            )
            embed.set_thumbnail(url=feeditem.logo_url)

            # More specific event info in footer
            start_date_string = fancy_format_datetime(
                datetime.datetime.fromisoformat(feeditem.start_date)
            )
            end_date_string = fancy_format_datetime(
                datetime.datetime.fromisoformat(feeditem.end_date)
            )

            duration_string = fancy_format_duration(
                feeditem.duration["days"], feeditem.duration["hours"]
            )
            location_string = (
                feeditem.location if feeditem.onsite == "True" else "Online"
            )
            footer_text = f"📌 {location_string} | ⛳ {feeditem.ctf_format} | 👮 {feeditem.restrictions}\n📅 {start_date_string} - {end_date_string} • ⏳ {duration_string}"
            embed.set_footer(text=footer_text, icon_url=None)

            yield embed


FEEDS = [
    CTFTimeFeed(
        "https://ctftime.org/event/list/upcoming/rss/",
        1256692414647635968,
        reversed_recency=True,
    )  # Bot channel
]


@client.event
async def on_ready():
    print(f"{client.user.name} has connected to Discord!")
    print("Updating feeds...")
    for feed in FEEDS:
        await feed.update()

    print("Posting new feed items...")
    await FEEDS[0].post_new_feed_items()

    print("Done.")


@client.event
async def on_member_join(member):
    await member.create_dm()
    await member.dm_channel.send(f"Hi {member.name}, welcome to my Discord server!")


@client.event
async def on_message(message):
    if message.author != client.user and message.content.startswith(CMD_PREFIX):
        await message.channel.send("No commands implemented yet.")


client.run(TOKEN)
