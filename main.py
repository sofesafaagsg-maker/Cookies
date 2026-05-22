# main.py
import os
import json
from datetime import datetime, timedelta
from io import BytesIO
from typing import List
from collections import defaultdict

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
# UI Classes (moved from original global scope)
# ----------------------------------------------------------------------
class WorkDetailsView(discord.ui.View):
    def __init__(self, work_name, chapters_list, user_id, user_name, currency, back_callback: callable = None):
        super().__init__(timeout=120)
        self.work_name = work_name
        self.chapters_list = chapters_list
        self.user_id = user_id
        self.user_name = user_name
        self.currency = currency
        self.current_page = 0
        self.items_per_page = 10
        self.total_pages = (len(chapters_list) + self.items_per_page - 1) // self.items_per_page
        self.back_callback = back_callback
        self.update_buttons()

    def update_buttons(self):
        self.clear_items()
        if self.back_callback:
            back_btn = discord.ui.Button(label="◀ رجوع", style=discord.ButtonStyle.secondary)
            back_btn.callback = self.back_callback
            self.add_item(back_btn)
        if self.total_pages > 1:
            if self.current_page > 0:
                prev_button = discord.ui.Button(label="◀ السابق", style=discord.ButtonStyle.primary)
                prev_button.callback = self.previous_page
                self.add_item(prev_button)
            if self.current_page < self.total_pages - 1:
                next_button = discord.ui.Button(label="التالي ▶", style=discord.ButtonStyle.primary)
                next_button.callback = self.next_page
                self.add_item(next_button)
        close_button = discord.ui.Button(label="❌ إغلاق", style=discord.ButtonStyle.danger)
        close_button.callback = self.close_view
        self.add_item(close_button)

    async def previous_page(self, interaction: discord.Interaction):
        self.current_page -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    async def next_page(self, interaction: discord.Interaction):
        self.current_page += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    async def close_view(self, interaction: discord.Interaction):
        await interaction.response.edit_message(content="تم إغلاق التفاصيل.", embed=None, view=None)

    def get_embed(self):
        start = self.current_page * self.items_per_page
        end = start + self.items_per_page
        page_chapters = self.chapters_list[start:end]
        embed = discord.Embed(title=f"**تفاصيل عمل: {self.work_name}**", color=discord.Color.teal())
        embed.set_author(name=self.user_name)
        total_amount = sum(ch['total'] for ch in self.chapters_list)
        embed.add_field(name="**📊 إجمالي الفصول**", value=str(len(self.chapters_list)), inline=True)
        embed.add_field(name="**💰 إجمالي المبلغ**", value=f"{self.currency}{total_amount:.2f}", inline=True)
        for ch in page_chapters:
            embed.add_field(
                name=f"**📖 فصل {ch['chapter']}**",
                value=f"**التخصص:** {ch['type']}\n**المبلغ:** {self.currency}{ch['total']:.2f}\n**ملاحظات:** {ch.get('notes', 'لا توجد')}",
                inline=False
            )
        if self.total_pages > 1:
            embed.set_footer(text=f"صفحة {self.current_page+1} من {self.total_pages}")
        return embed

class DeleteSelect(discord.ui.Select):
    def __init__(self, user_id, work_name=None):
        self.user_id = user_id
        self.work_name = work_name
        options = []
        if work_name:
            options.append(discord.SelectOption(label="🗑️ حذف كل فصول هذا العمل", value="delete_work", description=f"حذف كل فصول عمل {work_name}"))
            options.append(discord.SelectOption(label="🔍 حذف فصل محدد", value="delete_chapter", description="اختيار فصل لحذفه"))
        else:
            options.append(discord.SelectOption(label="👤 حذف كل سجلات العضو", value="delete_all_user", description="حذف كل سجلات العضو بالكامل"))
        options.append(discord.SelectOption(label="❌ إلغاء", value="cancel"))
        super().__init__(placeholder="اختر إجراء...", options=options)

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "cancel":
            await interaction.response.edit_message(content="تم الإلغاء.", view=None)
            return
        if self.values[0] == "delete_all_user":
            await interaction.response.send_message("⚠️ **تحذير:** هل أنت متأكد من حذف كل سجلات هذا العضو؟\nأرسل `تأكيد` خلال 30 ثانية.", ephemeral=True)
            def check(m):
                return m.author == interaction.user and m.content == "تأكيد" and m.channel == interaction.channel
            try:
                await bot.wait_for('message', timeout=30.0, check=check)
            except:
                await interaction.followup.send("❌ تم إلغاء العملية.", ephemeral=True)
                return
            records = await db.load_records()
            if str(self.user_id) in records:
                del records[str(self.user_id)]
                await db.save_records(records)
                await db.log_audit("حذف_كل_سجلات_العضو", interaction.user.id, self.user_id, "حذف كل السجلات")
                await db.update_stats()
                await interaction.followup.send(f"✅ تم حذف كل سجلات العضو.", ephemeral=True)
            else:
                await interaction.followup.send("❌ لا توجد سجلات لهذا العضو.", ephemeral=True)
        elif self.values[0] == "delete_work" and self.work_name:
            await interaction.response.send_message(f"⚠️ **تحذير:** هل أنت متأكد من حذف كل فصول عمل `{self.work_name}` للعضو؟\nأرسل `تأكيد` خلال 30 ثانية.", ephemeral=True)
            def check(m):
                return m.author == interaction.user and m.content == "تأكيد" and m.channel == interaction.channel
            try:
                await bot.wait_for('message', timeout=30.0, check=check)
            except:
                await interaction.followup.send("❌ تم إلغاء العملية.", ephemeral=True)
                return
            records = await db.load_records()
            user_id_str = str(self.user_id)
            if user_id_str in records:
                new_entries = [e for e in records[user_id_str] if e.get("work_name") != self.work_name]
                removed_count = len(records[user_id_str]) - len(new_entries)
                records[user_id_str] = new_entries
                if not records[user_id_str]:
                    del records[user_id_str]
                await db.save_records(records)
                await db.log_audit("حذف_عمل_كامل", interaction.user.id, self.user_id, f"حذف عمل {self.work_name} ({removed_count} فصل)")
                await db.update_stats()
                await interaction.followup.send(f"✅ تم حذف عمل `{self.work_name}` بالكامل ({removed_count} فصل).", ephemeral=True)
            else:
                await interaction.followup.send("❌ لا توجد سجلات لهذا العضو.", ephemeral=True)
        elif self.values[0] == "delete_chapter":
            records = await db.load_records()
            user_id_str = str(self.user_id)
            if user_id_str not in records:
                await interaction.response.send_message("❌ لا توجد سجلات لهذا العضو.", ephemeral=True)
                return
            work_entries = [e for e in records[user_id_str] if e.get("work_name") == self.work_name]
            if not work_entries:
                await interaction.response.send_message("❌ لا توجد فصول لهذا العمل.", ephemeral=True)
                return
            options = []
            for e in work_entries:
                options.append(discord.SelectOption(label=f"فصل {e.get('chapter')}", value=e.get('chapter'), description=f"التخصص: {e.get('work_type')}"))
            options.append(discord.SelectOption(label="❌ إلغاء", value="cancel"))
            select = discord.ui.Select(placeholder="اختر الفصل المراد حذفه...", options=options)
            async def select_callback(interaction2):
                if select.values[0] == "cancel":
                    await interaction2.response.edit_message(content="تم الإلغاء.", view=None)
                    return
                chapter = select.values[0]
                await interaction2.response.send_message(f"⚠️ هل أنت متأكد من حذف الفصل {chapter} من عمل `{self.work_name}`؟\nأرسل `تأكيد` خلال 30 ثانية.", ephemeral=True)
                def check(m):
                    return m.author == interaction2.user and m.content == "تأكيد" and m.channel == interaction2.channel
                try:
                    await bot.wait_for('message', timeout=30.0, check=check)
                except:
                    await interaction2.followup.send("❌ تم إلغاء العملية.", ephemeral=True)
                    return
                records2 = await db.load_records()
                if user_id_str in records2:
                    new_entries = [e for e in records2[user_id_str] if not (e.get("work_name") == self.work_name and e.get("chapter") == chapter)]
                    removed = len(records2[user_id_str]) - len(new_entries)
                    records2[user_id_str] = new_entries
                    if not records2[user_id_str]:
                        del records2[user_id_str]
                    await db.save_records(records2)
                    await db.log_audit("حذف_فصل", interaction2.user.id, self.user_id, f"حذف فصل {chapter} من عمل {self.work_name}")
                    await db.update_stats()
                    await interaction2.followup.send(f"✅ تم حذف الفصل {chapter} من عمل `{self.work_name}`.", ephemeral=True)
                else:
                    await interaction2.followup.send("❌ لا توجد سجلات لهذا العضو.", ephemeral=True)
            select.callback = select_callback
            view = discord.ui.View(timeout=60)
            view.add_item(select)
            await interaction.response.edit_message(content="**اختر الفصل المراد حذفه:**", view=view)

async def get_works_info(guild: discord.Guild):
    """Build list of works with their contributors."""
    approved_works = await db.load_works()
    records = await db.load_records()

    contrib_map = defaultdict(lambda: defaultdict(int))
    for user_id_str, entries in records.items():
        for entry in entries:
            work = entry.get("work_name")
            if work:
                contrib_map[work][user_id_str] += 1

    works_info = []
    for w in approved_works:
        work_name = w["name"]
        contributors = contrib_map.get(work_name, {})
        members_list = []
        for uid_str, count in contributors.items():
            uid = int(uid_str)
            username_hint = None
            if uid_str in records:
                for e in records[uid_str]:
                    if e.get("username"):
                        username_hint = e["username"]
                        break
            display = utils.format_member_display(guild, uid, username_hint)
            members_list.append((uid, display))
        works_info.append((work_name, members_list))
    return works_info

class MemberSelect(discord.ui.Select):
    def __init__(self, work_name, members_info, guild, works_info_callback=None):
        self.work_name = work_name
        self.members_info = members_info
        self.guild = guild
        self.works_info_callback = works_info_callback
        options = []
        for uid, name in members_info[:24]:
            options.append(discord.SelectOption(label=name, value=str(uid), description="عرض فصوله في هذا العمل"))
        options.append(discord.SelectOption(label="❌ إلغاء", value="cancel"))
        super().__init__(placeholder="اختر عضواً...", options=options)

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "cancel":
            await interaction.response.edit_message(content="تم الإلغاء.", view=None)
            return
        user_id = int(self.values[0])
        user_display = next((name for uid, name in self.members_info if uid == user_id), str(user_id))
        records = await db.load_records()
        user_entries = records.get(str(user_id), [])
        work_entries = [e for e in user_entries if e.get("work_name") == self.work_name]
        if not work_entries:
            await interaction.response.send_message(f"❌ لا توجد فصول للعضو {user_display} في عمل {self.work_name}.", ephemeral=True)
            return
        chapters_details = []
        for e in work_entries:
            chapters_details.append({
                "chapter": e.get("chapter"),
                "type": e.get("work_type"),
                "total": e.get("total", 0),
                "notes": e.get("notes", "")
            })

        async def back_to_members(interaction2: discord.Interaction):
            select = MemberSelect(self.work_name, self.members_info, self.guild, self.works_info_callback)
            view_back = discord.ui.View(timeout=60)
            view_back.add_item(select)
            if self.works_info_callback:
                back_list_btn = discord.ui.Button(label="◀ رجوع للقائمة", style=discord.ButtonStyle.secondary)
                back_list_btn.callback = self.works_info_callback
                view_back.add_item(back_list_btn)
            await interaction2.response.edit_message(content=f"**اختر عضواً من عمل `{self.work_name}`:**", view=view_back)

        view_details = WorkDetailsView(
            self.work_name, chapters_details, user_id, user_display,
            state.SETTINGS.get('currency', '$'), back_callback=back_to_members
        )
        await interaction.response.edit_message(content=None, embed=view_details.get_embed(), view=view_details)

class WorkSelect(discord.ui.Select):
    def __init__(self, works_info, guild, works_info_callback=None):
        self.works_info = works_info
        self.guild = guild
        self.works_info_callback = works_info_callback
        options = []
        for work_name, _ in works_info[:24]:
            options.append(discord.SelectOption(label=work_name, value=work_name))
        options.append(discord.SelectOption(label="❌ إلغاء", value="cancel"))
        super().__init__(placeholder="اختر العمل...", options=options)

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "cancel":
            await interaction.response.edit_message(content="تم الإلغاء.", view=None)
            return
        work_name = self.values[0]
        members_info = [(uid, name) for work, members in self.works_info if work == work_name for uid, name in members]
        if not members_info:
            await interaction.response.send_message(f"❌ لا يوجد مساهمين في عمل {work_name}.", ephemeral=True)
            return
        select = MemberSelect(work_name, members_info, self.guild, self.works_info_callback)
        view = discord.ui.View(timeout=60)
        view.add_item(select)
        if self.works_info_callback:
            back_btn = discord.ui.Button(label="◀ رجوع للقائمة", style=discord.ButtonStyle.secondary)
            back_btn.callback = self.works_info_callback
            view.add_item(back_btn)
        await interaction.response.edit_message(content=f"**اختر عضواً من عمل `{work_name}`:**", view=view)

class WorksPaginator(discord.ui.View):
    def __init__(self, all_works_info, guild):
        super().__init__(timeout=120)
        self.all_works_info = all_works_info
        self.guild = guild
        self.current_page = 0
        self.per_page = 24
        self.total_pages = max(1, (len(all_works_info) + self.per_page - 1) // self.per_page)
        self.update_buttons()

    async def show_works_list(self, interaction: discord.Interaction):
        new_info = await get_works_info(self.guild)
        self.all_works_info = new_info
        self.current_page = 0
        self.total_pages = max(1, (len(new_info) + self.per_page - 1) // self.per_page)
        self.update_buttons()
        embed = discord.Embed(title="📚 **قائمة الأعمال**", color=discord.Color.purple())
        embed.add_field(name="عدد الأعمال", value=str(len(new_info)), inline=False)
        embed.set_footer(text="اختر عملاً من القائمة لرؤية المساهمين. استخدم أزرار التنقل للصفحات.")
        await interaction.response.edit_message(embed=embed, view=self)

    def update_buttons(self):
        self.clear_items()
        start = self.current_page * self.per_page
        end = start + self.per_page
        page_works = self.all_works_info[start:end]
        select = WorkSelect(page_works, self.guild, works_info_callback=self.show_works_list)
        self.add_item(select)
        if self.total_pages > 1:
            if self.current_page > 0:
                prev_btn = discord.ui.Button(label="◀ السابق", style=discord.ButtonStyle.primary)
                prev_btn.callback = self.previous_page
                self.add_item(prev_btn)
            if self.current_page < self.total_pages - 1:
                next_btn = discord.ui.Button(label="التالي ▶", style=discord.ButtonStyle.primary)
                next_btn.callback = self.next_page
                self.add_item(next_btn)

    async def previous_page(self, interaction: discord.Interaction):
        self.current_page -= 1
        self.update_buttons()
        await interaction.response.edit_message(view=self)

    async def next_page(self, interaction: discord.Interaction):
        self.current_page += 1
        self.update_buttons()
        await interaction.response.edit_message(view=self)

class WorksListPaginator(discord.ui.View):
    def __init__(self, works: list):
        super().__init__(timeout=120)
        self.works = works
        self.current_page = 0
        self.per_page = 20
        self.total_pages = max(1, (len(works) + self.per_page - 1) // self.per_page)
        self.update_buttons()

    def update_buttons(self):
        self.clear_items()
        if self.current_page > 0:
            prev_btn = discord.ui.Button(label="◀ السابق", style=discord.ButtonStyle.primary)
            prev_btn.callback = self.previous_page
            self.add_item(prev_btn)
        if self.current_page < self.total_pages - 1:
            next_btn = discord.ui.Button(label="التالي ▶", style=discord.ButtonStyle.primary)
            next_btn.callback = self.next_page
            self.add_item(next_btn)
        page_indicator = discord.ui.Button(
            label=f"صفحة {self.current_page + 1} من {self.total_pages}",
            style=discord.ButtonStyle.secondary,
            disabled=True
        )
        self.add_item(page_indicator)

    def get_embed(self) -> discord.Embed:
        start = self.current_page * self.per_page
        end = start + self.per_page
        page_works = self.works[start:end]
        embed = discord.Embed(title="📋 **قائمة الأعمال المدفوعة**", color=discord.Color.blurple())
        for w in page_works:
            paid_info = "كل الفصول مدفوعة" if w.get("paid_start") is None else f"يبدأ من فصل {w['paid_start']}"
            active_icon = "✅" if w.get("active", True) else "❌"
            embed.add_field(name=f"{active_icon} {w['name']}", value=paid_info, inline=False)
        return embed

    async def previous_page(self, interaction: discord.Interaction):
        self.current_page -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    async def next_page(self, interaction: discord.Interaction):
        self.current_page += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

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