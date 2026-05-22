# cogs/admin_commands.py
import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timedelta
from io import BytesIO
import json
import pandas as pd

import state
import database as db
import utils
from main import is_admin, work_autocomplete, specialty_autocomplete, WorkDetailsView, MemberSelect, WorkSelect, WorksPaginator, DeleteSelect  # استيراد الكلاسات من main

class AdminCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ========== تحديد_قنوات ==========
    @app_commands.command(name="تحديد_قنوات", description="تحديد القنوات المسموحة (قناتين كحد أقصى) - للإدارة فقط")
    @app_commands.checks.cooldown(1, 5, key=lambda i: (i.user.id, i.command.qualified_name))
    async def set_allowed_channels_slash(self, interaction: discord.Interaction,
                                         channel1: discord.TextChannel,
                                         channel2: discord.TextChannel = None):
        if not is_admin(interaction):
            await db.log_unauthorized(interaction.user.id, "تحديد_قنوات")
            await interaction.response.send_message("❌ ما عندك صلاحية تستخدم هذا الأمر.", ephemeral=True)
            return
        channels = [channel1.name]
        if channel2:
            channels.append(channel2.name)
        channels = list(dict.fromkeys(channels))[:2]
        state.SETTINGS["allowed_channels"] = channels
        await db.save_settings(state.SETTINGS)
        channels_str = ", ".join([f"#{ch}" for ch in state.SETTINGS["allowed_channels"]])
        await interaction.response.send_message(f"✅ تم تحديث القنوات المسموحة إلى: {channels_str}", ephemeral=True)
        await db.log_audit("تحديد_قنوات", interaction.user.id, None, f"القنوات الجديدة: {channels_str}")

    @commands.command(name="تحديد_قنوات")
    @commands.has_permissions(manage_messages=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def set_allowed_channels_text(self, ctx, channel1: str, channel2: str = None):
        def extract_channel_name(input_str):
            if input_str.startswith('<#') and input_str.endswith('>'):
                channel_id = int(input_str[2:-1])
                channel = ctx.guild.get_channel(channel_id)
                if channel:
                    return channel.name
            elif input_str.isdigit():
                channel = ctx.guild.get_channel(int(input_str))
                if channel:
                    return channel.name
            else:
                for ch in ctx.guild.channels:
                    if ch.name == input_str:
                        return ch.name
            return input_str
        ch1_name = extract_channel_name(channel1)
        ch2_name = extract_channel_name(channel2) if channel2 else None
        channels = [ch1_name]
        if ch2_name:
            channels.append(ch2_name)
        channels = list(dict.fromkeys(channels))[:2]
        state.SETTINGS["allowed_channels"] = channels
        await db.save_settings(state.SETTINGS)
        channels_str = ", ".join([f"#{ch}" for ch in state.SETTINGS["allowed_channels"]])
        await ctx.send(f"✅ تم تحديث القنوات المسموحة إلى: {channels_str}")
        await db.log_audit("تحديد_قنوات", ctx.author.id, None, f"القنوات الجديدة: {channels_str}")

    # ========== رفع_البيانات ==========
    @app_commands.command(name="رفع_البيانات", description="رفع ملف JSON لاستعادة السجلات والأعمال إلى MongoDB")
    @app_commands.checks.cooldown(1, 10, key=lambda i: (i.user.id, i.command.qualified_name))
    async def upload_records(self, interaction: discord.Interaction, file: discord.Attachment):
        if not is_admin(interaction):
            await db.log_unauthorized(interaction.user.id, "رفع_البيانات")
            await interaction.response.send_message("❌ ما عندك صلاحية تستخدم هذا الأمر.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        if not file.filename.endswith('.json'):
            await interaction.followup.send("❌ الملف يجب أن يكون بصيغة JSON.", ephemeral=True)
            return
        try:
            content = await file.read()
            data = json.loads(content.decode('utf-8'))

            if isinstance(data, dict):
                records_data = data.get("records", data)
                works_data = data.get("works", None)
            else:
                await interaction.followup.send("❌ الملف غير صالح.", ephemeral=True)
                return

            if not isinstance(records_data, dict):
                await interaction.followup.send("❌ قسم records غير صالح.", ephemeral=True)
                return
            await state.collection.update_one({"_id": "records"}, {"$set": {"data": records_data}}, upsert=True)
            total_users = len(records_data)
            total_entries = sum(len(entries) for entries in records_data.values() if isinstance(entries, list))

            works_from_records = set()
            for user_entries in records_data.values():
                if isinstance(user_entries, list):
                    for entry in user_entries:
                        if isinstance(entry, dict) and "work_name" in entry:
                            works_from_records.add(entry["work_name"])

            if works_from_records:
                current_works = await db.load_works()
                existing_names = {w["name"] for w in current_works}
                added_works_count = 0
                for name in works_from_records:
                    if name not in existing_names:
                        current_works.append({"name": name, "paid_start": None, "active": True})
                        existing_names.add(name)
                        added_works_count += 1
                if added_works_count > 0:
                    await db.save_works(current_works)
            else:
                added_works_count = 0

            if works_data is not None:
                if isinstance(works_data, list):
                    await db.save_works(works_data)
                    added_works_count = len(works_data)
                else:
                    await interaction.followup.send("⚠️ تم تحديث السجلات لكن قسم works غير صالح (تم تجاهله).", ephemeral=True)
                    await db.log_audit("رفع_البيانات", interaction.user.id, None,
                                    f"تم رفع {total_entries} سجل (works غير محدثة)")
                    await db.update_stats()
                    await interaction.followup.send(
                        f"✅ تم استعادة السجلات بنجاح!\nعدد المستخدمين: {total_users}\nإجمالي السجلات: {total_entries}",
                        ephemeral=True)
                    return

            await db.log_audit("رفع_البيانات", interaction.user.id, None,
                            f"تم رفع {total_entries} سجل" + (f" و {added_works_count} عمل جديد" if added_works_count else ""))
            await db.update_stats()
            msg = f"✅ تم استعادة البيانات بنجاح!\nعدد المستخدمين: {total_users}\nإجمالي السجلات: {total_entries}"
            if added_works_count:
                msg += f"\nأعمال جديدة مضافة من السجلات: {added_works_count}"
            if works_data is not None:
                msg += f"\nالأعمال المحدثة من الملف: {len(works_data)}"
            await interaction.followup.send(msg, ephemeral=True)
        except json.JSONDecodeError:
            await interaction.followup.send("❌ الملف ليس بصيغة JSON صحيحة.", ephemeral=True)
        except Exception as e:
            print(f"[ERROR] Slash command restore failed: {e}")
            await interaction.followup.send(f"❌ حدث خطأ: {str(e)}", ephemeral=True)

    # ========== تعديل_سعر ==========
    @app_commands.command(name="تعديل_سعر", description="تعديل سعر تخصص (للمشرفين)")
    @app_commands.autocomplete(التخصص=specialty_autocomplete)
    @app_commands.checks.cooldown(1, 5, key=lambda i: (i.user.id, i.command.qualified_name))
    async def edit_price_slash(self, interaction: discord.Interaction, التخصص: str, السعر: float):
        if not is_admin(interaction):
            await db.log_unauthorized(interaction.user.id, "تعديل_سعر")
            await interaction.response.send_message("❌ ما عندك صلاحية تستخدم هذا الأمر.", ephemeral=True)
            return
        norm_type = utils.map_type(التخصص)
        if norm_type not in state.SETTINGS.get("specialties", {}):
            await interaction.response.send_message(f"❌ التخصص `{التخصص}` غير موجود. التخصصات المتاحة: {', '.join(state.SETTINGS['specialties'].keys())}", ephemeral=True)
            return
        state.SETTINGS["specialties"][norm_type]["price"] = السعر
        state.SETTINGS["specialties"][norm_type]["last_modified"] = datetime.utcnow().isoformat()
        await db.save_settings(state.SETTINGS)
        utils.rebuild_prices()
        await db.log_audit("تعديل_سعر", interaction.user.id, None, f"تغيير سعر {norm_type} إلى {السعر}")
        await interaction.response.send_message(f"✅ تم تحديث سعر `{norm_type}` إلى {state.SETTINGS.get('currency', '$')}{السعر:.2f}", ephemeral=True)
        await interaction.channel.send("⚠️ تذكير: لا تنس استخدام الأمر `/تحديث_أسعار` لتطبيق السعر الجديد على الفصول المسجلة هذا الشهر.")

    # ========== تسجيل_للغير ==========
    @app_commands.command(name="تسجيل_للغير", description="تسجيل شغل لعضو معين (للمشرفين فقط)")
    @app_commands.autocomplete(العمل=work_autocomplete)
    @app_commands.describe(
        عضو="العضو الذي تريد تسجيل الشغل له",
        العمل="اسم العمل (يجب أن يكون موجوداً في القائمة)",
        الفصول="نطاق الفصول مثل 1-5 أو 1,3,5",
        التخصصات="التخصصات مثل ترجمة كوري-تحرير-تبييض",
        ملاحظات="ملاحظات اختيارية"
    )
    @app_commands.checks.cooldown(1, 5, key=lambda i: (i.user.id, i.command.qualified_name))
    async def register_for_member(self, interaction: discord.Interaction,
                                 عضو: discord.Member, العمل: str, الفصول: str, التخصصات: str, ملاحظات: str = None):
        if not is_admin(interaction):
            await db.log_unauthorized(interaction.user.id, "تسجيل_للغير")
            await interaction.response.send_message("❌ ما عندك صلاحية تستخدم هذا الأمر.", ephemeral=True)
            return
        if interaction.channel.name not in state.SETTINGS.get("allowed_channels", []):
            channels_str = ", ".join([f"#{ch}" for ch in state.SETTINGS.get("allowed_channels", [])])
            await interaction.response.send_message(f"❌ استخدم هذا الأمر فقط في أحد الرومات: {channels_str}.", ephemeral=True)
            return

        work = await db.get_work(العمل)
        if not work:
            await interaction.response.send_message(f"❌ العمل `{العمل}` غير موجود في قائمة الأعمال المدفوعة.", ephemeral=True)
            return
        if not work.get("active", True):
            await interaction.response.send_message(f"❌ العمل `{العمل}` معطل حالياً ولا يمكن إضافة فصول إليه.", ephemeral=True)
            return

        chapters_list = utils.parse_chapter_range(الفصول)
        if not chapters_list:
            await interaction.response.send_message("❌ نطاق الفصول غير صالح. استخدم مثلاً `5` أو `1-5` أو `1,3,5`.", ephemeral=True)
            return

        paid_chapters, free_count = utils.filter_paid_chapters(work, chapters_list)
        if not paid_chapters:
            await interaction.response.send_message("⚠️ جميع الفصول المدخلة مجانية ولم تُسجّل.", ephemeral=True)
            return

        types_list = utils.parse_mixed_types(التخصصات, len(chapters_list))
        if types_list is None:
            await interaction.response.send_message(f"❌ عدد التخصصات لا يتطابق مع عدد الفصول ({len(chapters_list)}).", ephemeral=True)
            return

        mapped_types = [utils.map_type(t) for t in types_list]

        filtered_types = []
        kept_set = set(paid_chapters)
        for idx, ch in enumerate(chapters_list):
            if ch in kept_set:
                filtered_types.append(mapped_types[idx])

        for t in filtered_types:
            if t not in state.PRICES:
                await interaction.response.send_message(f"❌ التخصص `{t}` غير صحيح. التخصصات المسموحة: {', '.join(state.PRICES.keys())}", ephemeral=True)
                return

        records = await db.load_records()
        user_id = str(عضو.id)
        if user_id not in records:
            records[user_id] = []

        added = 0
        username = عضو.name
        for idx, ch in enumerate(paid_chapters):
            work_type = filtered_types[idx]
            if utils.is_duplicate(records, user_id, العمل, ch, work_type):
                continue
            total = state.PRICES[work_type]
            records[user_id].append({
                "work_name": العمل,
                "chapter": ch,
                "work_type": work_type,
                "total": total,
                "notes": ملاحظات or "",
                "timestamp": datetime.utcnow().isoformat(),
                "username": username,
                "added_by": str(interaction.user.id)
            })
            added += 1

        if added == 0:
            await interaction.response.send_message("⚠️ لم يتم إضافة أي فصل جديد (جميع الفصول مكررة).", ephemeral=True)
            return

        await db.save_records(records)
        await db.update_stats()

        embed = discord.Embed(title="✅ **تم حفظ الشغل بنجاح**", color=discord.Color.green())
        embed.add_field(name="**👤 العضو**", value=عضو.mention, inline=True)
        embed.add_field(name="**📖 العمل**", value=العمل, inline=True)
        embed.add_field(name="**🔢 عدد الفصول المدفوعة المسجلة**", value=str(added), inline=True)
        if free_count > 0:
            embed.add_field(name="⏭️ فصول مجانية لم تُسجّل", value=str(free_count), inline=True)
        if len(set(filtered_types)) == 1:
            embed.add_field(name="**🛠️ التخصص**", value=filtered_types[0], inline=True)
            total_amount = added * state.PRICES[filtered_types[0]]
        else:
            total_amount = sum(state.PRICES[t] for t in filtered_types)
            types_summary = "\n".join([f"فصل {ch}: {t}" for ch, t in zip(paid_chapters, filtered_types)])
            embed.add_field(name="**🛠️ تفاصيل التخصصات**", value=types_summary, inline=False)
        embed.add_field(name="**💰 المبلغ الإجمالي**", value=f"{state.SETTINGS.get('currency', '$')}{total_amount:.2f}", inline=False)
        embed.add_field(name="**🛡️ أضيف بواسطة**", value=interaction.user.mention, inline=True)
        if ملاحظات:
            embed.add_field(name="**📝 ملاحظات**", value=ملاحظات, inline=False)

        await interaction.response.send_message(embed=embed)

        notify_channel_id = state.SETTINGS.get("notify_channel_id")
        if notify_channel_id:
            channel = interaction.guild.get_channel(notify_channel_id)
            if channel:
                await channel.send(f"📢 {interaction.user.mention} أضاف {added} فصول مدفوعة للعضو {عضو.mention} في عمل `{العمل}`")

        await db.log_audit("تسجيل_للغير", interaction.user.id, عضو.id,
                        f"أضاف {added} فصل لـ {العمل} (التخصصات: {','.join(filtered_types)})")

        try:
            await عضو.send(f"📬 تم تسجيل {added} فصول مدفوعة لك في عمل `{العمل}` بواسطة {interaction.user.mention}.")
        except:
            pass

    # ========== حذف ==========
    @app_commands.command(name="حذف", description="حذف سجلات العضو - للمشرفين")
    @app_commands.checks.cooldown(1, 5, key=lambda i: (i.user.id, i.command.qualified_name))
    async def delete_advanced(self, interaction: discord.Interaction, member: discord.Member, work_name: str = None):
        if not is_admin(interaction):
            await db.log_unauthorized(interaction.user.id, "حذف")
            await interaction.response.send_message("❌ ما عندك صلاحية.", ephemeral=True)
            return
        if interaction.channel.name not in state.SETTINGS.get("allowed_channels", []):
            await interaction.response.send_message("❌ استخدم الأمر في القنوات المسموحة.", ephemeral=True)
            return
        records = await db.load_records()
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
            select = DeleteSelect(member.id, work_name)  # DeleteSelect defined in main, should be accessible
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
                        await self.bot.wait_for('message', timeout=30.0, check=check)
                    except:
                        await interaction2.followup.send("❌ تم إلغاء العملية.", ephemeral=True)
                        return
                    records2 = await db.load_records()
                    if str(member.id) in records2:
                        del records2[str(member.id)]
                        await db.save_records(records2)
                        await db.log_audit("حذف_كل_سجلات_العضو", interaction2.user.id, member.id, "حذف كل السجلات")
                        await db.update_stats()
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

    @commands.command(name="حذف")
    @commands.has_permissions(manage_messages=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def delete_work_text(self, ctx, member: discord.Member = None, number: int = None):
        if member is None or number is None:
            await ctx.send("**الاستخدام:** `!حذف @member 2`\nأو استخدم الأمر `/حذف` للخيارات المتقدمة.")
            return
        records = await db.load_records()
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
        await db.save_records(records)
        await db.log_audit("حذف سجل (نصي)", ctx.author.id, member.id, f"السجل #{number}: {deleted.get('work_name')} - فصل {deleted.get('chapter')}")
        await db.update_stats()
        embed = discord.Embed(title="🗑️ **تم حذف السجل**", color=discord.Color.red())
        embed.add_field(name="**المستخدم**", value=member.mention, inline=True)
        embed.add_field(name="**العمل**", value=deleted.get('work_name', 'غير محدد'), inline=True)
        embed.add_field(name="**الفصل**", value=deleted.get('chapter', 'غير محدد'), inline=True)
        embed.add_field(name="**التخصص**", value=deleted.get('work_type', 'غير محدد'), inline=True)
        embed.add_field(name="**المبلغ**", value=f"{state.SETTINGS.get('currency', '$')}{deleted.get('total', 0):.2f}", inline=True)
        await ctx.send(embed=embed)

    @app_commands.command(name="حذف_الكل", description="حذف كل السجلات - للمشرفين")
    @app_commands.checks.cooldown(1, 10, key=lambda i: (i.user.id, i.command.qualified_name))
    async def delete_all_work_slash(self, interaction: discord.Interaction):
        if not is_admin(interaction):
            await db.log_unauthorized(interaction.user.id, "حذف_الكل")
            await interaction.response.send_message("❌ ما عندك صلاحية.", ephemeral=True)
            return
        if interaction.channel.name not in state.SETTINGS.get("allowed_channels", []):
            await interaction.response.send_message("❌ القناة غير مسموحة.", ephemeral=True)
            return
        records = await db.load_records()
        total = sum(len(items) for items in records.values())
        if total == 0:
            await interaction.response.send_message("📭 ما فيه أي سجلات.", ephemeral=True)
            return
        records.clear()
        await db.save_records(records)
        await db.log_audit("حذف_الكل", interaction.user.id, None, f"{total} سجل")
        await db.update_stats()
        await interaction.response.send_message(f"🗑️ تم حذف كل السجلات ({total}).")

    @commands.command(name="حذف_الكل")
    @commands.has_permissions(manage_messages=True)
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def delete_all_work_text(self, ctx):
        records = await db.load_records()
        total = sum(len(items) for items in records.values())
        if total == 0:
            await ctx.send("📭 ما فيه أي سجلات.")
            return
        records.clear()
        await db.save_records(records)
        await db.log_audit("حذف_الكل", ctx.author.id, None, f"{total} سجل")
        await db.update_stats()
        await ctx.send(f"🗑️ تم حذف كل السجلات ({total}).")

    @app_commands.command(name="حذف_كل_الأعمال", description="حذف جميع الأعمال من القائمة (للمشرفين فقط)")
    @app_commands.checks.cooldown(1, 10, key=lambda i: (i.user.id, i.command.qualified_name))
    async def delete_all_works(self, interaction: discord.Interaction):
        if not is_admin(interaction):
            await db.log_unauthorized(interaction.user.id, "حذف_كل_الأعمال")
            await interaction.response.send_message("❌ ما عندك صلاحية.", ephemeral=True)
            return
        works = await db.load_works()
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
            await self.bot.wait_for('message', timeout=30.0, check=check)
        except:
            await interaction.followup.send("❌ تم إلغاء العملية.", ephemeral=True)
            return

        await db.save_works([])
        await db.log_audit("حذف_كل_الأعمال", interaction.user.id, None, f"تم حذف {len(works)} عمل")
        await interaction.followup.send(f"✅ تم حذف جميع الأعمال ({len(works)} عمل) من القائمة.", ephemeral=True)

    # ========== لوحة_التحكم ==========
    @app_commands.command(name="لوحة_التحكم", description="لوحة تحكم للمشرفين")
    @app_commands.checks.cooldown(1, 5, key=lambda i: (i.user.id, i.command.qualified_name))
    async def dashboard(self, interaction: discord.Interaction):
        if not is_admin(interaction):
            await db.log_unauthorized(interaction.user.id, "لوحة_التحكم")
            await interaction.response.send_message("❌ ما عندك صلاحية.", ephemeral=True)
            return
        records = await db.load_records()
        total_users = len(records)
        total_entries = sum(len(entries) for entries in records.values())
        total_amount = sum(sum(e.get("total", 0) for e in entries) for entries in records.values())
        embed = discord.Embed(title="🖥️ **لوحة التحكم**", color=discord.Color.gold())
        embed.add_field(name="**👥 عدد الأعضاء النشطين**", value=total_users, inline=True)
        embed.add_field(name="**📄 عدد السجلات الكلي**", value=total_entries, inline=True)
        embed.add_field(name="**💰 إجمالي المبالغ**", value=f"{state.SETTINGS.get('currency', '$')}{total_amount:.2f}", inline=True)
        embed.add_field(name="**⚙️ العملة**", value=state.SETTINGS.get('currency', '$'), inline=True)
        embed.add_field(name="**🔔 قناة الإشعارات**", value=f"<#{state.SETTINGS.get('notify_channel_id')}>" if state.SETTINGS.get('notify_channel_id') else "غير محدد", inline=True)
        embed.add_field(name="**💾 قناة النسخ الاحتياطي**", value=f"<#{state.SETTINGS.get('daily_backup_channel_id')}>" if state.SETTINGS.get('daily_backup_channel_id') else "غير محدد", inline=True)
        embed.add_field(name="**⚠️ حد التنبيه**", value=f"{state.SETTINGS.get('currency', '$')}{state.SETTINGS.get('alert_threshold', 10):.2f}", inline=True)
        payment_day = state.SETTINGS.get("payment_day")
        embed.add_field(name="**📅 موعد الدفع الشهري**", value=f"يوم {payment_day} الساعة {state.SETTINGS.get('payment_hour', 0)}" if payment_day else "غير محدد", inline=True)
        await interaction.response.send_message(embed=embed)

    # ========== سجل ==========
    @app_commands.command(name="سجل", description="عرض آخر 20 عملية إدارية")
    @app_commands.checks.cooldown(1, 5, key=lambda i: (i.user.id, i.command.qualified_name))
    async def audit_log(self, interaction: discord.Interaction):
        if not is_admin(interaction):
            await db.log_unauthorized(interaction.user.id, "سجل")
            await interaction.response.send_message("❌ ما عندك صلاحية.", ephemeral=True)
            return
        logs = await state.audit_collection.find().sort("timestamp", -1).limit(20).to_list(length=20)
        if not logs:
            await interaction.response.send_message("لا توجد سجلات.", ephemeral=True)
            return
        embed = discord.Embed(title="📜 **سجل العمليات**", color=discord.Color.dark_gray())
        for log in logs:
            embed.add_field(
                name=f"**{log.get('action', 'غير معروف')}**",
                value=f"بواسطة: <@{log.get('moderator_id')}>\nللـ: {log.get('target_id') if log.get('target_id') else 'عام'}\nالتفاصيل: {log.get('details')}\nالوقت: {log.get('timestamp')[:19]}",
                inline=False
            )
        await interaction.response.send_message(embed=embed)

    # ========== تصدير ==========
    @app_commands.command(name="تصدير", description="تصدير كل البيانات إلى Excel")
    @app_commands.checks.cooldown(1, 10, key=lambda i: (i.user.id, i.command.qualified_name))
    async def export_excel(self, interaction: discord.Interaction):
        if not is_admin(interaction):
            await db.log_unauthorized(interaction.user.id, "تصدير")
            await interaction.response.send_message("❌ ما عندك صلاحية.", ephemeral=True)
            return
        records = await db.load_records()
        rows = []
        for user_id, entries in records.items():
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
            df.to_excel(writer, index=False, sheet_name="الشغل")
        buffer.seek(0)
        await interaction.response.send_message(file=discord.File(buffer, filename="work_report.xlsx"))

    # ========== اعدادات ==========
    @app_commands.command(name="اعدادات", description="إعدادات البوت (للمشرفين)")
    @app_commands.checks.cooldown(1, 5, key=lambda i: (i.user.id, i.command.qualified_name))
    async def bot_settings(self, interaction: discord.Interaction, العملة: str = None, قناة_الإشعارات: discord.TextChannel = None, قناة_النسخ: discord.TextChannel = None, حد_التنبيه: float = None):
        if not is_admin(interaction):
            await db.log_unauthorized(interaction.user.id, "اعدادات")
            await interaction.response.send_message("❌ ما عندك صلاحية.", ephemeral=True)
            return
        if العملة:
            state.SETTINGS["currency"] = العملة
        if قناة_الإشعارات:
            state.SETTINGS["notify_channel_id"] = قناة_الإشعارات.id
        if قناة_النسخ:
            state.SETTINGS["daily_backup_channel_id"] = قناة_النسخ.id
        if حد_التنبيه is not None:
            state.SETTINGS["alert_threshold"] = حد_التنبيه
        await db.save_settings(state.SETTINGS)
        await interaction.response.send_message("✅ تم تحديث الإعدادات.", ephemeral=True)

    # ========== إدارة الأعمال ==========
    @app_commands.command(name="اضافة_عمل", description="إضافة عمل جديد إلى قائمة الأعمال المدفوعة (للمشرفين)")
    @app_commands.describe(الاسم="اسم العمل", بداية_الفصول_المدفوعة="أول فصل مدفوع (اختياري، اتركه فارغاً إذا كان العمل كله مدفوع)", نشط="هل العمل نشط الآن؟")
    @app_commands.checks.cooldown(1, 5, key=lambda i: (i.user.id, i.command.qualified_name))
    async def add_work(self, interaction: discord.Interaction, الاسم: str, بداية_الفصول_المدفوعة: int = None, نشط: bool = True):
        if not is_admin(interaction):
            await db.log_unauthorized(interaction.user.id, "اضافة_عمل")
            await interaction.response.send_message("❌ ما عندك صلاحية.", ephemeral=True)
            return
        works = await db.load_works()
        if any(w["name"] == الاسم for w in works):
            await interaction.response.send_message(f"❌ العمل `{الاسم}` موجود بالفعل.", ephemeral=True)
            return
        new_work = {"name": الاسم, "paid_start": بداية_الفصول_المدفوعة, "active": نشط}
        works.append(new_work)
        await db.save_works(works)
        await db.log_audit("اضافة_عمل", interaction.user.id, None, f"أضاف عمل {الاسم} (paid_start={بداية_الفصول_المدفوعة}, active={نشط})")
        desc = "كل الفصول مدفوعة" if بداية_الفصول_المدفوعة is None else f"يبدأ من فصل {بداية_الفصول_المدفوعة}"
        await interaction.response.send_message(f"✅ تمت إضافة العمل `{الاسم}`.\nالحالة: {desc} | نشط: {'✅' if نشط else '❌'}", ephemeral=True)

    @app_commands.command(name="حذف_عمل", description="حذف عمل من القائمة (للمشرفين)")
    @app_commands.autocomplete(العمل=work_autocomplete)
    @app_commands.checks.cooldown(1, 5, key=lambda i: (i.user.id, i.command.qualified_name))
    async def delete_work(self, interaction: discord.Interaction, العمل: str):
        if not is_admin(interaction):
            await db.log_unauthorized(interaction.user.id, "حذف_عمل")
            await interaction.response.send_message("❌ ما عندك صلاحية.", ephemeral=True)
            return
        works = await db.load_works()
        target = next((w for w in works if w["name"] == العمل), None)
        if not target:
            await interaction.response.send_message("❌ العمل غير موجود.", ephemeral=True)
            return

        view = discord.ui.View(timeout=60)
        async def delete_with_records(interaction2: discord.Interaction):
            await interaction2.response.send_message("⚠️ **تأكيد:** سيتم حذف العمل **وكل سجلاته** نهائياً.\nاكتب `تأكيد` خلال 30 ثانية.", ephemeral=True)
            def check(m):
                return m.author == interaction2.user and m.content == "تأكيد" and m.channel == interaction2.channel
            try:
                await self.bot.wait_for('message', timeout=30.0, check=check)
            except:
                await interaction2.followup.send("❌ تم الإلغاء.", ephemeral=True)
                return
            removed = await db.delete_all_records_of_work(العمل)
            new_works = [w for w in works if w["name"] != العمل]
            await db.save_works(new_works)
            await db.log_audit("حذف_عمل_مع_السجلات", interaction2.user.id, None, f"حذف {العمل} و {removed} سجل")
            await interaction2.followup.send(f"✅ تم حذف العمل `{العمل}` وكل سجلاته ({removed} سجل).", ephemeral=True)

        async def delete_work_only(interaction2: discord.Interaction):
            await interaction2.response.send_message("⚠️ **تأكيد:** سيتم حذف العمل من القائمة فقط (السجلات تبقى).\nاكتب `تأكيد` خلال 30 ثانية.", ephemeral=True)
            def check(m):
                return m.author == interaction2.user and m.content == "تأكيد" and m.channel == interaction2.channel
            try:
                await self.bot.wait_for('message', timeout=30.0, check=check)
            except:
                await interaction2.followup.send("❌ تم الإلغاء.", ephemeral=True)
                return
            new_works = [w for w in works if w["name"] != العمل]
            await db.save_works(new_works)
            await db.log_audit("حذف_عمل_فقط", interaction2.user.id, None, f"حذف {العمل} من القائمة (السجلات باقية)")
            await interaction2.followup.send(f"✅ تم حذف العمل `{العمل}` من القائمة (السجلات لم تمس).", ephemeral=True)

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

    @app_commands.command(name="تعديل_عمل", description="تعديل بيانات عمل (للمشرفين)")
    @app_commands.autocomplete(العمل=work_autocomplete)
    @app_commands.describe(العمل="اختر العمل", الاسم_الجديد="اسم جديد (اختياري)", بداية_الفصول_المدفوعة="أول فصل مدفوع (اتركه فارغاً إن لم يتغير)", الكل_مدفوع="تفعيل إذا كان العمل كله مدفوعاً", نشط="حالة النشاط")
    @app_commands.checks.cooldown(1, 5, key=lambda i: (i.user.id, i.command.qualified_name))
    async def edit_work(self, interaction: discord.Interaction, العمل: str, الاسم_الجديد: str = None, بداية_الفصول_المدفوعة: int = None, الكل_مدفوع: bool = False, نشط: bool = None):
        if not is_admin(interaction):
            await db.log_unauthorized(interaction.user.id, "تعديل_عمل")
            await interaction.response.send_message("❌ ما عندك صلاحية.", ephemeral=True)
            return
        works = await db.load_works()
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
        await db.save_works(works)
        await db.log_audit("تعديل_عمل", interaction.user.id, None, f"تعديل {العمل}: {', '.join(changed)}")
        await interaction.response.send_message(f"✅ تم تعديل العمل `{العمل}`:\n" + "\n".join(changed), ephemeral=True)

    # ========== عرض_الاعمال ==========
    @app_commands.command(name="عرض_الاعمال", description="عرض قائمة الأعمال المدفوعة وحالتها")
    @app_commands.checks.cooldown(1, 5, key=lambda i: (i.user.id, i.command.qualified_name))
    async def list_works(self, interaction: discord.Interaction):
        works = await db.load_works()
        if not works:
            await interaction.response.send_message("📭 لا توجد أعمال في القائمة.", ephemeral=True)
            return
        # WorksListPaginator is defined in main, we import and use it
        view = WorksListPaginator(works)
        await interaction.response.send_message(embed=view.get_embed(), view=view)

    # ========== إدارة التخصصات ==========
    @app_commands.command(name="اضافة_تخصص", description="إضافة تخصص جديد (للمشرفين)")
    @app_commands.describe(الاسم="اسم التخصص (مثال: تدقيق)", السعر="سعر الفصل الواحد", نشط="مفعل؟")
    @app_commands.checks.cooldown(1, 5, key=lambda i: (i.user.id, i.command.qualified_name))
    async def add_specialty(self, interaction: discord.Interaction, الاسم: str, السعر: float, نشط: bool = True):
        if not is_admin(interaction):
            await db.log_unauthorized(interaction.user.id, "اضافة_تخصص")
            await interaction.response.send_message("❌ ما عندك صلاحية.", ephemeral=True)
            return
        norm_name = utils.map_type(الاسم)
        if norm_name in state.SETTINGS.get("specialties", {}):
            await interaction.response.send_message("❌ التخصص موجود مسبقاً.", ephemeral=True)
            return
        state.SETTINGS["specialties"][norm_name] = {
            "price": السعر,
            "active": نشط,
            "last_modified": datetime.utcnow().isoformat()
        }
        await db.save_settings(state.SETTINGS)
        utils.rebuild_prices()
        await db.log_audit("اضافة_تخصص", interaction.user.id, None, f"أضاف تخصص {norm_name} بسعر {السعر}")
        await interaction.response.send_message(f"✅ تم إضافة تخصص `{norm_name}`.", ephemeral=True)

    @app_commands.command(name="حذف_تخصص", description="حذف (تعطيل) تخصص (للمشرفين)")
    @app_commands.autocomplete(الاسم=specialty_autocomplete)
    @app_commands.checks.cooldown(1, 5, key=lambda i: (i.user.id, i.command.qualified_name))
    async def delete_specialty(self, interaction: discord.Interaction, الاسم: str):
        if not is_admin(interaction):
            await db.log_unauthorized(interaction.user.id, "حذف_تخصص")
            await interaction.response.send_message("❌ ما عندك صلاحية.", ephemeral=True)
            return
        norm_name = utils.map_type(الاسم)
        if norm_name not in state.SETTINGS.get("specialties", {}):
            await interaction.response.send_message("❌ التخصص غير موجود.", ephemeral=True)
            return
        state.SETTINGS["specialties"][norm_name]["active"] = False
        await db.save_settings(state.SETTINGS)
        utils.rebuild_prices()
        await db.log_audit("حذف_تخصص", interaction.user.id, None, f"عطّل تخصص {norm_name}")
        await interaction.response.send_message(f"✅ تم تعطيل تخصص `{norm_name}`.", ephemeral=True)

    @app_commands.command(name="تفعيل_تخصص", description="تفعيل تخصص معطل (للمشرفين)")
    @app_commands.autocomplete(الاسم=specialty_autocomplete)
    @app_commands.checks.cooldown(1, 5, key=lambda i: (i.user.id, i.command.qualified_name))
    async def activate_specialty(self, interaction: discord.Interaction, الاسم: str):
        if not is_admin(interaction):
            await db.log_unauthorized(interaction.user.id, "تفعيل_تخصص")
            await interaction.response.send_message("❌ ما عندك صلاحية.", ephemeral=True)
            return
        norm_name = utils.map_type(الاسم)
        specialties = state.SETTINGS.get("specialties", {})
        if norm_name not in specialties:
            await interaction.response.send_message("❌ التخصص غير موجود.", ephemeral=True)
            return
        specialties[norm_name]["active"] = True
        await db.save_settings(state.SETTINGS)
        utils.rebuild_prices()
        await interaction.response.send_message(f"✅ تم تفعيل تخصص `{norm_name}`.", ephemeral=True)

    @app_commands.command(name="تعطيل_تخصص", description="تعطيل تخصص (للمشرفين)")
    @app_commands.autocomplete(الاسم=specialty_autocomplete)
    @app_commands.checks.cooldown(1, 5, key=lambda i: (i.user.id, i.command.qualified_name))
    async def deactivate_specialty(self, interaction: discord.Interaction, الاسم: str):
        if not is_admin(interaction):
            await db.log_unauthorized(interaction.user.id, "تعطيل_تخصص")
            await interaction.response.send_message("❌ ما عندك صلاحية.", ephemeral=True)
            return
        norm_name = utils.map_type(الاسم)
        specialties = state.SETTINGS.get("specialties", {})
        if norm_name not in specialties:
            await interaction.response.send_message("❌ التخصص غير موجود.", ephemeral=True)
            return
        specialties[norm_name]["active"] = False
        await db.save_settings(state.SETTINGS)
        utils.rebuild_prices()
        await interaction.response.send_message(f"✅ تم تعطيل تخصص `{norm_name}`.", ephemeral=True)

    # ========== مكافأة وخصم ==========
    @app_commands.command(name="مكافأة", description="إضافة مكافأة (مبلغ موجب) لعضو - للإدارة فقط")
    @app_commands.describe(عضو="العضو المستحق للمكافأة", المبلغ="المبلغ الموجب المراد إضافته", السبب="سبب المكافأة (اختياري)")
    @app_commands.checks.cooldown(1, 5, key=lambda i: (i.user.id, i.command.qualified_name))
    async def add_bonus(self, interaction: discord.Interaction, عضو: discord.Member, المبلغ: float, السبب: str = None):
        if not is_admin(interaction):
            await db.log_unauthorized(interaction.user.id, "مكافأة")
            await interaction.response.send_message("❌ ما عندك صلاحية تستخدم هذا الأمر.", ephemeral=True)
            return
        if المبلغ <= 0:
            await interaction.response.send_message("❌ المبلغ يجب أن يكون أكبر من صفر.", ephemeral=True)
            return

        records = await db.load_records()
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
        await db.save_records(records)
        await db.update_stats()

        embed = discord.Embed(title="🎁 **تمت إضافة المكافأة**", color=discord.Color.green())
        embed.add_field(name="**👤 العضو**", value=عضو.mention, inline=True)
        embed.add_field(name="**💰 المبلغ**", value=f"{state.SETTINGS.get('currency', '$')}{abs(المبلغ):.2f}", inline=True)
        if السبب:
            embed.add_field(name="**📝 السبب**", value=السبب, inline=False)
        embed.add_field(name="**🛡️ أضيفت بواسطة**", value=interaction.user.mention, inline=True)
        await interaction.response.send_message(embed=embed)

        await db.log_audit("مكافأة", interaction.user.id, عضو.id, f"مكافأة {abs(المبلغ):.2f} - السبب: {السبب or 'غير محدد'}")
        try:
            await عضو.send(f"🎁 لقد تلقيت مكافأة بقيمة {state.SETTINGS.get('currency', '$')}{abs(المبلغ):.2f} من {interaction.user.mention}.\nالسبب: {السبب or 'غير محدد'}")
        except:
            pass

    @app_commands.command(name="خصم", description="خصم مبلغ (سالب) من عضو - للإدارة فقط")
    @app_commands.describe(عضو="العضو المراد الخصم منه", المبلغ="المبلغ الموجب (سيتم خصمه)", السبب="سبب الخصم (اختياري)")
    @app_commands.checks.cooldown(1, 5, key=lambda i: (i.user.id, i.command.qualified_name))
    async def add_deduction(self, interaction: discord.Interaction, عضو: discord.Member, المبلغ: float, السبب: str = None):
        if not is_admin(interaction):
            await db.log_unauthorized(interaction.user.id, "خصم")
            await interaction.response.send_message("❌ ما عندك صلاحية تستخدم هذا الأمر.", ephemeral=True)
            return
        if المبلغ <= 0:
            await interaction.response.send_message("❌ المبلغ يجب أن يكون أكبر من صفر.", ephemeral=True)
            return

        records = await db.load_records()
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
        await db.save_records(records)
        await db.update_stats()

        embed = discord.Embed(title="🔻 **تم الخصم**", color=discord.Color.red())
        embed.add_field(name="**👤 العضو**", value=عضو.mention, inline=True)
        embed.add_field(name="**💸 المبلغ المخصوم**", value=f"{state.SETTINGS.get('currency', '$')}{abs(المبلغ):.2f}", inline=True)
        if السبب:
            embed.add_field(name="**📝 السبب**", value=السبب, inline=False)
        embed.add_field(name="**🛡️ أضيف بواسطة**", value=interaction.user.mention, inline=True)
        await interaction.response.send_message(embed=embed)

        await db.log_audit("خصم", interaction.user.id, عضو.id, f"خصم {abs(المبلغ):.2f} - السبب: {السبب or 'غير محدد'}")
        try:
            await عضو.send(f"🔻 تم خصم مبلغ {state.SETTINGS.get('currency', '$')}{abs(المبلغ):.2f} من رصيدك بواسطة {interaction.user.mention}.\nالسبب: {السبب or 'غير محدد'}")
        except:
            pass

    @app_commands.command(name="حذف_مكافأة_خصم", description="حذف مكافأة أو خصم سابق لعضو - للإدارة فقط")
    @app_commands.checks.cooldown(1, 5, key=lambda i: (i.user.id, i.command.qualified_name))
    async def delete_bonus_deduction(self, interaction: discord.Interaction, عضو: discord.Member):
        if not is_admin(interaction):
            await db.log_unauthorized(interaction.user.id, "حذف_مكافأة_خصم")
            await interaction.response.send_message("❌ ما عندك صلاحية.", ephemeral=True)
            return
        records = await db.load_records()
        user_id = str(عضو.id)
        if user_id not in records:
            await interaction.response.send_message("❌ لا يوجد سجلات لهذا العضو.", ephemeral=True)
            return

        all_entries = records[user_id]
        bonus_ded_entries = [e for e in all_entries if e.get("work_type") in ("مكافأة", "خصم")]
        bonus_ded_entries.reverse()
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
            await interaction2.response.send_message(f"⚠️ تأكيد حذف {entry_to_delete.get('work_type')} بمبلغ {abs(entry_to_delete.get('total',0)):.2f}.\nاكتب `تأكيد` خلال 30 ثانية.", ephemeral=True)
            def check(m):
                return m.author == interaction2.user and m.content == "تأكيد" and m.channel == interaction2.channel
            try:
                await self.bot.wait_for('message', timeout=30.0, check=check)
            except:
                await interaction2.followup.send("❌ تم الإلغاء.", ephemeral=True)
                return
            records2 = await db.load_records()
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
                    await db.save_records(records2)
                    await db.log_audit("حذف_مكافأة_خصم", interaction2.user.id, عضو.id, f"حذف {entry_to_delete.get('work_type')} {abs(entry_to_delete.get('total',0)):.2f}")
                    await db.update_stats()
                    await interaction2.followup.send("✅ تم حذف العملية بنجاح.", ephemeral=True)
                else:
                    await interaction2.followup.send("❌ لم يتم العثور على العملية.", ephemeral=True)
            else:
                await interaction2.followup.send("❌ لا توجد سجلات.", ephemeral=True)
        select.callback = select_callback
        view = discord.ui.View(timeout=60)
        view.add_item(select)
        await interaction.response.send_message(f"**عمليات المكافآت والخصومات للعضو {عضو.mention}:**", view=view)

    # ========== نظام الدفع ==========
    @app_commands.command(name="تحديد_موعد_الدفع", description="تحديد يوم وساعة الدفع الشهري (للمشرفين)")
    @app_commands.describe(اليوم="يوم الشهر (1-28)", الساعة="الساعة (0-23)، افتراضي 0")
    @app_commands.checks.cooldown(1, 5, key=lambda i: (i.user.id, i.command.qualified_name))
    async def set_payment_day(self, interaction: discord.Interaction, اليوم: int, الساعة: int = 0):
        if not is_admin(interaction):
            await db.log_unauthorized(interaction.user.id, "تحديد_موعد_الدفع")
            await interaction.response.send_message("❌ ما عندك صلاحية.", ephemeral=True)
            return
        if not (1 <= اليوم <= 28):
            await interaction.response.send_message("❌ اليوم يجب أن يكون بين 1 و 28.", ephemeral=True)
            return
        if not (0 <= الساعة <= 23):
            await interaction.response.send_message("❌ الساعة يجب أن تكون بين 0 و 23.", ephemeral=True)
            return
        state.SETTINGS["payment_day"] = اليوم
        state.SETTINGS["payment_hour"] = الساعة
        state.SETTINGS["payment_reminder_24h_sent"] = False
        state.SETTINGS["payment_day_sent"] = False
        await db.save_settings(state.SETTINGS)
        await interaction.response.send_message(f"✅ تم تعيين موعد الدفع الشهري يوم {اليوم} الساعة {الساعة}:00.", ephemeral=True)
        await db.log_audit("تحديد_موعد_الدفع", interaction.user.id, None, f"يوم {اليوم} ساعة {الساعة}")

    @app_commands.command(name="تقرير_دفع", description="تقرير الدفع الشهري مع خيار تصدير Excel")
    @app_commands.checks.cooldown(1, 10, key=lambda i: (i.user.id, i.command.qualified_name))
    async def payment_report(self, interaction: discord.Interaction):
        if not is_admin(interaction):
            await db.log_unauthorized(interaction.user.id, "تقرير_دفع")
            await interaction.response.send_message("❌ ما عندك صلاحية.", ephemeral=True)
            return
        records = await db.load_records()
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
        embed.add_field(name="إجمالي المبلغ المستحق", value=f"{state.SETTINGS.get('currency', '$')}{grand_total:.2f}", inline=False)
        sorted_totals = sorted(totals.items(), key=lambda x: x[1], reverse=True)[:10]
        member_list = "\n".join([f"<@{uid}>: {state.SETTINGS.get('currency', '$')}{amt:.2f}" for uid, amt in sorted_totals])
        embed.add_field(name="المستحقات (أول 10)", value=member_list, inline=False)

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

    @app_commands.command(name="تحديث_أسعار", description="تحديث مبالغ الفصول المسجلة بناءً على الأسعار الحالية (للمشرفين)")
    @app_commands.autocomplete(التخصص=specialty_autocomplete)
    @app_commands.describe(
        التخصص="تخصص محدد (اختياري، وإلا كل التخصصات)",
        من_تاريخ="بداية النطاق (YYYY-MM-DD، اختياري)",
        الى_تاريخ="نهاية النطاق (YYYY-MM-DD، اختياري)",
        كل_السجلات="تحديث كل السجلات بغض النظر عن التاريخ"
    )
    @app_commands.checks.cooldown(1, 10, key=lambda i: (i.user.id, i.command.qualified_name))
    async def update_prices(self, interaction: discord.Interaction, التخصص: str = None, من_تاريخ: str = None, الى_تاريخ: str = None, كل_السجلات: bool = False):
        if not is_admin(interaction):
            await db.log_unauthorized(interaction.user.id, "تحديث_أسعار")
            await interaction.response.send_message("❌ ما عندك صلاحية.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        records = await db.load_records()
        specialties = state.SETTINGS.get("specialties", {})
        updated_count = 0
        target_specialty = utils.map_type(التخصص) if التخصص else None
        if target_specialty and target_specialty not in specialties:
            await interaction.followup.send(f"❌ التخصص `{التخصص}` غير موجود.", ephemeral=True)
            return
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
            date_from = datetime.utcnow().replace(day=1)
            date_to = datetime.utcnow()

        for user_id, entries in records.items():
            for entry in entries:
                wtype = entry.get("work_type")
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
                if specialties[wtype].get("active", True):
                    entry["total"] = specialties[wtype]["price"]
                    updated_count += 1
        await db.save_records(records)
        await db.update_stats()
        await db.log_audit("تحديث_أسعار", interaction.user.id, None, f"تم تحديث {updated_count} سجل - التخصص: {التخصص or 'الكل'}, الفترة: {'كل السجلات' if كل_السجلات else f'{من_تاريخ or "بداية الشهر"} -> {الى_تاريخ or "الآن"}'}")
        await interaction.followup.send(f"✅ تم تحديث {updated_count} سجل بنجاح.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(AdminCommands(bot))