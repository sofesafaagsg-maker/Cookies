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
            await interaction.response.send_message("⚠️ **تحذير:** هل أنت متأكد من حذف كل سجلات هذا العضو؟\nأرسل `تأكيد` خلال 30 ثانية.", ephemeral=True)
            def check(m):
                return m.author == interaction.user and m.content == "تأكيد" and m.channel == interaction.channel
            try:
                await bot.wait_for('message', timeout=30.0, check=check)
            except:
                await interaction.followup.send("❌ تم إلغاء العملية.", ephemeral=True)
                return
            records = await load_records()
            if str(self.user_id) in records:
                del records[str(self.user_id)]
                await save_records(records)
                await log_audit("حذف_كل_سجلات_العضو", interaction.user.id, self.user_id, "حذف كل السجلات")
                await update_stats()
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
                await interaction.followup.send(f"✅ تم حذف عمل `{self.work_name}` بالكامل ({removed_count} فصل).", ephemeral=True)
            else:
                await interaction.followup.send("❌ لا توجد سجلات لهذا العضو.", ephemeral=True)
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
                records2 = await load_records()
                if user_id_str in records2:
                    new_entries = [e for e in records2[user_id_str] if not (e.get("work_name") == self.work_name and e.get("chapter") == chapter)]
                    removed = len(records2[user_id_str]) - len(new_entries)
                    records2[user_id_str] = new_entries
                    if not records2[user_id_str]:
                        del records2[user_id_str]
                    await save_records(records2)
                    await log_audit("حذف_فصل", interaction2.user.id, self.user_id, f"حذف فصل {chapter} من عمل {self.work_name}")
                    await update_stats()
                    await interaction2.followup.send(f"✅ تم حذف الفصل {chapter} من عمل `{self.work_name}`.", ephemeral=True)
                else:
                    await interaction2.followup.send("❌ لا توجد سجلات لهذا العضو.", ephemeral=True)
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
        async def select_callback(interaction2):
            if select.values[0] == "cancel":
                await interaction2.response.edit_message(content="تم الإلغاء.", view=None)
                return
            if select.values[0] == "delete_all_user":
                await interaction2.response.send_message("⚠️ **تحذير:** هل أنت متأكد من حذف كل سجلات هذا العضو؟\nأرسل `تأكيد` خلال 30 ثانية.", ephemeral=True)
                def check(m):
                    return m.author == interaction2.user and m.content == "تأكيد"
                try:
                    await bot.wait_for('message', timeout=30.0, check=check)
                except:
                    await interaction2.followup.send("❌ تم إلغاء العملية.", ephemeral=True)
                    return
                records2 = await load_records()
                if str(member.id) in records2:
                    del records2[str(member.id)]
                    await save_records(records2)
                    await log_audit("حذف_كل_سجلات_العضو", interaction2.user.id, member.id, "حذف كل السجلات")
                    await update_stats()
                    await interaction2.followup.send(f"✅ تم حذف كل سجلات العضو.", ephemeral=True)
                else:
                    await interaction2.followup.send("❌ لا توجد سجلات.", ephemeral=True)
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

@bot.tree.command(name="حذف_الكل", description="حذف كل السجلات - للمشرفين")
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
    total = sum(len(items) for items in records.values())
    if total == 0:
        await interaction.response.send_message("📭 ما فيه أي سجلات.", ephemeral=True)
        return
    records.clear()
    await save_records(records)
    await log_audit("حذف_الكل", interaction.user.id, None, f"{total} سجل")
    await update_stats()
    await interaction.response.send_message(f"🗑️ تم حذف كل السجلات ({total}).")

@bot.command(name="حذف_الكل")
@commands.has_permissions(manage_messages=True)
@commands.cooldown(1, 10, commands.BucketType.user)
async def delete_all_work_text(ctx):
    records = await load_records()
    total = sum(len(items) for items in records.values())
    if total == 0:
        await ctx.send("📭 ما فيه أي سجلات.")
        return
    records.clear()
    await save_records(records)
    await log_audit("حذف_الكل", ctx.author.id, None, f"{total} سجل")
    await update_stats()
    await ctx.send(f"🗑️ تم حذف كل السجلات ({total}).")

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

    await interaction.response.send_message(
        f"⚠️ **تحذير:** سيتم حذف جميع الأعمال ({len(works)} عمل) من القائمة.\n"
        "لن تتأثر السجلات.\n"
        "اكتب `تأكيد` خلال 30 ثانية للمتابعة.",
        ephemeral=True
    )
    def check(m):
        return m.author == interaction.user and m.content == "تأكيد" and m.channel == interaction.channel
    try:
        await bot.wait_for('message', timeout=30.0, check=check)
    except:
        await interaction.followup.send("❌ تم إلغاء العملية.", ephemeral=True)
        return

    await save_works([])
    await log_audit("حذف_كل_الأعمال", interaction.user.id, None, f"تم حذف {len(works)} عمل")
    await interaction.followup.send(f"✅ تم حذف جميع الأعمال ({len(works)} عمل) من القائمة.", ephemeral=True)