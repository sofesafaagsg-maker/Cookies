import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
MONGODB_URI = os.getenv("MONGODB_URI")

if not TOKEN or not MONGODB_URI:
    raise ValueError("Missing DISCORD_TOKEN or MONGODB_URI in .env")