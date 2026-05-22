import json
from datetime import datetime, timedelta
from collections import defaultdict
import state

async def load_records():
    try:
        doc = await state.collection.find_one({"_id": "records"})
        if doc and "data" in doc:
            return doc["data"]
        return {}
    except Exception as e:
        print(f"[ERROR] load_records() - {e}")
        return {}

async def save_records(records):
    try:
        await state.collection.update_one(
            {"_id": "records"},
            {"$set": {"data": records}},
            upsert=True
        )
    except Exception as e:
        print(f"[ERROR] save_records() - {e}")

async def load_works() -> list:
    doc = await state.collection.find_one({"_id": "works"})
    if doc and "data" in doc:
        return doc["data"]
    return []

async def save_works(works: list):
    await state.collection.update_one(
        {"_id": "works"},
        {"$set": {"data": works}},
        upsert=True
    )

async def get_work(work_name: str) -> dict | None:
    works = await load_works()
    for w in works:
        if w["name"] == work_name:
            return w
    return None

async def delete_all_records_of_work(work_name: str) -> int:
    records = await load_records()
    removed_total = 0
    users_to_delete = []
    for user_id, entries in records.items():
        new_entries = [e for e in entries if e.get("work_name") != work_name]
        removed = len(entries) - len(new_entries)
        if removed > 0:
            removed_total += removed
            if new_entries:
                records[user_id] = new_entries
            else:
                users_to_delete.append(user_id)
    for uid in users_to_delete:
        del records[uid]
    if removed_total > 0:
        await save_records(records)
        await update_stats()
    return removed_total

async def load_settings():
    try:
        doc = await state.settings_collection.find_one({"_id": "settings"})
        if doc:
            if "specialties" not in doc:
                doc["specialties"] = state.SETTINGS.get("specialties", {})
            if "payment_day" not in doc:
                doc["payment_day"] = None
                doc["payment_hour"] = 0
                doc["payment_reminder_24h_sent"] = False
                doc["payment_day_sent"] = False
            return doc
        return {
            "allowed_channels": ["تسجيــــــــل-اعمال〢💵"],
            "currency": "$",
            "notify_channel_id": None,
            "daily_backup_channel_id": None,
            "alert_threshold": 10.0,
            "specialties": {
                "تحرير": {"price": 0.50, "active": True, "last_modified": datetime.utcnow().isoformat()},
                "ترجمة_كوري": {"price": 0.75, "active": True, "last_modified": datetime.utcnow().isoformat()},
                "ترجمة_انجليزي": {"price": 0.60, "active": True, "last_modified": datetime.utcnow().isoformat()},
                "تبييض": {"price": 0.25, "active": True, "last_modified": datetime.utcnow().isoformat()},
                "سحب": {"price": 0.01, "active": True, "last_modified": datetime.utcnow().isoformat()},
                "دمج": {"price": 0.01, "active": True, "last_modified": datetime.utcnow().isoformat()},
                "رفع": {"price": 0.005, "active": True, "last_modified": datetime.utcnow().isoformat()},
            },
            "payment_day": None,
            "payment_hour": 0,
            "payment_reminder_24h_sent": False,
            "payment_day_sent": False
        }
    except Exception as e:
        print(f"[ERROR] load_settings() - {e}")
        return {
            "allowed_channels": ["تسجيــــــــل-اعمال〢💵"],
            "currency": "$",
            "notify_channel_id": None,
            "daily_backup_channel_id": None,
            "alert_threshold": 10.0,
            "specialties": {},
            "payment_day": None,
            "payment_hour": 0,
            "payment_reminder_24h_sent": False,
            "payment_day_sent": False
        }

async def save_settings(settings):
    try:
        await state.settings_collection.update_one(
            {"_id": "settings"},
            {"$set": settings},
            upsert=True
        )
    except Exception as e:
        print(f"[ERROR] save_settings() - {e}")

async def log_audit(action, moderator_id, target_id, details):
    log_entry = {
        "action": action,
        "moderator_id": str(moderator_id),
        "target_id": str(target_id) if target_id else None,
        "details": details,
        "timestamp": datetime.utcnow().isoformat()
    }
    await state.audit_collection.insert_one(log_entry)

async def log_unauthorized(user_id, command_name):
    await log_audit("محاولة_غير_مصرح_بها", user_id, None,
                    f"محاولة استخدام الأمر {command_name} بدون صلاحية")

async def update_stats():
    records = await load_records()
    total_entries = sum(len(entries) for entries in records.values())
    total_amount = 0
    type_counts = {}
    member_stats = {}

    for user_id, entries in records.items():
        member_total = 0
        member_counts = {}
        for entry in entries:
            amount = entry.get("total", 0)
            total_amount += amount
            member_total += amount
            wtype = entry.get("work_type")
            type_counts[wtype] = type_counts.get(wtype, 0) + 1
            member_counts[wtype] = member_counts.get(wtype, 0) + 1
        member_stats[user_id] = {
            "total_amount": member_total,
            "total_entries": len(entries),
            "type_counts": member_counts
        }

    top_members = sorted(member_stats.items(),
                         key=lambda x: x[1]["total_amount"], reverse=True)[:5]
    top_members_data = [(uid, stats) for uid, stats in top_members]

    today = datetime.utcnow().date()
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)
    daily_entries = 0
    daily_amount = 0
    weekly_entries = 0
    weekly_amount = 0
    monthly_entries = 0
    monthly_amount = 0

    for user_id, entries in records.items():
        for entry in entries:
            ts = entry.get("timestamp")
            if ts:
                try:
                    entry_date = datetime.fromisoformat(ts).date()
                    if entry_date == today:
                        daily_entries += 1
                        daily_amount += entry.get("total", 0)
                    if entry_date >= week_start:
                        weekly_entries += 1
                        weekly_amount += entry.get("total", 0)
                    if entry_date >= month_start:
                        monthly_entries += 1
                        monthly_amount += entry.get("total", 0)
                except:
                    pass

    stat_doc = {
        "total_entries": total_entries,
        "total_amount": total_amount,
        "type_counts": type_counts,
        "member_stats": member_stats,
        "top_members": top_members_data,
        "daily": {"entries": daily_entries, "amount": daily_amount},
        "weekly": {"entries": weekly_entries, "amount": weekly_amount},
        "monthly": {"entries": monthly_entries, "amount": monthly_amount},
        "last_updated": datetime.utcnow().isoformat()
    }
    await state.stats_collection.update_one(
        {"_id": "stats"},
        {"$set": stat_doc},
        upsert=True
    )