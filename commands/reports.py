from datetime import datetime, timedelta
import discord
from discord import app_commands
from discord.ext import commands
from state import bot
from helpers.core import *
from helpers.core import make_embed
from views.paginators import WorkDetailsView, WorksPaginator, get_works_info


# ═══════════════════════════════════════════════════
# 🎨 كلاس عرض الأعمال (مع صورة العضو)
# ═══════════════════════════════════════════════════
class WorkSummarySelectView(discord.ui.View):
    def __init__(self, works, bonuses, deductions, member: discord.Member, user_id,
                 currency, title_prefix="📊 ملخص شغل"):
        super().__init__(timeout=300)
        self.works = works
        self.bonuses = bonuses
        self.deductions = deductions
        self.member = member
        self.user_id = user_id
        self.currency = currency or '$'
        self.title_prefix = title_prefix
        self.avatar_url = member.display_avatar.replace(size=256).url

        self.select_menu = discord.ui.Select(
            placeholder="اختر عملاً لعرض التفاصيل...",
            options=self._build_options()
        )
        self.select_menu.callback = self.select_callback
        self.add_item(self.select_menu)

    def _build_options(self):
        options = []
        sorted_works = sorted(self.works.keys())
        for i, work_name in enumerate(sorted_works):
            if i >= 24:
                break
            chapters = len(self.works[work_name])
            options.append(
                discord.SelectOption(
                    label=work_name,
                    value=work_name,
                    description=f"{chapters} فصول",
                    emoji="📖"
                )
            )
        if self.bonuses or self.deductions:
            options.append(
                discord.SelectOption(
                    label="المكافآت والخصومات",
                    value="__bonuses__",
                    description="تفاصيل المكافآت والخصومات",
                    emoji="⚖️"
                )
            )
        if len(self.works) > 1:
            options.append(
                discord.SelectOption(
                    label="عرض الكل",
                    value="__all__",
                    description="جميع الفصول مجمعة",
                    emoji="📚"
                )
            )
        return options

    async def select_callback(self, interaction: discord.Interaction):
        selected = interaction.data['values'][0]
        if selected == "__all__":
            embed = self.build_all_details_embed()
        elif selected == "__bonuses__":
            embed = self.build_bonuses_details_embed()
        else:
            embed = self.build_work_detail_embed(selected)
        self._switch_to_back_mode(embed)
        await interaction.response.edit_message(embed=embed, view=self)

    async def back_callback(self, interaction: discord.Interaction):
        embed = self.build_summary_embed()
        self.clear_items()
        self.select_menu = discord.ui.Select(
            placeholder="اختر عملاً لعرض التفاصيل...",
            options=self._build_options()
        )
        self.select_menu.callback = self.select_callback
        self.add_item(self.select_menu)
        await interaction.response.edit_message(embed=embed, view=self)

    def _switch_to_back_mode(self, new_embed=None):
        self.clear_items()
        back_btn = discord.ui.Button(label="🔙 رجوع", style=discord.ButtonStyle.secondary, row=1)
        back_btn.callback = self.back_callback
        self.add_item(back_btn)

    def _base_embed(self, title, color):
        embed = discord.Embed(
            title=title,
            color=color,
            timestamp=datetime.utcnow()
        )
        embed.set_author(
            name=self.member.display_name,
            icon_url=self.member.display_avatar.url
        )
        embed.set_thumbnail(url=self.avatar_url)
        return embed

    def build_summary_embed(self):
        gross = sum(sum(e.get("total", 0) for e in entries)
                    for entries in self.works.values())
        total_bonus = sum(e.get("total", 0) for e in self.bonuses)
        total_deduct = sum(abs(e.get("total", 0)) for e in self.deductions)
        net = gross + total_bonus - total_deduct
        total_works = len(self.works)
        total_chapters = sum(len(entries) for entries in self.works.values())

        embed = self._base_embed(
            f"{self.title_prefix} {self.member.display_name}",
            discord.Color.gold()
        )
        embed.add_field(name="📁 عدد الأعمال", value=str(total_works), inline=True)
        embed.add_field(name="📑 إجمالي الفصول", value=str(total_chapters), inline=True)
        embed.add_field(name="💰 إجمالي الأعمال", value=f"{self.currency}{gross:.2f}", inline=True)
        if total_bonus:
            embed.add_field(name="🎁 إجمالي المكافآت", value=f"{self.currency}{total_bonus:.2f}", inline=True)
        if total_deduct:
            embed.add_field(name="🔻 إجمالي الخصومات", value=f"{self.currency}{total_deduct:.2f}", inline=True)
        embed.add_field(name="💵 الصافي النهائي", value=f"{self.currency}{net:.2f}", inline=False)
        embed.set_footer(text="اختر عملاً من القائمة لعرض التفاصيل")
        return embed

    def build_work_detail_embed(self, work_name):
        entries = self.works[work_name]
        total = sum(e.get("total", 0) for e in entries)
        count = len(entries)
        types_count = {}
        for e in entries:
            t = e.get("work_type", "غير محدد")
            types_count[t] = types_count.get(t, 0) + 1
        type_str = ", ".join(
            f"**{k.replace('_',' ').title()}:** {v}"
            for k, v in types_count.items() if v > 0
        )

        embed = self._base_embed(f"📖 {work_name}", discord.Color.blue())
        embed.add_field(name="📑 عدد الفصول", value=str(count), inline=True)
        embed.add_field(name="💰 المجموع", value=f"{self.currency}{total:.2f}", inline=True)
        if type_str:
            embed.add_field(name="📊 التخصصات", value=type_str, inline=False)

        lines = []
        for i, e in enumerate(entries, 1):
            ch = e.get("chapter", "؟")
            tp = e.get("work_type", "غير محدد")
            amt = e.get("total", 0)
            note = e.get("notes", "")
            note_str = f" | {note}" if note else ""
            lines.append(f"**{i}.** {ch} ({tp}) {self.currency}{amt:.2f}{note_str}")

        if lines:
            text = "\n".join(lines)
            if len(text) > 1024:
                text = "\n".join(lines[:10]) + f"\n... والمزيد ({len(lines)-10} فصل إضافي)"
            embed.add_field(name="📋 قائمة الفصول", value=text, inline=False)
        embed.set_footer(text=f"تفاصيل العمل • {datetime.utcnow().strftime('%Y-%m-%d')}")
        return embed

    def build_all_details_embed(self):
        embed = self._base_embed(
            f"📚 جميع الفصول لـ {self.member.display_name}",
            discord.Color.purple()
        )
        for work_name, entries in self.works.items():
            total = sum(e.get("total", 0) for e in entries)
            cnt = len(entries)
            prefix = f"📖 {work_name} ({cnt} فصل - {self.currency}{total:.2f})"
            preview = []
            for e in entries[:5]:
                ch = e.get("chapter", "؟")
                tp = e.get("work_type", "غير محدد")
                amt = e.get("total", 0)
                preview.append(f"• {ch} ({tp}) {self.currency}{amt:.2f}")
            if len(entries) > 5:
                preview.append("... والمزيد")
            embed.add_field(name=prefix, value="\n".join(preview), inline=False)
        embed.set_footer(text="عرض إجمالي لجميع الأعمال")
        return embed

    def build_bonuses_details_embed(self):
        embed = self._base_embed("⚖️ المكافآت والخصومات", discord.Color.orange())
        if self.bonuses:
            bon = "\n".join(
                f"🎁 {e.get('chapter','مكافأة')}: {self.currency}{e.get('total',0):.2f} - {e.get('notes','')}"
                for e in self.bonuses
            )
            embed.add_field(name="المكافآت", value=bon, inline=False)
        else:
            embed.add_field(name="المكافآت", value="لا يوجد", inline=False)
        if self.deductions:
            ded = "\n".join(
                f"🔻 {e.get('chapter','خصم')}: {self.currency}{abs(e.get('total',0)):.2f} - {e.get('notes','')}"
                for e in self.deductions
            )
            embed.add_field(name="الخصومات", value=ded, inline=False)
        else:
            embed.add_field(name="الخصومات", value="لا يوجد", inline=False)
        embed.set_footer(text="تفاصيل المكافآت والخصومات")
        return embed


# ═══════════════════════════════════════════════════
# 📊 دوال مساعدة للإحصائيات (خارج الكلاسات)
# ═══════════════════════════════════════════════════
def get_top_members_dict(stat_doc):
    """تحويل top_members إلى قاموس مهما كان شكلها (list/dict)"""
    data = stat_doc.get("top_members", {})
    if isinstance(data, dict):
        return data
    if isinstance(data, list):
        result = {}
        for item in data:
            if isinstance(item, (list, tuple)) and len(item) == 2:
                result[str(item[0])] = item[1]
            elif isinstance(item, dict) and 'user_id' in item:
                result[str(item['user_id'])] = item
        return result
    return {}

async def build_top_embed(guild: discord.Guild, currency, stat_doc, sort_by="amount", work_type=None, limit=10):
    records = await load_records()
    all_members = get_top_members_dict(stat_doc)
    members_stats = [(uid, stats) for uid, stats in all_members.items()]

    if sort_by == "amount":
        sorted_list = sorted(members_stats, key=lambda x: x[1].get('total_amount', 0), reverse=True)
        title = f"🏆 أفضل {limit} أعضاء (إجمالي المبلغ)"
    elif sort_by == "chapters":
        sorted_list = sorted(members_stats, key=lambda x: x[1].get('total_entries', 0), reverse=True)
        title = f"📑 أفضل {limit} أعضاء (عدد الفصول)"
    elif sort_by == "by_type" and work_type:
        filtered = []
        for uid, stats in members_stats:
            uid_str = str(uid)
            if uid_str in records:
                count = sum(1 for e in records[uid_str] if e.get("work_type") == work_type)
                total = sum(e.get("total", 0) for e in records[uid_str] if e.get("work_type") == work_type)
                if count > 0:
                    filtered.append((uid, {"total_entries": count, "total_amount": total}))
        sorted_list = sorted(filtered, key=lambda x: x[1].get('total_amount', 0), reverse=True)
        title = f"🏆 أفضل {limit} أعضاء في {work_type.replace('_',' ').title()}"
    else:
        sorted_list = sorted(members_stats, key=lambda x: x[1].get('total_amount', 0), reverse=True)
        title = f"🏆 أفضل {limit} أعضاء"

    embed = discord.Embed(title=title, color=discord.Color.gold(), timestamp=datetime.utcnow())

    if not sorted_list:
        embed.description = "لا توجد بيانات كافية."
        return embed

    top_items = sorted_list[:limit]
    medals = ["🥇", "🥈", "🥉"] + ["🏅"] * (limit - 3)
    lines = []

    for i, (uid, stats_data) in enumerate(top_items, 1):
        uid_int = int(uid)
        member = guild.get_member(uid_int)  # محاولة من الكاش

        if member is None:
            try:
                # جلب العضو من API إذا لم يكن في الكاش
                member = await guild.fetch_member(uid_int)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                member = None

        if member:
            # العضو موجود في السيرفر - منشن حقيقي
            display = member.mention
        else:
            # العضو غير موجود (ربما غادر) - نعرض اسم مخزن أو ID
            uid_str = str(uid)
            fallback_name = None
            if uid_str in records:
                for e in records[uid_str]:
                    if e.get("username"):
                        fallback_name = e["username"]
                        break
            if not fallback_name:
                try:
                    user = await bot.fetch_user(uid_int)
                    fallback_name = user.display_name
                except:
                    fallback_name = f"مستخدم {uid_int}"
            display = f"**{fallback_name}** (غادر)"

        medal = medals[i-1] if i-1 < len(medals) else "🏅"
        if sort_by == "chapters":
            detail = f"{stats_data['total_entries']} فصل"
        else:
            detail = f"{currency}{stats_data['total_amount']:,.2f}"
        lines.append(f"{medal} `{i}.` {display}\n┗ {detail}")

    embed.add_field(name="الترتيب", value="\n".join(lines), inline=False)
    if len(top_items) < limit:
        embed.set_footer(text=f"يوجد فقط {len(top_items)} أعضاء في التصنيف الحالي • سيتم تحديث الإحصائية تلقائياً")
    else:
        embed.set_footer(text="ZEUS....")
    return embed


# ═══════════════════════════════════════════════════
# 📊 عارض الإحصائيات التفاعلي (أزرار + قوائم منسدلة)
# ═══════════════════════════════════════════════════
class StatsView(discord.ui.View):
    def __init__(self, stat_doc, bot_member, currency, guild: discord.Guild):
        super().__init__(timeout=300)
        self.stat_doc = stat_doc
        self.bot_member = bot_member
        self.currency = currency if currency else '$'
        self.guild = guild
        self.avatar_url = bot_member.display_avatar.replace(size=256).url
        self.current_page = "overview"
        self._show_main_buttons()

    def _show_main_buttons(self):
        self.clear_items()
        self.overview_btn = discord.ui.Button(label="🏠 الرئيسية", style=discord.ButtonStyle.success, row=0)
        self.types_btn    = discord.ui.Button(label="📊 التخصصات", style=discord.ButtonStyle.secondary, row=0)
        self.time_btn     = discord.ui.Button(label="⏳ زمني", style=discord.ButtonStyle.secondary, row=0)
        self.top_btn      = discord.ui.Button(label="🏆 الأفضل", style=discord.ButtonStyle.secondary, row=0)

        self.overview_btn.callback = self._overview_callback
        self.types_btn.callback    = self._types_callback
        self.time_btn.callback     = self._time_callback
        self.top_btn.callback      = self._enter_top_mode

        self.add_item(self.overview_btn)
        self.add_item(self.types_btn)
        self.add_item(self.time_btn)
        self.add_item(self.top_btn)

    async def _overview_callback(self, interaction: discord.Interaction):
        embed = self._overview_embed()
        self._set_active("overview")
        await interaction.response.edit_message(embed=embed, view=self)

    async def _types_callback(self, interaction: discord.Interaction):
        embed = self._types_embed()
        self._set_active("types")
        await interaction.response.edit_message(embed=embed, view=self)

    async def _time_callback(self, interaction: discord.Interaction):
        embed = self._time_embed()
        self._set_active("time")
        await interaction.response.edit_message(embed=embed, view=self)

    def _set_active(self, active):
        self.current_page = active
        for btn in [self.overview_btn, self.types_btn, self.time_btn, self.top_btn]:
            if btn.label.startswith({"overview":"🏠","types":"📊","time":"⏳","top":"🏆"}[active]):
                btn.style = discord.ButtonStyle.success
            else:
                btn.style = discord.ButtonStyle.secondary

    def _base_embed(self, title, color):
        embed = discord.Embed(title=title, color=color, timestamp=datetime.utcnow())
        embed.set_author(
            name=self.bot_member.display_name,
            icon_url=self.bot_member.display_avatar.url
        )
        embed.set_thumbnail(url=self.avatar_url)
        return embed

    def _overview_embed(self):
        total_entries = self.stat_doc.get("total_entries", 0)
        total_amount = self.stat_doc.get("total_amount", 0)
        active = len(get_top_members_dict(self.stat_doc))
        embed = self._base_embed("📊 لوحة الإحصائيات • النظرة العامة", discord.Color.teal())
        embed.add_field(name="📄 إجمالي الفصول", value=f"```py\n{total_entries}```", inline=True)
        embed.add_field(name="💰 إجمالي المبالغ",
                        value=f"```css\n{self.currency}{total_amount:,.2f}```", inline=True)
        embed.add_field(name="👥 الأعضاء النشطون", value=f"```yaml\n{active}```", inline=True)
        embed.set_footer(text="استخدم الأزرار أدناه لاستعراض الأقسام")
        return embed

    def _types_embed(self):
        total_entries = self.stat_doc.get("total_entries", 0)
        type_counts = self.stat_doc.get("type_counts", {})
        embed = self._base_embed("📊 تفصيل التخصصات", discord.Color.blue())
        if type_counts:
            lines = ""
            for k, v in type_counts.items():
                pct = (v / total_entries * 100) if total_entries else 0
                bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
                lines += f"**{k.replace('_',' ').title()}**: `{v:>4}` {bar}\n"
            embed.add_field(name="📊 التوزيع", value=lines, inline=False)
        else:
            embed.description = "لا توجد بيانات تخصصات بعد."
        embed.set_footer(text="النسب المئوية مقربة • شريط التقدم يمثل النسبة")
        return embed

    def _time_embed(self):
        daily   = self.stat_doc.get("daily",   {"entries":0, "amount":0})
        weekly  = self.stat_doc.get("weekly",  {"entries":0, "amount":0})
        monthly = self.stat_doc.get("monthly", {"entries":0, "amount":0})
        total_entries = self.stat_doc.get("total_entries", 0)
        total_amount  = self.stat_doc.get("total_amount", 0)

        embed = self._base_embed("📅 النظرة الزمنية", discord.Color.purple())
        embed.add_field(
            name="📅 اليوم",
            value=f"📑 `{daily['entries']}` فصل\n💰 `{self.currency}{daily['amount']:,.2f}`",
            inline=True
        )
        embed.add_field(
            name="📆 الأسبوع",
            value=f"📑 `{weekly['entries']}` فصل\n💰 `{self.currency}{weekly['amount']:,.2f}`",
            inline=True
        )
        embed.add_field(
            name="📅 الشهر",
            value=f"📑 `{monthly['entries']}` فصل\n💰 `{self.currency}{monthly['amount']:,.2f}`",
            inline=True
        )
        embed.add_field(
            name="🌐 الإجمالي الكلي (منذ البداية)",
            value=f"📑 `{total_entries}` فصل\n💰 `{self.currency}{total_amount:,.2f}`",
            inline=False
        )
        embed.set_footer(text="إحصائيات تراكمية لنفس اليوم / الأسبوع / الشهر")
        return embed

    # ── نظام "الأفضل" التفاعلي ──
    async def _enter_top_mode(self, interaction: discord.Interaction):
        self.clear_items()
        self.current_page = "top"
        options = [
            discord.SelectOption(label="الأفضل عاماً (إجمالي المبلغ)", value="amount", emoji="💰"),
            discord.SelectOption(label="الأفضل في الفصول (العدد)", value="chapters", emoji="📑"),
            discord.SelectOption(label="الأفضل في تخصص...", value="by_type", emoji="📊"),
        ]
        self.top_filter_select = discord.ui.Select(
            placeholder="اختر معيار التصنيف...",
            options=options,
            row=0
        )
        self.top_filter_select.callback = self._top_filter_selected
        self.add_item(self.top_filter_select)

        self.back_from_top_btn = discord.ui.Button(label="🔙 رجوع", style=discord.ButtonStyle.secondary, row=1)
        self.back_from_top_btn.callback = self._back_from_top
        self.add_item(self.back_from_top_btn)

        embed = await build_top_embed(self.guild, self.currency, self.stat_doc, "amount")
        await interaction.response.edit_message(embed=embed, view=self)

    async def _top_filter_selected(self, interaction: discord.Interaction):
        value = interaction.data['values'][0]
        if value == "by_type":
            self.clear_items()
            type_counts = self.stat_doc.get("type_counts", {})
            if not type_counts:
                embed = self._base_embed("🏆 الأفضل في تخصص", discord.Color.gold())
                embed.description = "لا توجد بيانات تخصصات."
                back_btn = discord.ui.Button(label="🔙 عودة", style=discord.ButtonStyle.secondary, row=1)
                back_btn.callback = self._enter_top_mode
                self.add_item(back_btn)
                await interaction.response.edit_message(embed=embed, view=self)
                return

            type_options = [
                discord.SelectOption(label=k.replace('_',' ').title(), value=k, emoji="📊")
                for k in type_counts.keys()
            ][:25]
            self.type_select = discord.ui.Select(
                placeholder="اختر التخصص...",
                options=type_options,
                row=0
            )
            self.type_select.callback = self._type_specific_selected
            self.add_item(self.type_select)

            self.back_to_filter_btn = discord.ui.Button(label="🔙 عودة للتصنيفات", style=discord.ButtonStyle.secondary, row=1)
            self.back_to_filter_btn.callback = self._enter_top_mode
            self.add_item(self.back_to_filter_btn)

            embed = self._base_embed("📊 اختر تخصصاً", discord.Color.blue())
            embed.description = "اختر أحد التخصصات لعرض أفضل الأعضاء فيه."
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            embed = await build_top_embed(self.guild, self.currency, self.stat_doc, value)
            self.clear_items()
            options = [
                discord.SelectOption(label="الأفضل عاماً (إجمالي المبلغ)", value="amount", emoji="💰"),
                discord.SelectOption(label="الأفضل في الفصول (العدد)", value="chapters", emoji="📑"),
                discord.SelectOption(label="الأفضل في تخصص...", value="by_type", emoji="📊"),
            ]
            self.top_filter_select = discord.ui.Select(
                placeholder="اختر معيار التصنيف...",
                options=options,
                row=0
            )
            self.top_filter_select.callback = self._top_filter_selected
            self.add_item(self.top_filter_select)

            self.back_from_top_btn = discord.ui.Button(label="🔙 رجوع", style=discord.ButtonStyle.secondary, row=1)
            self.back_from_top_btn.callback = self._back_from_top
            self.add_item(self.back_from_top_btn)

            await interaction.response.edit_message(embed=embed, view=self)

    async def _type_specific_selected(self, interaction: discord.Interaction):
        work_type = interaction.data['values'][0]
        embed = await build_top_embed(self.guild, self.currency, self.stat_doc, "by_type", work_type)
        self.clear_items()
        type_counts = self.stat_doc.get("type_counts", {})
        type_options = [
            discord.SelectOption(label=k.replace('_',' ').title(), value=k, emoji="📊")
            for k in type_counts.keys()
        ][:25]
        self.type_select = discord.ui.Select(
            placeholder="اختر التخصص...",
            options=type_options,
            row=0
        )
        self.type_select.callback = self._type_specific_selected
        self.add_item(self.type_select)

        self.back_to_filter_btn = discord.ui.Button(label="🔙 عودة للتصنيفات", style=discord.ButtonStyle.secondary, row=1)
        self.back_to_filter_btn.callback = self._enter_top_mode
        self.add_item(self.back_to_filter_btn)

        await interaction.response.edit_message(embed=embed, view=self)

    async def _back_from_top(self, interaction: discord.Interaction):
        self._show_main_buttons()
        self._set_active("overview")
        embed = self._overview_embed()
        await interaction.response.edit_message(embed=embed, view=self)


# ═══════════════════════════════════════════════════
# 🆕 عارض مستقل لأمر /توب (بدون أزرار الإحصائيات)
# ═══════════════════════════════════════════════════
class TopView(discord.ui.View):
    def __init__(self, stat_doc, guild: discord.Guild, currency):
        super().__init__(timeout=300)
        self.stat_doc = stat_doc
        self.guild = guild
        self.currency = currency if currency else '$'
        self.bot_member = guild.me
        self.avatar_url = self.bot_member.display_avatar.replace(size=256).url

        # البدء مباشرة بقائمة التصنيف
        self._show_filter_menu()

    def _base_embed(self, title, color=discord.Color.gold()):
        embed = discord.Embed(title=title, color=color, timestamp=datetime.utcnow())
        embed.set_author(name=self.bot_member.display_name, icon_url=self.bot_member.display_avatar.url)
        embed.set_thumbnail(url=self.avatar_url)
        return embed

    def _show_filter_menu(self):
        self.clear_items()
        options = [
            discord.SelectOption(label="الأفضل عاماً (إجمالي المبلغ)", value="amount", emoji="💰"),
            discord.SelectOption(label="الأفضل في الفصول (العدد)", value="chapters", emoji="📑"),
            discord.SelectOption(label="الأفضل في تخصص...", value="by_type", emoji="📊"),
        ]
        self.filter_select = discord.ui.Select(
            placeholder="اختر معيار التصنيف...",
            options=options,
            row=0
        )
        self.filter_select.callback = self._filter_selected
        self.add_item(self.filter_select)

    async def _filter_selected(self, interaction: discord.Interaction):
        value = interaction.data['values'][0]
        if value == "by_type":
            self.clear_items()
            type_counts = self.stat_doc.get("type_counts", {})
            if not type_counts:
                embed = self._base_embed("🏆 الأفضل في تخصص")
                embed.description = "لا توجد بيانات تخصصات."
                back_btn = discord.ui.Button(label="🔙 رجوع", style=discord.ButtonStyle.secondary, row=1)
                back_btn.callback = self._go_back_to_filter
                self.add_item(back_btn)
                await interaction.response.edit_message(embed=embed, view=self)
                return

            type_options = [
                discord.SelectOption(label=k.replace('_',' ').title(), value=k, emoji="📊")
                for k in type_counts.keys()
            ][:25]
            self.type_select = discord.ui.Select(
                placeholder="اختر التخصص...",
                options=type_options,
                row=0
            )
            self.type_select.callback = self._type_selected
            self.add_item(self.type_select)

            self.back_btn = discord.ui.Button(label="🔙 رجوع", style=discord.ButtonStyle.secondary, row=1)
            self.back_btn.callback = self._go_back_to_filter
            self.add_item(self.back_btn)

            embed = self._base_embed("📊 اختر تخصصاً", discord.Color.blue())
            embed.description = "اختر أحد التخصصات لعرض أفضل الأعضاء فيه."
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            embed = await build_top_embed(self.guild, self.currency, self.stat_doc, value)
            # نظهر القائمة مرة أخرى مع النتيجة
            self._show_filter_menu()
            await interaction.response.edit_message(embed=embed, view=self)

    async def _type_selected(self, interaction: discord.Interaction):
        work_type = interaction.data['values'][0]
        embed = await build_top_embed(self.guild, self.currency, self.stat_doc, "by_type", work_type)
        # نبقي قائمة التخصصات ظاهرة
        self.clear_items()
        type_counts = self.stat_doc.get("type_counts", {})
        type_options = [
            discord.SelectOption(label=k.replace('_',' ').title(), value=k, emoji="📊")
            for k in type_counts.keys()
        ][:25]
        self.type_select = discord.ui.Select(
            placeholder="اختر التخصص...",
            options=type_options,
            row=0
        )
        self.type_select.callback = self._type_selected
        self.add_item(self.type_select)

        self.back_btn = discord.ui.Button(label="🔙 رجوع", style=discord.ButtonStyle.secondary, row=1)
        self.back_btn.callback = self._go_back_to_filter
        self.add_item(self.back_btn)

        await interaction.response.edit_message(embed=embed, view=self)

    async def _go_back_to_filter(self, interaction: discord.Interaction):
        self._show_filter_menu()
        embed = self._base_embed("🏆 ترتيب الأعضاء", discord.Color.gold())
        embed.description = "اختر معيار التصنيف من القائمة أدناه."
        await interaction.response.edit_message(embed=embed, view=self)


# ═══════════════════════════════════════════════
# 1️⃣ أمر الأعمال
# ═══════════════════════════════════════════════
@bot.tree.command(name="الأعمال", description="عرض جميع الأعمال والاعضاء")
@app_commands.checks.cooldown(1, 5, key=lambda i: (i.user.id, i.command.qualified_name))
async def projects_report(interaction: discord.Interaction):
    if interaction.channel.name not in SETTINGS.get("allowed_channels", []):
        await interaction.response.send_message("❌ القناة غير مسموحة.", ephemeral=True)
        return

    works_info = await get_works_info(interaction.guild)
    if not works_info:
        await interaction.response.send_message("📭 لا توجد أعمال مسجلة في القائمة.", ephemeral=True)
        return

    embed = discord.Embed(title="📚 **قائمة الأعمال**", color=discord.Color.purple())
    embed.add_field(name="عدد الأعمال", value=str(len(works_info)), inline=False)
    embed.set_footer(text="اختر عملاً من القائمة لرؤية المساهمين. استخدم أزرار التنقل للصفحات.")
    view = WorksPaginator(works_info, interaction.guild)
    await interaction.response.send_message(embed=embed, view=view)


# ═══════════════════════════════════════════════
# 2️⃣ إحصائيات (نظام تفاعلي كامل)
# ═══════════════════════════════════════════════
@bot.tree.command(name="احصائيات", description="عرض إحصائيات متقدمة")
@app_commands.checks.cooldown(1, 5, key=lambda i: (i.user.id, i.command.qualified_name))
async def stats(interaction: discord.Interaction):
    stat_doc = await stats_collection.find_one({"_id": "stats"})
    if not stat_doc:
        await interaction.response.send_message("لا توجد إحصائيات بعد.", ephemeral=True)
        return

    bot_member = interaction.guild.me
    currency = SETTINGS.get('currency', '$') or '$'
    view = StatsView(stat_doc, bot_member, currency, interaction.guild)
    embed = view._overview_embed()
    await interaction.response.send_message(embed=embed, view=view)


# ═══════════════════════════════════════════════
# 2.5️⃣ /توب (ترتيب الأعضاء المستقل)
# ═══════════════════════════════════════════════
@bot.tree.command(name="توب", description="عرض ترتيب الأعضاء حسب معايير مختلفة")
@app_commands.checks.cooldown(1, 5, key=lambda i: (i.user.id, i.command.qualified_name))
async def top_members(interaction: discord.Interaction):
    stat_doc = await stats_collection.find_one({"_id": "stats"})
    if not stat_doc:
        await interaction.response.send_message("لا توجد بيانات إحصائية بعد.", ephemeral=True)
        return

    currency = SETTINGS.get('currency', '$') or '$'
    view = TopView(stat_doc, interaction.guild, currency)
    embed = view._base_embed("🏆 ترتيب الأعضاء", discord.Color.gold())
    embed.description = "اختر معيار التصنيف من القائمة أدناه."
    await interaction.response.send_message(embed=embed, view=view)


# ═══════════════════════════════════════════════
# 3️⃣ أعمالي
# ═══════════════════════════════════════════════
@bot.tree.command(name="أعمالي", description="عرض أعمالك مجمعة مع المكافآت والخصومات")
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

    works, bonuses, deductions = _categorize_records(records[user_id])
    view = WorkSummarySelectView(
        works, bonuses, deductions,
        member=interaction.user,
        user_id=user_id,
        currency=SETTINGS.get('currency', '$'),
        title_prefix="💼 اللوحة الشخصية •"
    )
    embed = view.build_summary_embed()
    await interaction.response.send_message(embed=embed, view=view)


@bot.command(name="أعمالي")
@commands.cooldown(1, 5, commands.BucketType.user)
async def my_works_text(ctx):
    records = await load_records()
    user_id = str(ctx.author.id)
    if user_id not in records or not records[user_id]:
        await ctx.send("📭 ليس لديك أي شغل.")
        return

    works, bonuses, deductions = _categorize_records(records[user_id])
    view = WorkSummarySelectView(
        works, bonuses, deductions,
        member=ctx.author,
        user_id=user_id,
        currency=SETTINGS.get('currency', '$'),
        title_prefix="💼 اللوحة الشخصية •"
    )
    embed = view.build_summary_embed()
    await ctx.send(embed=embed, view=view)


# ═══════════════════════════════════════════════
# 4️⃣ شغل
# ═══════════════════════════════════════════════
@bot.tree.command(name="شغل", description="عرض شغل عضو مجمّع مع المكافآت والخصومات")
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

    works, bonuses, deductions = _categorize_records(records[user_id])
    view = WorkSummarySelectView(
        works, bonuses, deductions,
        member=target,
        user_id=user_id,
        currency=SETTINGS.get('currency', '$'),
        title_prefix="📊 ملخص شغل"
    )
    embed = view.build_summary_embed()
    await interaction.response.send_message(embed=embed, view=view)


@bot.command(name="شغل")
@commands.cooldown(1, 5, commands.BucketType.user)
async def show_work_text(ctx, member: discord.Member = None):
    member = member or ctx.author
    records = await load_records()
    user_id = str(member.id)
    if user_id not in records or not records[user_id]:
        await ctx.send(f"📭 ما عندي أي شغل للعضو {member.mention}.")
        return

    works, bonuses, deductions = _categorize_records(records[user_id])
    view = WorkSummarySelectView(
        works, bonuses, deductions,
        member=member,
        user_id=user_id,
        currency=SETTINGS.get('currency', '$'),
        title_prefix="📊 ملخص شغل"
    )
    embed = view.build_summary_embed()
    await ctx.send(embed=embed, view=view)


def _categorize_records(entries):
    works = {}
    bonuses = []
    deductions = []
    for entry in entries:
        wtype = entry.get("work_type")
        if wtype == "مكافأة":
            bonuses.append(entry)
        elif wtype == "خصم":
            deductions.append(entry)
        else:
            work = entry.get("work_name", "غير محدد")
            works.setdefault(work, []).append(entry)
    return works, bonuses, deductions


# ═══════════════════════════════════════════════
# 5️⃣ لوحة التحكم
# ═══════════════════════════════════════════════
@bot.tree.command(name="لوحة_التحكم", description="لوحة تحكم للمشرفين")
@app_commands.checks.cooldown(1, 5, key=lambda i: (i.user.id, i.command.qualified_name))
async def dashboard(interaction: discord.Interaction):
    if not is_admin(interaction):
        await log_unauthorized(interaction.user.id, "لوحة_التحكم")
        await interaction.response.send_message("❌ ما عندك صلاحية.", ephemeral=True)
        return

    records = await load_records()
    total_users = len(records)
    total_entries = sum(len(entries) for entries in records.values())
    total_amount = sum(sum(e.get("total", 0) for e in entries) for entries in records.values())

    embed = make_embed("admin", "🖥️ لوحة التحكم الرئيسية", "مركز إدارة شامل للمشرفين.",
                       interaction, interaction.user)
    embed.add_field(name="**👥 عدد الأعضاء النشطين**", value=total_users, inline=True)
    embed.add_field(name="**📄 عدد السجلات الكلي**", value=total_entries, inline=True)
    embed.add_field(name="**💰 إجمالي المبالغ**",
                    value=f"{SETTINGS.get('currency', '$')}{total_amount:.2f}", inline=True)
    embed.add_field(name="**⚙️ العملة**", value=SETTINGS.get('currency', '$'), inline=True)
    embed.add_field(
        name="**🔔 قناة الإشعارات**",
        value=f"<#{SETTINGS.get('notify_channel_id')}>" if SETTINGS.get('notify_channel_id') else "غير محدد",
        inline=True
    )
    embed.add_field(
        name="**💾 قناة النسخ الاحتياطي**",
        value=f"<#{SETTINGS.get('daily_backup_channel_id')}>" if SETTINGS.get('daily_backup_channel_id') else "غير محدد",
        inline=True
    )
    embed.add_field(
        name="**⚠️ حد التنبيه**",
        value=f"{SETTINGS.get('currency', '$')}{SETTINGS.get('alert_threshold', 10):.2f}",
        inline=True
    )
    payment_day = SETTINGS.get("payment_day")
    embed.add_field(
        name="**📅 موعد الدفع الشهري**",
        value=f"يوم {payment_day} الساعة {SETTINGS.get('payment_hour', 0)}" if payment_day else "غير محدد",
        inline=True
    )
    await interaction.response.send_message(embed=embed)


# ═══════════════════════════════════════════════
# 6️⃣ سجل العمليات
# ═══════════════════════════════════════════════
@bot.tree.command(name="سجل", description="عرض آخر 20 عملية إدارية")
@app_commands.checks.cooldown(1, 5, key=lambda i: (i.user.id, i.command.qualified_name))
async def audit_log(interaction: discord.Interaction):
    if not is_admin(interaction):
        await log_unauthorized(interaction.user.id, "سجل")
        await interaction.response.send_message("❌ ما عندك صلاحية.", ephemeral=True)
        return

    logs = await audit_collection.find().sort("timestamp", -1).limit(20).to_list(length=20)
    if not logs:
        await interaction.response.send_message("لا توجد سجلات.", ephemeral=True)
        return

    embed = discord.Embed(title="📜 **سجل العمليات**", color=discord.Color.dark_gray())
    for log in logs:
        embed.add_field(
            name=f"**{log.get('action', 'غير معروف')}**",
            value=(
                f"بواسطة: <@{log.get('moderator_id')}>\n"
                f"للـ: {log.get('target_id') if log.get('target_id') else 'عام'}\n"
                f"التفاصيل: {log.get('details')}\n"
                f"الوقت: {log.get('timestamp')[:19]}"
            ),
            inline=False
        )
    await interaction.response.send_message(embed=embed)


# ═══════════════════════════════════════════════
# 7️⃣ تقرير أسبوعي شخصي
# ═══════════════════════════════════════════════
@bot.tree.command(name="تقريري", description="تقرير أسبوعي خاص بك")
@app_commands.checks.cooldown(1, 5, key=lambda i: (i.user.id, i.command.qualified_name))
async def my_weekly_report(interaction: discord.Interaction):
    records = await load_records()
    user_id = str(interaction.user.id)
    if user_id not in records:
        await interaction.response.send_message("ليس لديك أي سجلات.", ephemeral=True)
        return

    week_ago = datetime.utcnow() - timedelta(days=7)
    week_entries = [
        e for e in records[user_id]
        if "timestamp" in e and datetime.fromisoformat(e["timestamp"]) > week_ago
    ]
    if not week_entries:
        await interaction.response.send_message("لا يوجد فصول خلال الأسبوع الماضي.", ephemeral=True)
        return

    total = sum(e.get("total", 0) for e in week_entries)
    embed = discord.Embed(title="📅 **تقريرك الأسبوعي**", color=discord.Color.green())
    embed.add_field(name="**عدد المهام**", value=len(week_entries), inline=True)
    embed.add_field(name="**المجموع**", value=f"{SETTINGS.get('currency', '$')}{total:.2f}", inline=True)
    await interaction.response.send_message(embed=embed)


# ═══════════════════════════════════════════════
# 8️⃣ تعديل آخر سجل
# ═══════════════════════════════════════════════
@bot.tree.command(name="تعديل", description="تعديل آخر سجل قمت بإضافته")
@app_commands.checks.cooldown(1, 5, key=lambda i: (i.user.id, i.command.qualified_name))
async def edit_last(interaction: discord.Interaction,
                    العمل: str = None,
                    الفصل: str = None,
                    التخصص: str = None,
                    ملاحظات: str = None):
    records = await load_records()
    user_id = str(interaction.user.id)
    if user_id not in records or not records[user_id]:
        await interaction.response.send_message("لا يوجد سجلات.", ephemeral=True)
        return

    last = records[user_id][-1]
    if العمل:
        last["work_name"] = العمل
    if الفصل:
        last["chapter"] = الفصل
    if التخصص:
        norm_type = map_type(التخصص)
        if norm_type not in PRICES:
            await interaction.response.send_message("التخصص غير صحيح.", ephemeral=True)
            return
        last["work_type"] = norm_type
        last["total"] = PRICES[norm_type]
    if ملاحظات is not None:
        last["notes"] = ملاحظات

    await save_records(records)
    await update_stats()
    await interaction.response.send_message("✅ تم تعديل آخر سجل بنجاح.", ephemeral=True)