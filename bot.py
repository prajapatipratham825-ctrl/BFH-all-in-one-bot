import discord
from discord.ext import commands, tasks
import os
import asyncio
from datetime import datetime, timedelta
from openai import OpenAI
from dotenv import load_dotenv
from discord import app_commands

# -------------------- LOAD SECRETS --------------------
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)  # Keep prefix for any legacy, but we'll use slash

# -------------------- DATA STORAGE --------------------
warnings = {}      # {guild_id: {user_id: count}}
reminders = []     # list of tuples (user_id, message, datetime)
notes = {}         # {user_id: [note1, note2]}

# -------------------- EVENTS --------------------
@bot.event
async def on_ready():
    print(f"Bot connected as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(e)
    reminder_task.start()

@bot.event
async def on_member_join(member):
    # Auto role
    role_name = "Member"
    role = discord.utils.get(member.guild.roles, name=role_name)
    if role:
        await member.add_roles(role)
    # Welcome message
    channel = member.guild.system_channel
    if channel:
        await channel.send(f"Welcome {member.mention}! Enjoy your stay!")

# -------------------- MODERATION --------------------
@bot.tree.command(name="kick", description="Kick a member from the server")
@app_commands.describe(member="The member to kick", reason="Reason for kicking")
@app_commands.checks.has_permissions(kick_members=True)
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    await member.kick(reason=reason)
    await interaction.response.send_message(f"{member} has been kicked. Reason: {reason}")

@bot.tree.command(name="ban", description="Ban a member from the server")
@app_commands.describe(member="The member to ban", reason="Reason for banning")
@app_commands.checks.has_permissions(ban_members=True)
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    await member.ban(reason=reason)
    await interaction.response.send_message(f"{member} has been banned. Reason: {reason}")

@bot.tree.command(name="mute", description="Mute a member for a duration")
@app_commands.describe(member="The member to mute", duration="Duration in minutes (default 5)")
@app_commands.checks.has_permissions(manage_roles=True)
async def mute(interaction: discord.Interaction, member: discord.Member, duration: int = 5):
    role = discord.utils.get(interaction.guild.roles, name="Muted")
    if not role:
        role = await interaction.guild.create_role(name="Muted")
        for ch in interaction.guild.channels:
            await ch.set_permissions(role, send_messages=False)
    await member.add_roles(role)
    await interaction.response.send_message(f"{member} has been muted for {duration} minutes.")
    await asyncio.sleep(duration*60)
    await member.remove_roles(role)
    # Note: Can't send follow-up after interaction times out, but for demo

@bot.tree.command(name="warn", description="Warn a member")
@app_commands.describe(member="The member to warn", reason="Reason for warning")
@app_commands.checks.has_permissions(manage_messages=True)
async def warn(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    guild_warnings = warnings.setdefault(interaction.guild.id, {})
    guild_warnings[member.id] = guild_warnings.get(member.id, 0) + 1
    await interaction.response.send_message(f"{member} has been warned. Total warnings: {guild_warnings[member.id]}\nReason: {reason}")

# -------------------- UTILITY --------------------
@bot.tree.command(name="userinfo", description="Get info about a user")
@app_commands.describe(member="The user to get info for (optional)")
async def userinfo(interaction: discord.Interaction, member: discord.Member = None):
    member = member or interaction.user
    embed = discord.Embed(title=f"{member}'s Info", color=discord.Color.blue())
    embed.add_field(name="Name", value=member.name)
    embed.add_field(name="ID", value=member.id)
    embed.add_field(name="Status", value=str(member.status))
    embed.add_field(name="Joined", value=member.joined_at.strftime("%Y-%m-%d %H:%M"))
    embed.add_field(name="Top Role", value=member.top_role.name if member.top_role else "None")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="serverinfo", description="Get info about the server")
async def serverinfo(interaction: discord.Interaction):
    g = interaction.guild
    embed = discord.Embed(title=f"{g.name} Info", color=discord.Color.green())
    embed.add_field(name="ID", value=g.id)
    embed.add_field(name="Owner", value=g.owner.name)
    embed.add_field(name="Member Count", value=g.member_count)
    embed.add_field(name="Created At", value=g.created_at.strftime("%Y-%m-%d"))
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="remind", description="Set a reminder")
@app_commands.describe(time="Time in minutes", message="Reminder message")
async def remind(interaction: discord.Interaction, time: int, message: str):
    remind_time = datetime.now() + timedelta(minutes=time)
    reminders.append((interaction.user.id, message, remind_time))
    await interaction.response.send_message(f"Okay {interaction.user.mention}, I will remind you in {time} minutes: {message}")

@tasks.loop(seconds=30)
async def reminder_task():
    now = datetime.now()
    for r in reminders.copy():
        user_id, message, remind_time = r
        if now >= remind_time:
            user = bot.get_user(user_id)
            if user:
                await user.send(f"⏰ Reminder: {message}")
            reminders.remove(r)

@bot.tree.command(name="addnote", description="Add a personal note")
@app_commands.describe(note="The note to add")
async def addnote(interaction: discord.Interaction, note: str):
    user_notes = notes.setdefault(interaction.user.id, [])
    user_notes.append(note)
    await interaction.response.send_message(f"Note added! You now have {len(user_notes)} notes.")

@bot.tree.command(name="noteslist", description="List your personal notes")
async def noteslist(interaction: discord.Interaction):
    user_notes = notes.get(interaction.user.id, [])
    if not user_notes:
        await interaction.response.send_message("You have no notes.")
    else:
        msg = "\n".join([f"{i+1}. {n}" for i,n in enumerate(user_notes)])
        await interaction.response.send_message(f"Your notes:\n{msg}")

@bot.tree.command(name="poll", description="Create a poll")
@app_commands.describe(question="The poll question", options="Options separated by commas")
async def poll(interaction: discord.Interaction, question: str, options: str):
    opts = [opt.strip() for opt in options.split(",")]
    if len(opts) < 2:
        await interaction.response.send_message("You need at least 2 options.")
        return
    reactions = ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣"]
    embed = discord.Embed(title="📊 " + question, color=discord.Color.purple())
    for i,opt in enumerate(opts):
        embed.add_field(name=f"{reactions[i]}", value=opt, inline=False)
    msg = await interaction.channel.send(embed=embed)
    for i in range(len(opts)):
        await msg.add_reaction(reactions[i])
    await interaction.response.send_message("Poll created!", ephemeral=True)

# -------------------- AI CHAT --------------------
@bot.tree.command(name="chat", description="Chat with AI")
@app_commands.describe(prompt="Your message to the AI")
async def chat(interaction: discord.Interaction, prompt: str):
    await interaction.response.defer()
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200
        )
        await interaction.followup.send(response.choices[0].message.content)
    except Exception as e:
        await interaction.followup.send(f"Error: {e}")

# -------------------- ERROR HANDLING --------------------
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("❌ You don't have permission to run this command.", ephemeral=True)
    elif isinstance(error, app_commands.MissingRequiredArgument):
        await interaction.response.send_message("❌ Missing arguments for this command.", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ Error: {error}", ephemeral=True)

# -------------------- RUN BOT --------------------
bot.run(TOKEN)