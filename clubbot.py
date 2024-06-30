#!/bin/python3
import os
import random

import discord
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
print(TOKEN)

intents = discord.Intents(messages=True, message_content=True)
client = discord.Client(intents=intents)

CMD_PREFIX = "!"


@client.event
async def on_ready():
    print(f"{client.user.name} has connected to Discord!")


@client.event
async def on_member_join(member):
    await member.create_dm()
    await member.dm_channel.send(f"Hi {member.name}, welcome to my Discord server!")


@client.event
async def on_message(message):
    if message.author != client.user and message.content.startswith(CMD_PREFIX):
        await message.channel.send("No commands implemented yet.")


client.run(TOKEN)
