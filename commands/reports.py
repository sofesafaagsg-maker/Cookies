from datetime import datetime, timezone, timedelta
import discord
from discord import app_commands
from discord.ext import commands
from state import bot, SETTINGS, stats_collection, audit_collection
from helpers.core import *
from helpers.core import make_embed
from views.paginators import WorkDetailsView, WorksPaginator, get_works_info

# ==========================================
# 🛠️ الدوال المساعدة لتوحيد وتسهيل الكود
# ==========================================

def _get_member_work_data(user_id: str, records: dict) -> dict:
    """تحليل سجلات العضو وتصنيف أعماله ومكافآته وخصوماته بدقة"""
    user_records = records.get(user_id, [])
    
    data = {
        "has_work": bool(user_records),
        "works": {},
        "bonuses": [],
        "deductions": [],
        "total_bonus": 0,
        "total_deduction": 0,
        "total_all": 0
    }
    
    if not data["has_work"]:
        return data

    for entry in user_records:
        wtype = entry.get("work_type")
        if wtype == "مكافأة":
            data["bonuses"].append(entry)
            data["total_bonus"] += entry.get("total", 0)
        elif wtype == "خصم":
            data["deductions"].append(entry)
            data["total_deduction"] += abs(entry.get("total", 0))
        else:
            work_name = entry.get("work_name", "غير محدد")
            data["works"].setdefault(work_name, []).append(entry)
            
    # حساب صافي إجمالي الأعمال العادية
    total_works_amount = sum(
        sum(e.get("total", 0) for e in entries) 
        for entries in data["works"].values()
    )
    
    data["total_all"] = total_works_amount + data["total_bonus"] - data["total_deduction"]
    return data


def _build_work_embed(target: discord.Member, data: dict, currency: str) -> discord.Embed:
    """بناء إمبيد موحد واحترافي لعرض الملف المالي للأعضاء"""
    embed = discord.Embed(
        title=f"💼 اللوحة الشخصية • {target.display_name}",
        description=f"📊 ملخص مالي وحسابي شامل لإجمالي السجلات الخاصة بالعضو {target.mention}.",
        color=discord.Color.blue()
    )
    # استخدام رابط الصورة الرمزية الافتراضية دائمًا (حتى لو لم يخصص صورة)
    embed.set_thumbnail(url=target.display_avatar.url)
    
    # عرض تفاصيل الأعمال
    for work, entries in data["works"].items():
        work_total = sum(e.get("total", 0) for e in entries)
        chapters_count = len(entries)
        
        types_count = {}
        for e in entries:
            wtype = e.get("work_type", "غير معروف")
            types_count[wtype] = types_count.get(wtype, 0) + 1
            
        type_str = " | ".join([f"**{k.replace('_',' ').title()}:** {v}" for k, v in types_count.items() if v > 0])
        
        embed.add_field(
            name=f"📁 {work}",
            value=f"📌 **الفصول:** {chapters_count}\n📈 **التخصصات:** {type_str}\n💰 **المجموع:** `{currency}{work_total:.2f}`",
            inline=False
        )

    # التسويات (المكافآت والخصومات)
    if data["bonuses"] or data["deductions"]:
        balance_details = ""
        if data["total_bonus"] > 0:
            # تم تصحيح علامات التنصيص في الأسطر التالية
            balance_details += f'🎁 **إجمالي المكافآت:** `{currency}{data["total_bonus"]:.2f}`\n'
        if data["total_deduction"] > 0:
            balance_details += f'🔻 **إجمالي الخصومات:** `{currency}{data["total_deduction"]:.2f}`\n'
        embed.add_field(name="⚖️ تسويات مالية اضافية", value=balance_details, inline=False)

    # الصافي النهائي المتميز
    embed.add_field(
        name="✨ الصافي المالي النهائي", 
        value=f"### 💵 `{currency}{data['total_all']:.2f}`", 
        inline=False
    )
    embed.set_footer(text="اضغط على الأزرار أدناه لمعاينة تفاصيل فصول كل عمل بشكل منفصل.")
    return embed


def _create_work_buttons(user_id: str, target_name: str, data: dict, currency: str) -> discord.ui.View:
    """إنشاء أزرار تفاعلية مخصصة لتفاصيل الأعمال المحددة"""
    view = discord.ui.View(timeout=60)
    # عرض أول 5 أعمال كأزرار لمنع تجاوز حدود واجهة ديسكورد
    for work, entries in list(data["works"].items())[:5]:
        chapters_details = [
            {"chapter": e.get("chapter"), "type": e.get("work_type"), "total": e.get("total", 0), "notes": e.get("notes", "")} 
            for e in entries
        ]
        
        button = discord.ui.Button(label=f"معاينة: {work}", style=discord.ButtonStyle.secondary, emoji="📖")
        
        # إصلاح مشكلة await في دالة غير متزامنة باستخدام الإغلاق المباشر
        async def btn_cb(interaction: discord.Interaction, wn=work, ch_list=chapters_details):
            v = WorkDetailsView(wn, ch_list, user_id, target_name, currency)
            await interaction.response.send_message(embed=v.get_embed(), view=v, ephemeral=True)
            
        button.callback = btn_cb
        view.add_item(button)
    return view


def _convert_to_timestamp(date_source) -> str:
    """تحويل التواريخ النصية أو الكائنات إلى صيغة ديسكورد التفاعلية"""
    try:
        if isinstance(date_source, str) and date_source != "غير معروف":
            dt = datetime.fromisoformat(date_source.replace("Z", "+00:00"))
            return f"<t:{int(dt.timestamp())}:R>"
        elif isinstance(date_source, datetime):
            return f"<t:{int(date_source.timestamp())}:R>"
    except Exception:
        pass
    return "غير محدد"


# ==========================================
# 🛑 نظام التحقق من القنوات المسموحة
# ==========================================

def is_channel_allowed():
    def predicate(interaction: discord.Interaction) -> bool:
        allowed = SETTINGS.get("allowed_channels", [])
        if not allowed or interaction.channel.name in allowed:
            return True
        return False
    return app_commands.check(predicate)


# ==========================================
# 🚀 حزمة الأوامر المحدثة والمطورة
# ==========================================

@bot.tree.command(name="الأعمال", description="📚 عرض كشاف شامل لجميع الأعمال المسجلة والمساهمين")
@app_commands.checks.cooldown(1, 5, key=lambda i: (i.user.id, i.command.qualified_name))
@is_channel_allowed()
async def projects_report(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=False)
    works_info = await get_works_info(interaction.guild)
    
    if not works_info:
        await interaction.followup.send("📭 لا توجد أعمال مسجلة حالياً في قاعدة البيانات.", ephemeral=True)
        return
        
    embed = discord.Embed(
        title="📚 كشاف قائمة الأعمال", 
        description="هنا تجد إحصائية سريعة بالأعمال المدرجة، يمكنك استخدام الأزرار والقوائم للتنقل السلس.",
        color=discord.Color.purple()
    )
    embed.add_field(name="📊 إجمالي المشاريع النشطة", value=f"`{len(works_info)} عمل مسجل`", inline=True)
    embed.set_footer(text="استخدم أزرار التحكم في الصفحات بالأسفل لاستعراض باقي المحتوى.")
    
    view = WorksPaginator(works_info, interaction.guild)
    await interaction.followup.send(embed=embed, view=view)


@projects_report.error
async def projects_report_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message("❌ عذراً، هذا الأمر غير متاح للاستخدام في هذه القناة.", ephemeral=True)


@bot.tree.command(name="احصائيات", description="📊 استعراض لوحة الإحصائيات المتقدمة للأداء المالي والعملي")
@app_commands.checks.cooldown(1, 5, key=lambda i: (i.user.id, i.command.qualified_name))
async def stats(interaction: discord.Interaction):
    stat_doc = await stats_collection.find_one({"_id": "stats"})
    if not stat_doc:
        await interaction.response.send_message("⚠️ لم يتم تجميع أي بيانات أو إحصائيات في الوقت الحالي.", ephemeral=True)
        return

    currency = SETTINGS.get('currency', '$')
    total_entries = stat_doc.get("total_entries", 0)
    total_amount = stat_doc.get("total_amount", 0)
    type_counts = stat_doc.get("type_counts", {})
    
    daily = stat_doc.get("daily", {"entries": 0, "amount": 0})
    weekly = stat_doc.get("weekly", {"entries": 0, "amount": 0})
    monthly = stat_doc.get("monthly", {"entries": 0, "amount": 0})
    top_members = stat_doc.get("top_members", [])
    
    embed = discord.Embed(
        title="📊 لوحة البيانات والإحصائيات العامة", 
        description="مظهر تحليلي تفصيلي يوضح وتيرة الإنتاجية الحالية ونسب التخصصات والمبالغ الصادرة.",
        color=discord.Color.teal()
    )
    
    embed.add_field(name="📄 إجمالي الفصول المنجزة", value=f"`{total_entries} فصل`", inline=True)
    embed.add_field(name="💰 إجمالي المبالغ التراكمية", value=f"`{currency}{total_amount:.2f}`", inline=True)
    
    # تنسيق قسم التخصصات بشكل منظم داخل صندوق كود
    if type_counts:
        type_lines = "\n".join([f"▫️ {k.replace('_',' ').title()}: {v} فصل" for k, v in type_counts.items()])
        embed.add_field(name="⚡ تفصيل الإنتاجية حسب التخصص", value=f"```md\n{type_lines}```", inline=False)

    # فترات العمل الزمني الموحد
    embed.add_field(name="📅 الحصاد اليومي", value=f"📝 فصول: `{daily['entries']}`\n💵 بمبلغ: `{currency}{daily['amount']:.2f}`", inline=True)
    embed.add_field(name="📆 الحصاد الأسبوعي", value=f"📝 فصول: `{weekly['entries']}`\n💵 بمبلغ: `{currency}{weekly['amount']:.2f}`", inline=True)
    embed.add_field(name="📆 الحصاد الشهري", value=f"📝 فصول: `{monthly['entries']}`\n💵 بمبلغ: `{currency}{monthly['amount']:.2f}`", inline=True)

    # قائمة المتصدرين (التوب 5) بشكل أيقونات ترتيب احترافي
    if top_members:
        top_list = ""
        records = await load_records()
        medals = ["🥇", "🥈", "🥉", "🏅", "🏅"]
        
        for i, (uid, stats_data) in enumerate(top_members[:5]):
            username_hint = None
            if uid in records:
                for e in records[uid]:
                    if e.get("username"):
                        username_hint = e["username"]
                        break
            display = format_member_display(interaction.guild, int(uid), username_hint)
            top_list += f"{medals[i]} {display} ➔ `{currency}{stats_data['total_amount']:.2f}` ({stats_data['total_entries']} فصل)\n"
            
        embed.add_field(name="🏆 قائمة الأعضاء الأكثر إنتاجية (Top 5)", value=top_list, inline=False)

    last_up_time = _convert_to_timestamp(stat_doc.get("last_updated", "غير معروف"))
    embed.add_field(name="🔄 حالة التحديث للوحة", value=f"تم التحديث: {last_up_time}", inline=False)
    
    await interaction.response.send_message(embed=embed)


# --- أوامر أعمالي (Slash & Text) ---

@bot.tree.command(name="أعمالي", description="💼 عرض لوحتك الشخصية المجمعة شاملة الأرباح والتفاصيل")
@app_commands.checks.cooldown(1, 5, key=lambda i: (i.user.id, i.command.qualified_name))
@is_channel_allowed()
async def my_works_slash(interaction: discord.Interaction):
    records = await load_records()
    user_id = str(interaction.user.id)
    currency = SETTINGS.get('currency', '$')
    
    data = _get_member_work_data(user_id, records)
    if not data["has_work"]:
        await interaction.response.send_message("📭 لا توجد أعمال أو سجلات مسجلة باسمك حتى الآن.", ephemeral=True)
        return

    embed = _build_work_embed(interaction.user, data, currency)
    view = _create_work_buttons(user_id, interaction.user.display_name, data, currency)
    
    await interaction.response.send_message(embed=embed, view=view)


@my_works_slash.error
async def my_works_slash_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message("❌ عذراً، هذا الأمر غير متاح للاستخدام في هذه القناة.", ephemeral=True)


@bot.command(name="أعمالي")
@commands.cooldown(1, 5, commands.BucketType.user)
async def my_works_text(ctx):
    records = await load_records()
    user_id = str(ctx.author.id)
    currency = SETTINGS.get('currency', '$')
    
    data = _get_member_work_data(user_id, records)
    if not data["has_work"]:
        await ctx.reply("📭 لا توجد أعمال أو سجلات مسجلة باسمك حتى الآن.")
        return

    embed = _build_work_embed(ctx.author, data, currency)
    view = _create_work_buttons(user_id, ctx.author.display_name, data, currency)
    
    await ctx.reply(embed=embed, view=view)


# --- أوامر شغل عضو آخر (Slash & Text) ---

@bot.tree.command(name="شغل", description="🔍 استعراض الملف المالي والعملي لعضو معين بالسيرفر")
@app_commands.checks.cooldown(1, 5, key=lambda i: (i.user.id, i.command.qualified_name))
@is_channel_allowed()
async def show_work_slash(interaction: discord.Interaction, member: discord.Member = None):
    target = member or interaction.user
    records = await load_records()
    user_id = str(target.id)
    currency = SETTINGS.get('currency', '$')
    
    data = _get_member_work_data(user_id, records)
    if not data["has_work"]:
        await interaction.response.send_message(f"📭 لا توجد سجلات أعمال محفوظة حالياً للعضو {target.mention}.", ephemeral=True)
        return

    embed = _build_work_embed(target, data, currency)
    view = _create_work_buttons(user_id, target.display_name, data, currency)
    
    await interaction.response.send_message(embed=embed, view=view)


@show_work_slash.error
async def show_work_slash_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message("❌ عذراً، هذا الأمر غير متاح للاستخدام في هذه القناة.", ephemeral=True)


@bot.command(name="شغل")
@commands.cooldown(1, 5, commands.BucketType.user)
async def show_work_text(ctx, member: discord.Member = None):
    target = member or ctx.author
    records = await load_records()
    user_id = str(target.id)
    currency = SETTINGS.get('currency', '$')
    
    data = _get_member_work_data(user_id, records)
    if not data["has_work"]:
        await ctx.reply(f"📭 لا توجد سجلات أعمال محفوظة حالياً للعضو {target.mention}.")
        return

    embed = _build_work_embed(target, data, currency)
    view = _create_work_buttons(user_id, target.display_name, data, currency)
    
    await ctx.reply(embed=embed, view=view)


# --- الأوامر الإدارية والتقارير ---

@bot.tree.command(name="لوحة_التحكم", description="🖥️ فتح وحدة الإدارة والتحكم الرئيسية (للمشرفين فقط)")
@app_commands.checks.cooldown(1, 5, key=lambda i: (i.user.id, i.command.qualified_name))
async def dashboard(interaction: discord.Interaction):
    if not is_admin(interaction):
        await log_unauthorized(interaction.user.id, "لوحة_التحكم")
        await interaction.response.send_message("❌ لا تمتلك الصلاحيات الإدارية المطلوبة لتنفيذ هذا الإجراء.", ephemeral=True)
        return
        
    records = await load_records()
    total_users = len(records)
    total_entries = sum(len(entries) for entries in records.values())
    total_amount = sum(sum(e.get("total", 0) for e in entries) for entries in records.values())
    currency = SETTINGS.get('currency', '$')
    
    embed = discord.Embed(
        title="🖥️ لوحة التحكم ومركز الإدارة الشامل",
        description="مؤشرات وإعدادات النظام الحالية ومراقبة أداء الميزانية العامة.",
        color=discord.Color.dark_red()
    )
    
    # قسم الإحصاءات العامة للمشرف
    embed.add_field(name="👥 طاقم العمل النشط", value=f"`{total_users} عضو`", inline=True)
    embed.add_field(name="📦 إجمالي قيود السجلات", value=f"`{total_entries} سجل مضاف`", inline=True)
    embed.add_field(name="💰 الموازنة المصروفة الكلية", value=f"`{currency}{total_amount:.2f}`", inline=True)
    
    # قسم التهيئة والقنوات السيستم
    notify_ch = f"<#{SETTINGS.get('notify_channel_id')}>" if SETTINGS.get('notify_channel_id') else "`غير معين`"
    backup_ch = f"<#{SETTINGS.get('daily_backup_channel_id')}>" if SETTINGS.get('daily_backup_channel_id') else "`غير معين`"
    
    config_info = (
        f"⚙️ **العملة المعتمدة:** `{currency}`\n"
        f"🔔 **قناة الإشعارات:** {notify_ch}\n"
        f"💾 **قناة النسخ الاحتياطي:** {backup_ch}\n"
        f"⚠️ **حد التنبيه والتحذير:** `{currency}{SETTINGS.get('alert_threshold', 10):.2f}`"
    )
    embed.add_field(name="⚙️ تهيئة قنوات النظام الأساسية", value=config_info, inline=False)
    
    payment_day = SETTINGS.get("payment_day")
    pay_hour = SETTINGS.get('payment_hour', 0)
    pay_info = f"📅 يوم `{payment_day}` من كل شهر - الساعة `{pay_hour}:00`" if payment_day else "`لم يتم تحديد موعد مسبق`"
    embed.add_field(name="📆 الجدولة الزمنية للصرف المالي", value=pay_info, inline=False)
    
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="سجل", description="📜 مراجعة آخر 20 عملية وتدقيق إداري تم تنفيذها بالمنظومة")
@app_commands.checks.cooldown(1, 5, key=lambda i: (i.user.id, i.command.qualified_name))
async def audit_log(interaction: discord.Interaction):
    if not is_admin(interaction):
        await log_unauthorized(interaction.user.id, "سجل")
        await interaction.response.send_message("❌ لا تمتلك الصلاحيات الإدارية لمشاهدة سجلات التدقيق والمراقبة.", ephemeral=True)
        return
        
    logs = await audit_collection.find().sort("timestamp", -1).limit(20).to_list(length=20)
    if not logs:
        await interaction.response.send_message("📭 سجل التدقيق فارغ تماماً، لا توجد عمليات مسجلة حديثاً.", ephemeral=True)
        return
        
    embed = discord.Embed(
        title="📜 سجل العمليات الإدارية والتدقيق", 
        description="مراقبة حية لآخر الإجراءات المتبعة من قبل المشرفين داخل النظام لضمان الشفافية.",
        color=discord.Color.dark_gray()
    )
    
    for log in logs:
        log_time = _convert_to_timestamp(log.get('timestamp'))
        target_str = f"<@{log.get('target_id')}>" if log.get('target_id') else "`عام`"
        
        log_content = (
            f"👤 **المشرف:** <@{log.get('moderator_id')}>\n"
            f"🎯 **المستهدف:** {target_str}\n"
            f"💬 **التفاصيل:** {log.get('details')}\n"
            f"⏱️ **التوقيت:** {log_time}"
        )
        embed.add_field(
            name=f"🔹 إجراء: {log.get('action', 'غير محدد')}", 
            value=log_content, 
            inline=False
        )
        
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="تقريري", description="📅 توليد ملخص حصاد أسبوعي تفاعلي خاص بأعمالك الشخصية")
@app_commands.checks.cooldown(1, 5, key=lambda i: (i.user.id, i.command.qualified_name))
async def my_weekly_report(interaction: discord.Interaction):
    records = await load_records()
    user_id = str(interaction.user.id)
    
    if user_id not in records:
        await interaction.response.send_message("📭 ليس لديك ملف بيانات أو فصول مضافة مسجلة بالسيستم.", ephemeral=True)
        return
        
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    week_entries = []
    
    for e in records[user_id]:
        if "timestamp" in e:
            try:
                # محاولة التحويل والتحقق من النطاق الزمني للأسبوع الأخير
                entry_dt = datetime.fromisoformat(e["timestamp"].replace("Z", "+00:00"))
                if entry_dt.tzinfo is None:
                    entry_dt = entry_dt.replace(tzinfo=timezone.utc)
                if entry_dt > week_ago:
                    week_entries.append(e)
            except ValueError:
                continue

    if not week_entries:
        await interaction.response.send_message("📭 لم تقم بتسجيل أي فصول أو تسويات خلال فترة الـ 7 أيام الماضية.", ephemeral=True)
        return
        
    total = sum(e.get("total", 0) for e in week_entries)
    currency = SETTINGS.get('currency', '$')
    
    embed = discord.Embed(
        title="📅 تقرير الحصاد والإنتاجية الأسبوعي", 
        description="ملخص سريع لمعدل الأداء المالي والعملي الخاص بك خلال آخر 7 أيام الماضية.",
        color=discord.Color.green()
    )
    embed.add_field(name="✅ عدد المهام والفصول المقيدة", value=f"`{len(week_entries)} مهمة`", inline=True)
    embed.add_field(name="💰 صافي أرباح الأسبوع الحالي", value=f"`{currency}{total:.2f}`", inline=True)
    embed.set_footer(text="استمر بهذا العطاء الرائع لرفع جودة وكفاءة العمل!")
    
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="تعديل", description="✏️ تعديل وتحديث بيانات آخر سجل قمت بإضافته إلى حسابك")
@app_commands.checks.cooldown(1, 5, key=lambda i: (i.user.id, i.command.qualified_name))
@app_commands.describe(
    العمل="اسم العمل الجديد المراد تعديله",
    الفصل="رقم أو اسم الفصل المحدث",
    التخصص="تحديد تخصص العمل الحالي المعتمد بالأسعار",
    ملاحظات="أي ملاحظات إضافية تريد إلحاقها بالقيد"
)
async def edit_last(
    interaction: discord.Interaction, 
    العمل: str = None, 
    الفصل: str = None, 
    التخصص: str = None, 
    ملاحظات: str = None
):
    records = await load_records()
    user_id = str(interaction.user.id)
    
    if user_id not in records or not records[user_id]:
        await interaction.response.send_message("⚠️ لم نجد أي سجلات حالية محفوظة في حسابك لتعديلها.", ephemeral=True)
        return
        
    last = records[user_id][-1]
    changes = []
    
    if العمل:
        changes.append(f"• العمل: `{last.get('work_name')}` ➔ `{العمل}`")
        last["work_name"] = العمل
    if الفصل:
        changes.append(f"• الفصل: `{last.get('chapter')}` ➔ `{الفصل}`")
        last["chapter"] = الفصل
    if التخصص:
        norm_type = map_type(التخصص)
        if norm_type not in PRICES:
            await interaction.response.send_message("❌ التخصص الذي قمت بإدخاله غير مدعوم أو غير صحيح بجدول الأسعار.", ephemeral=True)
            return
        changes.append(f"• التخصص: `{last.get('work_type')}` ➔ `{norm_type}`")
        last["work_type"] = norm_type
        last["total"] = PRICES[norm_type]
    if ملاحظات is not None:
        changes.append(f"• الملاحظات: `{last.get('notes', 'لا يوجد')}` ➔ `{ملاحظات}`")
        last["notes"] = ملاحظات
        
    if not changes:
        await interaction.response.send_message("ℹ️ لم تقم بإدخال أي متغيرات جديدة، تم إلغاء عملية التعديل السريع.", ephemeral=True)
        return
        
    await save_records(records)
    await update_stats()
    
    embed = discord.Embed(
        title="✅ تم تعديل وتحديث آخر سجل بنجاح",
        description="تمت مراجعة القيد الأخير وتعديل المتغيرات المطلوبة وتحديث قاعدة الإحصاءات العامة.",
        color=discord.Color.brand_green()
    )
    embed.add_field(name="📋 تفاصيل التحديثات المطبقة", value="\n".join(changes), inline=False)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)