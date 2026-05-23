from datetime import datetime
import json
import pandas as pd
from io import BytesIO
import discord
from discord import app_commands
from state import bot
from helpers.core import *
from tasks.lifecycle import work_autocomplete, specialty_autocomplete

@bot.tree.command(name="تصدير", description="تصدير كل البيانات إلى JSON (للعضو المخصص فقط)")
@app_commands.checks.cooldown(1, 10, key=lambda i: (i.user.id, i.command.qualified_name))
async def export_excel(interaction: discord.Interaction):
    # السماح فقط لعضو واحد محدد بمعرفه
    if interaction.user.id != 656783724662226963:
        await interaction.response.send_message("❌ غير مصرح لك باستخدام هذا الأمر.", ephemeral=True)
        return

    records = await load_records()
    data = json.dumps(records, ensure_ascii=False, indent=2)
    buffer = BytesIO(data.encode('utf-8'))
    buffer.seek(0)
    await interaction.response.send_message(
        file=discord.File(buffer, filename=f"backup_{datetime.utcnow().date()}.json")
    )

@bot.tree.command(name="اعدادات", description="إعدادات البوت (للمشرفين)")
@app_commands.checks.cooldown(1, 5, key=lambda i: (i.user.id, i.command.qualified_name))
async def bot_settings(interaction: discord.Interaction, العملة: str = None, قناة_الإشعارات: discord.TextChannel = None, حد_التنبيه: float = None):
    if not is_admin(interaction):
        await log_unauthorized(interaction.user.id, "اعدادات")
        await interaction.response.send_message("❌ ما عندك صلاحية.", ephemeral=True)
        return
    if العملة:
        SETTINGS["currency"] = العملة
    if قناة_الإشعارات:
        SETTINGS["notify_channel_id"] = قناة_الإشعارات.id
    if حد_التنبيه is not None:
        SETTINGS["alert_threshold"] = حد_التنبيه
    await save_settings(SETTINGS)
    await interaction.response.send_message("✅ تم تحديث الإعدادات.", ephemeral=True)

# ----------------------------------------------------------------------
# Works management commands
# ----------------------------------------------------------------------
@bot.tree.command(name="اضافة_عمل", description="إضافة عمل جديد إلى قائمة الأعمال المدفوعة (للمشرفين)")
@app_commands.describe(الاسم="اسم العمل", بداية_الفصول_المدفوعة="أول فصل مدفوع (اختياري، اتركه فارغاً إذا كان العمل كله مدفوع)", نشط="هل العمل نشط الآن؟")
@app_commands.checks.cooldown(1, 5, key=lambda i: (i.user.id, i.command.qualified_name))
async def add_work(interaction: discord.Interaction, الاسم: str, بداية_الفصول_المدفوعة: int = None, نشط: bool = True):
    if not is_admin(interaction):
        await log_unauthorized(interaction.user.id, "اضافة_عمل")
        await interaction.response.send_message("❌ ما عندك صلاحية.", ephemeral=True)
        return
    works = await load_works()
    if any(w["name"] == الاسم for w in works):
        await interaction.response.send_message(f"❌ العمل `{الاسم}` موجود بالفعل.", ephemeral=True)
        return
    new_work = {"name": الاسم, "paid_start": بداية_الفصول_المدفوعة, "active": نشط}
    works.append(new_work)
    await save_works(works)
    await log_audit("اضافة_عمل", interaction.user.id, None, f"أضاف عمل {الاسم} (paid_start={بداية_الفصول_المدفوعة}, active={نشط})")
    desc = "كل الفصول مدفوعة" if بداية_الفصول_المدفوعة is None else f"يبدأ من فصل {بداية_الفصول_المدفوعة}"
    await interaction.response.send_message(f"✅ تمت إضافة العمل `{الاسم}`.\nالحالة: {desc} | نشط: {'✅' if نشط else '❌'}", ephemeral=True)

@bot.tree.command(name="حذف_عمل", description="حذف عمل من القائمة (للمشرفين)")
@app_commands.autocomplete(العمل=work_autocomplete)
@app_commands.checks.cooldown(1, 5, key=lambda i: (i.user.id, i.command.qualified_name))
async def delete_work(interaction: discord.Interaction, العمل: str):
    if not is_admin(interaction):
        await log_unauthorized(interaction.user.id, "حذف_عمل")
        await interaction.response.send_message("❌ ما عندك صلاحية.", ephemeral=True)
        return
    works = await load_works()
    target = next((w for w in works if w["name"] == العمل), None)
    if not target:
        await interaction.response.send_message("❌ العمل غير موجود.", ephemeral=True)
        return

    view = discord.ui.View(timeout=60)
    async def delete_with_records(interaction2: discord.Interaction):
        confirm_view = discord.ui.View(timeout=30)
        async def confirm_callback(interaction3: discord.Interaction):
            removed = await delete_all_records_of_work(العمل)
            new_works = [w for w in works if w["name"] != العمل]
            await save_works(new_works)
            await log_audit("حذف_عمل_مع_السجلات", interaction2.user.id, None, f"حذف {العمل} و {removed} سجل")
            await interaction3.response.edit_message(content=f"✅ تم حذف العمل `{العمل}` وكل سجلاته ({removed} سجل).", view=None)
            confirm_view.stop()
        async def cancel_callback(interaction3: discord.Interaction):
            await interaction3.response.edit_message(content="❌ تم الإلغاء.", view=None)
            confirm_view.stop()
        confirm_btn = discord.ui.Button(label="تأكيد", style=discord.ButtonStyle.danger)
        confirm_btn.callback = confirm_callback
        cancel_btn = discord.ui.Button(label="إلغاء", style=discord.ButtonStyle.secondary)
        cancel_btn.callback = cancel_callback
        confirm_view.add_item(confirm_btn)
        confirm_view.add_item(cancel_btn)
        await interaction2.response.send_message("⚠️ **تأكيد:** سيتم حذف العمل **وكل سجلاته** نهائياً.", view=confirm_view, ephemeral=True)

    async def delete_work_only(interaction2: discord.Interaction):
        confirm_view = discord.ui.View(timeout=30)
        async def confirm_callback(interaction3: discord.Interaction):
            new_works = [w for w in works if w["name"] != العمل]
            await save_works(new_works)
            await log_audit("حذف_عمل_فقط", interaction2.user.id, None, f"حذف {العمل} من القائمة (السجلات باقية)")
            await interaction3.response.edit_message(content=f"✅ تم حذف العمل `{العمل}` من القائمة (السجلات لم تمس).", view=None)
            confirm_view.stop()
        async def cancel_callback(interaction3: discord.Interaction):
            await interaction3.response.edit_message(content="❌ تم الإلغاء.", view=None)
            confirm_view.stop()
        confirm_btn = discord.ui.Button(label="تأكيد", style=discord.ButtonStyle.danger)
        confirm_btn.callback = confirm_callback
        cancel_btn = discord.ui.Button(label="إلغاء", style=discord.ButtonStyle.secondary)
        cancel_btn.callback = cancel_callback
        confirm_view.add_item(confirm_btn)
        confirm_view.add_item(cancel_btn)
        await interaction2.response.send_message("⚠️ **تأكيد:** سيتم حذف العمل من القائمة فقط (السجلات تبقى).", view=confirm_view, ephemeral=True)

    delete_with_btn = discord.ui.Button(label="🗑️ حذف العمل وكل سجلاته", style=discord.ButtonStyle.danger)
    delete_with_btn.callback = delete_with_records
    delete_only_btn = discord.ui.Button(label="📁 حذف العمل فقط (إخفاؤه)", style=discord.ButtonStyle.primary)
    delete_only_btn.callback = delete_work_only
    cancel_btn = discord.ui.Button(label="❌ إلغاء", style=discord.ButtonStyle.secondary)
    async def cancel_cb(interaction2: discord.Interaction):
        await interaction2.response.edit_message(content="تم الإلغاء.", view=None)
    cancel_btn.callback = cancel_cb
    view.add_item(delete_with_btn)
    view.add_item(delete_only_btn)
    view.add_item(cancel_btn)
    await interaction.response.send_message(f"**🗑️ حذف العمل:** `{العمل}`\nاختر الطريقة:", view=view, ephemeral=True)

@bot.tree.command(name="تعديل_عمل", description="تعديل بيانات عمل (للمشرفين)")
@app_commands.autocomplete(العمل=work_autocomplete)
@app_commands.describe(العمل="اختر العمل", الاسم_الجديد="اسم جديد (اختياري)", بداية_الفصول_المدفوعة="أول فصل مدفوع (اتركه فارغاً إن لم يتغير)", الكل_مدفوع="تفعيل إذا كان العمل كله مدفوعاً", نشط="حالة النشاط")
@app_commands.checks.cooldown(1, 5, key=lambda i: (i.user.id, i.command.qualified_name))
async def edit_work(interaction: discord.Interaction, العمل: str, الاسم_الجديد: str = None, بداية_الفصول_المدفوعة: int = None, الكل_مدفوع: bool = False, نشط: bool = None):
    if not is_admin(interaction):
        await log_unauthorized(interaction.user.id, "تعديل_عمل")
        await interaction.response.send_message("❌ ما عندك صلاحية.", ephemeral=True)
        return
    works = await load_works()
    target = next((w for w in works if w["name"] == العمل), None)
    if not target:
        await interaction.response.send_message("❌ العمل غير موجود.", ephemeral=True)
        return
    changed = []
    if الاسم_الجديد and الاسم_الجديد != target["name"]:
        if any(w["name"] == الاسم_الجديد for w in works):
            await interaction.response.send_message("❌ الاسم الجديد موجود مسبقاً.", ephemeral=True)
            return
        target["name"] = الاسم_الجديد
        changed.append(f"الاسم → {الاسم_الجديد}")
    if الكل_مدفوع:
        target["paid_start"] = None
        changed.append("كل الفصول مدفوعة")
    elif بداية_الفصول_المدفوعة is not None:
        target["paid_start"] = بداية_الفصول_المدفوعة
        changed.append(f"بداية الدفع = {بداية_الفصول_المدفوعة}")
    if نشط is not None and نشط != target.get("active", True):
        target["active"] = نشط
        changed.append(f"نشط = {نشط}")
    if not changed:
        await interaction.response.send_message("لم تقم بأي تغيير.", ephemeral=True)
        return
    await save_works(works)
    await log_audit("تعديل_عمل", interaction.user.id, None, f"تعديل {العمل}: {', '.join(changed)}")
    await interaction.response.send_message(f"✅ تم تعديل العمل `{العمل}`:\n" + "\n".join(changed), ephemeral=True)

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

@bot.tree.command(name="عرض_الاعمال", description="عرض قائمة الأعمال المدفوعة وحالتها")
@app_commands.checks.cooldown(1, 5, key=lambda i: (i.user.id, i.command.qualified_name))
async def list_works(interaction: discord.Interaction):
    works = await load_works()
    if not works:
        await interaction.response.send_message("📭 لا توجد أعمال في القائمة.", ephemeral=True)
        return
    view = WorksListPaginator(works)
    await interaction.response.send_message(embed=view.get_embed(), view=view)

# ----------------------------------------------------------------------
# NEW: Specialty management commands
# ----------------------------------------------------------------------
@bot.tree.command(name="اضافة_تخصص", description="إضافة تخصص جديد (للمشرفين)")
@app_commands.describe(الاسم="اسم التخصص (مثال: تدقيق)", السعر="سعر الفصل الواحد", نشط="مفعل؟")
@app_commands.checks.cooldown(1, 5, key=lambda i: (i.user.id, i.command.qualified_name))
async def add_specialty(interaction: discord.Interaction, الاسم: str, السعر: float, نشط: bool = True):
    if not is_admin(interaction):
        await log_unauthorized(interaction.user.id, "اضافة_تخصص")
        await interaction.response.send_message("❌ ما عندك صلاحية.", ephemeral=True)
        return
    norm_name = map_type(الاسم)
    if norm_name in SETTINGS.get("specialties", {}):
        await interaction.response.send_message("❌ التخصص موجود مسبقاً.", ephemeral=True)
        return
    SETTINGS["specialties"][norm_name] = {
        "price": السعر,
        "active": نشط,
        "last_modified": datetime.utcnow().isoformat()
    }
    await save_settings(SETTINGS)
    rebuild_prices()
    await log_audit("اضافة_تخصص", interaction.user.id, None, f"أضاف تخصص {norm_name} بسعر {السعر}")
    await interaction.response.send_message(f"✅ تم إضافة تخصص `{norm_name}`.", ephemeral=True)

@bot.tree.command(name="حذف_تخصص", description="حذف (تعطيل) تخصص (للمشرفين)")
@app_commands.autocomplete(الاسم=specialty_autocomplete)
@app_commands.checks.cooldown(1, 5, key=lambda i: (i.user.id, i.command.qualified_name))
async def delete_specialty(interaction: discord.Interaction, الاسم: str):
    if not is_admin(interaction):
        await log_unauthorized(interaction.user.id, "حذف_تخصص")
        await interaction.response.send_message("❌ ما عندك صلاحية.", ephemeral=True)
        return
    norm_name = map_type(الاسم)
    if norm_name not in SETTINGS.get("specialties", {}):
        await interaction.response.send_message("❌ التخصص غير موجود.", ephemeral=True)
        return
    SETTINGS["specialties"][norm_name]["active"] = False
    await save_settings(SETTINGS)
    rebuild_prices()
    await log_audit("حذف_تخصص", interaction.user.id, None, f"عطّل تخصص {norm_name}")
    await interaction.response.send_message(f"✅ تم تعطيل تخصص `{norm_name}`.", ephemeral=True)

@bot.tree.command(name="تفعيل_تخصص", description="تفعيل تخصص معطل (للمشرفين)")
@app_commands.autocomplete(الاسم=specialty_autocomplete)
@app_commands.checks.cooldown(1, 5, key=lambda i: (i.user.id, i.command.qualified_name))
async def activate_specialty(interaction: discord.Interaction, الاسم: str):
    if not is_admin(interaction):
        await log_unauthorized(interaction.user.id, "تفعيل_تخصص")
        await interaction.response.send_message("❌ ما عندك صلاحية.", ephemeral=True)
        return
    norm_name = map_type(الاسم)
    specialties = SETTINGS.get("specialties", {})
    if norm_name not in specialties:
        await interaction.response.send_message("❌ التخصص غير موجود.", ephemeral=True)
        return
    specialties[norm_name]["active"] = True
    await save_settings(SETTINGS)
    rebuild_prices()
    await interaction.response.send_message(f"✅ تم تفعيل تخصص `{norm_name}`.", ephemeral=True)

@bot.tree.command(name="تعطيل_تخصص", description="تعطيل تخصص (للمشرفين)")
@app_commands.autocomplete(الاسم=specialty_autocomplete)
@app_commands.checks.cooldown(1, 5, key=lambda i: (i.user.id, i.command.qualified_name))
async def deactivate_specialty(interaction: discord.Interaction, الاسم: str):
    if not is_admin(interaction):
        await log_unauthorized(interaction.user.id, "تعطيل_تخصص")
        await interaction.response.send_message("❌ ما عندك صلاحية.", ephemeral=True)
        return
    norm_name = map_type(الاسم)
    specialties = SETTINGS.get("specialties", {})
    if norm_name not in specialties:
        await interaction.response.send_message("❌ التخصص غير موجود.", ephemeral=True)
        return
    specialties[norm_name]["active"] = False
    await save_settings(SETTINGS)
    rebuild_prices()
    await interaction.response.send_message(f"✅ تم تعطيل تخصص `{norm_name}`.", ephemeral=True)

# ----------------------------------------------------------------------
# NEW: /مكافأة and /خصم (Admin bonus and deduction system)
# ----------------------------------------------------------------------
@bot.tree.command(name="مكافأة", description="إضافة مكافأة (مبلغ موجب) لعضو - للإدارة فقط")
@app_commands.describe(عضو="العضو المستحق للمكافأة", المبلغ="المبلغ الموجب المراد إضافته", السبب="سبب المكافأة (اختياري)")
@app_commands.checks.cooldown(1, 5, key=lambda i: (i.user.id, i.command.qualified_name))
async def add_bonus(interaction: discord.Interaction, عضو: discord.Member, المبلغ: float, السبب: str = None):
    if not is_admin(interaction):
        await log_unauthorized(interaction.user.id, "مكافأة")
        await interaction.response.send_message("❌ ما عندك صلاحية تستخدم هذا الأمر.", ephemeral=True)
        return
    if المبلغ <= 0:
        await interaction.response.send_message("❌ المبلغ يجب أن يكون أكبر من صفر.", ephemeral=True)
        return

    records = await load_records()
    user_id = str(عضو.id)
    if user_id not in records:
        records[user_id] = []

    bonus_entry = {
        "work_name": "نظام المكافآت والخصومات",
        "chapter": "مكافأة",
        "work_type": "مكافأة",
        "total": abs(المبلغ),
        "notes": السبب or "",
        "timestamp": datetime.utcnow().isoformat(),
        "username": عضو.name,
        "added_by": str(interaction.user.id)
    }
    records[user_id].append(bonus_entry)
    await save_records(records)
    await update_stats()

    embed = discord.Embed(title="🎁 **تمت إضافة المكافأة**", color=discord.Color.green())
    embed.add_field(name="**👤 العضو**", value=عضو.mention, inline=True)
    embed.add_field(name="**💰 المبلغ**", value=f"{SETTINGS.get('currency', '$')}{abs(المبلغ):.2f}", inline=True)
    if السبب:
        embed.add_field(name="**📝 السبب**", value=السبب, inline=False)
    embed.add_field(name="**🛡️ أضيفت بواسطة**", value=interaction.user.mention, inline=True)
    await interaction.response.send_message(embed=embed)

    await log_audit("مكافأة", interaction.user.id, عضو.id, f"مكافأة {abs(المبلغ):.2f} - السبب: {السبب or 'غير محدد'}")
    try:
        await عضو.send(f"🎁 لقد تلقيت مكافأة بقيمة {SETTINGS.get('currency', '$')}{abs(المبلغ):.2f} من {interaction.user.mention}.\nالسبب: {السبب or 'غير محدد'}")
    except:
        pass

@bot.tree.command(name="خصم", description="خصم مبلغ (سالب) من عضو - للإدارة فقط")
@app_commands.describe(عضو="العضو المراد الخصم منه", المبلغ="المبلغ الموجب (سيتم خصمه)", السبب="سبب الخصم (اختياري)")
@app_commands.checks.cooldown(1, 5, key=lambda i: (i.user.id, i.command.qualified_name))
async def add_deduction(interaction: discord.Interaction, عضو: discord.Member, المبلغ: float, السبب: str = None):
    if not is_admin(interaction):
        await log_unauthorized(interaction.user.id, "خصم")
        await interaction.response.send_message("❌ ما عندك صلاحية تستخدم هذا الأمر.", ephemeral=True)
        return
    if المبلغ <= 0:
        await interaction.response.send_message("❌ المبلغ يجب أن يكون أكبر من صفر.", ephemeral=True)
        return

    records = await load_records()
    user_id = str(عضو.id)
    if user_id not in records:
        records[user_id] = []

    deduction_entry = {
        "work_name": "نظام المكافآت والخصومات",
        "chapter": "خصم",
        "work_type": "خصم",
        "total": -abs(المبلغ),
        "notes": السبب or "",
        "timestamp": datetime.utcnow().isoformat(),
        "username": عضو.name,
        "added_by": str(interaction.user.id)
    }
    records[user_id].append(deduction_entry)
    await save_records(records)
    await update_stats()

    embed = discord.Embed(title="🔻 **تم الخصم**", color=discord.Color.red())
    embed.add_field(name="**👤 العضو**", value=عضو.mention, inline=True)
    embed.add_field(name="**💸 المبلغ المخصوم**", value=f"{SETTINGS.get('currency', '$')}{abs(المبلغ):.2f}", inline=True)
    if السبب:
        embed.add_field(name="**📝 السبب**", value=السبب, inline=False)
    embed.add_field(name="**🛡️ أضيف بواسطة**", value=interaction.user.mention, inline=True)
    await interaction.response.send_message(embed=embed)

    await log_audit("خصم", interaction.user.id, عضو.id, f"خصم {abs(المبلغ):.2f} - السبب: {السبب or 'غير محدد'}")
    try:
        await عضو.send(f"🔻 تم خصم مبلغ {SETTINGS.get('currency', '$')}{abs(المبلغ):.2f} من رصيدك بواسطة {interaction.user.mention}.\nالسبب: {السبب or 'غير محدد'}")
    except:
        pass

# ----------------------------------------------------------------------
# NEW: /حذف_مكافأة_خصم (Delete bonus/deduction entry)
# ----------------------------------------------------------------------
@bot.tree.command(name="حذف_مكافأة_خصم", description="حذف مكافأة أو خصم سابق لعضو - للإدارة فقط")
@app_commands.checks.cooldown(1, 5, key=lambda i: (i.user.id, i.command.qualified_name))
async def delete_bonus_deduction(interaction: discord.Interaction, عضو: discord.Member):
    if not is_admin(interaction):
        await log_unauthorized(interaction.user.id, "حذف_مكافأة_خصم")
        await interaction.response.send_message("❌ ما عندك صلاحية.", ephemeral=True)
        return
    records = await load_records()
    user_id = str(عضو.id)
    if user_id not in records:
        await interaction.response.send_message("❌ لا يوجد سجلات لهذا العضو.", ephemeral=True)
        return

    # Gather last 10 bonus/deduction entries
    all_entries = records[user_id]
    bonus_ded_entries = [e for e in all_entries if e.get("work_type") in ("مكافأة", "خصم")]
    bonus_ded_entries.reverse()  # newest first
    recent = bonus_ded_entries[:10]
    if not recent:
        await interaction.response.send_message("❌ لا يوجد عمليات مكافأة أو خصم لهذا العضو.", ephemeral=True)
        return

    options = []
    for i, e in enumerate(recent):
        desc = f"{e.get('work_type')} {abs(e.get('total', 0)):.2f} - {e.get('notes','')[:50]}"
        options.append(discord.SelectOption(label=f"{i+1}. {desc}", value=str(i)))
    options.append(discord.SelectOption(label="❌ إلغاء", value="cancel"))

    select = discord.ui.Select(placeholder="اختر العملية للحذف...", options=options)
    async def select_callback(interaction2: discord.Interaction):
        if select.values[0] == "cancel":
            await interaction2.response.edit_message(content="تم الإلغاء.", view=None)
            return
        idx = int(select.values[0])
        entry_to_delete = recent[idx]
        # Confirm with buttons
        confirm_view = discord.ui.View(timeout=30)
        async def confirm_callback(interaction3: discord.Interaction):
            records2 = await load_records()
            if user_id in records2:
                new_entries = []
                removed = False
                for e in records2[user_id]:
                    if not removed and e == entry_to_delete:
                        removed = True
                        continue
                    new_entries.append(e)
                if removed:
                    records2[user_id] = new_entries
                    if not records2[user_id]:
                        del records2[user_id]
                    await save_records(records2)
                    await log_audit("حذف_مكافأة_خصم", interaction2.user.id, عضو.id, f"حذف {entry_to_delete.get('work_type')} {abs(entry_to_delete.get('total',0)):.2f}")
                    await update_stats()
                    await interaction3.response.edit_message(content="✅ تم حذف العملية بنجاح.", view=None)
                    confirm_view.stop()
                else:
                    await interaction3.response.edit_message(content="❌ لم يتم العثور على العملية.", view=None)
                    confirm_view.stop()
            else:
                await interaction3.response.edit_message(content="❌ لا توجد سجلات.", view=None)
                confirm_view.stop()
        async def cancel_callback(interaction3: discord.Interaction):
            await interaction3.response.edit_message(content="❌ تم الإلغاء.", view=None)
            confirm_view.stop()
        confirm_btn = discord.ui.Button(label="تأكيد", style=discord.ButtonStyle.danger)
        confirm_btn.callback = confirm_callback
        cancel_btn = discord.ui.Button(label="إلغاء", style=discord.ButtonStyle.secondary)
        cancel_btn.callback = cancel_callback
        confirm_view.add_item(confirm_btn)
        confirm_view.add_item(cancel_btn)
        await interaction2.response.send_message(f"⚠️ تأكيد حذف {entry_to_delete.get('work_type')} بمبلغ {abs(entry_to_delete.get('total',0)):.2f}.", view=confirm_view, ephemeral=True)
    select.callback = select_callback
    view = discord.ui.View(timeout=60)
    view.add_item(select)
    await interaction.response.send_message(f"**عمليات المكافآت والخصومات للعضو {عضو.mention}:**", view=view)

# ----------------------------------------------------------------------
# NEW: Payment schedule command
# ----------------------------------------------------------------------
@bot.tree.command(name="تحديد_موعد_الدفع", description="تحديد يوم وساعة الدفع الشهري (للمشرفين)")
@app_commands.describe(اليوم="يوم الشهر (1-28)", الساعة="الساعة (0-23)، افتراضي 0")
@app_commands.checks.cooldown(1, 5, key=lambda i: (i.user.id, i.command.qualified_name))
async def set_payment_day(interaction: discord.Interaction, اليوم: int, الساعة: int = 0):
    if not is_admin(interaction):
        await log_unauthorized(interaction.user.id, "تحديد_موعد_الدفع")
        await interaction.response.send_message("❌ ما عندك صلاحية.", ephemeral=True)
        return
    if not (1 <= اليوم <= 28):
        await interaction.response.send_message("❌ اليوم يجب أن يكون بين 1 و 28.", ephemeral=True)
        return
    if not (0 <= الساعة <= 23):
        await interaction.response.send_message("❌ الساعة يجب أن تكون بين 0 و 23.", ephemeral=True)
        return
    SETTINGS["payment_day"] = اليوم
    SETTINGS["payment_hour"] = الساعة
    SETTINGS["payment_reminder_24h_sent"] = False
    SETTINGS["payment_day_sent"] = False
    await save_settings(SETTINGS)
    await interaction.response.send_message(f"✅ تم تعيين موعد الدفع الشهري يوم {اليوم} الساعة {الساعة}:00.", ephemeral=True)
    await log_audit("تحديد_موعد_الدفع", interaction.user.id, None, f"يوم {اليوم} ساعة {الساعة}")

@bot.tree.command(name="تقرير_دفع", description="تقرير الدفع الشهري مع خيار تصدير Excel")
@app_commands.checks.cooldown(1, 10, key=lambda i: (i.user.id, i.command.qualified_name))
async def payment_report(interaction: discord.Interaction):
    if not is_admin(interaction):
        await log_unauthorized(interaction.user.id, "تقرير_دفع")
        await interaction.response.send_message("❌ ما عندك صلاحية.", ephemeral=True)
        return
    records = await load_records()
    month_start = datetime.utcnow().replace(day=1)
    totals = {}
    details = {}
    for user_id, entries in records.items():
        user_total = 0
        user_entries = []
        for e in entries:
            try:
                entry_date = datetime.fromisoformat(e["timestamp"])
                if entry_date >= month_start:
                    user_total += e.get("total", 0)
                    user_entries.append(e)
            except:
                pass
        if user_entries:
            totals[user_id] = user_total
            details[user_id] = user_entries
    if not totals:
        await interaction.response.send_message("لا توجد أي سجلات لهذا الشهر.", ephemeral=True)
        return

    embed = discord.Embed(title="📅 **تقرير الدفع الشهري**", color=discord.Color.green())
    grand_total = sum(totals.values())
    embed.add_field(name="إجمالي المبلغ المستحق", value=f"{SETTINGS.get('currency', '$')}{grand_total:.2f}", inline=False)
    # Show top 10
    sorted_totals = sorted(totals.items(), key=lambda x: x[1], reverse=True)[:10]
    member_list = "\n".join([f"<@{uid}>: {SETTINGS.get('currency', '$')}{amt:.2f}" for uid, amt in sorted_totals])
    embed.add_field(name="المستحقات (أول 10)", value=member_list, inline=False)

    # Button to export monthly Excel
    async def export_callback(interaction2: discord.Interaction):
        rows = []
        for user_id, entries in details.items():
            user = interaction.guild.get_member(int(user_id))
            username = user.display_name if user else user_id
            for entry in entries:
                rows.append({
                    "اسم العضو": username,
                    "معرف العضو": user_id,
                    "العمل": entry.get("work_name"),
                    "الفصل": entry.get("chapter"),
                    "التخصص": entry.get("work_type"),
                    "المبلغ": entry.get("total"),
                    "ملاحظات": entry.get("notes"),
                    "التاريخ": entry.get("timestamp", "")
                })
        df = pd.DataFrame(rows)
        buffer = BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name="تقرير_الشهر")
        buffer.seek(0)
        await interaction2.response.send_message(file=discord.File(buffer, filename=f"payment_report_{datetime.utcnow().date()}.xlsx"))

    view = discord.ui.View(timeout=60)
    export_btn = discord.ui.Button(label="📥 تصدير Excel", style=discord.ButtonStyle.primary)
    export_btn.callback = export_callback
    view.add_item(export_btn)
    await interaction.response.send_message(embed=embed, view=view)

# ----------------------------------------------------------------------
# NEW: /ملخص_شهري for members
# ----------------------------------------------------------------------
@bot.tree.command(name="ملخص_شهري", description="ملخص شغلك للشهر الحالي")
@app_commands.checks.cooldown(1, 5, key=lambda i: (i.user.id, i.command.qualified_name))
async def monthly_summary(interaction: discord.Interaction):
    if interaction.channel.name not in SETTINGS.get("allowed_channels", []):
        await interaction.response.send_message("❌ القناة غير مسموحة.", ephemeral=True)
        return
    records = await load_records()
    user_id = str(interaction.user.id)
    if user_id not in records:
        await interaction.response.send_message("📭 ليس لديك أي شغل.", ephemeral=True)
        return
    month_start = datetime.utcnow().replace(day=1)
    month_entries = [e for e in records[user_id] if "timestamp" in e and datetime.fromisoformat(e["timestamp"]) >= month_start]
    if not month_entries:
        await interaction.response.send_message("لم تقم بأي عمل هذا الشهر.", ephemeral=True)
        return
    total = sum(e.get("total", 0) for e in month_entries)
    works_count = defaultdict(int)
    for e in month_entries:
        works_count[e.get("work_name", "غير محدد")] += 1
    details_str = "\n".join([f"**{w}:** {c} فصول" for w, c in works_count.items()])
    embed = discord.Embed(title="📆 **ملخصك الشهري**", color=discord.Color.blue())
    embed.add_field(name="عدد الفصول المنجزة", value=len(month_entries), inline=True)
    embed.add_field(name="المبلغ المستحق", value=f"{SETTINGS.get('currency', '$')}{total:.2f}", inline=True)
    embed.add_field(name="تفصيل الأعمال", value=details_str, inline=False)
    await interaction.response.send_message(embed=embed)

# ----------------------------------------------------------------------
# NEW: /تحديث_أسعار command
# ----------------------------------------------------------------------
@bot.tree.command(name="تحديث_أسعار", description="تحديث مبالغ الفصول المسجلة بناءً على الأسعار الحالية (للمشرفين)")
@app_commands.autocomplete(التخصص=specialty_autocomplete)
@app_commands.describe(
    التخصص="تخصص محدد (اختياري، وإلا كل التخصصات)",
    من_تاريخ="بداية النطاق (YYYY-MM-DD، اختياري)",
    الى_تاريخ="نهاية النطاق (YYYY-MM-DD، اختياري)",
    كل_السجلات="تحديث كل السجلات بغض النظر عن التاريخ"
)
@app_commands.checks.cooldown(1, 10, key=lambda i: (i.user.id, i.command.qualified_name))
async def update_prices(interaction: discord.Interaction, التخصص: str = None, من_تاريخ: str = None, الى_تاريخ: str = None, كل_السجلات: bool = False):
    if not is_admin(interaction):
        await log_unauthorized(interaction.user.id, "تحديث_أسعار")
        await interaction.response.send_message("❌ ما عندك صلاحية.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    records = await load_records()
    specialties = SETTINGS.get("specialties", {})
    updated_count = 0
    # Determine specialty filter
    target_specialty = map_type(التخصص) if التخصص else None
    if target_specialty and target_specialty not in specialties:
        await interaction.followup.send(f"❌ التخصص `{التخصص}` غير موجود.", ephemeral=True)
        return
    # Determine date range
    if كل_السجلات:
        date_from = None
        date_to = None
    elif من_تاريخ or الى_تاريخ:
        try:
            date_from = datetime.fromisoformat(من_تاريخ) if من_تاريخ else datetime.min
            date_to = datetime.fromisoformat(الى_تاريخ) if الى_تاريخ else datetime.max
        except:
            await interaction.followup.send("❌ صيغة التاريخ غير صحيحة. استخدم YYYY-MM-DD.", ephemeral=True)
            return
    else:
        # Default: current month
        date_from = datetime.utcnow().replace(day=1)
        date_to = datetime.utcnow()
    # Iterate records and update
    for user_id, entries in records.items():
        for entry in entries:
            wtype = entry.get("work_type")
            # Only update work types that are in specialties (ignore bonus/deduction)
            if wtype not in specialties:
                continue
            if target_specialty and wtype != target_specialty:
                continue
            if not كل_السجلات:
                try:
                    entry_date = datetime.fromisoformat(entry.get("timestamp"))
                    if entry_date < date_from or entry_date > date_to:
                        continue
                except:
                    continue
            # Update total to current price of that specialty
            if specialties[wtype].get("active", True):
                entry["total"] = specialties[wtype]["price"]
                updated_count += 1
    await save_records(records)
    await update_stats()
    await log_audit("تحديث_أسعار", interaction.user.id, None, f"تم تحديث {updated_count} سجل - التخصص: {التخصص or 'الكل'}, الفترة: {'كل السجلات' if كل_السجلات else f'{من_تاريخ or "بداية الشهر"} -> {الى_تاريخ or "الآن"}'}")
    await interaction.followup.send(f"✅ تم تحديث {updated_count} سجل بنجاح.", ephemeral=True)

# ----------------------------------------------------------------------
# Init & run
# ----------------------------------------------------------------------