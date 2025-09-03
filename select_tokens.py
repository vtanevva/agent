import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()
MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)
try:
    db = client.get_database()
except Exception:
    db = client["mentalassistant"]

print("Inspecting tokens collection:\n")
for doc in db.tokens.find({}, {"user_id": 1, "google.refresh_token": 1}):
    user = doc.get("user_id")
    rtok = doc.get("google", {}).get("refresh_token")
    print(f" - user_id: {user:6} | has refresh_token: {'YES' if rtok else 'NO'}")
