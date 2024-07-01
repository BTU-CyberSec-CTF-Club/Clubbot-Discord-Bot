#!/bin/python3
import asyncio
import os
import lxml

import Feeds

import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv


load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents(messages=True, message_content=True, guilds=True)
client = discord.Client(intents=intents)

CMD_PREFIX = "!"

FEEDS = [
    Feeds.CTFTimeFeed(
        client,
        "https://ctftime.org/event/list/upcoming/rss/",
        int(os.getenv("CTFTIME_CHANNEL")),
        reversed_recency=True,
    ),
    Feeds.NewsFeed(
        client,
        "https://www.darkreading.com/rss.xml",
        int(os.getenv("DARKREADING_CHANNEL")),
        "Darkreading",
    ),
    Feeds.NewsFeed(
        client,
        "https://www.bleepingcomputer.com/feed/",
        int(os.getenv("BLEEPING_COMPUTER_CHANNEL")),
        "Bleeping Computer",
    ),
    Feeds.NewsFeed(
        client,
        "https://feeds.feedburner.com/TheHackersNews",
        int(os.getenv("THE_HACKER_NEWS_CHANNEL")),
        "The Hacker News",
    ),
    Feeds.NewsFeed(
        client,
        "https://rss.packetstormsecurity.com/",
        int(os.getenv("PACKET_STORM_CHANNEL")),
        "Packet Storm",
    ),
    Feeds.SecurityNowFeed(
        client, "https://feeds.twit.tv/sn.xml", int(os.getenv("SECURITY_NOW_CHANNEL"))
    ),
]
# TODO: Full-disclosure, reddit-netsec


@client.event
async def on_ready():
    print(f"{client.user.name} has connected to Discord!")
    feed_update_task.start()


@client.event
async def on_member_join(member):
    await member.create_dm()
    await member.dm_channel.send(f"Hi {member.name}, welcome to my Discord server!")


@client.event
async def on_message(message):
    if message.author != client.user and message.content.startswith(CMD_PREFIX):
        await message.channel.send("No commands implemented yet.")


@tasks.loop(hours=1)
async def feed_update_task():
    await client.wait_until_ready()
    print("Updating feeds...")
    for feed in FEEDS:
        await feed.update()
    print()

    print("Posting new feed items...")
    for feed in FEEDS:
        await feed.post_new_feed_items()

    print("Done.")
    print()


client.run(TOKEN)
