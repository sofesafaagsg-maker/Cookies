import discord
from discord import app_commands
from state import bot
from helpers.core import *
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

# ----------------------------------------------------------------------
# /الأعمال command
# ----------------------------------------------------------------------
async def get_works_info(guild: discord.Guild):
    """Build list of works with their contributors."""
    approved_works = await load_works()
    records = await load_records()
    isolated = get_isolated_work_names(approved_works)

    contrib_map = defaultdict(lambda: defaultdict(lambda: {"count": 0, "total": 0.0, "types": defaultdict(int)}))
    for user_id_str, entries in records.items():
        for entry in entries:
            work = entry.get("work_name")
            if work and work not in isolated:
                info = contrib_map[work][user_id_str]
                info["count"] += 1
                info["total"] += entry.get("total", 0)
                info["types"][entry.get("work_type", "غير محدد")] += 1

    works_info = []
    for w in approved_works:
        if is_work_isolated(w):
            continue
        work_name = w["name"]
        contributors = contrib_map.get(work_name, {})
        members_list = []
        for uid_str, member_stats in contributors.items():
            uid = int(uid_str)
            username_hint = None
            if uid_str in records:
                for e in records[uid_str]:
                    if e.get("username"):
                        username_hint = e["username"]
                        break
            display = format_member_display(guild, uid, username_hint)
            members_list.append((uid, display, member_stats["count"], member_stats["total"], dict(member_stats["types"])))
        members_list.sort(key=lambda item: (item[2], item[3]), reverse=True)
        works_info.append((work_name, members_list))
    return works_info

class MemberSelect(discord.ui.Select):
    def __init__(self, work_name, members_info, guild, works_info_callback=None):
        self.work_name = work_name
        self.members_info = members_info
        self.guild = guild
        self.works_info_callback = works_info_callback
        options = []
        for member_info in members_info[:24]:
            uid, name = member_info[0], member_info[1]
            count = member_info[2] if len(member_info) > 2 else 0
            total = member_info[3] if len(member_info) > 3 else 0
            options.append(discord.SelectOption(label=name[:100], value=str(uid), description=f"{count} فصول • {SETTINGS.get('currency', '$')}{total:.2f}"[:100]))
        options.append(discord.SelectOption(label="❌ إلغاء", value="cancel"))
        super().__init__(placeholder="اختر عضواً...", options=options)

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "cancel":
            await interaction.response.edit_message(content="تم الإلغاء.", view=None)
            return
        user_id = int(self.values[0])
        user_display = next((info[1] for info in self.members_info if info[0] == user_id), str(user_id))
        records = await load_records()
        isolated = get_isolated_work_names(await load_works())
        user_entries = records.get(str(user_id), [])
        work_entries = [e for e in user_entries if e.get("work_name") == self.work_name and e.get("work_name") not in isolated]
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
            SETTINGS.get('currency', '$'), back_callback=back_to_members
        )
        await interaction.response.edit_message(content=None, embed=view_details.get_embed(), view=view_details)

class WorkSelect(discord.ui.Select):
    def __init__(self, works_info, guild, works_info_callback=None):
        self.works_info = works_info
        self.guild = guild
        self.works_info_callback = works_info_callback
        options = []
        for work_name, members in works_info[:24]:
            chapters = sum(member[2] for member in members) if members else 0
            total = sum(member[3] for member in members) if members else 0
            options.append(discord.SelectOption(
                label=work_name[:100],
                value=work_name,
                description=f"{len(members)} أعضاء • {chapters} فصول • {SETTINGS.get('currency', '$')}{total:.2f}"[:100]
            ))
        options.append(discord.SelectOption(label="❌ إلغاء", value="cancel"))
        super().__init__(placeholder="اختر العمل...", options=options)

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "cancel":
            await interaction.response.edit_message(content="تم الإلغاء.", view=None)
            return
        work_name = self.values[0]
        members_info = [member for work, members in self.works_info if work == work_name for member in members]
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
        summary = "\n".join(
            f"• {member[1]} — {member[2]} فصول — {SETTINGS.get('currency', '$')}{member[3]:.2f}"
            for member in members_info[:10]
        )
        if len(members_info) > 10:
            summary += f"\n... والمزيد ({len(members_info) - 10} عضو)"
        embed = discord.Embed(title=f"📖 أعضاء عمل: {work_name}", color=discord.Color.teal())
        embed.add_field(name="👥 المساهمون حسب عدد الفصول", value=summary or "لا يوجد", inline=False)
        await interaction.response.edit_message(content=None, embed=embed, view=view)

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
