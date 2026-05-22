import discord
from datetime import datetime
from discord import app_commands
from discord.ext import commands
from state import bot
from helpers.core import SETTINGS, save_settings, load_settings, rebuild_prices, PRICES
from tasks.lifecycle import specialty_autocomplete
@bot.tree.command(name="اوامر", description="عرض قائمة بجميع أوامر البوت")
@app_commands.checks.cooldown(1, 5, key=lambda i: (i.user.id, i.command.qualified_name))
async def help_slash(interaction: discord.Interaction):
    embed = discord.Embed(title="📌 **أوامر البوت**", color=discord.Color.purple())
    embed.add_field(name="**▸ تسجيل شغل جديد**",
                    value="`!تحليل` أو `/تسجيل`\n*يدعم فصلاً واحداً أو عدة فصول، وأنماط تخصصات مثل `ترجمة كوري-تحرير`*",
                    inline=False)
    embed.add_field(name="**▸ عرض أعمالي**", value="`!أعمالي` أو `/أعمالي`", inline=False)
    embed.add_field(name="**▸ عرض شغل عضو**", value="`!شغل @member` أو `/شغل`", inline=False)
    embed.add_field(name="**▸ عرض الأسعار**", value="`!اسعار` أو `/اسعار`", inline=False)
    embed.add_field(name="**▸ تعديل السعر (للمشرفين)**", value="`/تعديل_سعر`", inline=False)
    embed.add_field(name="**▸ حذف (للمشرفين)**",
                    value="`/حذف` (يدعم حذف كل السجلات، أو عمل كامل، أو فصل محدد)", inline=False)
    embed.add_field(name="**▸ حذف كل السجلات (للمشرفين)**", value="`!حذف_الكل` أو `/حذف_الكل`", inline=False)
    embed.add_field(name="**▸ تسجيل شغل لعضو (للمشرفين)**", value="`/تسجيل_للغير`", inline=False)
    embed.add_field(name="**▸ حذف كل الأعمال (للمشرفين)**", value="`/حذف_كل_الأعمال`", inline=False)
    embed.add_field(name="**▸ تحديد القنوات (للمشرفين)**", value="`!تحديد_قنوات` أو `/تحديد_قنوات`", inline=False)
    embed.add_field(name="**▸ لوحة التحكم (للمشرفين)**", value="`/لوحة_التحكم`", inline=False)
    embed.add_field(name="**▸ الإحصائيات**", value="`/احصائيات`", inline=False)
    embed.add_field(name="**▸ سجل العمليات (للمشرفين)**", value="`/سجل`", inline=False)
    embed.add_field(name="**▸ تقريري الأسبوعي**", value="`/تقريري`", inline=False)
    embed.add_field(name="**▸ تعديل آخر سجل**", value="`/تعديل`", inline=False)
    embed.add_field(name="**▸ تصدير Excel (للمشرفين)**", value="`/تصدير`", inline=False)
    embed.add_field(name="**▸ إعدادات العملة والإشعارات (للمشرفين)**", value="`/اعدادات`", inline=False)
    embed.add_field(name="**▸ قائمة الأعمال**", value="`/الأعمال`", inline=False)
    embed.add_field(name="**▸ إدارة الأعمال (للمشرفين)**",
                    value="`/اضافة_عمل` `/حذف_عمل` `/تعديل_عمل` `/عرض_الاعمال`", inline=False)
    embed.add_field(name="**▸ مكافأة وخصم (للمشرفين)**",
                    value="`/مكافأة` `/خصم` `/حذف_مكافأة_خصم`", inline=False)
    embed.add_field(name="**▸ إدارة التخصصات (للمشرفين)**",
                    value="`/اضافة_تخصص` `/حذف_تخصص` `/تفعيل_تخصص` `/تعطيل_تخصص`", inline=False)
    embed.add_field(name="**▸ نظام الدفع الشهري (للمشرفين)**",
                    value="`/تحديد_موعد_الدفع` `/تقرير_دفع`", inline=False)
    embed.add_field(name="**▸ الملخص الشهري (للأعضاء)**", value="`/ملخص_شهري`", inline=False)
    embed.add_field(name="**▸ تحديث أسعار الفصول المسجلة (للمشرفين)**", value="`/تحديث_أسعار`", inline=False)
    embed.set_footer(text=f"القنوات المسموحة: {', '.join([f'#{ch}' for ch in SETTINGS.get('allowed_channels', [])])}")
    await interaction.response.send_message(embed=embed)

@bot.command(name="اوامر")
@commands.cooldown(1, 5, commands.BucketType.user)
async def help_commands(ctx):
    embed = discord.Embed(title="📌 **أوامر البوت**", color=discord.Color.purple())
    embed.add_field(name="**▸ تسجيل شغل جديد**",
                    value="`!تحليل` أو `/تسجيل`\n*يدعم فصلاً واحداً أو عدة فصول، وأنماط تخصصات مثل `ترجمة كوري-تحرير`*",
                    inline=False)
    embed.add_field(name="**▸ عرض أعمالي**", value="`!أعمالي` أو `/أعمالي`", inline=False)
    embed.add_field(name="**▸ عرض شغل عضو**", value="`!شغل @member` أو `/شغل`", inline=False)
    embed.add_field(name="**▸ عرض الأسعار**", value="`!اسعار` أو `/اسعار`", inline=False)
    embed.add_field(name="**▸ تعديل السعر (للمشرفين)**", value="`/تعديل_سعر`", inline=False)
    embed.add_field(name="**▸ حذف (للمشرفين)**", value="`/حذف` (خيارات متعددة)", inline=False)
    embed.add_field(name="**▸ حذف كل السجلات (للمشرفين)**", value="`!حذف_الكل` أو `/حذف_الكل`", inline=False)
    embed.add_field(name="**▸ تسجيل شغل لعضو (للمشرفين)**", value="`/تسجيل_للغير`", inline=False)
    embed.add_field(name="**▸ حذف كل الأعمال (للمشرفين)**", value="`/حذف_كل_الأعمال`", inline=False)
    embed.add_field(name="**▸ تحديد القنوات (للمشرفين)**", value="`!تحديد_قنوات` أو `/تحديد_قنوات`", inline=False)
    embed.add_field(name="**▸ لوحة التحكم (للمشرفين)**", value="`/لوحة_التحكم`", inline=False)
    embed.add_field(name="**▸ الإحصائيات**", value="`/احصائيات`", inline=False)
    embed.add_field(name="**▸ سجل العمليات (للمشرفين)**", value="`/سجل`", inline=False)
    embed.add_field(name="**▸ تقريري الأسبوعي**", value="`/تقريري`", inline=False)
    embed.add_field(name="**▸ تعديل آخر سجل**", value="`/تعديل`", inline=False)
    embed.add_field(name="**▸ تصدير Excel (للمشرفين)**", value="`/تصدير`", inline=False)
    embed.add_field(name="**▸ إعدادات العملة والإشعارات (للمشرفين)**", value="`/اعدادات`", inline=False)
    embed.add_field(name="**▸ قائمة الأعمال**", value="`/الأعمال`", inline=False)
    embed.add_field(name="**▸ إدارة الأعمال (للمشرفين)**",
                    value="`/اضافة_عمل` `/حذف_عمل` `/تعديل_عمل` `/عرض_الاعمال`", inline=False)
    embed.add_field(name="**▸ مكافأة وخصم (للمشرفين)**",
                    value="`/مكافأة` `/خصم` `/حذف_مكافأة_خصم`", inline=False)
    embed.add_field(name="**▸ إدارة التخصصات (للمشرفين)**",
                    value="`/اضافة_تخصص` `/حذف_تخصص` `/تفعيل_تخصص` `/تعطيل_تخصص`", inline=False)
    embed.add_field(name="**▸ نظام الدفع الشهري (للمشرفين)**",
                    value="`/تحديد_موعد_الدفع` `/تقرير_دفع`", inline=False)
    embed.add_field(name="**▸ الملخص الشهري (للأعضاء)**", value="`/ملخص_شهري`", inline=False)
    embed.add_field(name="**▸ تحديث أسعار الفصول المسجلة (للمشرفين)**", value="`/تحديث_أسعار`", inline=False)
    embed.set_footer(text=f"القنوات المسموحة: {', '.join([f'#{ch}' for ch in SETTINGS.get('allowed_channels', [])])}")
    await ctx.send(embed=embed)

# ----------------------------------------------------------------------
# Command: اسعار
# ----------------------------------------------------------------------
@bot.tree.command(name="اسعار", description="عرض أسعار التخصصات الحالية")
@app_commands.checks.cooldown(1, 5, key=lambda i: (i.user.id, i.command.qualified_name))
async def prices_slash(interaction: discord.Interaction):
    embed = discord.Embed(title="💰 **قائمة الأسعار**", color=discord.Color.gold())
    for t, price in PRICES.items():
        display_name = t.replace('_', ' ').title()
        if t == "رفع":
            # Special formatting: 1 cent per 2 chapters
            embed.add_field(name=f"**{display_name}**",
                            value=f"{SETTINGS.get('currency', '$')}{price:.3f} (1 سنت لكل فصلين)",
                            inline=True)
        else:
            embed.add_field(name=f"**{display_name}**",
                            value=f"{SETTINGS.get('currency', '$')}{price:.2f}",
                            inline=True)
    await interaction.response.send_message(embed=embed)

@bot.command(name="اسعار")
@commands.cooldown(1, 5, commands.BucketType.user)
async def prices_text(ctx):
    embed = discord.Embed(title="💰 **قائمة الأسعار**", color=discord.Color.gold())
    for t, price in PRICES.items():
        display_name = t.replace('_', ' ').title()
        if t == "رفع":
            embed.add_field(name=f"**{display_name}**",
                            value=f"{SETTINGS.get('currency', '$')}{price:.3f} (1 سنت لكل فصلين)",
                            inline=True)
        else:
            embed.add_field(name=f"**{display_name}**",
                            value=f"{SETTINGS.get('currency', '$')}{price:.2f}",
                            inline=True)
    await ctx.send(embed=embed)

# ----------------------------------------------------------------------
# Command: تعديل_سعر
# ----------------------------------------------------------------------
@bot.tree.command(name="تعديل_سعر", description="تعديل سعر تخصص (للمشرفين)")
@app_commands.autocomplete(التخصص=specialty_autocomplete)
@app_commands.checks.cooldown(1, 5, key=lambda i: (i.user.id, i.command.qualified_name))
async def edit_price_slash(interaction: discord.Interaction, التخصص: str, السعر: float):
    if not is_admin(interaction):
        await log_unauthorized(interaction.user.id, "تعديل_سعر")
        await interaction.response.send_message("❌ ما عندك صلاحية تستخدم هذا الأمر.", ephemeral=True)
        return
    norm_type = map_type(التخصص)
    if norm_type not in SETTINGS.get("specialties", {}):
        await interaction.response.send_message(f"❌ التخصص `{التخصص}` غير موجود. التخصصات المتاحة: {', '.join(SETTINGS['specialties'].keys())}", ephemeral=True)
        return
    SETTINGS["specialties"][norm_type]["price"] = السعر
    SETTINGS["specialties"][norm_type]["last_modified"] = datetime.utcnow().isoformat()
    await save_settings(SETTINGS)
    rebuild_prices()
    await log_audit("تعديل_سعر", interaction.user.id, None, f"تغيير سعر {norm_type} إلى {السعر}")
    await interaction.response.send_message(f"✅ تم تحديث سعر `{norm_type}` إلى {SETTINGS.get('currency', '$')}{السعر:.2f}", ephemeral=True)
    # Send a follow-up warning
    await interaction.channel.send("⚠️ تذكير: لا تنس استخدام الأمر `/تحديث_أسعار` لتطبيق السعر الجديد على الفصول المسجلة هذا الشهر.")

# ----------------------------------------------------------------------
# Slash command: تسجيل (without modal, using autocomplete)
# ----------------------------------------------------------------------
