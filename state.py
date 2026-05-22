# state.py
import motor.motor_asyncio

bot = None
SETTINGS = {}
PRICES = {}

mongo_client = None
db = None
collection = None
settings_collection = None
audit_collection = None
stats_collection = None