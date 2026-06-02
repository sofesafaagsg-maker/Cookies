import discord
from discord.ext import commands
from discord import app_commands
from state import bot
from helpers.core import *

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
            confirm_view = discord.ui.View(timeout=30)
            async def confirm_callback(interaction2: discord.Interaction):
                records = await load_records()
                if str(self.user_id) in records:
                    del records[str(self.user_id)]
                    await save_records(records)
                    await log_audit("حذف_كل_سجلات_العضو", interaction.user.id, self.user_id, "حذف كل السجلات")
                    await update_stats()
                    await interaction2.response.edit_message(content=f"✅ تم حذف كل سجلات العضو.", view=None)
                else:
                    await interaction2.response.edit_message(content="❌ لا توجد سجلات لهذا العضو.", view=None)
                confirm_view.stop()
            async def cancel_callback(interaction2: discord.Interaction):
                await interaction2.response.edit_message(content="❌ تم إلغاء العملية.", view=None)
                confirm_view.stop()
            confirm_btn = discord.ui.Button(label="تأكيد", style=discord.ButtonStyle.danger)
            confirm_btn.callback = confirm_callback
            cancel_btn = discord.ui.Button(label="إلغاء", style=discord.ButtonStyle.secondary)
            cancel_btn.callback = cancel_callback
            confirm_view.add_item(confirm_btn)
            confirm_view.add_item(cancel_btn)
            await interaction.response.send_message("⚠️ **تحذير:** هل أنت متأكد من حذف كل سجلات هذا العضو؟", view=confirm_view, ephemeral=True)

        elif self.values[0] == "delete_work" and self.work_name:
            confirm_view = discord.ui.View(timeout=30)
            async def confirm_callback(interaction2: discord.Interaction):
                records = await load_records()
                user_id_str = str(self.user_id)
                if user_id_str in records:
                    new_entries = [e for e in records[user_id_str] if e.get("work_name") != self.work_name]
                    removed_count = len(records[user_id_str]) - len(new_entries)
                    records[user_id_str] = new_entries
                    if not records[user_id_str]:
                        del records[user_id_str]
                    await save_records(records)
                    await log_audit("حذف_عمل_كامل", interaction.user.id, self.user_id, f"حذف عمل {self.work_name} ({removed_count} فصل)")
                    await update_stats()
                    await interaction2.response.edit_message(content=f"✅ تم حذف عمل `{self.work_name}` بالكامل ({removed_count} فصل).", view=None)
                else:
                    await interaction2.response.edit_message(content="❌ لا توجد سجلات لهذا العضو.", view=None)
                confirm_view.stop()
            async def cancel_callback(interaction2: discord.Interaction):
                await interaction2.response.edit_message(content="❌ تم إلغاء العملية.", view=None)
                confirm_view.stop()
            confirm_btn = discord.ui.Button(label="تأكيد", style=discord.ButtonStyle.danger)
            confirm_btn.callback = confirm_callback
            cancel_btn = discord.ui.Button(label="إلغاء", style=discord.ButtonStyle.secondary)
            cancel_btn.callback = cancel_callback
            confirm_view.add_item(confirm_btn)
            confirm_view.add_item(cancel_btn)
            await interaction.response.send_message(f"⚠️ **تحذير:** هل أنت متأكد من حذف كل فصول عمل `{self.work_name}` للعضو؟", view=confirm_view, ephemeral=True)

        elif self.values[0] == "delete_chapter":
            records = await load_records()
            user_id_str = str(self.user_id)
            if user_id_str not in records:
                await interaction.response.send_message("❌ لا توجد سجلات لهذا العضو.", ephemeral=True)
                return
            work_entries = [e for e in records[user_id_str] if e.get("work_name") == self.work_name]
            if not work_entries:
                await interaction.response.send_message("❌ لا توجد فصول لهذا العمل.", ephemeral=True)
                return
            options = []
            seen_chapters = set()
            for e in work_entries:
                ch = e.get('chapter')
                if ch not in seen_chapters:
                    seen_chapters.add(ch)
                    options.append(discord.SelectOption(label=f"فصل {ch}", value=ch, description=f"التخصص: {e.get('work_type')}"))
            options.append(discord.SelectOption(label="❌ إلغاء", value="cancel"))
            select = discord.ui.Select(placeholder="اختر الفصل المراد حذفه...", options=options)
            async def select_callback(interaction2: discord.Interaction):
                if select.values[0] == "cancel":
                    await interaction2.response.edit_message(content="تم الإلغاء.", view=None)
                    return
                chapter = select.values[0]
                confirm_view = discord.ui.View(timeout=30)
                async def confirm_callback(interaction3: discord.Interaction):
                    records2 = await load_records()
                    if user_id_str in records2:
                        new_entries = [e for e in records2[user_id_str] if not (e.get("work_name") == self.work_name and e.get("chapter") == chapter)]
                        removed = len(records2[user_id_str]) - len(new_entries)
                        records2[user_id_str] = new_entries
                        if not records2[user_id_str]:
                            del records2[user_id_str]
                        await save_records(records2)
                        await log_audit("حذف_فصل", interaction.user.id, self.user_id, f"حذف فصل {chapter} من عمل {self.work_name}")
                        await update_stats()
                        await interaction3.response.edit_message(content=f"✅ تم حذف الفصل {chapter} من عمل `{self.work_name}`.", view=None)
                    else:
                        await interaction3.response.edit_message(content="❌ لا توجد سجلات لهذا العضو.", view=None)
                    confirm_view.stop()
                async def cancel_callback(interaction3: discord.Interaction):
                    await interaction3.response.edit_message(content="❌ تم إلغاء العملية.", view=None)
                    confirm_view.stop()
                confirm_btn = discord.ui.Button(label="تأكيد", style=discord.ButtonStyle.danger)
                confirm_btn.callback = confirm_callback
                cancel_btn = discord.ui.Button(label="إلغاء", style=discord.ButtonStyle.secondary)
                cancel_btn.callback = cancel_callback
                confirm_view.add_item(confirm_btn)
                confirm_view.add_item(cancel_btn)
                await interaction2.response.send_message(f"⚠️ هل أنت متأكد من حذف الفصل {chapter} من عمل `{self.work_name}`؟", view=confirm_view, ephemeral=True)
            select.callback = select_callback
            view = discord.ui.View(timeout=60)
            view.add_item(select)
            await interaction.response.edit_message(content="**اختر الفصل المراد حذفه:**", view=view)

@bot.tree.command(name="حذف", description="حذف سجلات العضو - للمشرفين")
@app_commands.checks.cooldown(1, 5, key=lambda i: (i.user.id, i.command.qualified_name))
async def delete_advanced(interaction: discord.Interaction, member: discord.Member, work_name: str = None):
    if not is_admin(interaction):
        await log_unauthorized(interaction.user.id, "حذف")
        await interaction.response.send_message("❌ ما عندك صلاحية.", ephemeral=True)
        return
    if interaction.channel.name not in SETTINGS.get("allowed_channels", []):
        await interaction.response.send_message("❌ استخدم الأمر في القنوات المسموحة.", ephemeral=True)
        return
    records = await load_records()
    user_id_str = str(member.id)
    if user_id_str not in records or not records[user_id_str]:
        await interaction.response.send_message("❌ هذا العضو ما عنده أي شغل محفوظ.", ephemeral=True)
        return
    if work_name:
        work_exists = any(e.get("work_name") == work_name for e in records[user_id_str])
        if not work_exists:
            await interaction.response.send_message(f"❌ لا يوجد عمل باسم `{work_name}` لهذا العضو.", ephemeral=True)
            return
        view = discord.ui.View(timeout=60)
        select = DeleteSelect(member.id, work_name)
        view.add_item(select)
        await interaction.response.send_message(f"**🗑️ خيارات الحذف لعضو:** {member.mention}\n**العمل:** `{work_name}`", view=view)
    else:
        works = set(e.get("work_name") for e in records[user_id_str])
        options = []
        for w in works:
            options.append(discord.SelectOption(label=f"📖 {w}", value=w))
        options.append(discord.SelectOption(label="👤 حذف كل سجلات العضو", value="delete_all_user"))
        options.append(discord.SelectOption(label="❌ إلغاء", value="cancel"))
        if len(options) > 25:
            options = options[:25]
        select = discord.ui.Select(placeholder="اختر عملاً أو خياراً...", options=options)
        async def select_callback(interaction2: discord.Interaction):
            if select.values[0] == "cancel":
                await interaction2.response.edit_message(content="تم الإلغاء.", view=None)
                return
            if select.values[0] == "delete_all_user":
                confirm_view = discord.ui.View(timeout=30)
                async def confirm_callback(interaction3: discord.Interaction):
                    records2 = await load_records()
                    if str(member.id) in records2:
                        del records2[str(member.id)]
                        await save_records(records2)
                        await log_audit("حذف_كل_سجلات_العضو", interaction.user.id, member.id, "حذف كل السجلات")
                        await update_stats()
                        await interaction3.response.edit_message(content=f"✅ تم حذف كل سجلات العضو.", view=None)
                    else:
                        await interaction3.response.edit_message(content="❌ لا توجد سجلات.", view=None)
                    confirm_view.stop()
                async def cancel_callback(interaction3: discord.Interaction):
                    await interaction3.response.edit_message(content="❌ تم إلغاء العملية.", view=None)
                    confirm_view.stop()
                confirm_btn = discord.ui.Button(label="تأكيد", style=discord.ButtonStyle.danger)
                confirm_btn.callback = confirm_callback
                cancel_btn = discord.ui.Button(label="إلغاء", style=discord.ButtonStyle.secondary)
                cancel_btn.callback = cancel_callback
                confirm_view.add_item(confirm_btn)
                confirm_view.add_item(cancel_btn)
                await interaction2.response.send_message("⚠️ **تحذير:** هل أنت متأكد من حذف كل سجلات هذا العضو؟", view=confirm_view, ephemeral=True)
            else:
                work = select.values[0]
                view2 = discord.ui.View(timeout=60)
                select2 = DeleteSelect(member.id, work)
                view2.add_item(select2)
                await interaction2.response.edit_message(content=f"**خيارات الحذف لعمل `{work}`:**", view=view2)
        select.callback = select_callback
        view = discord.ui.View(timeout=60)
        view.add_item(select)
        await interaction.response.send_message(f"**🗑️ اختر العمل أو الإجراء لعضو:** {member.mention}", view=view)

@bot.command(name="حذف")
@commands.has_permissions(manage_messages=True)
@commands.cooldown(1, 5, commands.BucketType.user)
async def delete_work_text(ctx, member: discord.Member = None, number: int = None):
    if member is None or number is None:
        await ctx.send("**الاستخدام:** `!حذف @member 2`\nأو استخدم الأمر `/حذف` للخيارات المتقدمة.")
        return
    records = await load_records()
    user_id = str(member.id)
    if user_id not in records or not records[user_id]:
        await ctx.send("❌ هذا العضو ما عنده أي شغل محفوظ.")
        return
    if number < 1 or number > len(records[user_id]):
        await ctx.send("❌ رقم السجل غير صحيح.")
        return
    deleted = records[user_id].pop(number - 1)
    if not records[user_id]:
        del records[user_id]
    await save_records(records)
    await log_audit("حذف سجل (نصي)", ctx.author.id, member.id, f"السجل #{number}: {deleted.get('work_name')} - فصل {deleted.get('chapter')}")
    await update_stats()
    embed = discord.Embed(title="🗑️ **تم حذف السجل**", color=discord.Color.red())
    embed.add_field(name="**المستخدم**", value=member.mention, inline=True)
    embed.add_field(name="**العمل**", value=deleted.get('work_name', 'غير محدد'), inline=True)
    embed.add_field(name="**الفصل**", value=deleted.get('chapter', 'غير محدد'), inline=True)
    embed.add_field(name="**التخصص**", value=deleted.get('work_type', 'غير محدد'), inline=True)
    embed.add_field(name="**المبلغ**", value=f"{SETTINGS.get('currency', '$')}{deleted.get('total', 0):.2f}", inline=True)
    await ctx.send(embed=embed)

@bot.tree.command(name="حذف_الكل", description="حذف كل السجلات - للمشرفين (يستثني الأعمال المعزولة)")
@app_commands.checks.cooldown(1, 10, key=lambda i: (i.user.id, i.command.qualified_name))
async def delete_all_work_slash(interaction: discord.Interaction):
    if not is_admin(interaction):
        await log_unauthorized(interaction.user.id, "حذف_الكل")
        await interaction.response.send_message("❌ ما عندك صلاحية.", ephemeral=True)
        return
    if interaction.channel.name not in SETTINGS.get("allowed_channels", []):
        await interaction.response.send_message("❌ القناة غير مسموحة.", ephemeral=True)
        return

    records = await load_records()
    works = await load_works()
    isolated_names = get_isolated_work_names(works)

    total_removed = 0
    preserved_isolated = 0
    for user_id in list(records.keys()):
        new_entries = [e for e in records[user_id] if e.get("work_name") in isolated_names]
        removed = len(records[user_id]) - len(new_entries)
        total_removed += removed
        preserved_isolated += len(new_entries)
        if new_entries:
            records[user_id] = new_entries
        else:
            del records[user_id]

    if total_removed == 0:
        await interaction.response.send_message("📭 لا توجد سجلات قابلة للحذف (جميعها معزولة أو لا سجلات).", ephemeral=True)
        return

    await save_records(records)
    await log_audit("حذف_الكل", interaction.user.id, None, f"{total_removed} سجل (استثناء المعزولة: {preserved_isolated})")
    await update_stats()
    msg = f"🗑️ تم حذف {total_removed} سجل."
    if preserved_isolated > 0:
        msg += f"\n⏸️ تم استثناء {preserved_isolated} سجل من أعمال معزولة."
    await interaction.response.send_message(msg)

@bot.command(name="حذف_الكل")
@commands.has_permissions(manage_messages=True)
@commands.cooldown(1, 10, commands.BucketType.user)
async def delete_all_work_text(ctx):
    records = await load_records()
    works = await load_works()
    isolated_names = get_isolated_work_names(works)

    total_removed = 0
    preserved_isolated = 0
    for user_id in list(records.keys()):
        new_entries = [e for e in records[user_id] if e.get("work_name") in isolated_names]
        removed = len(records[user_id]) - len(new_entries)
        total_removed += removed
        preserved_isolated += len(new_entries)
        if new_entries:
            records[user_id] = new_entries
        else:
            del records[user_id]

    if total_removed == 0:
        await ctx.send("📭 لا توجد سجلات قابلة للحذف (جميعها معزولة أو لا سجلات).")
        return

    await save_records(records)
    await log_audit("حذف_الكل", ctx.author.id, None, f"{total_removed} سجل (استثناء المعزولة: {preserved_isolated})")
    await update_stats()
    msg = f"🗑️ تم حذف {total_removed} سجل."
    if preserved_isolated > 0:
        msg += f"\n⏸️ تم استثناء {preserved_isolated} سجل من أعمال معزولة."
    await ctx.send(msg)

# ----------------------------------------------------------------------
# NEW: /حذف_كل_الأعمال (Admin deletes all works)
# ----------------------------------------------------------------------
@bot.tree.command(name="حذف_كل_الأعمال", description="حذف جميع الأعمال من القائمة (للمشرفين فقط)")
@app_commands.checks.cooldown(1, 10, key=lambda i: (i.user.id, i.command.qualified_name))
async def delete_all_works(interaction: discord.Interaction):
    if not is_admin(interaction):
        await log_unauthorized(interaction.user.id, "حذف_كل_الأعمال")
        await interaction.response.send_message("❌ ما عندك صلاحية.", ephemeral=True)
        return
    works = await load_works()
    if not works:
        await interaction.response.send_message("📭 لا توجد أعمال في القائمة.", ephemeral=True)
        return

    confirm_view = discord.ui.View(timeout=30)
    async def confirm_callback(interaction2: discord.Interaction):
        await save_works([])
        await log_audit("حذف_كل_الأعمال", interaction.user.id, None, f"تم حذف {len(works)} عمل")
        await interaction2.response.edit_message(content=f"✅ تم حذف جميع الأعمال ({len(works)} عمل) من القائمة.", view=None)
        confirm_view.stop()

    async def cancel_callback(interaction2: discord.Interaction):
        await interaction2.response.edit_message(content="❌ تم إلغاء العملية.", view=None)
        confirm_view.stop()

    confirm_btn = discord.ui.Button(label="تأكيد", style=discord.ButtonStyle.danger)
    confirm_btn.callback = confirm_callback
    cancel_btn = discord.ui.Button(label="إلغاء", style=discord.ButtonStyle.secondary)
    cancel_btn.callback = cancel_callback
    confirm_view.add_item(confirm_btn)
    confirm_view.add_item(cancel_btn)

    await interaction.response.send_message(
        f"⚠️ **تحذير:** سيتم حذف جميع الأعمال ({len(works)} عمل) من القائمة.\nلن تتأثر السجلات.",
        view=confirm_view,
        ephemeral=True
    )