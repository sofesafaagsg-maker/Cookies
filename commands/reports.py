from datetime import datetime, timedelta, timezone
import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Modal, TextInput, Select, Button, View
import math
from state import bot
from helpers.core import *
from helpers.core import make_embed
from views.paginators import WorkDetailsView, WorksPaginator, get_works_info

# ----------------------------------------------------------------------
# Utility functions
# ----------------------------------------------------------------------
def make_bar(percentage: float, length: int = 10) -> str:
    filled = max(0, min(length, round(percentage / 100 * length)))
    empty = length - filled
    return "█" * filled + "░" * empty

def format_currency(amount: float) -> str:
    currency = SETTINGS.get('currency', '$')
    if currency is None:
        currency = '$'
    return f"{currency}{amount:.2f}"

def get_week_boundaries():
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=now.weekday())
    start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=7)
    return start, end

def get_previous_week_boundaries():
    start, end = get_week_boundaries()
    return start - timedelta(days=7), end - timedelta(days=7)

def week_days_labels():
    return ["الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]

# ----------------------------------------------------------------------
# Modals
# ----------------------------------------------------------------------
class SearchWorkModal(Modal, title="بحث عن عمل"):
    name = TextInput(label="اسم العمل", placeholder="أدخل جزءاً من اسم العمل", required=True, max_length=100)

    def __init__(self, parent_view):
        super().__init__()
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.parent_view.search_query = self.name.value.strip()
        self.parent_view.current_page = 0
        await self.parent_view.update_message(interaction)

class EditEntryModal(Modal, title="تعديل السجل"):
    work_name = TextInput(label="العمل", placeholder="اسم العمل", required=False, max_length=100)
    chapter = TextInput(label="الفصل", placeholder="رقم الفصل أو وصفه", required=False, max_length=100)
    work_type = TextInput(label="التخصص", placeholder="ترجمة، تدقيق، كتابة...", required=False, max_length=50)
    notes = TextInput(label="ملاحظات", placeholder="ملاحظات إضافية", required=False, max_length=200)

    def __init__(self, record, parent_view):
        super().__init__()
        self.record = record
        self.parent_view = parent_view
        self.work_name.default = record.get("work_name", "")
        self.chapter.default = record.get("chapter", "")
        self.work_type.default = record.get("work_type", "")
        self.notes.default = record.get("notes", "")
        self.work_name.placeholder = self.work_name.default or "اسم العمل"
        self.chapter.placeholder = self.chapter.default or "رقم الفصل"
        self.work_type.placeholder = self.work_type.default or "التخصص"
        self.notes.placeholder = self.notes.default or "ملاحظات"

    async def on_submit(self, interaction: discord.Interaction):
        if self.work_type.value:
            norm_type = map_type(self.work_type.value)
            if norm_type not in PRICES:
                await interaction.response.send_message("❌ التخصص غير صحيح.", ephemeral=True)
                return
            self.record["work_type"] = norm_type
            self.record["total"] = PRICES[norm_type]
        if self.work_name.value:
            self.record["work_name"] = self.work_name.value
        if self.chapter.value:
            self.record["chapter"] = self.chapter.value
        if self.notes.value is not None:
            self.record["notes"] = self.notes.value

        records = await load_records()
        user_id = str(interaction.user.id)
        if hasattr(self.parent_view, 'entry_index') and self.parent_view.entry_index is not None:
            records[user_id][self.parent_view.entry_index] = self.record
        await save_records(records)
        await update_stats()
        await interaction.response.send_message("✅ تم تعديل السجل بنجاح.", ephemeral=True)
        if hasattr(self.parent_view, 'original_interaction'):
            await self.parent_view.update_original()

class SettingModal(Modal):
    def __init__(self, title, setting_key, current_value, parent_view):
        super().__init__(title=title)
        self.setting_key = setting_key
        self.parent_view = parent_view
        self.add_item(TextInput(label="القيمة الجديدة", default=str(current_value), required=True))

    async def on_submit(self, interaction: discord.Interaction):
        new_val = self.children[0].value
        if self.setting_key in ("alert_threshold", "payment_day", "payment_hour", "notify_channel_id", "daily_backup_channel_id"):
            try:
                new_val = int(new_val)
            except ValueError:
                await interaction.response.send_message("❌ القيمة يجب أن تكون رقماً.", ephemeral=True)
                return
        SETTINGS[self.setting_key] = new_val
        await interaction.response.send_message(f"✅ تم تحديث `{self.setting_key}` إلى `{new_val}`.", ephemeral=True)
        if self.parent_view:
            await self.parent_view.refresh_embed()

class DateRangeModal(Modal):
    def __init__(self, parent_view, start_label="تاريخ البداية (YYYY-MM-DD)", end_label="تاريخ النهاية (YYYY-MM-DD)"):
        super().__init__(title="تحديد نطاق زمني")
        self.parent_view = parent_view
        self.start_input = TextInput(label=start_label, placeholder="2026-01-01", required=False)
        self.end_input = TextInput(label=end_label, placeholder="2026-12-31", required=False)
        self.add_item(self.start_input)
        self.add_item(self.end_input)

    async def on_submit(self, interaction: discord.Interaction):
        start_str = self.start_input.value
        end_str = self.end_input.value
        try:
            start = datetime.fromisoformat(start_str) if start_str else None
            end = datetime.fromisoformat(end_str) if end_str else None
            if start and end and start > end:
                raise ValueError
        except:
            await interaction.response.send_message("❌ التواريخ غير صحيحة. استخدم الصيغة YYYY-MM-DD.", ephemeral=True)
            return
        await interaction.response.defer()
        self.parent_view.date_filter = (start, end)
        self.parent_view.current_page = 0
        await self.parent_view.update_message(interaction)

# ----------------------------------------------------------------------
# Views
# ----------------------------------------------------------------------
class EnhancedWorksView(View):
    def __init__(self, works_info, guild):
        super().__init__(timeout=300)
        self.works_info = works_info  # list of tuples (work_name, members, total_chapters)
        self.guild = guild
        self.current_page = 0
        self.per_page = 5
        self.search_query = None
        self.sort_by = "name"
        self.message = None
        self.prepare_sorted_list()

    def prepare_sorted_list(self):
        # Convert tuples to dicts for easier handling
        data = []
        for w in self.works_info:
            if isinstance(w, tuple):
                # Assume order: work_name, members_list, total_chapters
                work_dict = {
                    "work_name": w[0] if len(w) > 0 else "غير معروف",
                    "members": w[1] if len(w) > 1 else [],
                    "total_chapters": w[2] if len(w) > 2 else 0
                }
                data.append(work_dict)
            else:
                data.append(w)

        if self.search_query:
            data = [w for w in data if self.search_query.lower() in w.get('work_name', '').lower()]
        if self.sort_by == "members":
            data.sort(key=lambda w: len(w.get('members', [])), reverse=True)
        elif self.sort_by == "chapters":
            data.sort(key=lambda w: w.get('total_chapters', 0), reverse=True)
        else:
            data.sort(key=lambda w: w.get('work_name', ''))
        self.filtered_works = data

    def get_page_data(self):
        start = self.current_page * self.per_page
        end = start + self.per_page
        return self.filtered_works[start:end]

    def build_embed(self):
        if not self.filtered_works:
            embed = discord.Embed(title="📚 قائمة الأعمال", color=discord.Color.purple(), description="لا توجد أعمال مطابقة.")
            return embed
        total_pages = math.ceil(len(self.filtered_works) / self.per_page)
        embed = discord.Embed(
            title="📚 **قائمة الأعمال**",
            color=discord.Color.purple(),
            description=f"عدد الأعمال: {len(self.filtered_works)} (الصفحة {self.current_page+1}/{total_pages})"
        )
        for i, work in enumerate(self.get_page_data(), start=self.current_page*self.per_page+1):
            member_count = len(work.get('members', []))
            chapters = work.get('total_chapters', 0)
            embed.add_field(
                name=f"{i}. {work.get('work_name', 'غير معروف')}",
                value=f"👥 الأعضاء: {member_count}\n📖 الفصول: {chapters}",
                inline=False
            )
        embed.set_footer(text="استخدم القائمة المنسدلة للترتيب أو زر البحث للتصفية.")
        return embed

    async def update_message(self, interaction):
        self.prepare_sorted_list()
        embed = self.build_embed()
        if self.message is None:
            await interaction.response.send_message(embed=embed, view=self)
            self.message = await interaction.original_response()
        else:
            await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="السابق", style=discord.ButtonStyle.secondary, emoji="⬅️")
    async def prev_page(self, interaction: discord.Interaction, button: Button):
        if self.current_page > 0:
            self.current_page -= 1
            await self.update_message(interaction)
        else:
            await interaction.response.defer()

    @discord.ui.button(label="التالي", style=discord.ButtonStyle.secondary, emoji="➡️")
    async def next_page(self, interaction: discord.Interaction, button: Button):
        if (self.current_page + 1) * self.per_page < len(self.filtered_works):
            self.current_page += 1
            await self.update_message(interaction)
        else:
            await interaction.response.defer()

    @discord.ui.select(
        placeholder="ترتيب حسب...",
        options=[
            discord.SelectOption(label="الاسم", value="name", emoji="🔤"),
            discord.SelectOption(label="عدد الأعضاء", value="members", emoji="👥"),
            discord.SelectOption(label="عدد الفصول", value="chapters", emoji="📖"),
        ]
    )
    async def sort_selector(self, interaction: discord.Interaction, select: Select):
        self.sort_by = select.values[0]
        self.current_page = 0
        await self.update_message(interaction)

    @discord.ui.button(label="بحث", style=discord.ButtonStyle.primary, emoji="🔍")
    async def search_button(self, interaction: discord.Interaction, button: Button):
        modal = SearchWorkModal(self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="تحديث", style=discord.ButtonStyle.success, emoji="🔄")
    async def refresh_button(self, interaction: discord.Interaction, button: Button):
        new_info = await get_works_info(self.guild)
        self.works_info = new_info
        self.current_page = 0
        self.search_query = None
        await self.update_message(interaction)

    async def on_timeout(self):
        if self.message:
            try:
                await self.message.edit(view=None)
            except:
                pass

class StatsView(View):
    def __init__(self, stat_doc, interaction):
        super().__init__(timeout=120)
        self.stat_doc = stat_doc
        self.mode = "all"
        self.message = None
        self.interaction = interaction  # keep for guild info

    def build_embed(self):
        doc = self.stat_doc
        if not doc:
            return discord.Embed(title="لا توجد إحصائيات", color=discord.Color.red())

        currency = SETTINGS.get("currency", "$") or "$"
        if self.mode == "daily":
            d = doc.get("daily", {"entries":0, "amount":0})
            title = "📊 إحصائيات اليوم"
            entries = d["entries"]
            amount = d["amount"]
            fields = {"الفصول": entries, "المبلغ": format_currency(amount)}
        elif self.mode == "weekly":
            w = doc.get("weekly", {"entries":0, "amount":0})
            title = "📆 إحصائيات الأسبوع"
            entries = w["entries"]
            amount = w["amount"]
            fields = {"الفصول": entries, "المبلغ": format_currency(amount)}
        elif self.mode == "monthly":
            m = doc.get("monthly", {"entries":0, "amount":0})
            title = "📆 إحصائيات الشهر"
            entries = m["entries"]
            amount = m["amount"]
            fields = {"الفصول": entries, "المبلغ": format_currency(amount)}
        else:
            title = "📊 إحصائيات شاملة"
            total_entries = doc.get("total_entries", 0)
            total_amount = doc.get("total_amount", 0)
            type_counts = doc.get("type_counts", {})
            top_members = doc.get("top_members", [])
            last_updated = doc.get("last_updated", "غير معروف")

            embed = discord.Embed(title=title, color=discord.Color.teal())
            embed.add_field(name="📄 إجمالي الفصول", value=total_entries, inline=True)
            embed.add_field(name="💰 إجمالي المبالغ", value=format_currency(total_amount), inline=True)

            type_lines = []
            max_val = max(type_counts.values()) if type_counts else 1
            for k, v in type_counts.items():
                pct = (v / max_val) * 100
                bar = make_bar(pct, 8)
                type_lines.append(f"**{k.replace('_',' ').title()}:** {v} {bar}")
            embed.add_field(name="📊 تفصيل التخصصات", value="\n".join(type_lines) if type_lines else "لا يوجد", inline=False)

            if top_members:
                top_list = []
                for i, (uid, s) in enumerate(top_members[:5], 1):
                    uid_int = int(uid)
                    top_list.append(f"{i}. <@{uid_int}> - {format_currency(s['total_amount'])} ({s['total_entries']} فصل)")
                embed.add_field(name="🏆 أفضل 5 أعضاء", value="\n".join(top_list), inline=False)

            embed.set_footer(text=f"آخر تحديث: {last_updated[:19] if last_updated != 'غير معروف' else last_updated}")
            return embed

        embed = discord.Embed(title=title, color=discord.Color.teal())
        for k, v in fields.items():
            embed.add_field(name=k, value=v, inline=True)
        return embed

    async def update_message(self, interaction):
        embed = self.build_embed()
        if self.message is None:
            await interaction.response.send_message(embed=embed, view=self)
            self.message = await interaction.original_response()
        else:
            await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="الكل", style=discord.ButtonStyle.primary, emoji="🌐")
    async def all_btn(self, interaction: discord.Interaction, button: Button):
        self.mode = "all"
        await self.update_message(interaction)

    @discord.ui.button(label="اليوم", style=discord.ButtonStyle.secondary, emoji="📅")
    async def daily_btn(self, interaction: discord.Interaction, button: Button):
        self.mode = "daily"
        await self.update_message(interaction)

    @discord.ui.button(label="الأسبوع", style=discord.ButtonStyle.secondary, emoji="📆")
    async def weekly_btn(self, interaction: discord.Interaction, button: Button):
        self.mode = "weekly"
        await self.update_message(interaction)

    @discord.ui.button(label="الشهر", style=discord.ButtonStyle.secondary, emoji="📅")
    async def monthly_btn(self, interaction: discord.Interaction, button: Button):
        self.mode = "monthly"
        await self.update_message(interaction)

    @discord.ui.button(label="تحديث", style=discord.ButtonStyle.success, emoji="🔄")
    async def refresh_btn(self, interaction: discord.Interaction, button: Button):
        new_doc = await stats_collection.find_one({"_id": "stats"})
        if new_doc:
            self.stat_doc = new_doc
        await self.update_message(interaction)

class MyWorksView(View):
    def __init__(self, works, bonuses, deductions, records, user_id, display_name, ctx_interaction):
        super().__init__(timeout=180)
        self.works = works
        self.bonuses = bonuses
        self.deductions = deductions
        self.records = records
        self.user_id = user_id
        self.display_name = display_name
        self.ctx_interaction = ctx_interaction
        self.sort_order = "amount_desc"
        self.message = None

    def sorted_works_items(self):
        items = list(self.works.items())
        if self.sort_order == "amount_desc":
            items.sort(key=lambda x: sum(e.get("total",0) for e in x[1]), reverse=True)
        elif self.sort_order == "amount_asc":
            items.sort(key=lambda x: sum(e.get("total",0) for e in x[1]))
        elif self.sort_order == "name_asc":
            items.sort(key=lambda x: x[0].lower())
        elif self.sort_order == "chapters_desc":
            items.sort(key=lambda x: len(x[1]), reverse=True)
        return items

    def build_embed(self):
        embed = make_embed("finance", f"💼 اللوحة الشخصية • {self.display_name}", "ملخص مالي وحسابي لأعمالك.", self.ctx_interaction, self.ctx_interaction.user)
        total_all = 0
        for work, entries in self.sorted_works_items():
            work_total = sum(e.get("total", 0) for e in entries)
            total_all += work_total
            chapters_count = len(entries)
            types_count = {}
            for e in entries:
                wtype = e.get("work_type")
                types_count[wtype] = types_count.get(wtype, 0) + 1
            type_str = ", ".join([f"**{k.replace('_',' ').title()}:** {v}" for k,v in types_count.items() if v>0])
            embed.add_field(
                name=f"**▸ {work}**",
                value=f"**الفصول:** {chapters_count}\n**التفصيل:** {type_str}\n**المجموع:** {format_currency(work_total)}",
                inline=False
            )

        total_bonus = sum(e.get("total", 0) for e in self.bonuses)
        total_deduction = sum(abs(e.get("total", 0)) for e in self.deductions)
        total_all += total_bonus - total_deduction

        if self.bonuses or self.deductions:
            details = ""
            if total_bonus > 0:
                details += f"🎁 إجمالي المكافآت: {format_currency(total_bonus)}\n"
            if total_deduction > 0:
                details += f"🔻 إجمالي الخصومات: {format_currency(total_deduction)}\n"
            embed.add_field(name="**⚖️ مكافآت وخصومات**", value=details, inline=False)

        embed.add_field(name="💵 الصافي النهائي", value=format_currency(total_all), inline=False)
        return embed

    async def update_message(self, interaction):
        embed = self.build_embed()
        if self.message is None:
            await interaction.response.send_message(embed=embed, view=self, ephemeral=True)
            self.message = await interaction.original_response()
        else:
            await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.select(
        placeholder="ترتيب الأعمال...",
        options=[
            discord.SelectOption(label="المبلغ (تنازلي)", value="amount_desc", emoji="💰"),
            discord.SelectOption(label="المبلغ (تصاعدي)", value="amount_asc", emoji="💸"),
            discord.SelectOption(label="الاسم (أبجدي)", value="name_asc", emoji="🔤"),
            discord.SelectOption(label="عدد الفصول", value="chapters_desc", emoji="📖"),
        ]
    )
    async def sort_select(self, interaction: discord.Interaction, select: Select):
        self.sort_order = select.values[0]
        await self.update_message(interaction)

    @discord.ui.button(label="عرض تفاصيل الأعمال", style=discord.ButtonStyle.primary, emoji="📋")
    async def details_btn(self, interaction: discord.Interaction, button: Button):
        view = WorkDetailButtonsView(self.works, self.user_id, self.display_name)
        embed = discord.Embed(title="اختر عملاً لعرض التفاصيل", color=discord.Color.blurple())
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="تقرير أسبوعي", style=discord.ButtonStyle.success, emoji="📅")
    async def weekly_report_btn(self, interaction: discord.Interaction, button: Button):
        records = await load_records()
        user_id = str(interaction.user.id)
        entries = records.get(user_id, [])
        now = datetime.now(timezone.utc)
        week_ago = now - timedelta(days=7)
        week_entries = [e for e in entries if "timestamp" in e and datetime.fromisoformat(e["timestamp"]) > week_ago]
        if not week_entries:
            await interaction.response.send_message("لا يوجد فصول خلال الأسبوع الماضي.", ephemeral=True)
            return
        total = sum(e.get("total", 0) for e in week_entries)
        daily_counts = {}
        for e in week_entries:
            day = datetime.fromisoformat(e["timestamp"]).strftime("%A")
            daily_counts[day] = daily_counts.get(day, 0) + 1
        days_list = week_days_labels()
        lines = []
        for day in days_list:
            cnt = daily_counts.get(day, 0)
            bar = make_bar((cnt / max(1, len(week_entries))) * 100, 6)
            lines.append(f"{day}: {bar} {cnt} فصل")
        embed = discord.Embed(title="📅 تقريرك الأسبوعي", color=discord.Color.green())
        embed.add_field(name="عدد المهام", value=len(week_entries), inline=True)
        embed.add_field(name="المجموع", value=format_currency(total), inline=True)
        embed.add_field(name="التفصيل اليومي", value="\n".join(lines), inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

class WorkDetailButtonsView(View):
    def __init__(self, works, user_id, display_name):
        super().__init__(timeout=60)
        self.works = works
        self.user_id = user_id
        self.display_name = display_name
        for work, entries in list(works.items())[:5]:
            chapters_details = [
                {"chapter": e.get("chapter"), "type": e.get("work_type"), "total": e.get("total", 0), "notes": e.get("notes", "")}
                for e in entries
            ]
            btn = Button(label=f"📖 {work}", style=discord.ButtonStyle.secondary)
            async def callback(interaction, wn=work, ch_list=chapters_details):
                v = WorkDetailsView(wn, ch_list, self.user_id, self.display_name, SETTINGS.get('currency', '$'))
                await interaction.response.send_message(embed=v.get_embed(), view=v, ephemeral=True)
            btn.callback = callback
            self.add_item(btn)

class AuditLogView(View):
    def __init__(self, all_logs, guild):
        super().__init__(timeout=300)
        self.all_logs = all_logs
        self.guild = guild
        self.current_page = 0
        self.per_page = 5
        self.action_filter = None
        self.date_filter = None
        self.message = None

    def filtered_logs(self):
        logs = self.all_logs
        if self.action_filter:
            logs = [l for l in logs if l.get("action") == self.action_filter]
        if self.date_filter:
            start, end = self.date_filter
            logs = [
                l for l in logs
                if "timestamp" in l and (datetime.fromisoformat(l["timestamp"]) >= start and datetime.fromisoformat(l["timestamp"]) <= end)
            ]
        return logs

    def build_embed(self):
        logs = self.filtered_logs()
        total_pages = math.ceil(len(logs) / self.per_page) if logs else 1
        embed = discord.Embed(title="📜 سجل العمليات", color=discord.Color.dark_gray())
        start = self.current_page * self.per_page
        page_logs = logs[start:start+self.per_page]
        if not page_logs:
            embed.description = "لا توجد سجلات مطابقة."
            return embed
        for log in page_logs:
            embed.add_field(
                name=f"**{log.get('action', 'غير معروف')}**",
                value=f"بواسطة: <@{log.get('moderator_id')}>\nللـ: {log.get('target_id') if log.get('target_id') else 'عام'}\nالتفاصيل: {log.get('details')}\nالوقت: {log.get('timestamp')[:19]}",
                inline=False
            )
        embed.set_footer(text=f"الصفحة {self.current_page+1}/{total_pages} | استخدم القائمة للتصفية")
        return embed

    async def update_message(self, interaction):
        embed = self.build_embed()
        if self.message is None:
            await interaction.response.send_message(embed=embed, view=self)
            self.message = await interaction.original_response()
        else:
            await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="السابق", style=discord.ButtonStyle.secondary, emoji="⬅️")
    async def prev_page(self, interaction, button):
        if self.current_page > 0:
            self.current_page -= 1
            await self.update_message(interaction)
        else:
            await interaction.response.defer()

    @discord.ui.button(label="التالي", style=discord.ButtonStyle.secondary, emoji="➡️")
    async def next_page(self, interaction, button):
        logs = self.filtered_logs()
        if (self.current_page+1)*self.per_page < len(logs):
            self.current_page += 1
            await self.update_message(interaction)
        else:
            await interaction.response.defer()

    @discord.ui.select(
        placeholder="تصفية حسب العملية...",
        options=[
            discord.SelectOption(label="الكل", value="all", emoji="🔍"),
            discord.SelectOption(label="تعديل", value="تعديل", emoji="✏️"),
            discord.SelectOption(label="حذف", value="حذف", emoji="🗑️"),
            discord.SelectOption(label="إضافة", value="إضافة", emoji="➕"),
            discord.SelectOption(label="دفع", value="دفع", emoji="💸"),
        ],
        row=2
    )
    async def action_filter_select(self, interaction, select):
        val = select.values[0]
        self.action_filter = None if val == "all" else val
        self.current_page = 0
        await self.update_message(interaction)

    @discord.ui.button(label="نطاق زمني", style=discord.ButtonStyle.primary, emoji="📅", row=3)
    async def date_range_btn(self, interaction, button):
        modal = DateRangeModal(self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="تحديث", style=discord.ButtonStyle.success, emoji="🔄", row=3)
    async def refresh_btn(self, interaction, button):
        logs = await audit_collection.find().sort("timestamp", -1).limit(200).to_list(length=200)
        self.all_logs = logs
        self.current_page = 0
        await self.update_message(interaction)

class DashboardView(View):
    def __init__(self, interaction):
        super().__init__(timeout=300)
        self.interaction = interaction
        self.message = None

    async def refresh_embed(self):
        records = await load_records()
        total_users = len(records)
        total_entries = sum(len(entries) for entries in records.values())
        total_amount = sum(sum(e.get("total", 0) for e in entries) for entries in records.values())
        embed = make_embed("admin", "🖥️ لوحة التحكم الرئيسية", "مركز إدارة شامل للمشرفين.", self.interaction, self.interaction.user)
        embed.add_field(name="👥 عدد الأعضاء النشطين", value=total_users, inline=True)
        embed.add_field(name="📄 عدد السجلات الكلي", value=total_entries, inline=True)
        embed.add_field(name="💰 إجمالي المبالغ", value=format_currency(total_amount), inline=True)
        embed.add_field(name="⚙️ العملة", value=SETTINGS.get('currency', '$') or '$', inline=True)
        embed.add_field(name="🔔 قناة الإشعارات", value=f"<#{SETTINGS.get('notify_channel_id')}>" if SETTINGS.get('notify_channel_id') else "غير محدد", inline=True)
        embed.add_field(name="💾 قناة النسخ الاحتياطي", value=f"<#{SETTINGS.get('daily_backup_channel_id')}>" if SETTINGS.get('daily_backup_channel_id') else "غير محدد", inline=True)
        embed.add_field(name="⚠️ حد التنبيه", value=format_currency(SETTINGS.get('alert_threshold', 10)), inline=True)
        payment_day = SETTINGS.get("payment_day")
        embed.add_field(name="📅 موعد الدفع الشهري", value=f"يوم {payment_day} الساعة {SETTINGS.get('payment_hour', 0)}" if payment_day else "غير محدد", inline=True)
        return embed

    async def update_message(self, interaction=None):
        embed = await self.refresh_embed()
        if self.message is None:
            if interaction:
                await interaction.response.send_message(embed=embed, view=self)
                self.message = await interaction.original_response()
            else:
                pass
        else:
            await self.message.edit(embed=embed, view=self)

    @discord.ui.button(label="تغيير العملة", style=discord.ButtonStyle.primary, emoji="💱")
    async def currency_btn(self, interaction, button):
        modal = SettingModal("تغيير العملة", "currency", SETTINGS.get('currency', '$'), self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="تغيير موعد الدفع", style=discord.ButtonStyle.primary, emoji="📅")
    async def payment_day_btn(self, interaction, button):
        modal = SettingModal("تغيير يوم الدفع", "payment_day", SETTINGS.get('payment_day', 1), self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="تغيير حد التنبيه", style=discord.ButtonStyle.primary, emoji="⚠️")
    async def alert_threshold_btn(self, interaction, button):
        modal = SettingModal("تغيير حد التنبيه", "alert_threshold", SETTINGS.get('alert_threshold', 10), self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="تحديث الإحصائيات", style=discord.ButtonStyle.success, emoji="🔄")
    async def update_stats_btn(self, interaction, button):
        await interaction.response.defer(ephemeral=True)
        await update_stats()
        await self.update_message(interaction)

class WeeklyReportView(View):
    def __init__(self, user_id, user_name, interaction):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.user_name = user_name
        self.original_interaction = interaction
        self.message = None

    async def generate_report(self, include_previous=False):
        records = await load_records()
        entries = records.get(str(self.user_id), [])
        now = datetime.now(timezone.utc)
        week_ago = now - timedelta(days=7)
        two_weeks_ago = now - timedelta(days=14)
        current_week = [e for e in entries if "timestamp" in e and datetime.fromisoformat(e["timestamp"]) > week_ago]
        previous_week = [e for e in entries if "timestamp" in e and two_weeks_ago < datetime.fromisoformat(e["timestamp"]) <= week_ago]

        embed = discord.Embed(title=f"📅 تقرير {self.user_name} الأسبوعي", color=discord.Color.green())
        embed.add_field(name="الفصول هذا الأسبوع", value=len(current_week), inline=True)
        embed.add_field(name="المبلغ هذا الأسبوع", value=format_currency(sum(e.get("total",0) for e in current_week)), inline=True)
        if include_previous and previous_week:
            prev_total = sum(e.get("total",0) for e in previous_week)
            change = (sum(e.get("total",0) for e in current_week) - prev_total)
            sign = "+" if change >= 0 else ""
            embed.add_field(name="التغير عن الأسبوع الماضي", value=f"{sign}{format_currency(change)}", inline=True)

        days = week_days_labels()
        daily_counts = {}
        for e in current_week:
            day = datetime.fromisoformat(e["timestamp"]).strftime("%A")
            daily_counts[day] = daily_counts.get(day, 0) + 1
        max_count = max(daily_counts.values()) if daily_counts else 1
        lines = []
        for day in days:
            cnt = daily_counts.get(day, 0)
            pct = (cnt / max_count) * 100
            bar = make_bar(pct, 8)
            lines.append(f"**{day}**: {bar} {cnt} فصل")
        embed.add_field(name="📊 النشاط اليومي", value="\n".join(lines), inline=False)
        return embed

    async def update_message(self, interaction, include_previous=False):
        embed = await self.generate_report(include_previous)
        if self.message is None:
            await interaction.response.send_message(embed=embed, view=self)
            self.message = await interaction.original_response()
        else:
            await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="مقارنة بالأسبوع الماضي", style=discord.ButtonStyle.primary, emoji="📈")
    async def compare_btn(self, interaction, button):
        await self.update_message(interaction, include_previous=True)

class EditRecordView(View):
    def __init__(self, records, user_id, interaction):
        super().__init__(timeout=60)
        self.records = records
        self.user_id = user_id
        self.interaction = interaction
        self.message = None
        entries = records.get(user_id, [])
        last_five = entries[-5:]
        options = []
        for i, entry in enumerate(reversed(last_five)):
            idx = len(entries) - 1 - i
            desc = f"{entry.get('work_name','?')} - {entry.get('chapter','?')}"
            options.append(discord.SelectOption(label=f"السجل #{idx+1}", description=desc[:50], value=str(idx)))
        if options:
            self.select.options = options
        else:
            self.remove_item(self.select)

    @discord.ui.select(placeholder="اختر السجل الذي تريد تعديله", min_values=1, max_values=1)
    async def select(self, interaction: discord.Interaction, select: Select):
        idx = int(select.values[0])
        entries = self.records.get(self.user_id, [])
        if idx >= len(entries):
            await interaction.response.send_message("السجل غير موجود.", ephemeral=True)
            return
        record = entries[idx]
        modal = EditEntryModal(record, self)
        modal.parent_view.entry_index = idx
        await interaction.response.send_modal(modal)

    async def update_original(self):
        if self.message:
            await self.message.edit(view=None)

# ----------------------------------------------------------------------
# Commands
# ----------------------------------------------------------------------
@bot.tree.command(name="الأعمال", description="عرض جميع الأعمال والاعضاء مع بحث وترتيب متقدم")
@app_commands.checks.cooldown(1, 5, key=lambda i: (i.user.id, i.command.qualified_name))
async def projects_report(interaction: discord.Interaction):
    if interaction.channel.name not in SETTINGS.get("allowed_channels", []):
        await interaction.response.send_message("❌ القناة غير مسموحة.", ephemeral=True)
        return
    works_info = await get_works_info(interaction.guild)
    if not works_info:
        await interaction.response.send_message("📭 لا توجد أعمال مسجلة في القائمة.", ephemeral=True)
        return
    view = EnhancedWorksView(works_info, interaction.guild)
    await view.update_message(interaction)

@bot.tree.command(name="احصائيات", description="عرض إحصائيات متقدمة مع رسوم بيانية وتفاعلية")
@app_commands.checks.cooldown(1, 5, key=lambda i: (i.user.id, i.command.qualified_name))
async def stats(interaction: discord.Interaction):
    stat_doc = await stats_collection.find_one({"_id": "stats"})
    if not stat_doc:
        await interaction.response.send_message("لا توجد إحصائيات بعد.", ephemeral=True)
        return
    view = StatsView(stat_doc, interaction)
    await view.update_message(interaction)

@bot.tree.command(name="أعمالي", description="عرض أعمالك مجمعة مع المكافآت والخصومات وترتيب وإجراءات")
@app_commands.checks.cooldown(1, 5, key=lambda i: (i.user.id, i.command.qualified_name))
async def my_works_slash(interaction: discord.Interaction):
    if interaction.channel.name not in SETTINGS.get("allowed_channels", []):
        await interaction.response.send_message("❌ القناة غير مسموحة.", ephemeral=True)
        return
    records = await load_records()
    user_id = str(interaction.user.id)
    if user_id not in records or not records[user_id]:
        await interaction.response.send_message("📭 ليس لديك أي شغل.", ephemeral=True)
        return

    works = {}
    bonuses = []
    deductions = []
    for entry in records[user_id]:
        wtype = entry.get("work_type")
        if wtype == "مكافأة":
            bonuses.append(entry)
        elif wtype == "خصم":
            deductions.append(entry)
        else:
            work = entry.get("work_name", "غير محدد")
            works.setdefault(work, []).append(entry)

    view = MyWorksView(works, bonuses, deductions, records, user_id, interaction.user.display_name, interaction)
    await view.update_message(interaction)

@bot.command(name="أعمالي")
@commands.cooldown(1, 5, commands.BucketType.user)
async def my_works_text(ctx):
    records = await load_records()
    user_id = str(ctx.author.id)
    if user_id not in records or not records[user_id]:
        await ctx.send("📭 ليس لديك أي شغل.")
        return
    works = {}
    bonuses = []
    deductions = []
    for entry in records[user_id]:
        wtype = entry.get("work_type")
        if wtype == "مكافأة":
            bonuses.append(entry)
        elif wtype == "خصم":
            deductions.append(entry)
        else:
            work = entry.get("work_name", "غير محدد")
            works.setdefault(work, []).append(entry)

    embed = discord.Embed(title=f"**📚 أعمال {ctx.author.display_name}**", color=discord.Color.blue())
    total_all = 0
    for work, entries in works.items():
        work_total = sum(e.get("total", 0) for e in entries)
        total_all += work_total
        chapters_count = len(entries)
        types_count = {}
        for e in entries:
            wtype = e.get("work_type")
            types_count[wtype] = types_count.get(wtype, 0) + 1
        type_str = ", ".join([f"**{k.replace('_',' ').title()}:** {v}" for k,v in types_count.items() if v>0])
        embed.add_field(name=f"**▸ {work}**", value=f"**الفصول:** {chapters_count}\n**التفصيل:** {type_str}\n**المجموع:** {format_currency(work_total)}", inline=False)
    total_bonus = sum(e.get("total", 0) for e in bonuses)
    total_deduction = sum(abs(e.get("total", 0)) for e in deductions)
    total_all += total_bonus - total_deduction
    if bonuses or deductions:
        details = ""
        if total_bonus > 0:
            details += f"🎁 إجمالي المكافآت: {format_currency(total_bonus)}\n"
        if total_deduction > 0:
            details += f"🔻 إجمالي الخصومات: {format_currency(total_deduction)}\n"
        embed.add_field(name="**⚖️ مكافآت وخصومات**", value=details, inline=False)
    embed.add_field(name="💵 الصافي النهائي", value=format_currency(total_all), inline=False)
    await ctx.send(embed=embed)

@bot.tree.command(name="شغل", description="عرض شغل عضو مجمّع مع المكافآت والخصومات وترتيب")
@app_commands.checks.cooldown(1, 5, key=lambda i: (i.user.id, i.command.qualified_name))
async def show_work_slash(interaction: discord.Interaction, member: discord.Member = None):
    if interaction.channel.name not in SETTINGS.get("allowed_channels", []):
        await interaction.response.send_message("❌ القناة غير مسموحة.", ephemeral=True)
        return
    target = member or interaction.user
    records = await load_records()
    user_id = str(target.id)
    if user_id not in records or not records[user_id]:
        await interaction.response.send_message(f"📭 لا يوجد شغل للعضو {target.mention}.", ephemeral=True)
        return

    works = {}
    bonuses = []
    deductions = []
    for entry in records[user_id]:
        wtype = entry.get("work_type")
        if wtype == "مكافأة":
            bonuses.append(entry)
        elif wtype == "خصم":
            deductions.append(entry)
        else:
            work = entry.get("work_name", "غير محدد")
            works.setdefault(work, []).append(entry)

    view = MyWorksView(works, bonuses, deductions, records, user_id, target.display_name, interaction)
    await view.update_message(interaction)

@bot.command(name="شغل")
@commands.cooldown(1, 5, commands.BucketType.user)
async def show_work_text(ctx, member: discord.Member = None):
    member = member or ctx.author
    records = await load_records()
    user_id = str(member.id)
    if user_id not in records or not records[user_id]:
        await ctx.send(f"📭 ما عندي أي شغل للعضو {member.mention}.")
        return
    works = {}
    bonuses = []
    deductions = []
    for entry in records[user_id]:
        wtype = entry.get("work_type")
        if wtype == "مكافأة":
            bonuses.append(entry)
        elif wtype == "خصم":
            deductions.append(entry)
        else:
            work = entry.get("work_name", "غير محدد")
            works.setdefault(work, []).append(entry)

    embed = discord.Embed(title=f"**📚 شغل {member.display_name}**", color=discord.Color.blue())
    total_all = 0
    for work, entries in works.items():
        work_total = sum(e.get("total", 0) for e in entries)
        total_all += work_total
        chapters_count = len(entries)
        types_count = {}
        for e in entries:
            wtype = e.get("work_type")
            types_count[wtype] = types_count.get(wtype, 0) + 1
        type_str = ", ".join([f"**{k.replace('_',' ').title()}:** {v}" for k,v in types_count.items() if v>0])
        embed.add_field(name=f"**▸ {work}**", value=f"**الفصول:** {chapters_count}\n**التفصيل:** {type_str}\n**المجموع:** {format_currency(work_total)}", inline=False)
    total_bonus = sum(e.get("total", 0) for e in bonuses)
    total_deduction = sum(abs(e.get("total", 0)) for e in deductions)
    total_all += total_bonus - total_deduction
    if bonuses or deductions:
        details = ""
        if total_bonus > 0:
            details += f"🎁 إجمالي المكافآت: {format_currency(total_bonus)}\n"
        if total_deduction > 0:
            details += f"🔻 إجمالي الخصومات: {format_currency(total_deduction)}\n"
        embed.add_field(name="**⚖️ مكافآت وخصومات**", value=details, inline=False)
    embed.add_field(name="💵 الصافي النهائي", value=format_currency(total_all), inline=False)
    await ctx.send(embed=embed)

@bot.tree.command(name="لوحة_التحكم", description="لوحة تحكم تفاعلية للمشرفين مع أزرار تغيير الإعدادات")
@app_commands.checks.cooldown(1, 5, key=lambda i: (i.user.id, i.command.qualified_name))
async def dashboard(interaction: discord.Interaction):
    if not is_admin(interaction):
        await log_unauthorized(interaction.user.id, "لوحة_التحكم")
        await interaction.response.send_message("❌ ما عندك صلاحية.", ephemeral=True)
        return
    view = DashboardView(interaction)
    await view.update_message(interaction)

@bot.tree.command(name="سجل", description="عرض آخر 200 عملية إدارية مع تصفية وترقيم صفحات")
@app_commands.checks.cooldown(1, 5, key=lambda i: (i.user.id, i.command.qualified_name))
async def audit_log(interaction: discord.Interaction):
    if not is_admin(interaction):
        await log_unauthorized(interaction.user.id, "سجل")
        await interaction.response.send_message("❌ ما عندك صلاحية.", ephemeral=True)
        return
    logs = await audit_collection.find().sort("timestamp", -1).limit(200).to_list(length=200)
    if not logs:
        await interaction.response.send_message("لا توجد سجلات.", ephemeral=True)
        return
    view = AuditLogView(logs, interaction.guild)
    await view.update_message(interaction)

@bot.tree.command(name="تقريري", description="تقرير أسبوعي تفاعلي مع رسم بياني يومي ومقارنة")
@app_commands.checks.cooldown(1, 5, key=lambda i: (i.user.id, i.command.qualified_name))
async def my_weekly_report(interaction: discord.Interaction):
    records = await load_records()
    user_id = str(interaction.user.id)
    if user_id not in records:
        await interaction.response.send_message("ليس لديك أي سجلات.", ephemeral=True)
        return
    view = WeeklyReportView(user_id, interaction.user.display_name, interaction)
    await view.update_message(interaction, include_previous=False)

@bot.tree.command(name="تعديل", description="تعديل أحدث السجلات باستخدام قائمة اختيار ونافذة تحرير")
@app_commands.checks.cooldown(1, 5, key=lambda i: (i.user.id, i.command.qualified_name))
async def edit_last(interaction: discord.Interaction):
    records = await load_records()
    user_id = str(interaction.user.id)
    if user_id not in records or not records[user_id]:
        await interaction.response.send_message("لا يوجد سجلات.", ephemeral=True)
        return
    view = EditRecordView(records, user_id, interaction)
    embed = discord.Embed(title="تعديل السجلات", description="اختر السجل الذي ترغب في تعديله من القائمة.", color=discord.Color.orange())
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    view.message = await interaction.original_response()