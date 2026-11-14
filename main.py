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

TAMBAYAN_CHANNEL_ID = (
    1571083268445704262  # Replace with Tambayan Voice Channel ID
)

WARNING_DELAY = 60  # 1 minute before sending the warning DM (in seconds)
GRACE_PERIOD = 300  # 5 minutes total grace period (in seconds)
# =================================================

# Dictionary to track active timers: {user_id: asyncio.Task}
tracking_tasks = {}


@bot.event
async def on_ready():
  print(f"[{bot.user.name}] is online and hunting!")
  print("Monitoring Steam Room categories with custom warning prompts...")


def is_violating(member: discord.Member, target_category_id: int) -> bool:
  """Helper function to check if the member is currently violating category rules."""
  if (
      not member.voice
      or not member.voice.channel
      or not member.voice.channel.category
      or member.voice.channel.category.id != target_category_id
  ):
    return False

  has_mic = not member.voice.self_mute and not member.voice.deaf
  has_cam = member.voice.self_video

  if target_category_id == GOON_ROOM_CATEGORY_ID:
    return not (has_mic and has_cam)
  elif target_category_id == MOVIE_ROOM_CATEGORY_ID:
    return not has_cam
  elif target_category_id == MUSIC_ROOM_CATEGORY_ID:
    return not has_mic

  return False


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

  is_target = current_category_id in (
      GOON_ROOM_CATEGORY_ID,
      MOVIE_ROOM_CATEGORY_ID,
      MUSIC_ROOM_CATEGORY_ID,
  )

  if is_target:
    if not is_violating(member, current_category_id):
      if member.id in tracking_tasks:
        tracking_tasks[member.id].cancel()
        del tracking_tasks[member.id]
      return

    # Start the 5-minute enforcement timer if not already running
    if member.id not in tracking_tasks:
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
        " stay in this channel! You have 4 minutes left."
    )
  elif category_id == MOVIE_ROOM_CATEGORY_ID:
    msg = (
        "🚨 **bad boi hunter:** You need to open your Camera to stay in this"
        " channel! You have 4 minutes left."
    )
  elif category_id == MUSIC_ROOM_CATEGORY_ID:
    msg = (
        "🚨 **bad boi hunter:** You need to open your Microphone to stay in"
        " this channel! You have 4 minutes left."
    )
  else:
    return

  try:
    await member.send(msg)
  except discord.Forbidden:
    pass  # User has DMs closed; fails silently without crashing the script


async def enforce_rules(member: discord.Member, target_category_id: int):
  try:
    # Step 1: Wait 1 minute before sending the warning DM
    await asyncio.sleep(WARNING_DELAY)

    if is_violating(member, target_category_id):
      await send_warning_prompt(member, target_category_id)
    else:
      return

    # Step 2: Wait the remaining 4 minutes
    await asyncio.sleep(GRACE_PERIOD - WARNING_DELAY)

    # Step 3: Re-verify after the full 5 minutes and move to Tambayan if still violating
    if is_violating(member, target_category_id):
      guild = member.guild
      tambayan_channel = guild.get_channel(TAMBAYAN_CHANNEL_ID)

      if not isinstance(tambayan_channel, discord.VoiceChannel):
        print(
            "[ERROR] TAMBAYAN_CHANNEL_ID is invalid or is not a Voice Channel."
        )
        return

      try:
        await member.move_to(
            tambayan_channel,
            reason=(
                "Failed to meet category media requirements within 5 minutes."
            ),
        )
        try:
          await member.send(
              "⚠️ **bad boi hunter:** You were moved to **Tambayan** because"
              " the voice channel requirements were not met in time."
          )
        except discord.Forbidden:
          pass
      except discord.Forbidden:
        print(
            f"[ERROR] Missing 'Move Members' permission or {member.name} has a"
            " higher role / is Server Owner."
        )
      except discord.HTTPException as e:
        print(f"[ERROR] Failed to move {member.name}: {e}")

  except asyncio.CancelledError:
    pass  # Timer canceled because they satisfied requirements or left
  finally:
    if member.id in tracking_tasks:
      del tracking_tasks[member.id]


# Run the bot securely using the environment variable
bot.run(os.getenv("DISCORD_TOKEN"))
