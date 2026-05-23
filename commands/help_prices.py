import discord
from discord import app_commands
from discord.ext import commands
from state import bot
from helpers.core import SETTINGS

# ----------------------------------------------------------------------
# واجهة الأزرار التفاعلية للأوامر
# ----------------------------------------------------------------------
class HelpView(discord.ui.View):
    def __init__(self, user: discord.User):
        super().__init__(timeout=120)  # تنتهي صلاحية الأزرار بعد دقيقتين من عدم الاستخدام
        self.user = user

    # التحقق من أن الشخص الذي ضغط على الزر هو نفسه من كتب الأمر
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ هذه الأزرار ليست لك! اكتب الأمر الخاص بك لتتمكن من التحكم.", ephemeral=True)
            return False
        return True

    # 1. زر العودة للرئيسية
    @discord.ui.button(label="الصفحة الرئيسية", style=discord.ButtonStyle.secondary, emoji="🏠", row=0)
    async def home_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="📌 مركز التحكم والمساعدة",
            description=(
                f" أهلاً بك يا جميل {interaction.user.mention} في بوت إدارة فلوس فريق كوكيز الرائع 👀🔥.\n\n"
                "اضغط على الأزرار في الأسفل للتنقل بين قوائم الأوامر المتاحة ومعرفة طريقة الاستخدام."
            ),
            color=discord.Color.purple()
        )
        embed.add_field(name="👥 أوامر الأعضاء", value="استعراض أوامر تسجيل الفصول وكشوفات الحساب الشخصية.", inline=True)
        embed.add_field(name="⚙️ أوامر الإدارة", value="استعراض أدوات المشرفين، إدارة الاعمال والتحكم المالي.", inline=True)
        embed.set_footer(text="🤓 بُوت زيوس • صُنع بكل حب")
        await interaction.response.edit_message(embed=embed, view=self)

    # 2. زر أوامر الأعضاء
    @discord.ui.button(label="أوامر الأعضاء", style=discord.Style.primary, emoji="👥", row=0)
    async def members_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="👥 أوامر اعضاء الفريق",
            description="هذه الأوامر متاحة لجميع أعضاء الفريق لتسجيل وإدارة أعمالهم اليومية:",
            color=discord.Color.blue()
        )
        embed.add_field(name="▸ `/تسجيل` أو `!تحليل`", value="تسجيل فصول جديدة (يدعم النطاقات مثل `1-5` `).", inline=False)
        embed.add_field(name="▸ `/أعمالي` أو `!أعمالي`", value="عرض كشف حسابك بالتفصيل (الفصول المنجزة والمبالغ المستحقة).", inline=False)
        embed.add_field(name="▸ `/شغل` أو `!شغل`", value="عرض كشف الحساب الخاص بعضو آخر عبر الإشارة إليه (منشن).", inline=False)
        embed.add_field(name="▸ `/اسعار` أو `!اسعار`", value="عرض قائمة أسعار التخصصات الحالية المعتمدة في السيرفر.", inline=False)
        embed.add_field(name="▸ `/الأعمال`", value="عرض قائمة الاعمال المعتمدة والمساهمين فيها بنظام صفحات.", inline=False)
        embed.add_field(name="▸ `/تعديل`", value="تعديل تفاصيل آخر سجل قمت بإضافته مباشرة في حال حدوث خطأ.", inline=False)
        embed.set_footer(text="يمكنك الضغط على 'الصفحة الرئيسية' للعودة")
        await interaction.response.edit_message(embed=embed, view=self)

    # 3. زر أوامر الإدارة
    @discord.ui.button(label="أوامر الإدارة", style=discord.Style.danger, emoji="⚙️", row=0)
    async def admin_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="⚙️ أدوات التحكم والإدارة",
            description="هذه الأوامر حصرية للمشرفين والمسؤولين لإدارة البيانات والمالية:",
            color=discord.Color.red()
        )
        embed.add_field(name="▸ `/تصدير`", value="استخراج وتصدير قاعدة البيانات بالكامل إلى ملف Excel منظم.", inline=False)
        embed.add_field(name="▸ `/إعدادات`", value="ضبط العملة، قنوات الإشعارات، والحد المالي للتنبيهات الحساسة.", inline=False)
        embed.add_field(name="▸ `/عمل`", value="إضافة عمل جديد أو حذفه (مع خيار تطهير سجلاته بالكامل).", inline=False)
        embed.add_field(name="▸ `/تعديل_سعر`", value="تعديل سعر تخصص معين (مثل الترجمة أو التبييض) فوراً.", inline=False)
        embed.add_field(name="▸ `/تحديث_أسعار`", value="تطبيق الأسعار الجديدة على السجلات القديمة بأثر رجعي.", inline=False)
        embed.add_field(name="▸ `/تحديد_قنوات`", value="تحديد الغرف المسموح للبوت باستقبال أوامر التسجيل داخلها.", inline=False)
        embed.add_field(name="▸ `/حذف`", value="فتح قائمة الاختيارات لحذف سجلات عضو، أو عمل، أو فصل معين.", inline=False)
        embed.add_field(name="▸ `/حذف_كل_الأعمال`", value="مسح قائمة الاعمال النشطة بالكامل مع حماية السجلات الماليّة.", inline=False)
        embed.set_footer(text="يمكنك الضغط على 'الصفحة الرئيسية' للعودة")
        await interaction.response.edit_message(embed=embed, view=self)


# ----------------------------------------------------------------------
# الأمر البرمجي الأساسي للمساعدة
# ----------------------------------------------------------------------
@bot.tree.command(name="اوامر", description="عرض دليل الأوامر للبوت")
@app_commands.checks.cooldown(1, 5, key=lambda i: (i.user.id, i.command.qualified_name))
async def help_slash(interaction: discord.Interaction):
    # إنشاء بطاقة ترحيبية أساسية
    embed = discord.Embed(
        title="📌 مركز التحكم والمساعدة",
        description=(
                f" أهلاً بك يا جميل {interaction.user.mention} في بوت إدارة فلوس فريق كوكيز الرائع 👀🔥.\n\n"
            "اضغط على الأزرار في الأسفل للتنقل بين قوائم الأوامر المتاحة ومعرفة طريقة الاستخدام."
        ),
        color=discord.Color.purple()
    )
    embed.add_field(name="👥 أوامر الأعضاء", value="استعراض أوامر تسجيل الفصول وكشوفات الحساب الشخصية.", inline=True)
    embed.add_field(name="⚙️ أوامر الإدارة", value="استعراض أدوات المشرفين، إدارة الاعمال والتحكم المالي.", inline=True)
    embed.set_footer(text="بُوت إدارة المستحقات • صُنع بكل حب")

    # استدعاء الأزرار وإرسالها مع الرسالة
    view = HelpView(interaction.user)
    await interaction.response.send_message(embed=embed, view=view)


# ----------------------------------------------------------------------
# كود تعديل الأسعار القديم (الموجود مسبقاً في ملفك لتفادي أي نقص)
# ----------------------------------------------------------------------
from datetime import datetime
from helpers.core import save_settings, rebuild_prices, map_type
from tasks.lifecycle import is_admin, specialty_autocomplete

@bot.tree.command(name="تعديل_سعر", description="تعديل سعر تخصص معين (للمشرفين فقط)")
@app_commands.autocomplete(التخصص=specialty_autocomplete)
@app_commands.checks.cooldown(1, 5, key=lambda i: (i.user.id, i.command.qualified_name))
async def edit_price_slash(interaction: discord.Interaction, التخصص: str, السعر: float):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ ما عندك صلاحية تستخدم هذا الأمر.", ephemeral=True)
        return
    norm_type = map_type(التخصص)
    if norm_type not in SETTINGS.get("specialties", {}):
        await interaction.response.send_message(f"❌ التخصص `{التخصص}` غير موجود.", ephemeral=True)
        return
    SETTINGS["specialties"][norm_type]["price"] = السعر
    SETTINGS["specialties"][norm_type]["last_modified"] = datetime.utcnow().isoformat()
    await save_settings(SETTINGS)
    rebuild_prices()
    await interaction.response.send_message(f"✅ تم تحديث سعر `{norm_type}` إلى {SETTINGS.get('currency', '$')}{السعر:.2f}", ephemeral=True)
    await interaction.channel.send("⚠️ تذكير: لا تنس استخدام الأمر `/تحديث_أسعار` لتطبيق السعر الجديد على السجلات القديمة إذا كنت ترغب في ذلك.")