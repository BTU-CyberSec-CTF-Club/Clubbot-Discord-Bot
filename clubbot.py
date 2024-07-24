#!/bin/python3
import os
import sys
import time
from aiohttp.client_exceptions import ClientConnectorError
from Common import CTF_FLAG_EMOJI, fetch_ctftime_api_info

import logging
from logging.handlers import RotatingFileHandler

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        RotatingFileHandler("runtime.log", maxBytes=256 * 1024 * 1024, backupCount=1),
        logging.StreamHandler(sys.stdout),
    ],
)

logger.setLevel(logging.DEBUG)

import Feeds

import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# See https://discordpy.readthedocs.io/en/stable/api.html#discord.Intents
intents = discord.Intents(
    messages=True, message_content=True, guilds=True, reactions=True
)
client = discord.Client(intents=intents)

CMD_PREFIX = "!"

FEEDS = [
    #     Feeds.CTFTimeFeed(
    #         client,
    #         "https://ctftime.org/event/list/upcoming/rss/",
    #         int(os.getenv("CTFTIME_CHANNEL")),
    #         reversed_recency=True,
    #     ),
    #     Feeds.NewsFeed(
    #         client,
    #         "https://www.darkreading.com/rss.xml",
    #         int(os.getenv("DARKREADING_CHANNEL")),
    #         "Darkreading",
    #     ),
    #     Feeds.NewsFeed(
    #         client,
    #         "https://www.bleepingcomputer.com/feed/",
    #         int(os.getenv("BLEEPING_COMPUTER_CHANNEL")),
    #         "Bleeping Computer",
    #     ),
    #     Feeds.NewsFeed(
    #         client,
    #         "https://feeds.feedburner.com/TheHackersNews",
    #         int(os.getenv("THE_HACKER_NEWS_CHANNEL")),
    #         "The Hacker News",
    #     ),
    #     Feeds.NewsFeed(
    #         client,
    #         "https://rss.packetstormsecurity.com/",
    #         int(os.getenv("PACKET_STORM_CHANNEL")),
    #         "Packet Storm",
    #     ),
    #     Feeds.SecurityNowFeed(
    #         client, "https://feeds.twit.tv/sn.xml", int(os.getenv("SECURITY_NOW_CHANNEL"))
    #     ),
]
# TODO: Full-disclosure, reddit-netsec


@client.event
async def on_ready():
    logger.info(f"{client.user.name} has connected to Discord!")
    feed_update_task.start()


# @client.event
# async def on_member_join(member):
#     await member.create_dm()
#     await member.dm_channel.send(f"Hi {member.name}, welcome to my Discord server!")


@client.event
async def on_message(message):
    if message.author != client.user and message.content.startswith(CMD_PREFIX):
        await message.channel.send("Sorry folks, no commands are implemented yet.")


# useful example: https://stackoverflow.com/a/52212888
@client.event
async def on_raw_reaction_add(payload):
    if payload.user_id == client.user.id:
        # Don't react to emojis done by the bot
        return

    if payload.channel_id == int(os.getenv("CTFTIME_CHANNEL")):
        if str(payload.emoji) == CTF_FLAG_EMOJI:
            ctftime_msg = await client.get_channel(payload.channel_id).fetch_message(
                payload.message_id
            )
            ctftime_embed = ctftime_msg.embeds[0]
            ctftime_url = ctftime_embed.footer.text.split("\n")[-1]
            ctftime_api_info = fetch_ctftime_api_info(ctftime_url)

            # Create an Event
            # title
            # logo (may be empty)
            # Channel (to be created)
            # Start date and time
            # End date and time
            # Description referring to this message id
            # https://gist.github.com/adamsbytes/8445e2f9a97ae98052297a4415b5356f


@client.event
async def on_raw_reaction_remove(payload):
    if payload.user_id == client.user.id:
        # Don't react to emojis done by the bot
        return
    # TODO


@tasks.loop(hours=1)
async def feed_update_task():
    try:
        await client.wait_until_ready()
        logger.info("Updating feeds...")
        for feed in FEEDS:
            await feed.update()
        logger.info("")

        logger.info("Posting new feed items...")
        for feed in FEEDS:
            await feed.post_new_feed_items()

        logger.info("Done.")
        logger.info("")
    except Exception:
        logger.exception("Error in Feed Update Task")


client.run(TOKEN)
