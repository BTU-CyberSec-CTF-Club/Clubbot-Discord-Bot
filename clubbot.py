#!/bin/python3
import os
from Common import CTF_FLAG_EMOJI, fetch_ctftime_api_info
from Util import print, print_exception, as_kebab_case
import dateutil.parser
import requests
from PIL import Image
import random


import Feeds

import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
CTF_CATEGORY_ID = int(os.getenv("CTF_CATEGORY_ID"))
UPCOMING_CTFS_CHANNEL_ID = int(os.getenv("UPCOMING_CTFS_CHANNEL_ID"))

# See https://discordpy.readthedocs.io/en/stable/api.html#discord.Intents
intents = discord.Intents(
    messages=True, message_content=True, guilds=True, reactions=True
)
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


@client.event
async def on_ready():
    print(f"{client.user.name} has connected to Discord!")
    feed_update_task.start()


# @client.event
# async def on_member_join(member):
#     await member.create_dm()
#     await member.dm_channel.send(f"Hi {member.name}, welcome to my Discord server!")


@client.event
async def on_message(message):
    if message.author != client.user and message.content.startswith(CMD_PREFIX):
        await message.channel.send("Sorry folks, no commands are implemented yet.")


def bannerize_logo(logo_link):
    _, ending = logo_link.rsplit(".", maxsplit=1)

    distinguisher = random.randint(0, 2**16)
    download_logofile_name = f"/tmp/logofile-{distinguisher}.{ending}"
    edited_logofile_name = f"/tmp/logofile-{distinguisher}-edit.png"

    r = requests.get(logo_link)
    with open(download_logofile_name, "wb") as logofile:
        for chunk in r:
            logofile.write(chunk)

    pil_img = Image.open(download_logofile_name)
    img_width, img_height = pil_img.size
    new_img_width = int(img_height / 2 * 5)  # Discord recommends a banner in 5:2 format
    if new_img_width > img_width:
        os.system(
            f"magick {download_logofile_name} -gravity center -background none -extent {new_img_width}x{img_height} {edited_logofile_name}"
        )

    with open(edited_logofile_name, "rb") as logofile:
        logofile_bytes = logofile.read()

    return logofile_bytes


@client.event
async def on_raw_reaction_add(payload):
    guild = client.get_guild(payload.guild_id)

    if payload.user_id == client.user.id:
        # Don't react to emojis done by the bot
        return

    if payload.channel_id == int(os.getenv("CTFTIME_CHANNEL")):
        if str(payload.emoji) == CTF_FLAG_EMOJI:
            # NOTE: If the system is abused, could also check if user is organizer before doing any of the following

            # Determine what message / CTF this is
            ctftime_msg = await client.get_channel(payload.channel_id).fetch_message(
                payload.message_id
            )
            ctftime_embed = ctftime_msg.embeds[0]
            ctftime_url = ctftime_embed.footer.text.split("\n")[-1]

            # Gain necessary CTF info for creating the event
            ctftime_api_info = fetch_ctftime_api_info(ctftime_url)

            title = ctftime_api_info["title"]
            start_time = dateutil.parser.isoparse(ctftime_api_info["start"])
            end_time = dateutil.parser.isoparse(ctftime_api_info["finish"])

            ctf_website = ctftime_api_info["url"]
            event_desc = ctftime_api_info["description"]
            msglink = f"https://discord.com/channels/{payload.guild_id}/{payload.channel_id}/{payload.message_id}"
            description = f"Official Website: {ctf_website} || See {msglink} for more information.\n---\n{event_desc}"
            logo = ctftime_api_info["logo"]

            # Create a text channel for the CTF
            new_channel_name = as_kebab_case(title)
            existing_channel = discord.utils.get(guild.channels, name=new_channel_name)
            if existing_channel:
                print(
                    "A flag-reaction was given, but a fitting ctf channel already seems to exist. Returning."
                )
                return

            tournament_channel = await guild.create_text_channel(
                new_channel_name,
                category=guild.get_channel(CTF_CATEGORY_ID),
            )
            location = f"https://discord.com/channels/{payload.guild_id}/{tournament_channel.id}"

            # Create an Event
            if logo:
                edited_logodata = bannerize_logo(logo)
                event = await guild.create_scheduled_event(
                    name=title,
                    start_time=start_time,
                    end_time=end_time,
                    image=edited_logodata,
                    location=location,
                    entity_type=discord.EntityType.external,
                    description=description,
                    # "guild_only" is actually the only option it gives us.. Maybe that will
                    # change in the future.
                    privacy_level=discord.PrivacyLevel.guild_only,
                )
            else:
                event = await guild.create_scheduled_event(
                    name=title,
                    start_time=start_time,
                    end_time=end_time,
                    location=location,
                    entity_type=discord.EntityType.external,
                    description=description,
                    # "guild_only" is actually the only option it gives us.. Maybe that will
                    # change in the future.
                    privacy_level=discord.PrivacyLevel.guild_only,
                )
            event_link = f"https://discord.com/events/{payload.guild_id}/{event.id}"

            # Post an initial message in the text channel, and the event in the upcoming
            # CTFs channel
            await tournament_channel.send(event_link)
            await guild.get_channel(UPCOMING_CTFS_CHANNEL_ID).send(event_link)
            # TODO: Channel Topic


@client.event
async def on_raw_reaction_remove(payload):
    if payload.user_id == client.user.id:
        # Don't react to emojis done by the bot
        return


@tasks.loop(hours=1)
async def feed_update_task():
    try:
        await client.wait_until_ready()
        print("Updating feeds...")
        for feed in FEEDS:
            await feed.update()
        print("")

        print("Posting new feed items...")
        for feed in FEEDS:
            await feed.post_new_feed_items()

        print("Done.")
        print("")
    except Exception as e:
        print_exception("ERROR IN FEED UPDATE TASK", e)


client.run(TOKEN)
