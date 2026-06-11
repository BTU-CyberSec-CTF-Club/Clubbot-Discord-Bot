#!/bin/python3
"""
The Clubbot discord bot's main definitions. Serves as the entrypoint, and gives the basic skeleton
for handling events.
"""

import logging

log = logging.getLogger("Clubbot")
import sys

import discord
import env
from discord.ext import commands, tasks

import Feeds
from Actions import (
    handle_ctftime_reaction,
    handle_ctftime_role_react_add,
    handle_ctftime_role_react_remove,
    handle_intel_role_react_add,
    handle_intel_role_react_remove,
    handle_news_reaction,
)
from Common import CTF_FLAG_EMOJI, NEWSPAPER_EMOJI

intents = discord.Intents(messages=True, message_content=True, guilds=True, reactions=True)
bot = commands.Bot(intents=intents, command_prefix="!")

FEEDS = [
    Feeds.CTFTimeFeed(
        bot,  # CTFs registered at CTFtime - posts upcoming CTFs scheduled within the next 6 weeks
        "https://ctftime.org/event/list/upcoming/rss/",
        env.CTFTIME_CHANNEL,
        reversed_recency=True,
    ),
    Feeds.ExploitDBFeed(
        bot,  # Proof of Concept Exploit Codes
        "https://www.exploit-db.com/rss.xml",
        env.EXPLOIT_DB_CHANNEL,
        "Exploit DB",
    ),
    Feeds.KrebsOnSecurityFeed(
        bot,  # Deep cybercrime investigations & scoops
        "https://krebsonsecurity.com/feed/",
        env.KREBS_ON_SECURITY_CHANNEL,
        "Krebs on Security",
    ),
    Feeds.NewsFeed(
        bot,  # Threat intel & security strategy (practitioner‑focused)
        "https://www.darkreading.com/rss.xml",
        env.DARKREADING_CHANNEL,
        "Darkreading",
    ),
    Feeds.NewsFeed(
        bot,  # Malware, ransomware, & tech support news
        "https://www.bleepingcomputer.com/feed/",
        env.BLEEPING_COMPUTER_CHANNEL,
        "Bleeping Computer",
    ),
    Feeds.NewsFeed(
        bot,  # Exploits, tools, & fast‑moving threats
        "https://feeds.feedburner.com/TheHackersNews",
        env.THE_HACKER_NEWS_CHANNEL,
        "The Hacker News",
    ),
    Feeds.NewsFeed(
        bot,  # Business & corporate security insights
        "https://www.securitymagazine.com/rss/15",
        env.SECURITY_MAGAZINE_CHANNEL,
        "Security Magazine",
    ),
    Feeds.SecurityNowFeed(
        bot,  # Weekly unique news + deep dives (audio + pdf show notes)
        "https://feeds.twit.tv/sn.xml",
        env.SECURITY_NOW_CHANNEL,
    ),
]


# @bot.event
# async def on_member_join(member):
#     await member.create_dm()
#     await member.dm_channel.send(f"Hi {member.name}, welcome to my Discord server!")

# @bot.listen
# async def on_message(message):
#     if message.author != bot.user and message.content.startswith(CMD_PREFIX):
#         log.info(f"Command received: {message.content}")
#         await message.channel.send("Sorry folks, no commands are implemented yet.")


@bot.event
async def on_raw_reaction_add(payload):
    guild = bot.get_guild(payload.guild_id)
    if guild is None:
        log.error(
            f"Could not process reaction - guild is None! (user_id={payload.user_id}, message_id={payload.message_id}, emoji={payload.emoji})"
        )
        return

    if payload.user_id == bot.user.id:
        # Don't react to emojis done by the bot
        return
    elif payload.channel_id == env.CTFTIME_CHANNEL and str(payload.emoji) == CTF_FLAG_EMOJI:
        await handle_ctftime_reaction(payload, guild)
    elif payload.channel_id in [f.associated_channel for f in FEEDS]:
        reacted_on_msg = await bot.get_channel(payload.channel_id).fetch_message(payload.message_id)
        await handle_news_reaction(payload, guild, reacted_on_msg)
    elif (
        payload.message_id == env.INTEL_ROLE_REACT_MESSAGE_ID
        and str(payload.emoji) == NEWSPAPER_EMOJI
    ):
        await handle_intel_role_react_add(payload, guild)
    elif (
        payload.message_id == env.CTFTIME_ROLE_REACT_MESSAGE_ID
        and str(payload.emoji) == CTF_FLAG_EMOJI
    ):
        await handle_ctftime_role_react_add(payload, guild)


@bot.event
async def on_raw_reaction_remove(payload):
    guild = bot.get_guild(payload.guild_id)
    if guild is None:
        log.error(
            f"Could not process reaction - guild is None! (user_id={payload.user_id}, message_id={payload.message_id}, emoji={payload.emoji})"
        )
        return

    if payload.user_id == bot.user.id:
        # Don't react to emojis done by the bot
        return
    elif (
        payload.message_id == env.INTEL_ROLE_REACT_MESSAGE_ID
        and str(payload.emoji) == NEWSPAPER_EMOJI
    ):
        await handle_intel_role_react_remove(payload, guild)
    elif (
        payload.message_id == env.CTFTIME_ROLE_REACT_MESSAGE_ID
        and str(payload.emoji) == CTF_FLAG_EMOJI
    ):
        await handle_ctftime_role_react_remove(payload, guild)


@tasks.loop(hours=8)
async def feed_update_task():
    try:
        await bot.wait_until_ready()
        log.info("Started updating feeds")
        try:
            for feed in FEEDS:
                await feed.update()
        except Exception:
            log.exception(f"Error updating feed {feed}", exc_info=True)

        log.info("Posting new feed items")
        posted = 0
        for feed in FEEDS:
            posted += await feed.post_new_feed_items()

        log.info(f"Finished posting {posted} feeditems across {len(FEEDS)} feeds")
    except Exception:
        log.exception("Fatal error in feed update task")


@bot.event
async def on_ready():
    log.info(f"{bot.user.name} has connected to Discord!")
    feed_update_task.start()


if __name__ == "__main__":
    # Configure logging, including setting own settings for the Discord logger
    logging.basicConfig(
        level=logging.INFO,
        # format="[%(asctime)s] [%(levelname)-8s] %(funcName)s: %(message)s",
        format="%(asctime)s [%(levelname)s] %(funcName)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout)
        ],  # only stdout - logfiles shall be handled by external tools
    )

    # TODO: This still does not work properly
    discord_logger = logging.getLogger("discord")
    discord_logger.handlers.clear()
    discord_logger.propagate = True
    discord_logger.setLevel(logging.WARNING)

    # Begin!
    bot.run(env.DISCORD_TOKEN)
