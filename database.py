import motor.motor_asyncio
from config import MONGODB_URI

client = motor.motor_asyncio.AsyncIOMotorClient(MONGODB_URI)
db = client["work_bot"]

# Collections
records_col = db["records"]          # سجل واحد لكل عملية تسجيل
works_col = db["works"]              # كل عمل وثيقة
specialties_col = db["specialties"]  # كل تخصص وثيقة
settings_col = db["settings"]        # وثيقة واحدة
audit_col = db["audit_log"]          # سجل التدقيق
stats_col = db["stats"]              # إحصائيات