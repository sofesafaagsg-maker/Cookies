# main.py
import os
import json
from datetime import datetime, timedelta
from io import BytesIO
from typing import List

import discord
from discord.ext import commands, tasks
from discord import app_commands
from dotenv import load_dotenv
import motor.motor_asyncio

import state
import database as db
import utils

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
if TOKEN is None:
    raise ValueError("DISCORD_TOKEN is missing from .env file")

MONGODB_URI = os.getenv("MONGODB_URI")
if MONGODB_URI is None:
    raise ValueError("MONGODB_URI is missing from .env file")

# MongoDB setup
print("[LOG] Creating MongoDB client...")
state.mongo_client = motor.motor_asyncio.AsyncIOMotorClient(MONGODB_URI)
state.db = state.mongo_client["work_bot"]
state.collection = state.db["records"]          # unified collection (records + works)
state.settings_collection = state.db["settings"]
state.audit_collection = state.db["audit_log"]
state.stats_collection = state.db["stats"]

# Bot setup
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
bot.remove_command("help")  # disable default help
state.bot = bot

# ----------------------------------------------------------------------
# Events & checks
# ----------------------------------------------------------------------
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.CheckFailure):
        return
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ ما عندك صلاحية تستخدم هذا الأمر.")
        return
    await ctx.send(f"⚠️ صار خطأ: `{error}`")

@bot.event
async def on_ready():
    global SETTINGS
    print(f"[LOG] Logged in as {bot.user}")
    state.SETTINGS = await db.load_settings()
    utils.rebuild_prices()
    print(f"[LOG] Settings loaded: allowed_channels={state.SETTINGS.get('allowed_channels')}, "
          f"currency={state.SETTINGS.get('currency')}")
    try:
        await state.mongo_client.admin.command('ping')
        print("[LOG] MongoDB connection successful!")
    except Exception as e:
        print(f"[ERROR] MongoDB connection failed: {e}")
    await bot.tree.sync()
    print("[LOG] Slash commands synced")
    await db.update_stats()
    daily_backup.start()
    update_stats_task.start()
    payment_reminder_task.start()

@bot.check
async def only_allowed_channel(ctx):
    if ctx.author.bot:
        return False
    if ctx.channel.name in state.SETTINGS.get("allowed_channels", []):
        return True
    channels_str = ", ".join([f"#{ch}" for ch in state.SETTINGS.get("allowed_channels", [])])
    await ctx.send(f"❌ استخدم أوامر البوت فقط في أحد الرومات: {channels_str}.")
    return False

def is_admin(interaction: discord.Interaction) -> bool:
    return interaction.user.guild_permissions.manage_messages

# ----------------------------------------------------------------------
# Tasks
# ----------------------------------------------------------------------
@tasks.loop(hours=24)
async def daily_backup():
    backup_channel_id = state.SETTINGS.get("daily_backup_channel_id")
    if not backup_channel_id:
        return
    channel = bot.get_channel(backup_channel_id)
    if not channel:
        return
    records = await db.load_records()
    data = json.dumps(records, ensure_ascii=False, indent=2)
    file = discord.File(BytesIO(data.encode('utf-8')), filename=f"backup_{datetime.utcnow().date()}.json")
    await channel.send(f"📦 نسخة احتياطية يومية - {datetime.utcnow().date()}", file=file)

@tasks.loop(hours=1)
async def update_stats_task():
    await db.update_stats()

@tasks.loop(minutes=10)
async def payment_reminder_task():
    await check_payment_reminder()

async def check_payment_reminder():
    """Check if it's time to send payment reminders."""
    payment_day = state.SETTINGS.get("payment_day")
    if not payment_day:
        return
    now = datetime.utcnow()
    payment_hour = state.SETTINGS.get("payment_hour", 0)
    # Check if today is the payment day
    today = now.date()
    payment_date = today.replace(day=min(payment_day, 28))  # avoid month issues
    if payment_day > 28:
        payment_date = today.replace(day=28)  # safe fallback

    # 24 hours before reminder
    reminder_date = payment_date - timedelta(days=1)
    if now.date() == reminder_date and now.hour >= payment_hour and not state.SETTINGS.get("payment_reminder_24h_sent"):
        await send_payment_reminder(24)
        state.SETTINGS["payment_reminder_24h_sent"] = True
        await db.save_settings(state.SETTINGS)
    # Payment day reminder
    elif now.date() == payment_date and now.hour >= payment_hour and not state.SETTINGS.get("payment_day_sent"):
        await send_payment_reminder(0)
        state.SETTINGS["payment_day_sent"] = True
        await db.save_settings(state.SETTINGS)
    # Reset flags when day passes
    elif now.date() > payment_date:
        state.SETTINGS["payment_reminder_24h_sent"] = False
        state.SETTINGS["payment_day_sent"] = False
        await db.save_settings(state.SETTINGS)

async def send_payment_reminder(hours_before):
    """Send a payment reminder message."""
    notify_channel_id = state.SETTINGS.get("notify_channel_id") or state.SETTINGS.get("daily_backup_channel_id")
    if not notify_channel_id:
        return
    channel = bot.get_channel(notify_channel_id)
    if not channel:
        return
    # Gather monthly totals
    records = await db.load_records()
    month_start = datetime.utcnow().replace(day=1)
    totals = {}
    for user_id, entries in records.items():
        user_total = 0
        for e in entries:
            try:
                entry_date = datetime.fromisoformat(e["timestamp"])
                if entry_date >= month_start:
                    user_total += e.get("total", 0)
            except:
                pass
        if user_total != 0:
            totals[user_id] = user_total
    total_all = sum(totals.values())
    embed = discord.Embed(title="🔔 تذكير بموعد الدفع", color=discord.Color.orange())
    if hours_before == 24:
        embed.description = "⏰ تبقى 24 ساعة على موعد الدفع الشهري"
    else:
        embed.description = "📅 اليوم هو موعد الدفع الشهري"
    embed.add_field(name="إجمالي المبلغ المستحق", value=f"{state.SETTINGS.get('currency', '$')}{total_all:.2f}", inline=False)
    top5 = sorted(totals.items(), key=lambda x: x[1], reverse=True)[:5]
    top_str = "\n".join([f"<@{uid}>: {state.SETTINGS.get('currency', '$')}{amt:.2f}" for uid, amt in top5])
    embed.add_field(name="أعلى 5 مستحقات", value=top_str, inline=False)
    await channel.send(embed=embed)

# ----------------------------------------------------------------------
# Autocomplete helper (must be defined before any command that uses it)
# ----------------------------------------------------------------------
async def work_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    works = await db.load_works()
    choices = []
    for w in works:
        if current.lower() in w["name"].lower():
            choices.append(app_commands.Choice(name=w["name"][:100], value=w["name"]))
    return choices[:25]

async def specialty_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    """Autocomplete for specialty names (showing active ones)."""
    choices = []
    for name in state.PRICES.keys():
        display_name = name.replace('_', ' ').title()
        if current.lower() in display_name.lower():
            choices.append(app_commands.Choice(name=display_name[:100], value=name))
    return choices[:25]

# ----------------------------------------------------------------------
# Init & run
# ----------------------------------------------------------------------
async def init_prices():
    settings = await db.load_settings()
    if "specialties" not in settings:
        settings["specialties"] = {
            "تحرير": {"price": 0.50, "active": True, "last_modified": datetime.utcnow().isoformat()},
            "ترجمة_كوري": {"price": 0.75, "active": True, "last_modified": datetime.utcnow().isoformat()},
            "ترجمة_انجليزي": {"price": 0.60, "active": True, "last_modified": datetime.utcnow().isoformat()},
            "تبييض": {"price": 0.25, "active": True, "last_modified": datetime.utcnow().isoformat()},
            "سحب": {"price": 0.01, "active": True, "last_modified": datetime.utcnow().isoformat()},
            "دمج": {"price": 0.01, "active": True, "last_modified": datetime.utcnow().isoformat()},
            "رفع": {"price": 0.005, "active": True, "last_modified": datetime.utcnow().isoformat()},
        }
        await db.save_settings(settings)

async def custom_setup():
    await init_prices()

bot.setup_hook = custom_setup

async def main():
    await bot.load_extension("cogs.member_commands")
    await bot.load_extension("cogs.admin_commands")
    await bot.start(TOKEN)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())