# utils.py
from typing import List
import state

def format_member_display(guild, user_id: int, username_hint: str = None) -> str:
    """Return a nice display string for a user: @username if known, otherwise the ID."""
    member = guild.get_member(user_id)
    if member:
        return f"@{member.name}"
    if username_hint:
        return f"@{username_hint}"
    return str(user_id)

def filter_paid_chapters(work: dict, chapters_list: List[str]):
    """Returns (paid_chapters, free_count) based on work's paid_start."""
    if work.get("paid_start") is None:
        return chapters_list, 0
    paid_start = work["paid_start"]
    paid = []
    free = 0
    for ch in chapters_list:
        try:
            ch_num = int(ch)
        except ValueError:
            paid.append(ch)
            continue
        if ch_num >= paid_start:
            paid.append(ch)
        else:
            free += 1
    return paid, free

def parse_fields(text):
    fields = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().lower()
        value = value.strip()
        fields[key] = value
    return fields

def parse_chapter_range(range_str):
    range_str = range_str.strip()
    chapters = []
    if '-' in range_str:
        parts = range_str.split('-')
        if len(parts) == 2:
            try:
                start = int(parts[0])
                end = int(parts[1])
                for i in range(start, end+1):
                    chapters.append(str(i))
            except:
                pass
    elif ',' in range_str:
        for part in range_str.split(','):
            part = part.strip()
            if part.isdigit():
                chapters.append(part)
    else:
        if range_str.isdigit():
            chapters.append(range_str)
    return chapters

def parse_mixed_types(types_input, chapters_count):
    types_input = types_input.strip()
    if '-' in types_input:
        parts = types_input.split('-')
        if len(parts) == chapters_count:
            return [p.strip() for p in parts]
        elif len(parts) == 2:
            first = parts[0].strip()
            rest = parts[1].strip()
            return [first] + [rest] * (chapters_count - 1)
        else:
            if ',' in types_input:
                return parse_mixed_types(types_input.replace('-', ','), chapters_count)
            return None
    elif ',' in types_input:
        parts = [p.strip() for p in types_input.split(',')]
        if len(parts) == chapters_count:
            return parts
        elif len(parts) == 1:
            return [parts[0]] * chapters_count
        else:
            return None
    else:
        return [types_input] * chapters_count

def map_type(t):
    """Convert user-friendly type (with spaces) to internal key (underscores)."""
    return t.strip().replace(' ', '_')

def is_duplicate(records, user_id, work_name, chapter, work_type):
    """Check if the same (work, chapter, type) already exists for this user."""
    user_entries = records.get(str(user_id), [])
    for e in user_entries:
        if (e.get("work_name") == work_name and 
            e.get("chapter") == chapter and 
            e.get("work_type") == work_type):
            return True
    return False

def rebuild_prices():
    """Rebuild global PRICES dict from active specialties in SETTINGS."""
    specialties = state.SETTINGS.get("specialties", {})
    state.PRICES = {k: v["price"] for k, v in specialties.items() if v.get("active", True)}