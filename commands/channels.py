import json
from io import BytesIO
import discord
from discord import app_commands
from discord.ext import commands
from state import bot
from helpers.core import (
    SETTINGS, log_unauthorized, log_audit, update_stats,
    load_settings, save_settings, load_records, save_records, load_works, save_works
)
from tasks.lifecycle import is_admin

@bot.tree.command(name="تحديد_قنوات", description="تحديد القنوات المسموحة (قناتين كحد أقصى) - للإدارة فقط")
@app_commands.checks.cooldown(1, 5, key=lambda i: (i.user.id, i.command.qualified_name))
async def set_allowed_channels_slash(interaction: discord.Interaction,
                                     channel1: str,
                                     channel2: str = None):
    if not is_admin(interaction):
        await log_unauthorized(interaction.user.id, "تحديد_قنوات")
        await interaction.response.send_message("❌ ما عندك صلاحية تستخدم هذا الأمر.", ephemeral=True)
        return

    def resolve_channel(input_str: str):
        # Try to parse as mention <#123456>
        if input_str.startswith('<#') and input_str.endswith('>'):
            channel_id = int(input_str[2:-1])
            ch = bot.get_channel(channel_id)
            if ch:
                return ch.name
        # Try as numeric ID
        elif input_str.isdigit():
            ch = bot.get_channel(int(input_str))
            if ch:
                return ch.name
        # Otherwise treat as channel name (fallback, may not exist in current guild but we store it anyway)
        return input_str

    ch1_name = resolve_channel(channel1)
    channels = [ch1_name]
    if channel2:
        ch2_name = resolve_channel(channel2)
        channels.append(ch2_name)
    channels = list(dict.fromkeys(channels))[:2]
    SETTINGS["allowed_channels"] = channels
    await save_settings(SETTINGS)
    channels_str = ", ".join([f"#{ch}" for ch in SETTINGS["allowed_channels"]])
    await interaction.response.send_message(f"✅ تم تحديث القنوات المسموحة إلى: {channels_str}", ephemeral=True)
    await log_audit("تحديد_قنوات", interaction.user.id, None, f"القنوات الجديدة: {channels_str}")

@bot.command(name="تحديد_قنوات")
@commands.has_permissions(manage_messages=True)
@commands.cooldown(1, 5, commands.BucketType.user)
async def set_allowed_channels_text(ctx, channel1: str, channel2: str = None):
    def extract_channel_name(input_str):
        # Try to resolve as mention or ID first (cross-server)
        if input_str.startswith('<#') and input_str.endswith('>'):
            channel_id = int(input_str[2:-1])
            ch = bot.get_channel(channel_id)
            if ch:
                return ch.name
        elif input_str.isdigit():
            ch = bot.get_channel(int(input_str))
            if ch:
                return ch.name
        # Fallback to local guild channel lookup by name or mention
        if input_str.startswith('<#') and input_str.endswith('>'):
            channel_id = int(input_str[2:-1])
            channel = ctx.guild.get_channel(channel_id)
            if channel:
                return channel.name
        elif input_str.isdigit():
            channel = ctx.guild.get_channel(int(input_str))
            if channel:
                return channel.name
        else:
            for ch in ctx.guild.channels:
                if ch.name == input_str:
                    return ch.name
        return input_str
    ch1_name = extract_channel_name(channel1)
    ch2_name = extract_channel_name(channel2) if channel2 else None
    channels = [ch1_name]
    if ch2_name:
        channels.append(ch2_name)
    channels = list(dict.fromkeys(channels))[:2]
    SETTINGS["allowed_channels"] = channels
    await save_settings(SETTINGS)
    channels_str = ", ".join([f"#{ch}" for ch in SETTINGS["allowed_channels"]])
    await ctx.send(f"✅ تم تحديث القنوات المسموحة إلى: {channels_str}")
    await log_audit("تحديد_قنوات", ctx.author.id, None, f"القنوات الجديدة: {channels_str}")

# ----------------------------------------------------------------------
# Command: رفع_البيانات (now also handles works)
# ----------------------------------------------------------------------
@bot.tree.command(name="رفع_البيانات", description="رفع ملف JSON لاستعادة السجلات والأعمال إلى MongoDB")
@app_commands.checks.cooldown(1, 10, key=lambda i: (i.user.id, i.command.qualified_name))
async def upload_records(interaction: discord.Interaction, file: discord.Attachment):
    if not is_admin(interaction):
        await log_unauthorized(interaction.user.id, "رفع_البيانات")
        await interaction.response.send_message("❌ ما عندك صلاحية تستخدم هذا الأمر.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    if not file.filename.endswith('.json'):
        await interaction.followup.send("❌ الملف يجب أن يكون بصيغة JSON.", ephemeral=True)
        return
    try:
        content = await file.read()
        data = json.loads(content.decode('utf-8'))

        # Support both old format (plain records dict) and new format with "records" and optional "works"
        if isinstance(data, dict):
            records_data = data.get("records", data)  # fallback to whole dict
            works_data = data.get("works", None)
        else:
            await interaction.followup.send("❌ الملف غير صالح.", ephemeral=True)
            return

        # Update records
        if not isinstance(records_data, dict):
            await interaction.followup.send("❌ قسم records غير صالح.", ephemeral=True)
            return
        await collection.update_one({"_id": "records"}, {"$set": {"data": records_data}}, upsert=True)
        total_users = len(records_data)
        total_entries = sum(len(entries) for entries in records_data.values() if isinstance(entries, list))

        # --- NEW: Auto-extract works from records ---
        works_from_records = set()
        for user_entries in records_data.values():
            if isinstance(user_entries, list):
                for entry in user_entries:
                    if isinstance(entry, dict) and "work_name" in entry:
                        works_from_records.add(entry["work_name"])

        if works_from_records:
            current_works = await load_works()
            existing_names = {w["name"] for w in current_works}
            added_works_count = 0
            for name in works_from_records:
                if name not in existing_names:
                    current_works.append({"name": name, "paid_start": None, "active": True})
                    existing_names.add(name)
                    added_works_count += 1
            if added_works_count > 0:
                await save_works(current_works)
        else:
            added_works_count = 0
        # --- End of auto-extract ---

        # Update works from file if present (overwrites if the user provided a "works" section)
        if works_data is not None:
            if isinstance(works_data, list):
                await save_works(works_data)
                added_works_count = len(works_data)  # override count with explicit works data
            else:
                await interaction.followup.send("⚠️ تم تحديث السجلات لكن قسم works غير صالح (تم تجاهله).", ephemeral=True)
                await log_audit("رفع_البيانات", interaction.user.id, None,
                                f"تم رفع {total_entries} سجل (works غير محدثة)")
                await update_stats()
                await interaction.followup.send(
                    f"✅ تم استعادة السجلات بنجاح!\nعدد المستخدمين: {total_users}\nإجمالي السجلات: {total_entries}",
                    ephemeral=True)
                return

        await log_audit("رفع_البيانات", interaction.user.id, None,
                        f"تم رفع {total_entries} سجل" + (f" و {added_works_count} عمل جديد" if added_works_count else ""))
        await update_stats()
        msg = f"✅ تم استعادة البيانات بنجاح!\nعدد المستخدمين: {total_users}\nإجمالي السجلات: {total_entries}"
        if added_works_count:
            msg += f"\nأعمال جديدة مضافة من السجلات: {added_works_count}"
        if works_data is not None:
            msg += f"\nالأعمال المحدثة من الملف: {len(works_data)}"
        await interaction.followup.send(msg, ephemeral=True)
    except json.JSONDecodeError:
        await interaction.followup.send("❌ الملف ليس بصيغة JSON صحيحة.", ephemeral=True)
    except Exception as e:
        print(f"[ERROR] Slash command restore failed: {e}")
        await interaction.followup.send(f"❌ حدث خطأ: {str(e)}", ephemeral=True)

# ----------------------------------------------------------------------
# Command: اوامر (help)
# ----------------------------------------------------------------------