from enum import Enum

class Colors:
    SUCCESS = 0x2ECC71
    ERROR = 0xE74C3C
    WARNING = 0xF1C40F
    INFO = 0x3498DB
    ADMIN = 0x9B59B6
    FINANCE = 0xF39C12
    CANCELLED = 0x95A5A6

class RecordStatus(str, Enum):
    ACTIVE = "active"
    REVIEW = "review"
    APPROVED = "approved"
    REJECTED = "rejected"
    PAID = "paid"
    DELETED = "deleted"

class WorkStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"

class Icons:
    MEMBER = "👤"
    WORK = "📖"
    CHAPTER = "📄"
    SPECIALTY = "🛠️"
    MONEY = "💰"
    BONUS = "🎁"
    DEDUCTION = "🔻"
    SETTINGS = "⚙️"
    NOTIFICATION = "🔔"
    BACKUP = "💾"
    AUDIT = "📜"
    DASHBOARD = "🖥️"
    HELP = "📌"
    STATS = "📊"
    EXPORT = "📥"
    DELETE = "🗑️"
    CONFIRM = "✅"
    CANCEL = "❌"
    WARNING = "⚠️"