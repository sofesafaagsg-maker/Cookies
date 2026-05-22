from config import MONGODB_URI
import motor.motor_asyncio

# Currency symbol (can be changed by admin)
CURRENCY = "$"

# MongoDB setup
print("[LOG] Creating MongoDB client...")
mongo_client = motor.motor_asyncio.AsyncIOMotorClient(MONGODB_URI)
db = mongo_client["work_bot"]
collection = db["records"]          # unified collection (records + works)
settings_collection = db["settings"]
audit_collection = db["audit_log"]
stats_collection = db["stats"]
