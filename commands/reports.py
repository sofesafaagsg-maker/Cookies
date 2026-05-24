from datetime import datetime, timedelta
import discord
from discord import app_commands
from discord.ext import commands
from state import bot
from helpers.core import *
from helpers.core import make_embed
from views.paginators import WorkDetailsView, WorksPaginator, get_works_info

# ═══════════════════════════════════════════════
# 🧩 عرض محسّن لعمل (شغل/أعمالي) مع قائمة اختيار
# ═══════════════════════════════════════════════
class WorkSummarySelectView(discord.ui.View):
    def __init__(self, works, bonuses, deductions, target_name, user_id, currency,
                 title_prefix="📊 ملخص شغل"):
        super().__init__(timeout=300)
        self.works = works            # dict: اسم_العمل -> قائمة الفصول
        self.bonuses = bonuses
        self.deductions = deductions
        self.target_name = target_name
        self.user_id = user_id
        self.currency = currency
        self.title_prefix = title_prefix

        # إنشاء القائمة المنسدلة
        self.select_menu = discord.ui.Select(
            placeholder="اختر عملاً لعرض التفاصيل...",
            options=self._build_options()
        )
        self.select_menu.callback = self.select_callback
        self.add_item(self.select_menu)

    def _build_options(self):
        options = []
        # نقسم الأعمال أبجدياً ونأخذ أول 24 (لترك مكان للخيارات الخاصة)
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
        # خيار المكافآت والخصومات إن وجدت
        if self.bonuses or self.deductions:
            options.append(
                discord.SelectOption(
                    label="المكافآت والخصومات",
                    value="__bonuses__",
                    description="عرض تفاصيل المكافآت والخصومات",
                    emoji="⚖️"
                )
            )
        # خيار "عرض الكل" إذا تعددت الأعمال
        if len(self.works) > 1:
            options.append(
                discord.SelectOption(
                    label="عرض الكل",
                    value="__all__",
                    description="عرض جميع الفصول مجمعة",
                    emoji="📚"
                )
            )
        return options

    async def select_callback(self, interaction: discord.Interaction):
        selected = interaction.data['values'][0]
        if selected == "__all__":
            embed = self.build_all_details_embed()
            self._switch_to_back_mode(embed)
            await interaction.response.edit_message(embed=embed, view=self)
        elif selected == "__bonuses__":
            embed = self.build_bonuses_details_embed()
            self._switch_to_back_mode(embed)
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            embed = self.build_work_detail_embed(selected)
            self._switch_to_back_mode(embed)
            await interaction.response.edit_message(embed=embed, view=self)

    async def back_callback(self, interaction: discord.Interaction):
        # العودة إلى الملخص
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

    # ───────── بناء الإمبيدات ─────────
    def build_summary_embed(self):
        gross = sum(sum(e.get("total", 0) for e in entries)
                    for entries in self.works.values())
        total_bonus = sum(e.get("total", 0) for e in self.bonuses)
        total_deduct = sum(abs(e.get("total", 0)) for e in self.deductions)
        net = gross + total_bonus - total_deduct
        total_works = len(self.works)
        total_chapters = sum(len(entries) for entries in self.works.values())

        embed = discord.Embed(
            title=f"{self.title_prefix} {self.target_name}",
            color=discord.Color.gold()
        )
        embed.add_field(name="📁 عدد الأعمال", value=str(total_works), inline=True)
        embed.add_field(name="📑 إجمالي الفصول", value=str(total_chapters), inline=True)
        embed.add_field(name="💰 إجمالي الأعمال", value=f"{self.currency}{gross:.2f}", inline=True)
        if total_bonus:
            embed.add_field(name="🎁 إجمالي المكافآت", value=f"{self.currency}{total_bonus:.2f}", inline=True)
        if total_deduct:
            embed.add_field(name="🔻 إجمالي الخصومات", value=f"{self.currency}{total_deduct:.2f}", inline=True)
        embed.add_field(name="💵 الصافي النهائي", value=f"{self.currency}{net:.2f}", inline=False)
        embed.set_footer(text="اختر عملاً من القائمة لعرض التفاصيل.")
        return embed

    def build_work_detail_embed(self, work_name):
        entries = self.works[work_name]
        total = sum(e.get("total", 0) for e in entries)
        count = len(entries)
        types_count = {}
        for e in entries:
            t = e.get("work_type", "غير محدد")
            types_count[t] = types_count.get(t, 0) + 1
        type_str = ", ".join(f"**{k.replace('_',' ').title()}:** {v}"
                             for k, v in types_count.items() if v > 0)

        embed = discord.Embed(
            title=f"📖 {work_name}",
            description=f"تفاصيل العمل لـ {self.target_name}",
            color=discord.Color.blue()
        )
        embed.add_field(name="📑 عدد الفصول", value=str(count), inline=True)
        embed.add_field(name="💰 المجموع", value=f"{self.currency}{total:.2f}", inline=True)
        if type_str:
            embed.add_field(name="📊 التخصصات", value=type_str, inline=False)

        # قائمة الفصول (مرتبة)
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
        return embed

    def build_all_details_embed(self):
        embed = discord.Embed(
            title=f"📚 جميع الفصول لـ {self.target_name}",
            color=discord.Color.purple()
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
        return embed

    def build_bonuses_details_embed(self):
        embed = discord.Embed(
            title="⚖️ المكافآت والخصومات",
            color=discord.Color.orange()
        )
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
        return embed


# ═══════════════════════════════════════════════
# 1️⃣ أمر الأعمال (تقارير المشاريع)
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
# 2️⃣ إحصائيات متقدمة
# ═══════════════════════════════════════════════
@bot.tree.command(name="احصائيات", description="عرض إحصائيات متقدمة")
@app_commands.checks.cooldown(1, 5, key=lambda i: (i.user.id, i.command.qualified_name))
async def stats(interaction: discord.Interaction):
    stat_doc = await stats_collection.find_one({"_id": "stats"})
    if not stat_doc:
        await interaction.response.send_message("لا توجد إحصائيات بعد.", ephemeral=True)
        return

    total_entries = stat_doc.get("total_entries", 0)
    total_amount = stat_doc.get("total_amount", 0)
    type_counts = stat_doc.get("type_counts", {})
    daily = stat_doc.get("daily", {"entries":0, "amount":0})
    weekly = stat_doc.get("weekly", {"entries":0, "amount":0})
    monthly = stat_doc.get("monthly", {"entries":0, "amount":0})
    top_members = stat_doc.get("top_members", [])
    last_updated = stat_doc.get("last_updated", "غير معروف")

    embed = discord.Embed(title="📊 **إحصائيات شاملة**", color=discord.Color.teal())
    embed.add_field(name="**📄 إجمالي الفصول**", value=total_entries, inline=True)
    embed.add_field(name="**💰 إجمالي المبالغ**",
                    value=f"{SETTINGS.get('currency', '$')}{total_amount:.2f}", inline=True)

    type_lines = "\n".join(
        [f"**{k.replace('_',' ').title()}:** {v}" for k, v in type_counts.items()]
    )
    embed.add_field(name="**📊 تفصيل التخصصات**", value=type_lines, inline=False)

    embed.add_field(
        name="**📅 اليوم**",
        value=f"فصول: {daily['entries']}\nالمبلغ: {SETTINGS.get('currency', '$')}{daily['amount']:.2f}",
        inline=True
    )
    embed.add_field(
        name="**📆 هذا الأسبوع**",
        value=f"فصول: {weekly['entries']}\nالمبلغ: {SETTINGS.get('currency', '$')}{weekly['amount']:.2f}",
        inline=True
    )
    embed.add_field(
        name="**📆 هذا الشهر**",
        value=f"فصول: {monthly['entries']}\nالمبلغ: {SETTINGS.get('currency', '$')}{monthly['amount']:.2f}",
        inline=True
    )

    if top_members:
        top_list = ""
        records = await load_records()
        for i, (uid, stats_data) in enumerate(top_members[:5], 1):
            uid_int = int(uid)
            username_hint = None
            if uid in records:
                for e in records[uid]:
                    if e.get("username"):
                        username_hint = e["username"]
                        break
            display = format_member_display(interaction.guild, uid_int, username_hint)
            top_list += (
                f"{i}. {display} - "
                f"{stats_data['total_amount']:.2f} {SETTINGS.get('currency', '$')} "
                f"({stats_data['total_entries']} فصل)\n"
            )
        embed.add_field(name="**🏆 أفضل 5 أعضاء**", value=top_list, inline=False)

    embed.set_footer(
        text=f"آخر تحديث: {last_updated[:19] if last_updated != 'غير معروف' else last_updated}"
    )
    await interaction.response.send_message(embed=embed)


# ═══════════════════════════════════════════════
# 3️⃣ أعمالي (خاص بالمستخدم)
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
        target_name=interaction.user.display_name,
        user_id=user_id,
        currency=SETTINGS.get('currency', '$'),
        title_prefix="💼 اللوحة الشخصية •"
    )
    embed = view.build_summary_embed()
    # تخصيص إضافي لرسالة أعمالي
    embed.color = discord.Color.purple()
    embed.set_footer(text="لوحة تحكم شخصية • اختر عملاً للتفاصيل")
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
        target_name=ctx.author.display_name,
        user_id=user_id,
        currency=SETTINGS.get('currency', '$'),
        title_prefix="💼 اللوحة الشخصية •"
    )
    embed = view.build_summary_embed()
    embed.color = discord.Color.purple()
    embed.set_footer(text="لوحة تحكم شخصية • اختر عملاً للتفاصيل")
    await ctx.send(embed=embed, view=view)


# ═══════════════════════════════════════════════
# 4️⃣ شغل (عرض شغل أي عضو)
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
        target_name=target.display_name,
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
        target_name=member.display_name,
        user_id=user_id,
        currency=SETTINGS.get('currency', '$'),
        title_prefix="📊 ملخص شغل"
    )
    embed = view.build_summary_embed()
    await ctx.send(embed=embed, view=view)


# ── دالة مساعدة لتصنيف السجلات ──
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
# 5️⃣ لوحة التحكم (مشرفين)
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