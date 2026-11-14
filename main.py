import asyncio
import os
import discord
from discord.ext import commands

# Set up intents
intents = discord.Intents.default()
intents.guilds = True
intents.voice_states = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ================= CONFIGURATION =================
GOON_ROOM_CATEGORY_ID = 1571061360349937764  # Both Camera & Mic required
MOVIE_ROOM_CATEGORY_ID = 1571061443460333729  # Only Camera required
MUSIC_ROOM_CATEGORY_ID = 1571061845475721306  # Only Microphone required

WELCOME_CHANNEL_ID = 1571060347060625508  # Channel to kick violators into

GRACE_PERIOD = 300  # 5 minutes (in seconds)
# =================================================

# Dictionary to track active timers: {user_id: asyncio.Task}
tracking_tasks = {}


@bot.event
async def on_ready():
  print(f"[{bot.user.name}] is online and hunting!")
  print("Monitoring Steam Room categories with custom warning prompts...")


@bot.event
async def on_voice_state_update(
    member: discord.Member,
    before: discord.VoiceState,
    after: discord.VoiceState,
):
  if member.bot:
    return

  # Check which category the user is currently in (if any)
  current_category_id = (
      after.channel.category.id
      if after.channel and after.channel.category
      else None
  )

  is_goon = current_category_id == GOON_ROOM_CATEGORY_ID
  is_movie = current_category_id == MOVIE_ROOM_CATEGORY_ID
  is_music = current_category_id == MUSIC_ROOM_CATEGORY_ID

  # If they are in one of our target categories
  if is_goon or is_movie or is_music:
    has_mic = not after.self_mute and not after.deaf
    has_cam = after.self_video

    compliant = False
    if is_goon:
      compliant = has_mic and has_cam
    elif is_movie:
      compliant = has_cam
    elif is_music:
      compliant = has_mic

    if compliant:
      if member.id in tracking_tasks:
        tracking_tasks[member.id].cancel()
        del tracking_tasks[member.id]
      return

    # If not compliant, send the warning prompt and start/keep the timer
    if member.id not in tracking_tasks:
      await send_warning_prompt(member, current_category_id)
      tracking_tasks[member.id] = asyncio.create_task(
          enforce_rules(member, current_category_id)
      )

  # If they left the target categories entirely, cancel their timer
  else:
    if member.id in tracking_tasks:
      tracking_tasks[member.id].cancel()
      del tracking_tasks[member.id]


async def send_warning_prompt(member: discord.Member, category_id: int):
  """Sends the specific warning message depending on the category requirements."""
  if category_id == GOON_ROOM_CATEGORY_ID:
    msg = (
        "🚨 **bad boi hunter:** You need to open your Camera and Microphone to"
        " stay in this channel!"
    )
  elif category_id == MOVIE_ROOM_CATEGORY_ID:
    msg = (
        "🚨 **bad boi hunter:** You need to open your Camera to stay in this"
        " channel!"
    )
  elif category_id == MUSIC_ROOM_CATEGORY_ID:
    msg = (
        "🚨 **bad boi hunter:** You need to open your Microphone to stay in"
        " this channel!"
    )
  else:
    return

  try:
    await member.send(msg)
  except discord.Forbidden:
    pass  # User has DMs closed; fails silently without crashing the script


async def enforce_rules(member: discord.Member, target_category_id: int):
  try:
    # Wait for the 5-minute grace period
    await asyncio.sleep(GRACE_PERIOD)

    # Re-verify their state after 5 minutes
    if (
        member.voice
        and member.voice.channel
        and member.voice.channel.category
        and member.voice.channel.category.id == target_category_id
    ):
      has_mic = not member.voice.self_mute and not member.voice.deaf
      has_cam = member.voice.self_video

      is_goon = target_category_id == GOON_ROOM_CATEGORY_ID
      is_movie = target_category_id == MOVIE_ROOM_CATEGORY_ID
      is_music = target_category_id == MUSIC_ROOM_CATEGORY_ID

      still_violating = False
      if is_goon and not (has_mic and has_cam):
        still_violating = True
      elif is_movie and not has_cam:
        still_violating = True
      elif is_music and not has_mic:
        still_violating = True

      if still_violating:
        guild = member.guild
        welcome_channel = guild.get_channel(WELCOME_CHANNEL_ID)

        # Move them out of the voice channel and into the Welcome channel
        await member.move_to(
            welcome_channel,
            reason=(
                "Failed to meet category media requirements within 5 minutes."
            ),
        )

        try:
          await member.send(
              "⚠️ **bad boi hunter:** You were kicked out of the voice channel"
              " because the requirements were not met in time."
          )
        except discord.Forbidden:
          pass

  except asyncio.CancelledError:
    pass  # Timer canceled because they satisfied requirements or left
  finally:
    if member.id in tracking_tasks:
      del tracking_tasks[member.id]


# Run the bot securely using the environment variable
bot.run(os.getenv("DISCORD_TOKEN"))