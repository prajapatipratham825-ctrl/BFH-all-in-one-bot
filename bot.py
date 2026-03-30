import discord
from discord.ext import commands, tasks
import os
import asyncio
from datetime import datetime, timedelta
from openai import OpenAI
from dotenv import load_dotenv

# -------------------- LOAD SECRETS --------------------
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# -------------------- DATA STORAGE --------------------
warnings = {}      # {guild_id: {user_id: count}}
reminders = []     # list of tuples (user_id, message, datetime)
notes = {}         # {user_id: [note1, note2]}

# -------------------- EVENTS --------------------
@bot.event
async def on_ready():
    print(f"Bot connected as {bot.user}")
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
@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason=None):
    await member.kick(reason=reason)
    await ctx.send(f"{member} has been kicked. Reason: {reason}")

@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason=None):
    await member.ban(reason=reason)
    await ctx.send(f"{member} has been banned. Reason: {reason}")

@bot.command()
@commands.has_permissions(manage_roles=True)
async def mute(ctx, member: discord.Member, duration: int = 5):
    role = discord.utils.get(ctx.guild.roles, name="Muted")
    if not role:
        role = await ctx.guild.create_role(name="Muted")
        for ch in ctx.guild.channels:
            await ch.set_permissions(role, send_messages=False)
    await member.add_roles(role)
    await ctx.send(f"{member} has been muted for {duration} minutes.")
    await asyncio.sleep(duration*60)
    await member.remove_roles(role)
    await ctx.send(f"{member} has been unmuted.")

@bot.command()
@commands.has_permissions(manage_messages=True)
async def warn(ctx, member: discord.Member, *, reason="No reason provided"):
    guild_warnings = warnings.setdefault(ctx.guild.id, {})
    guild_warnings[member.id] = guild_warnings.get(member.id, 0) + 1
    await ctx.send(f"{member} has been warned. Total warnings: {guild_warnings[member.id]}\nReason: {reason}")

# -------------------- UTILITY --------------------
@bot.command()
async def userinfo(ctx, member: discord.Member = None):
    member = member or ctx.author
    embed = discord.Embed(title=f"{member}'s Info", color=discord.Color.blue())
    embed.add_field(name="Name", value=member.name)
    embed.add_field(name="ID", value=member.id)
    embed.add_field(name="Status", value=member.status)
    embed.add_field(name="Joined", value=member.joined_at.strftime("%Y-%m-%d %H:%M"))
    embed.add_field(name="Top Role", value=member.top_role)
    await ctx.send(embed=embed)

@bot.command()
async def serverinfo(ctx):
    g = ctx.guild
    embed = discord.Embed(title=f"{g.name} Info", color=discord.Color.green())
    embed.add_field(name="ID", value=g.id)
    embed.add_field(name="Owner", value=g.owner)
    embed.add_field(name="Member Count", value=g.member_count)
    embed.add_field(name="Created At", value=g.created_at.strftime("%Y-%m-%d"))
    await ctx.send(embed=embed)

@bot.command()
async def remind(ctx, time: int, *, message):
    remind_time = datetime.now() + timedelta(minutes=time)
    reminders.append((ctx.author.id, message, remind_time))
    await ctx.send(f"Okay {ctx.author.mention}, I will remind you in {time} minutes: {message}")

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

@bot.command()
async def addnote(ctx, *, note):
    user_notes = notes.setdefault(ctx.author.id, [])
    user_notes.append(note)
    await ctx.send(f"Note added! You now have {len(user_notes)} notes.")

@bot.command()
async def noteslist(ctx):
    user_notes = notes.get(ctx.author.id, [])
    if not user_notes:
        await ctx.send("You have no notes.")
    else:
        msg = "\n".join([f"{i+1}. {n}" for i,n in enumerate(user_notes)])
        await ctx.send(f"Your notes:\n{msg}")

@bot.command()
async def poll(ctx, question, *options):
    if len(options) < 2:
        await ctx.send("You need at least 2 options.")
        return
    reactions = ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣"]
    embed = discord.Embed(title="📊 " + question, color=discord.Color.purple())
    for i,opt in enumerate(options):
        embed.add_field(name=f"{reactions[i]}", value=opt, inline=False)
    msg = await ctx.send(embed=embed)
    for i in range(len(options)):
        await msg.add_reaction(reactions[i])

# -------------------- AI CHAT --------------------
@bot.command()
async def chat(ctx, *, prompt):
    await ctx.trigger_typing()
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200
        )
        await ctx.send(response.choices[0].message.content)
    except Exception as e:
        await ctx.send(f"Error: {e}")

# -------------------- ERROR HANDLING --------------------
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You don't have permission to run this command.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("❌ Missing arguments for this command.")
    elif isinstance(error, commands.CommandNotFound):
        await ctx.send("❌ Command not found.")
    else:
        await ctx.send(f"❌ Error: {error}")

# -------------------- RUN BOT --------------------
bot.run(TOKEN)