"""
Feed drivers, interfacing with different types of feeds to extract postable items in Discord's embed
format, and keep track of the last posted items to avoid repetitions.
"""

import asyncio
import datetime
import json
import logging
from abc import ABC, abstractmethod
from collections import deque
from html import unescape as html_unescape
from types import SimpleNamespace

import dateutil.parser
import discord
import feedparser
import requests
from bs4 import BeautifulSoup
from lxml import html

from Common import CTF_FLAG_EMOJI, REQUESTS_HEADERS, fetch_ctftime_api_info
from Util import (
    BERLIN_TZ,
    UTC_TZ,
    fancy_format_datetime,
    fancy_format_duration,
    published_or_updated_datetime,
    strip_html_tags,
)

log = logging.getLogger(__name__)


class RSSFeed(ABC):
    first_update = False
    client = None  # Discord client object
    last_feedupdate_etag = None
    last_feedupdate_modified = None
    last_seen_item_id = None
    feed_url = None
    posted_ids = None  # Contains feeditem unique IDs that have already been posted or queued for posting (hence not new)
    new_feed_items = None  # New feed items, in order from oldest to newest
    unposted_feed_items = None  # List of feed items that have not been posted in the last iterations (from oldest to newest)
    associated_channel = None
    reversed_recency = False
    msg_emoji = None  # An emoji to add to every message

    # How many feeditems to post in one make_posts operation to avoid rate limiting
    MAX_FEEDITEMS_POSTED = 15
    # How many of the latest IDs to remember to ensure no duplicate posts
    # Necessary since items in RSS Feeds can re-order due to modifications / updates
    # Should be greater than your biggest RSS feed to guarantee no reposts
    MAX_REMEMBERED_IDS = 80

    # An additional check on a feeditem; if False, the feeditem is not posted and retained till the next posting chance
    def feeditem_posting_condition(self, feeditem):
        return True

    def _iter_feedentries(self, f):
        return iter(f.entries) if not self.reversed_recency else reversed(f.entries)

    def _get_msg_feeditem_id(self, msg):
        """
        Takes a discord msg and, assuming it has an embed associated with some feeditem, tries to
        build that feeditem's id from the available info.

        Raises: ValueError if no valid ID can be determined

        Returns: The feeditem ID
        """
        try:
            embed_url = msg.embeds[0].url
            embed_title = msg.embeds[0].title
            return f"{embed_url}{embed_title}"
        except IndexError:
            raise ValueError("Message has no associated feeditem ID")

    def _get_feedentry_id(self, entry):
        url = getattr(entry, "link", None) or getattr(entry, "href", None)
        title = getattr(entry, "title", None) or getattr(entry, "itunes_title", None)
        title = html_unescape(title)

        if url and title:
            return f"{url}{title}"
        else:
            return title or url

    def _get_feeditem_id(self, item):
        url = getattr(item, "url", None)
        title = getattr(item, "title", None)

        if url and title:
            return f"{url}{title}"
        else:
            return title or url

    def __init__(self, client, feed_url, associated_channel, reversed_recency=False):
        """
        Args:
            client: The discord client
            feed_url: The URL of the RSS feed
            associated_channel: ID of the discord channel to post feed updates into
            reversed_recency: If True, the newest RSS feed items will be taken from the bottom of the feed list, rather than the top.
        """
        self.first_update = True

        self.queued_feeditems = []
        self.posted_ids = deque(maxlen=self.MAX_REMEMBERED_IDS)

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
        log.info(f"Updating feed for {self.feed_url}...")
        f = feedparser.parse(
            self.feed_url,
            etag=self.last_feedupdate_etag,
            modified=self.last_feedupdate_modified,
        )
        if hasattr(f, "etag") and f.etag:
            self.last_feedupdate_etag = f.etag
        if hasattr(f, "modified") and f.modified:
            self.last_feedupdate_modified = f.modified

        # Populate posted_ids ring buffer with discord messages
        if self.first_update:
            self.first_update = False
            last_msgs = [
                m
                async for m in self.client.get_channel(self.associated_channel).history(
                    limit=self.MAX_REMEMBERED_IDS
                )
            ]

            for msg in last_msgs:
                # Use URL+title as a unique identifier for the RSS feed item
                # URL alone does not suffice, e.g. for CTFs with a qualification and a
                # finals stage (URL will be the same there, and both are announced at a
                # similar time)
                try:
                    id = self._get_msg_feeditem_id(msg)
                except ValueError:
                    log.debug(f"Encountered message without a feeditem id: {msg.content}. Skipping")
                    continue

                if id not in self.posted_ids:
                    self.posted_ids.append(id)

        # Parse entries returned by RSS feed and add only those that are not already posted / queued
        new_feeditems = []
        for i, entry in enumerate(self._iter_feedentries(f)):
            # Only consider the newest MAX_FEEDITEMS_POSTED entries for addition
            # -> helps not posting older entries once new entries already exist
            if i == self.MAX_FEEDITEMS_POSTED:
                break

            entry_id = self._get_feedentry_id(entry)
            if (entry_id not in self.posted_ids) and (
                entry_id not in [self._get_feeditem_id(item) for item in self.queued_feeditems]
            ):
                log.info(f"\tFound new feeditem with ID {entry.id}")
                self.posted_ids.append(entry_id)  # Queued for being posted
                feed_item = self.make_feeditem(entry)
                new_feeditems.append(feed_item)

        # Limit the amount of feeditems you take - can't post more anyways; helps keeping news fresh
        # on bot restart / new server
        new_feeditems = new_feeditems[: self.MAX_FEEDITEMS_POSTED]

        self.queued_feeditems += list(reversed(new_feeditems))

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
        Posts enqueued feeditems as embeds into the associated channel.

        If a feeditem_posting_condition was configured by the feed class implementation, only those feeditems that match the condition are posted, while the remainder remains enqueued.

        Returns: How many feeditems were posted
        """
        post_candidates = list(filter(self.feeditem_posting_condition, self.queued_feeditems))

        posted = 0
        for feeditem in post_candidates[-self.MAX_FEEDITEMS_POSTED :]:
            embed = self.make_feeditem_embed(feeditem)
            try:
                msg = await self.client.get_channel(self.associated_channel).send(embed=embed)
                if self.msg_emoji:
                    await msg.add_reaction(self.msg_emoji)

                posted += 1
            except Exception:
                log.error(f"Could not post embed {embed} due to errors")

            self.queued_feeditems.remove(feeditem)

        return posted


class SecurityNowFeed(RSSFeed):
    def _get_feedentry_id(self, entry):
        url = getattr(entry, "link", None) or getattr(entry, "href", None)
        title = getattr(entry, "title", None) or getattr(entry, "itunes_title", None)
        title = html_unescape(title)
        # Strip the SN 1082: ... away so it's consistent with other IDs
        title = title.split(": ", maxsplit=1)[1]

        if url and title:
            return f"{url}{title}"
        else:
            return title or url

    def make_feeditem(self, entry):
        feeditem = {
            "id": entry.id,
            "title": entry.itunes_title,
            "prefixed_title": entry.title,
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

            if not feeditem.thumbnail:
                thumb = None
                try:
                    thumb = entry.media_thumbnail[0]["url"]
                except AttributeError:
                    # Try gaining it from a links field
                    try:
                        link_element = list(filter(lambda e: e.type == "image/jpeg", entry.links))[
                            0
                        ]
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
                            if "property" in meta.attrs and meta.attrs["property"] == "og:image"
                        ]
                        thumb = thumb_options[0] if len(thumb_options) > 0 else None

                feeditem.thumbnail = thumb

            if not feeditem.description:
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

                feeditem.description = html_unescape(description)

            if not feeditem.author:
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
                        if "property" in meta.attrs and meta.attrs["property"] == "article:author"
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
                            if "type" in m.attrs and m.attrs["type"] == "application/ld+json"
                        ]
                    except KeyError:
                        author_in_jsonld_scripts = []
                    except TypeError:
                        # Maybe just a list not a dictionary
                        try:
                            author_in_jsonld_scripts = [
                                json.loads(m.text)["author"][0]
                                for m in soup.find_all("script")
                                if "type" in m.attrs and m.attrs["type"] == "application/ld+json"
                            ]
                        except (KeyError, IndexError, TypeError):
                            author_in_jsonld_scripts = []

                    author_options = (
                        author_in_metas_content + author_in_metas_parsely + author_in_jsonld_scripts
                    )
                    author = author_options[0] if len(author_options) > 0 else None

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


class ExploitDBFeed(NewsFeed):
    def make_feeditem_embed(self, feeditem):
        self.finalize_feeditem(feeditem)

        # Color depends on category
        exploitdb_colors = {
            "remote": discord.Color.red(),
            "local": discord.Color.orange(),
            "webapps": discord.Color.blue(),
            "dos": discord.Color.dark_grey(),
            "shellcode": discord.Color.purple(),
            "papers": discord.Color.teal(),
            None: discord.Color.light_grey(),
        }

        if feeditem.title.startswith("[") and "]" in feeditem.title:
            category = feeditem.title[1:].split("]", 1)[0].lower()
        else:
            category = None

        color = exploitdb_colors.get(category, discord.Color.random())

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


class KrebsOnSecurityFeed(NewsFeed):
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

        # Often, but not always, Krebs also includes a cover image to the blogpost. This is not
        # directly given in the feed and must be extracted from the HTML content.
        if (
            hasattr(entry, "content")
            and entry.content
            and (html := entry.content[0].get("value", ""))
        ):
            soup = BeautifulSoup(html, "html.parser")

            # Find the first div or figure with class containing 'wp-caption'
            if wp_caption := soup.find(
                "div", class_=lambda c: c and "wp-caption" in c
            ) or soup.find("figure", class_=lambda c: c and "wp-caption" in c):
                if (img := wp_caption.find("img")) and img.get("src"):
                    feeditem["thumbnail"] = img["src"]

        return SimpleNamespace(**feeditem)


class CTFTimeFeed(RSSFeed):
    MAX_DESCRIPTION_LENGTH = 1000
    MAX_FEEDITEMS_POSTED = 80

    def __init__(self, client, feed_url, associated_channel, reversed_recency=True):
        self.msg_emoji = CTF_FLAG_EMOJI

        super().__init__(client, feed_url, associated_channel, reversed_recency)

    def _get_feedentry_id(self, entry):
        url = getattr(entry, "id", None)  # The CTFTime URL is the unique identifier
        return url

    def _get_msg_feeditem_id(self, msg):
        """
        Takes a discord msg and, assuming it has an embed associated with some feeditem, tries to
        build that feeditem's id from the available info.

        Raises: ValueError if no valid ID can be determined

        Returns: The feeditem ID (in this case, the CTFTime URL is the unique identifier)
        """
        try:
            embed_footer = msg.embeds[0].footer.text
        except IndexError:
            raise ValueError("Message has no associated feeditem ID")

        # The actual identifying URL is the ctftime URL, saved in our footer in line 3
        embed_url = embed_footer.split("\n")[2].strip()

        return f"{embed_url}"

    def feeditem_posting_condition(self, feeditem):
        # Only make posts if the CTF is within the next 6 weeks
        ctf_is_soon = dateutil.parser.isoparse(feeditem.start_date) < (
            datetime.datetime.now() + datetime.timedelta(days=6 * 7)
        )

        ctf_is_applicable = not (feeditem.onsite == "True" or feeditem.restrictions != "Open")

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

        start_dt = UTC_TZ.localize(dateutil.parser.isoparse(feeditem.start_date))
        end_dt = UTC_TZ.localize(dateutil.parser.isoparse(feeditem.end_date))

        # Determine colour based on time
        color = self._get_ctf_color(start_dt, end_dt)

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

        # Format human‑readable dates and duration
        start_berlin = start_dt.astimezone(BERLIN_TZ)
        end_berlin = end_dt.astimezone(BERLIN_TZ)

        start_date_string = fancy_format_datetime(start_berlin)
        end_date_string = fancy_format_datetime(end_berlin)

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

    def _get_ctf_color(self, start_dt, end_dt):
        now = datetime.datetime.now(datetime.timezone.utc)
        if end_dt < now:
            # Already over
            return discord.Color.light_grey()
        elif start_dt <= now <= end_dt:
            # Currently running
            return discord.Color.orange()
        elif (start_dt - now).days <= 14:
            # Upcoming
            return discord.Color.red()
        else:
            # In the future
            return discord.Color.green()

    def _parse_ctf_embed(self, embed):
        """
        Extracts CTF info from a Discord embed footer.

        Returns:
            dict with: start_dt, end_dt, title, url (ctftime), msg_url (set later).

        Raises:
            ValueError if parsing fails.
        """
        if not embed.footer or "ctftime.org/event/" not in embed.footer.text:
            raise ValueError("Not a CTFTime embed")

        footer_text = embed.footer.text
        date_line = next((line for line in footer_text.split("\n") if line.startswith("📅")), None)
        if not date_line:
            raise ValueError("No date line found")

        date_part = date_line.replace("📅", "").strip()
        parts = date_part.split(" - ")
        if len(parts) < 2:
            raise ValueError("Invalid date format")

        start_str = parts[0].strip()
        end_str = parts[1].split(" • ")[0].strip()

        start_dt = dateutil.parser.parse(start_str, fuzzy=True)
        end_dt = dateutil.parser.parse(end_str, fuzzy=True)

        start_dt = BERLIN_TZ.localize(start_dt).astimezone(UTC_TZ)
        end_dt = BERLIN_TZ.localize(end_dt).astimezone(UTC_TZ)

        return {
            "start_dt": start_dt,
            "end_dt": end_dt,
            "title": embed.title,
            "ctftime_url": footer_text.split("\n")[-1].strip(),  # last line is the URL
            "embed": embed,
        }

    async def get_upcoming_ctfs(self, days=21, max_messages=100):
        """
        Scans the channel and returns a list of CTFs running within the next `days`,
        sorted by start date (soonest first). Includes already started CTFs that haven't ended yet.

        Args:
            days: How many days to consider (default: 21)
            max_messages: How many messages to scan (default: 100)

        Returns:
            List of dicts with keys: start_dt, end_dt, title, msg_url, ctftime_url.
        """
        channel = self.client.get_channel(self.associated_channel)
        if channel is None:
            raise RuntimeError(f"Channel {self.associated_channel} not found")

        now = datetime.datetime.now(datetime.timezone.utc)
        cutoff = now + datetime.timedelta(days=days)

        upcoming = []

        async for msg in channel.history(limit=max_messages, oldest_first=False):
            if not msg.embeds:
                continue
            embed = msg.embeds[0]

            try:
                data = self._parse_ctf_embed(embed)
            except ValueError:
                continue

            start = data["start_dt"]
            end = data["end_dt"]
            if start <= cutoff and end >= now:
                data["msg_url"] = msg.jump_url
                upcoming.append(data)

        # Sort by start date (soonest first)
        upcoming.sort(key=lambda c: c["start_dt"])

        # Deduplicate by ctftime_url, keeping the first (earliest start)
        seen = set()
        unique = []
        for c in upcoming:
            url = c["ctftime_url"]
            if url not in seen:
                seen.add(url)
                unique.append(c)

        return unique

    async def update_embed_colors(self, max_messages=50):
        """
        Scans recent CTF announcements and updates embed colours based on current status.

        Args:
            max_messages: Maximum count of messages to fetch (default: 50)
        """
        channel = self.client.get_channel(self.associated_channel)
        if channel is None:
            log.warning(f"Channel {self.associated_channel} not found")
            return

        updated = 0
        scanned = 0

        async for msg in channel.history(limit=max_messages, oldest_first=False):
            scanned += 1
            if not msg.embeds:
                continue

            embed = msg.embeds[0]
            if not embed.footer or "ctftime.org/event/" not in embed.footer.text:
                continue

            # Extract the date line from the footer
            try:
                data = self._parse_ctf_embed(embed)
            except ValueError:
                continue
            start_dt = data["start_dt"]
            end_dt = data["end_dt"]

            # Apply new colour
            new_color = self._get_ctf_color(start_dt, end_dt)

            if embed.color != new_color:
                new_embed = embed.copy()
                new_embed.color = new_color
                try:
                    await msg.edit(embed=new_embed)
                    updated += 1
                    await asyncio.sleep(0.5)
                except Exception as e:
                    log.error(f"Failed to edit message {msg.id}: {e}")

        log.info(f"Updated {updated} CTF embeds (scanned {scanned} messages)")
