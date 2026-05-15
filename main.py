import os
import json
from pathlib import Path

import discord
from discord.ext import commands
from dotenv import load_dotenv
import motor.motor_asyncio

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
if TOKEN is None:
    raise ValueError("DISCORD_TOKEN is missing from .env file")

MONGODB_URI = os.getenv("MONGODB_URI")
if MONGODB_URI is None:
    raise ValueError("MONGODB_URI is missing from .env file")

# Default allowed channels (will be loaded from DB)
DEFAULT_ALLOWED_CHANNELS = ["تسجيــــــــل-اعمال〢💵"]

PRICES = {
    "تحرير": 0.50,
    "ترجمة": 0.50,
    "تبييض": 0.25,
}

# MongoDB setup
print("[LOG] Creating MongoDB client...")
mongo_client = motor.motor_asyncio.AsyncIOMotorClient(MONGODB_URI)
db = mongo_client["work_bot"]
collection = db["records"]
settings_collection = db["settings"]

async def load_records():
    """Load records from MongoDB"""
    print("[LOG] load_records() called - Attempting to fetch data from MongoDB...")
    try:
        doc = await collection.find_one({"_id": "records"})
        if doc and "data" in doc:
            print("[LOG] load_records() - Data found, returning records.")
            return doc["data"]
        else:
            print("[LOG] load_records() - No records found, returning empty dict.")
            return {}
    except Exception as e:
        print(f"[ERROR] load_records() - Failed to fetch data: {e}")
        return {}

async def save_records(records):
    """Save records to MongoDB"""
    print("[LOG] save_records() called - Attempting to save data to MongoDB...")
    try:
        await collection.update_one(
            {"_id": "records"},
            {"$set": {"data": records}},
            upsert=True
        )
        print("[LOG] save_records() - Data saved successfully.")
    except Exception as e:
        print(f"[ERROR] save_records() - Failed to save data: {e}")

async def load_settings():
    """Load settings (allowed channels) from MongoDB"""
    print("[LOG] load_settings() called")
    try:
        doc = await settings_collection.find_one({"_id": "settings"})
        if doc and "allowed_channels" in doc:
            return doc["allowed_channels"]
        else:
            return DEFAULT_ALLOWED_CHANNELS.copy()
    except Exception as e:
        print(f"[ERROR] load_settings() - Failed: {e}")
        return DEFAULT_ALLOWED_CHANNELS.copy()

async def save_settings(allowed_channels):
    """Save settings (allowed channels) to MongoDB"""
    print(f"[LOG] save_settings() called with {allowed_channels}")
    try:
        await settings_collection.update_one(
            {"_id": "settings"},
            {"$set": {"allowed_channels": allowed_channels}},
            upsert=True
        )
        print("[LOG] save_settings() - Settings saved successfully")
    except Exception as e:
        print(f"[ERROR] save_settings() - Failed: {e}")

def parse_fields(text):
    fields = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().lower()
        value = value.strip()
        fields[key] = value
    return fields

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Global variable for allowed channels (will be set in on_ready)
ALLOWED_CHANNELS = []

@bot.event
async def on_ready():
    global ALLOWED_CHANNELS
    print(f"[LOG] Logged in as {bot.user}")
    
    # Load settings from DB
    ALLOWED_CHANNELS = await load_settings()
    print(f"[LOG] Allowed channels loaded: {ALLOWED_CHANNELS}")
    
    # Test MongoDB connection
    print("[LOG] Testing MongoDB connection...")
    try:
        await mongo_client.admin.command('ping')
        print("[LOG] MongoDB connection successful! (ping command succeeded)")
    except Exception as e:
        print(f"[ERROR] MongoDB connection failed: {e}")
    
    # Sync slash commands
    print("[LOG] Syncing slash commands...")
    await bot.tree.sync()
    print("[LOG] Slash commands synced")

@bot.check
async def only_allowed_channel(ctx):
    # Check if current channel name is in the list of allowed channel names
    if ctx.channel.name in ALLOWED_CHANNELS:
        return True
    # Build list of allowed channels for error message (display channel names as #name)
    channels_str = ", ".join([f"#{ch}" for ch in ALLOWED_CHANNELS])
    await ctx.send(f"استخدم أوامر البوت فقط في أحد الرومات: {channels_str}.")
    return False

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        return
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("ما عندك صلاحية تستخدم هذا الأمر.")
        return
    await ctx.send(f"صار خطأ: `{error}`")

# ---------- Helper function to check admin permission for commands that need it ----------
def is_admin(interaction: discord.Interaction) -> bool:
    return interaction.user.guild_permissions.manage_messages

# ---------- Slash and Text command: تحديد_قنوات ----------
# Slash version expects text channel arguments (type discord.TextChannel)
@bot.tree.command(name="تحديد_قنوات", description="تحديد القنوات المسموحة (قناتين كحد أقصى) - للإدارة فقط")
async def set_allowed_channels_slash(
    interaction: discord.Interaction, 
    channel1: discord.TextChannel, 
    channel2: discord.TextChannel = None
):
    if not is_admin(interaction):
        await interaction.response.send_message("ما عندك صلاحية تستخدم هذا الأمر.", ephemeral=True)
        return
    
    # Extract channel names
    channels = [channel1.name]
    if channel2:
        channels.append(channel2.name)
    
    # Remove duplicates and limit to 2
    channels = list(dict.fromkeys(channels))[:2]
    
    # Update global variable and save to DB
    global ALLOWED_CHANNELS
    ALLOWED_CHANNELS = channels
    await save_settings(ALLOWED_CHANNELS)
    
    channels_str = ", ".join([f"#{ch}" for ch in ALLOWED_CHANNELS])
    await interaction.response.send_message(f"✅ تم تحديث القنوات المسموحة إلى: {channels_str}", ephemeral=True)

# Text version: accepts channel mentions or names
@bot.command(name="تحديد_قنوات")
@commands.has_permissions(manage_messages=True)
async def set_allowed_channels_text(ctx, channel1: str, channel2: str = None):
    # Helper to extract channel name from various input formats
    def extract_channel_name(input_str):
        # If input is a channel mention like <#123456789>
        if input_str.startswith('<#') and input_str.endswith('>'):
            channel_id = int(input_str[2:-1])
            channel = ctx.guild.get_channel(channel_id)
            if channel:
                return channel.name
        # If input is a numeric ID
        elif input_str.isdigit():
            channel = ctx.guild.get_channel(int(input_str))
            if channel:
                return channel.name
        # Otherwise assume it's a channel name
        else:
            # Try to find channel by name
            for ch in ctx.guild.channels:
                if ch.name == input_str:
                    return ch.name
        return input_str  # fallback to original string
    
    ch1_name = extract_channel_name(channel1)
    ch2_name = extract_channel_name(channel2) if channel2 else None
    
    channels = [ch1_name]
    if ch2_name:
        channels.append(ch2_name)
    
    # Remove duplicates and limit to 2
    channels = list(dict.fromkeys(channels))[:2]
    
    global ALLOWED_CHANNELS
    ALLOWED_CHANNELS = channels
    await save_settings(ALLOWED_CHANNELS)
    
    channels_str = ", ".join([f"#{ch}" for ch in ALLOWED_CHANNELS])
    await ctx.send(f"✅ تم تحديث القنوات المسموحة إلى: {channels_str}")

# ---------- Slash command to restore data from JSON file ----------
@bot.tree.command(name="رفع_البيانات", description="رفع ملف records.json لاستعادة البيانات إلى MongoDB")
async def upload_records(interaction: discord.Interaction, file: discord.Attachment):
    if not is_admin(interaction):
        await interaction.response.send_message("ما عندك صلاحية تستخدم هذا الأمر.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    if not file.filename.endswith('.json'):
        await interaction.followup.send("الملف يجب أن يكون بصيغة JSON.", ephemeral=True)
        return

    try:
        content = await file.read()
        data = json.loads(content.decode('utf-8'))

        if not isinstance(data, dict):
            await interaction.followup.send("الملف غير صالح: البيانات الأساسية يجب أن تكون قاموساً (object).", ephemeral=True)
            return

        await collection.update_one(
            {"_id": "records"},
            {"$set": {"data": data}},
            upsert=True
        )

        total_users = len(data)
        total_entries = sum(len(entries) for entries in data.values() if isinstance(entries, list))

        print(f"[LOG] Data restored via slash command: users={total_users}, entries={total_entries}")

        await interaction.followup.send(
            f"✅ تم استعادة البيانات بنجاح!\n"
            f"عدد المستخدمين: {total_users}\n"
            f"إجمالي السجلات: {total_entries}",
            ephemeral=True
        )
    except json.JSONDecodeError:
        await interaction.followup.send("الملف ليس بصيغة JSON صحيحة.", ephemeral=True)
    except Exception as e:
        print(f"[ERROR] Slash command restore failed: {e}")
        await interaction.followup.send(f"حدث خطأ: {str(e)}", ephemeral=True)

# ---------- Slash and Text command: اوامر (help) ----------
@bot.tree.command(name="اوامر", description="عرض قائمة بجميع أوامر البوت")
async def help_slash(interaction: discord.Interaction):
    channels_str = ", ".join([f"#{ch}" for ch in ALLOWED_CHANNELS])
    await interaction.response.send_message(
        "**📌 أوامر البوت:**\n\n"
        "**1. تسجيل شغل جديد**\n"
        "`!تحليل` أو `/تسجيل`\n"
        "يستخدمه العضو عشان يحفظ شغله.\n\n"
        "الصيغة للنصي:\n"
        "```text\n"
        "!تحليل\n"
        "العمل: اسم العمل\n"
        "الفصل: رقم الفصل\n"
        "النوع: ترجمة\n"
        "ملاحظات: اختياري\n"
        "```\n"
        "**الأنواع المسموحة:**\n"
        "`ترجمة` = $0.50\n"
        "`تحرير` = $0.50\n"
        "`تبييض` = $0.25\n\n"
        "**2. عرض شغلك**\n"
        "`!شغل` أو `/شغل`\n"
        "يعرض كل الشغل المحفوظ لك مع المجموع.\n\n"
        "**3. عرض شغل عضو**\n"
        "`!شغل @member` أو `/شغل member:`\n"
        "يعرض شغل العضو المحدد.\n\n"
        "**4. حذف سجل - للإدارة فقط**\n"
        "`!حذف @member رقم_السجل` أو `/حذف`\n"
        "يحذف سجل معين من شغل عضو.\n\n"
        "مثال: `!حذف @jamal 2`\n\n"
        "**5. حذف كل السجلات - للإدارة فقط**\n"
        "`!حذف_الكل` أو `/حذف_الكل`\n"
        "يحذف كل السجلات المحفوظة لكل الأعضاء.\n\n"
        "**6. تحديد القنوات المسموحة - للإدارة فقط**\n"
        "`!تحديد_قنوات` أو `/تحديد_قنوات`\n"
        "يحدد قناة أو قناتين حيث يمكن استخدام البوت.\n\n"
        f"**القنوات الحالية:** {channels_str}\n\n"
        "رقم السجل يظهر عند استخدام أمر `!شغل @member` مثل `#1` و `#2`."
    )

@bot.command(name="اوامر")
async def help_commands(ctx):
    channels_str = ", ".join([f"#{ch}" for ch in ALLOWED_CHANNELS])
    await ctx.send(
        "**📌 أوامر البوت:**\n\n"
        "**1. تسجيل شغل جديد**\n"
        "`!تحليل` أو `/تسجيل`\n"
        "يستخدمه العضو عشان يحفظ شغله.\n\n"
        "الصيغة:\n"
        "```text\n"
        "!تحليل\n"
        "العمل: اسم العمل\n"
        "الفصل: رقم الفصل\n"
        "النوع: ترجمة\n"
        "ملاحظات: اختياري\n"
        "```\n"
        "الأنواع المسموحة:\n"
        "`ترجمة` = $0.50\n"
        "`تحرير` = $0.50\n"
        "`تبييض` = $0.25\n\n"
        "**2. عرض شغلك**\n"
        "`!شغل` أو `/شغل`\n"
        "يعرض كل الشغل المحفوظ لك مع المجموع.\n\n"
        "**3. عرض شغل عضو**\n"
        "`!شغل @member` أو `/شغل member:`\n"
        "يعرض شغل العضو المحدد.\n\n"
        "**4. حذف سجل - للإدارة فقط**\n"
        "`!حذف @member رقم_السجل` أو `/حذف`\n"
        "يحذف سجل معين من شغل عضو.\n\n"
        "مثال: `!حذف @jamal 2`\n\n"
        "**5. حذف كل السجلات - للإدارة فقط**\n"
        "`!حذف_الكل` أو `/حذف_الكل`\n"
        "يحذف كل السجلات المحفوظة لكل الأعضاء.\n\n"
        "**6. تحديد القنوات المسموحة - للإدارة فقط**\n"
        "`!تحديد_قنوات` أو `/تحديد_قنوات`\n"
        "يحدد قناة أو قناتين حيث يمكن استخدام البوت.\n\n"
        f"**القنوات الحالية:** {channels_str}\n\n"
        "رقم السجل يظهر عند استخدام أمر `!شغل @member` مثل `#1` و `#2`."
    )

# ---------- Slash and Text command: تحليل (تسجيل شغل) ----------
@bot.tree.command(name="تسجيل", description="تسجيل شغل جديد (العمل، الفصل، النوع، ملاحظات)")
async def register_slash(
    interaction: discord.Interaction,
    العمل: str,
    الفصل: str,
    النوع: str,
    ملاحظات: str = ""
):
    # Check if channel is allowed
    if interaction.channel.name not in ALLOWED_CHANNELS:
        channels_str = ", ".join([f"#{ch}" for ch in ALLOWED_CHANNELS])
        await interaction.response.send_message(f"استخدم هذا الأمر فقط في أحد الرومات: {channels_str}.", ephemeral=True)
        return
    
    work_type = النوع.strip()
    if work_type not in PRICES:
        await interaction.response.send_message("النوع لازم يكون واحد من: تحرير، ترجمة، تبييض", ephemeral=True)
        return
    
    total = PRICES[work_type]
    
    records = await load_records()
    user_id = str(interaction.user.id)
    
    if user_id not in records:
        records[user_id] = []
    
    records[user_id].append({
        "work_name": العمل,
        "chapter": الفصل,
        "work_type": work_type,
        "total": total,
        "notes": ملاحظات,
    })
    
    await save_records(records)
    
    await interaction.response.send_message(
        f"✅ تم حفظ الشغل.\n\n"
        f"📖 العمل: {العمل}\n"
        f"🔢 الفصل: {الفصل}\n"
        f"🛠️ النوع: {work_type}\n"
        f"💰 المبلغ: ${total:.2f}"
    )

@bot.command(name="تحليل")
async def analysis(ctx, *, text=None):
    if not text:
        await ctx.send(
            "اكتبها كذا في رسالة واحدة:\n\n"
            "```text\n"
            "!تحليل\n"
            "العمل: اسم العمل\n"
            "الفصل: رقم الفصل\n"
            "النوع: تحرير\n"
            "ملاحظات: اختياري\n"
            "```\n"
            "الأنواع: تحرير، ترجمة، تبييض"
        )
        return

    fields = parse_fields(text)

    work_name = fields.get("العمل") or fields.get("اسم العمل")
    chapter = fields.get("الفصل") or fields.get("رقم الفصل")
    work_type = fields.get("النوع") or fields.get("الشغل")
    notes = fields.get("ملاحظات", "")

    if not work_name or not chapter or not work_type:
        await ctx.send(
            "فيه بيانات ناقصة. لازم تكتب:\n"
            "`العمل`، `الفصل`، `النوع`"
        )
        return

    work_type = work_type.strip()

    if work_type not in PRICES:
        await ctx.send("النوع لازم يكون واحد من: تحرير، ترجمة، تبييض")
        return

    total = PRICES[work_type]

    records = await load_records()
    user_id = str(ctx.author.id)

    if user_id not in records:
        records[user_id] = []

    records[user_id].append({
        "work_name": work_name,
        "chapter": chapter,
        "work_type": work_type,
        "total": total,
        "notes": notes,
    })

    await save_records(records)

    await ctx.send(
        f"✅ تم حفظ الشغل.\n\n"
        f"📖 العمل: {work_name}\n"
        f"🔢 الفصل: {chapter}\n"
        f"🛠️ النوع: {work_type}\n"
        f"💰 المبلغ: ${total:.2f}"
    )

# ---------- Slash and Text command: شغل ----------
@bot.tree.command(name="شغل", description="عرض شغل عضو (نفسك أو عضو آخر)")
async def show_work_slash(interaction: discord.Interaction, member: discord.Member = None):
    if interaction.channel.name not in ALLOWED_CHANNELS:
        channels_str = ", ".join([f"#{ch}" for ch in ALLOWED_CHANNELS])
        await interaction.response.send_message(f"استخدم هذا الأمر فقط في أحد الرومات: {channels_str}.", ephemeral=True)
        return
    
    target = member or interaction.user
    records = await load_records()
    user_id = str(target.id)

    if user_id not in records or not records[user_id]:
        await interaction.response.send_message("ما عندي أي شغل محفوظ لهذا العضو.", ephemeral=True)
        return

    result = f"📋 **شغل {target.display_name}:**\n\n"
    grand_total = 0

    for index, item in enumerate(records[user_id], start=1):
        work_type = item.get("work_type", "غير محدد")
        total = item.get("total")
        if total is None:
            total = PRICES.get(work_type, 0)
        grand_total += total

        block = (
            f"**#{index}**\n"
            f"📖 العمل: {item.get('work_name', 'غير محدد')}\n"
            f"🔢 الفصل: {item.get('chapter', 'غير محدد')}\n"
            f"🛠️ النوع: {work_type}\n"
            f"💰 المبلغ: ${total:.2f}\n"
        )
        if item.get("notes"):
            block += f"📝 ملاحظات: {item['notes']}\n"
        block += "\n"

        if len(result) + len(block) > 1900:
            await interaction.followup.send(result)
            result = ""

        result += block

    result += f"──────────────\n💵 **المجموع: ${grand_total:.2f}**"
    await interaction.response.send_message(result)

@bot.command(name="شغل")
async def show_work(ctx, member: discord.Member = None):
    member = member or ctx.author

    records = await load_records()
    user_id = str(member.id)

    if user_id not in records or not records[user_id]:
        await ctx.send("ما عندي أي شغل محفوظ لهذا العضو.")
        return

    result = f"📋 **شغل {member.display_name}:**\n\n"
    grand_total = 0

    for index, item in enumerate(records[user_id], start=1):
        work_type = item.get("work_type", "غير محدد")
        total = item.get("total")

        if total is None:
            total = PRICES.get(work_type, 0)

        grand_total += total

        block = (
            f"**#{index}**\n"
            f"📖 العمل: {item.get('work_name', 'غير محدد')}\n"
            f"🔢 الفصل: {item.get('chapter', 'غير محدد')}\n"
            f"🛠️ النوع: {work_type}\n"
            f"💰 المبلغ: ${total:.2f}\n"
        )

        if item.get("notes"):
            block += f"📝 ملاحظات: {item['notes']}\n"

        block += "\n"

        if len(result) + len(block) > 1900:
            await ctx.send(result)
            result = ""

        result += block

    result += f"──────────────\n💵 **المجموع: ${grand_total:.2f}**"

    await ctx.send(result)

# ---------- Slash and Text command: حذف ----------
@bot.tree.command(name="حذف", description="حذف سجل معين من شغل عضو (للمشرفين)")
async def delete_work_slash(interaction: discord.Interaction, member: discord.Member, number: int):
    if not is_admin(interaction):
        await interaction.response.send_message("ما عندك صلاحية تستخدم هذا الأمر.", ephemeral=True)
        return
    
    if interaction.channel.name not in ALLOWED_CHANNELS:
        channels_str = ", ".join([f"#{ch}" for ch in ALLOWED_CHANNELS])
        await interaction.response.send_message(f"استخدم هذا الأمر فقط في أحد الرومات: {channels_str}.", ephemeral=True)
        return
    
    records = await load_records()
    user_id = str(member.id)

    if user_id not in records or not records[user_id]:
        await interaction.response.send_message("هذا العضو ما عنده أي شغل محفوظ.", ephemeral=True)
        return

    if number < 1 or number > len(records[user_id]):
        await interaction.response.send_message("رقم السجل غير صحيح.", ephemeral=True)
        return

    deleted = records[user_id].pop(number - 1)
    await save_records(records)

    deleted_type = deleted.get("work_type", "غير محدد")
    deleted_total = deleted.get("total")
    if deleted_total is None:
        deleted_total = PRICES.get(deleted_type, 0)

    await interaction.response.send_message(
        f"🗑️ تم حذف السجل #{number} من شغل {member.mention}:\n"
        f"📖 {deleted.get('work_name', 'غير محدد')} - "
        f"{deleted_type} - ${deleted_total:.2f}"
    )

@bot.command(name="حذف")
@commands.has_permissions(manage_messages=True)
async def delete_work(ctx, member: discord.Member = None, number: int = None):
    if member is None or number is None:
        await ctx.send("الاستخدام: `!حذف @member 2`")
        return

    records = await load_records()
    user_id = str(member.id)

    if user_id not in records or not records[user_id]:
        await ctx.send("هذا العضو ما عنده أي شغل محفوظ.")
        return

    if number < 1 or number > len(records[user_id]):
        await ctx.send("رقم السجل غير صحيح.")
        return

    deleted = records[user_id].pop(number - 1)
    await save_records(records)

    deleted_type = deleted.get("work_type", "غير محدد")
    deleted_total = deleted.get("total")

    if deleted_total is None:
        deleted_total = PRICES.get(deleted_type, 0)

    await ctx.send(
        f"🗑️ تم حذف السجل #{number} من شغل {member.mention}:\n"
        f"📖 {deleted.get('work_name', 'غير محدد')} - "
        f"{deleted_type} - ${deleted_total:.2f}"
    )

# ---------- Slash and Text command: حذف_الكل ----------
@bot.tree.command(name="حذف_الكل", description="حذف كل السجلات من كل الأعضاء (للمشرفين)")
async def delete_all_work_slash(interaction: discord.Interaction):
    if not is_admin(interaction):
        await interaction.response.send_message("ما عندك صلاحية تستخدم هذا الأمر.", ephemeral=True)
        return
    
    if interaction.channel.name not in ALLOWED_CHANNELS:
        channels_str = ", ".join([f"#{ch}" for ch in ALLOWED_CHANNELS])
        await interaction.response.send_message(f"استخدم هذا الأمر فقط في أحد الرومات: {channels_str}.", ephemeral=True)
        return
    
    records = await load_records()
    total_deleted = sum(len(items) for items in records.values())

    if total_deleted == 0:
        await interaction.response.send_message("ما فيه أي سجلات محفوظة.", ephemeral=True)
        return

    records.clear()
    await save_records(records)

    await interaction.response.send_message(f"🗑️ تم حذف كل السجلات من كل الأعضاء. عدد السجلات المحذوفة: {total_deleted}")

@bot.command(name="حذف_الكل")
@commands.has_permissions(manage_messages=True)
async def delete_all_work(ctx):
    records = await load_records()
    total_deleted = sum(len(items) for items in records.values())

    if total_deleted == 0:
        await ctx.send("ما فيه أي سجلات محفوظة.")
        return

    records.clear()
    await save_records(records)

    await ctx.send(f"🗑️ تم حذف كل السجلات من كل الأعضاء. عدد السجلات المحذوفة: {total_deleted}")

bot.run(TOKEN)