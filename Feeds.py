import feedparser
import datetime
import requests
import json
import sys
import time
import discord
from lxml import html
import dateutil.parser
from Common import CTF_FLAG_EMOJI, REQUESTS_HEADERS, fetch_ctftime_api_info
from html import unescape as html_unescape

from types import SimpleNamespace
from abc import ABC, abstractmethod
from bs4 import BeautifulSoup

from Util import UTC_TZ, BERLIN_TZ, strip_html_tags
from Util import (
    print,
    published_or_updated_datetime,
    fancy_format_datetime,
    fancy_format_duration,
)


class RSSFeed(ABC):
    client = None  # Discord client object
    last_feedupdate_etag = None
    last_feedupdate_modified = None
    last_seen_item_id = None
    feed_url = None
    new_feed_items = None  # New feed items, in order from oldest to newest
    unposted_feed_items = None  # List of feed items that have not been posted in the last iterations (from oldest to newest)
    associated_channel = None
    reversed_recency = False
    msg_emoji = None  # An emoji to add to every message

    MAX_FEEDITEMS_POSTED = 10

    # An additional check on a feeditem; if False, the feeditem is not posted and retained till the next posting chance
    def feeditem_posting_condition(self, feeditem):
        return True

    def _iter_feedentries(self, f):
        return iter(f.entries) if not self.reversed_recency else reversed(f.entries)

    def __init__(self, client, feed_url, associated_channel, reversed_recency=False):
        """
        Args:
            client: The discord client
            feed_url: The URL of the RSS feed
            associated_channel: ID of the discord channel to post feed updates into
            reversed_recency: If True, the newest RSS feed items will be taken from the bottom of the feed list, rather than the top.
        """
        self.new_feed_items = []
        self.unposted_feed_items = []

        self.client = client
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
        print(f"Updating feed for {self.feed_url}...")

        # Determine last seen ID in case of initial execution
        if self.last_seen_item_id is None:
            try:
                last_msg = [
                    m
                    async for m in self.client.get_channel(
                        self.associated_channel
                    ).history(limit=1)
                ][0]

                last_embed_url = last_msg.embeds[0].url
                last_embed_title = last_msg.embeds[0].title

                # Use URL+title as a unique identifier for the RSS feed item
                # URL alone does not suffice, e.g. for CTFs with a qualification and a
                # finals stage (URL will be the same there, and both are announced at a
                # similar time)
                for entry in self._iter_feedentries(f):
                    try:
                        elink = entry.link
                    except AttributeError:
                        elink = None

                    try:
                        ehref = entry.href
                    except AttributeError:
                        ehref = None

                    try:
                        etitle = entry.title
                    except AttributeError:
                        etitle = None
                    try:
                        e_tunestitle = entry.itunes_title
                    except AttributeError:
                        e_tunestitle = None

                    if last_embed_url in [elink, ehref] and last_embed_title in [
                        etitle,
                        e_tunestitle,
                    ]:
                        self.last_seen_item_id = entry.id
                        break
            except IndexError:
                # There was no valid last message in the channel, i.e. the bot never posted there.
                # Keep last_seen None and post everything!
                pass

        new_rss_feeditems = []
        for entry in self._iter_feedentries(f):
            if entry.id != self.last_seen_item_id:
                print(f"\tFound new feeditem with ID {entry.id}")
                feed_item = self.make_feeditem(entry)
                new_rss_feeditems.append(feed_item)
            else:
                break

        self.new_feed_items += list(
            reversed(new_rss_feeditems)
        )  # Reversed, so newest are at the back
        if self.new_feed_items:
            self.last_seen_item_id = self.new_feed_items[-1].id

    @abstractmethod
    def make_feeditem(entry):
        """
        Turns the RSS Feed entry into a feeditem dictionary / namespace.

        This feeditem is not necessarily finalized already - some fields may have the
        value None. However, important fields allowing for checks (e.g. for the posting
        condition) will be available already. The finalize_feeditem should be called to receive additional
        information before creating the discord embed.

        Returns: The feeditem as a SimpleNamespace. The exact fields depend on the feed itself.
        """
        return None

    @abstractmethod
    def finalize_feeditem(feeditem):
        """
        Finalizes the feeditem dictionary / namespace by filling fields whose value is
        expensive to determine (e.g. because additional API calls or website requests are necessary).
        """

    @abstractmethod
    def make_feeditem_embed(self, fielditem):
        """
        Creates a Discord embed representing the field item.

        Returns: Discord embed for the field item
        """
        return None

    async def post_new_feed_items(self):
        """
        Posts new (and temporarily retained) feeditems as embeds into the associated channel.

        If a feeditem_posting_condition was configured by the feed class implementation, only those (new) feeditems that match the condition are posted.
        """
        available_feeditems = self.unposted_feed_items + self.new_feed_items
        post_candidates = list(
            filter(self.feeditem_posting_condition, available_feeditems)
        )

        for feeditem in post_candidates[-self.MAX_FEEDITEMS_POSTED :]:
            embed = self.make_feeditem_embed(feeditem)
            try:
                msg = await self.client.get_channel(self.associated_channel).send(
                    embed=embed
                )
                if self.msg_emoji:
                    await msg.add_reaction(self.msg_emoji)
            except Exception:
                print(f"Could not post embed {embed} due to errors", file=sys.stderr)

            available_feeditems.remove(feeditem)

        self.unposted_feed_items = available_feeditems
        self.clear_new_feed_items()

    def clear_new_feed_items(self):
        self.new_feed_items = []


class SecurityNowFeed(RSSFeed):
    def make_feeditem(self, entry):

        feeditem = {
            "id": entry.id,
            "title": entry.itunes_title,
            #             "title": entry.title,
            "url": entry.link,
            "thumbnail": entry.image["href"],
            "publish_date": published_or_updated_datetime(entry),
            "author": "Security Now! with Steve Gibson",
            "episode": entry.podcast_episode,
            "description": None,
            "duration": entry.itunes_duration,
            "entry_obj": entry,
            "is_finalized": False,
        }

        return SimpleNamespace(**feeditem)

    def finalize_feeditem(self, feeditem):
        if not feeditem.is_finalized:
            entry = feeditem.entry_obj
            html_summary_tree = html.fromstring(entry.summary)
            summary_topics = ""
            for child in html_summary_tree.find("ul").getchildren():
                summary_topics += f"* {child.text}\n"
            description = summary_topics

            feeditem.description = description
            feeditem.is_finalized = True

    def make_feeditem_embed(self, feeditem):
        self.finalize_feeditem(feeditem)

        color = discord.Color.random()

        # Embed with baseinfo
        embed = discord.Embed(
            title=feeditem.title,
            description=(feeditem.description),
            url=feeditem.url,
            color=color,
            timestamp=feeditem.publish_date,
        )
        embed.set_author(name=feeditem.author)
        embed.set_image(url=feeditem.thumbnail)
        embed.set_footer(text=f"Episode {feeditem.episode} • {feeditem.duration}")

        return embed


class NewsFeed(RSSFeed):
    MAX_DESCRIPTION_LENGTH = 800
    newssource_name = None

    def __init__(
        self,
        client,
        feed_url,
        associated_channel,
        newssource_name,
        reversed_recency=False,
    ):
        self.newssource_name = newssource_name

        super().__init__(client, feed_url, associated_channel, reversed_recency)

    def make_feeditem(self, entry):
        feeditem = {
            "id": entry.id,
            "title": html_unescape(entry.title),
            "url": entry.link,
            "thumbnail": None,
            "publish_date": published_or_updated_datetime(entry),
            "author": None,
            "description": None,
            "entry_obj": entry,
            "is_finalized": False,
        }

        return SimpleNamespace(**feeditem)

    def finalize_feeditem(self, feeditem):
        if not feeditem.is_finalized:
            entry = feeditem.entry_obj

            metas = None

            thumb = None
            try:
                thumb = entry.media_thumbnail[0]["url"]
            except AttributeError:
                # Try gaining it from a links field
                try:
                    link_element = list(
                        filter(lambda e: e.type == "image/jpeg", entry.links)
                    )[0]
                    thumb = link_element["href"]
                except (AttributeError, IndexError):
                    # Fallback to trying to gain the image from the webpage
                    if not metas:
                        r = requests.get(entry.link, headers=REQUESTS_HEADERS)
                        soup = BeautifulSoup(r.text, features="html.parser")
                        metas = soup.find_all("meta")

                    thumb_options = [
                        meta.attrs["content"]
                        for meta in metas
                        if "property" in meta.attrs
                        and meta.attrs["property"] == "og:image"
                    ]
                    thumb = thumb_options[0] if len(thumb_options) > 0 else None

            description = None
            try:
                description = entry.summary
                if not entry.summary:
                    # An empty summary doesn't satisfy either.
                    raise AttributeError
            except AttributeError:
                # Fallback to gaining description from webpage meta
                if not metas:
                    r = requests.get(entry.link, headers=REQUESTS_HEADERS)
                    soup = BeautifulSoup(r.text, features="html.parser")
                    metas = soup.find_all("meta")

                description = "\n".join(
                    [
                        meta.attrs["content"]
                        for meta in metas
                        if "name" in meta.attrs and meta.attrs["name"] == "description"
                    ]
                )
            if description is not None:
                description = strip_html_tags(description)

            author = None
            try:
                author = entry.author
                if not author:
                    raise AttributeError
            except AttributeError:
                if not metas:
                    r = requests.get(entry.link, headers=REQUESTS_HEADERS)
                    soup = BeautifulSoup(r.text, features="html.parser")
                    metas = soup.find_all("meta")

                author_in_metas_content = [
                    meta.attrs["content"]
                    for meta in metas
                    if "property" in meta.attrs
                    and meta.attrs["property"] == "article:author"
                ] + [
                    meta.attrs["content"]
                    for meta in metas
                    if "name" in meta.attrs and meta.attrs["name"] == "author"
                ]

                try:
                    author_in_metas_parsely = [
                        json.loads(m.attrs["content"])["author"]
                        for m in metas
                        if "name" in m.attrs and m.attrs["name"] == "parsely-page"
                    ]
                except KeyError:
                    author_in_metas_parsely = []

                try:
                    author_in_jsonld_scripts = [
                        json.loads(m.text)["author"]["name"]
                        for m in soup.find_all("script")
                        if "type" in m.attrs
                        and m.attrs["type"] == "application/ld+json"
                    ]
                except KeyError:
                    author_in_jsonld_scripts = []
                except TypeError:
                    # Maybe just a list not a dictionary
                    try:
                        author_in_jsonld_scripts = [
                            json.loads(m.text)["author"][0]
                            for m in soup.find_all("script")
                            if "type" in m.attrs
                            and m.attrs["type"] == "application/ld+json"
                        ]
                    except (KeyError, IndexError, TypeError):
                        author_in_jsonld_scripts = []

                author_options = (
                    author_in_metas_content
                    + author_in_metas_parsely
                    + author_in_jsonld_scripts
                )
                author = author_options[0] if len(author_options) > 0 else None

            feeditem.thumbnail = thumb
            feeditem.description = html_unescape(description)
            feeditem.author = author
            feeditem.is_finalized = True

    def make_feeditem_embed(self, feeditem):
        self.finalize_feeditem(feeditem)
        color = discord.Color.random()

        # Embed with baseinfo
        embed = discord.Embed(
            title=feeditem.title,
            description=(
                feeditem.description
                if len(feeditem.description) <= self.MAX_DESCRIPTION_LENGTH
                else feeditem.description[0 : self.MAX_DESCRIPTION_LENGTH] + " [...]"
            ),
            url=feeditem.url,
            color=color,
            timestamp=feeditem.publish_date,
        )
        embed.set_author(name=self.newssource_name)
        embed.set_image(url=feeditem.thumbnail)
        embed.set_footer(text=feeditem.author)

        return embed


class CTFTimeFeed(RSSFeed):
    MAX_DESCRIPTION_LENGTH = 1000
    MAX_FEEDITEMS_POSTED = 80

    def __init__(self, client, feed_url, associated_channel, reversed_recency=True):
        self.msg_emoji = CTF_FLAG_EMOJI

        super().__init__(client, feed_url, associated_channel, reversed_recency)

    def feeditem_posting_condition(self, feeditem):
        # Only make posts if the CTF is within the next 6 weeks
        ctf_is_soon = dateutil.parser.isoparse(feeditem.start_date) < (
            datetime.datetime.now() + datetime.timedelta(days=6 * 7)
        )

        ctf_is_applicable = not (
            feeditem.onsite == "True" or feeditem.restrictions != "Open"
        )

        return ctf_is_applicable and ctf_is_soon

    def make_feeditem(self, entry):
        """
        Turns the RSS Feed entry into a feeditem dictionary / namespace

        Returns: The feeditem as a SimpleNamespace. The exact fields depend on the feed itself.
        """
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
            "description": None,
            "expected_participants": None,
            "prizes": None,
            "duration": None,
            "entry_obj": entry,
            "is_finalized": False,
        }

        return SimpleNamespace(**feeditem)

    def finalize_feeditem(self, feeditem):
        if not feeditem.is_finalized:
            entry = feeditem.entry_obj

            ctftime_api_info = fetch_ctftime_api_info(entry.id)

            feeditem.description = ctftime_api_info["description"]
            feeditem.expected_participants = ctftime_api_info["participants"]
            feeditem.prizes = ctftime_api_info["prizes"]
            feeditem.duration = ctftime_api_info["duration"]
            feeditem.is_finalized = True

    def make_feeditem_embed(self, feeditem):
        """
        Creates a Discord embed representing the field item.

        Returns: Discord embed for the field item
        """
        self.finalize_feeditem(feeditem)

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
                else feeditem.description[0 : self.MAX_DESCRIPTION_LENGTH] + " [...]"
            ),
            url=feeditem.url,
            color=color,
        )
        embed.set_thumbnail(url=feeditem.logo_url)

        # More specific event info in footer
        start_datetime = UTC_TZ.localize(dateutil.parser.isoparse(feeditem.start_date))
        start_date_string = fancy_format_datetime(start_datetime.astimezone(BERLIN_TZ))
        end_datetime = UTC_TZ.localize(dateutil.parser.isoparse(feeditem.end_date))
        end_date_string = fancy_format_datetime(end_datetime.astimezone(BERLIN_TZ))

        duration_string = fancy_format_duration(
            feeditem.duration["days"], feeditem.duration["hours"]
        )
        location_string = feeditem.location if feeditem.onsite == "True" else "Online"
        footer_text = (
            f"📌 {location_string} | ⛳ {feeditem.ctf_format} | 👮 {feeditem.restrictions}\n"
            + f"📅 {start_date_string} - {end_date_string} • ⏳ {duration_string}\n"
            + f"{feeditem.id}"
        )
        embed.set_footer(text=footer_text, icon_url=None)

        return embed
