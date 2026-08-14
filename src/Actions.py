"""
Actions of the Clubbot discord bot, to be called by the bot when handling specific events.
"""

import datetime
import logging

import dateutil.parser
import discord
import env

from Common import fetch_ctftime_api_info
from Util import BERLIN_TZ, bannerize_logo, fancy_format_datetime

log = logging.getLogger(__name__)


async def handle_ctftime_reaction(payload, guild):
    # NOTE: If the system is abused, could also check if user is organizer before doing any of the following

    # Determine what message / CTF this is
    ctftime_msg = await guild.get_channel(payload.channel_id).fetch_message(payload.message_id)
    ctftime_embed = ctftime_msg.embeds[0]
    ctftime_url = ctftime_embed.footer.text.split("\n")[-1]

    log.info(f"Received flag reaction on ctftime element {ctftime_url}")

    # Gain necessary CTF info for creating the event
    ctftime_api_info = fetch_ctftime_api_info(ctftime_url)

    title = ctftime_api_info["title"]
    start_time = dateutil.parser.isoparse(ctftime_api_info["start"])
    end_time = dateutil.parser.isoparse(ctftime_api_info["finish"])

    ctf_website = ctftime_api_info["url"]
    event_desc = ctftime_api_info["description"]
    msglink = (
        f"https://discord.com/channels/{payload.guild_id}/{payload.channel_id}/{payload.message_id}"
    )
    description = (
        f"Official Website: {ctf_website} || See {msglink} for more information.\n---\n{event_desc}"
    )
    if len(description) > 999:
        description = description[: 999 - len(" [...]")]  # Must be at most 1000 chars in length
        description += " [....]"
    logo = ctftime_api_info["logo"]

    # Create a text channel for the CTF
    #             new_channel_name = as_kebab_case(title)
    #             existing_channel = discord.utils.get(guild.channels, name=new_channel_name)
    #             if existing_channel:
    #                 log.info(
    #                     "A flag-reaction was given, but a fitting ctf channel already seems to exist. Returning."
    #                 )
    #                 return
    #
    #             tournament_channel = await guild.create_text_channel(
    #                 new_channel_name,
    #                 category=guild.get_channel(CTF_CATEGORY_ID),
    #             )
    #             location = f"https://discord.com/channels/{payload.guild_id}/{tournament_channel.id}"

    # Create an Event
    if logo:
        edited_logodata = bannerize_logo(logo)
        event = await guild.create_scheduled_event(
            name=title,
            start_time=start_time,
            end_time=end_time,
            image=edited_logodata,
            # location=location,
            location="BTU CTF Club",
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
            # location=location,
            location="BTU CTF Club",
            entity_type=discord.EntityType.external,
            description=description,
            # "guild_only" is actually the only option it gives us.. Maybe that will
            # change in the future.
            privacy_level=discord.PrivacyLevel.guild_only,
        )

    # Post an initial message in the text channel, and the event in the upcoming
    #             event_link = f"https://discord.com/events/{payload.guild_id}/{event.id}"
    #             # CTFs channel
    #             await tournament_channel.send(event_link)
    #             await guild.get_channel(UPCOMING_CTFS_CHANNEL_ID).send(event_link)


async def handle_news_reaction(payload, guild, reacted_on_msg):
    reacted_on_embed = reacted_on_msg.embeds[0]
    log.info(
        f"Received reaction on news article '{reacted_on_embed.title}' by user ID {payload.user_id}"
    )

    # Try to find this message embed already posted in the curated channel
    curated_channel = guild.get_channel(env.CURATED_NEWS_CHANNEL)
    msg = None
    async for m in curated_channel.history(limit=200):
        if len(m.embeds) != 0:
            embed = m.embeds[0]
            if all(
                [
                    embed.title == reacted_on_embed.title,
                    embed.url == reacted_on_embed.url,
                    embed.description == reacted_on_embed.description,
                    embed.footer == reacted_on_embed.footer,
                ]
            ):
                # Same embed!
                msg = m
                break

    # If it wasn't found, post the embed into the channel
    if not msg:
        log.info(f"Posting '{reacted_on_embed.title}' to curated channel")
        msg = await curated_channel.send(embed=reacted_on_embed)
    else:
        log.info(f"Article '{reacted_on_embed.title}' already exists in curated channel")

    # Add the specified reaction
    await msg.add_reaction(payload.emoji)


async def handle_ctftime_role_react_add(payload, guild):
    member = guild.get_member(payload.user_id)
    if member is None:
        # Fallback: fetch member if not cached
        try:
            member = await guild.fetch_member(payload.user_id)
        except:
            return

    role = guild.get_role(env.CTFTIME_ROLE_ID)
    if role is None:
        log.error(f"@ctftime role ID {env.CTFTIME_ROLE_ID} not found")
        return

    if role not in member.roles:
        try:
            await member.add_roles(role, reason="Opt-in via reaction")
            log.info(f"Added @{role.name} role to {member.display_name}")
        except Exception:
            log.exception(f"Failed to add role {role.name} to {member.display_name}")


async def handle_ctftime_role_react_remove(payload, guild):
    member = guild.get_member(payload.user_id)
    if member is None:
        # Fallback: fetch member if not cached
        try:
            member = await guild.fetch_member(payload.user_id)
        except:
            return

    role = guild.get_role(env.CTFTIME_ROLE_ID)
    if role is None:
        log.error(f"@ctftime role ID {env.CTFTIME_ROLE_ID} not found")
        return

    if role in member.roles:
        try:
            await member.remove_roles(role, reason="Opt-out via reaction removal")
            log.info(f"Removed @{role.name} role from {member.display_name}")
        except Exception:
            log.exception(f"Failed to remove role {role.name} from {member.display_name}")


async def handle_intel_role_react_add(payload, guild):
    member = guild.get_member(payload.user_id)
    if member is None:
        # Fallback: fetch member if not cached
        try:
            member = await guild.fetch_member(payload.user_id)
        except:
            return

    role = guild.get_role(env.INTEL_ROLE_ID)
    if role is None:
        log.error(f"@intel role ID {env.INTEL_ROLE_ID} not found")
        return

    if role not in member.roles:
        try:
            await member.add_roles(role, reason="Opt-in via reaction")
            log.info(f"Added @{role.name} role to {member.display_name}")
        except Exception:
            log.exception(f"Failed to add role {role.name} to {member.display_name}")


async def handle_intel_role_react_remove(payload, guild):
    member = guild.get_member(payload.user_id)
    if member is None:
        # Fallback: fetch member if not cached
        try:
            member = await guild.fetch_member(payload.user_id)
        except:
            return

    role = guild.get_role(env.INTEL_ROLE_ID)
    if role is None:
        log.error(f"@intel role ID {env.INTEL_ROLE_ID} not found")
        return

    if role in member.roles:
        try:
            await member.remove_roles(role, reason="Opt-out via reaction removal")
            log.info(f"Removed @{role.name} role from {member.display_name}")
        except Exception:
            log.exception(f"Failed to remove role {role.name} from {member.display_name}")


async def upcoming_ctfs_command(interaction: discord.Interaction, feed):
    """
    Handles the /upcomingctfs command.

    Args:
        interaction: The interaction object
        feed: the CTFTimeFeed instance.
    """
    try:
        ctfs = await feed.get_upcoming_ctfs(days=21)
    except Exception as e:
        log.exception("Failed to fetch upcoming CTFs")
        await interaction.response.send_message(
            "Could not retrieve CTF data. Try again later.", ephemeral=True
        )
        return

    if not ctfs:
        await interaction.response.send_message(
            "No upcoming CTFs found in the next 4 weeks.", ephemeral=True
        )
        return

    now = datetime.datetime.now(datetime.timezone.utc)
    week_later = now + datetime.timedelta(days=7)

    # Split into three categories
    running = [c for c in ctfs if c["start_dt"] <= now <= c["end_dt"]]
    imminent = [c for c in ctfs if c["start_dt"] > now and c["start_dt"] <= week_later]
    upcoming = [
        c
        for c in ctfs
        if c["start_dt"] > week_later and c["start_dt"] <= now + datetime.timedelta(days=21)
    ]

    # Build an embed
    embed = discord.Embed(
        title="🚩 Upcoming CTFs (next 3 weeks)",
        color=discord.Color.blue(),
        timestamp=now,
    )

    def format_ctf_list(ctf_list, max_items=5):
        if not ctf_list:
            return "None"
        lines = []
        for i, c in enumerate(ctf_list):
            if i >= max_items:
                lines.append(f"... and {len(ctf_list) - max_items} more")
                break
            start_berlin = c["start_dt"].astimezone(BERLIN_TZ)
            date_str = fancy_format_datetime(start_berlin)
            # Compact format: bullet, title, date, and a clickable details link
            lines.append(f"• **{c['title']}** – {date_str} – ([Details]({c['msg_url']}))")
        return "\n".join(lines)

    # Build description – skip empty sections
    parts = []
    if running:
        parts.append(f"🔴 **Running**\n\n{format_ctf_list(running)}")
    if imminent:
        parts.append(f"🚀 **Imminent (next 7 days)**\n\n{format_ctf_list(imminent)}")
    if upcoming:
        parts.append(f"📆 **Upcoming (next 21 days)**\n\n{format_ctf_list(upcoming)}")
    description = "\n\n".join(parts)

    embed.description = description

    await interaction.response.send_message(embed=embed, ephemeral=True)
